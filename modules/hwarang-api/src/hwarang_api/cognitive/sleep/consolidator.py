"""Memory Consolidator — episodic → semantic.

NREM 단계의 핵심: 여러 episodic memory 를 LLM 으로 클러스터링한 후, 각
클러스터에서 일반화된 규칙(semantic rule)을 추출해 ``SemanticRule`` 테이블에
저장한다. 같은 topic 의 규칙이 이미 있으면 sourceCount 증가 + confidence 평균
+ lastReinforced 갱신 (= 강화 학습).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat

from .replay_buffer import Memory

logger = logging.getLogger(__name__)


@dataclass
class ConsolidationResult:
    """배치 통합 결과 요약."""

    clusters_processed: int = 0
    rules_created: int = 0
    rules_updated: int = 0
    total_memories_consolidated: int = 0
    errors: int = 0


def _safe_json_extract(text: str) -> dict | list | None:
    """LLM 응답에서 첫 JSON 객체/배열을 안전 추출. 실패 시 None."""
    if not text:
        return None
    # ```json ... ``` 블록 정리
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fenced:
        text = fenced.group(1)
    # object 우선
    for opener, closer in (("{", "}"), ("[", "]")):
        s = text.find(opener)
        e = text.rfind(closer)
        if s != -1 and e != -1 and e > s:
            try:
                return json.loads(text[s : e + 1])
            except Exception:
                continue
    return None


class MemoryConsolidator:
    """LLM 클러스터링 + 규칙 추출 + DB upsert."""

    CLUSTER_SYSTEM = (
        "당신은 기억 통합 전문가입니다. 주어진 episodic memory 들을 의미적으로 "
        "유사한 topic 클러스터로 묶으세요. 응답은 JSON 만, 다른 설명 없이."
    )
    RULE_SYSTEM = (
        "당신은 일반화 추론 전문가입니다. 같은 topic 의 episode 들에서 핵심 "
        "일반화 규칙을 추출하세요. 응답은 JSON 만."
    )

    def __init__(self, max_cluster_input: int = 30):
        # LLM 컨텍스트 보호 — 한 번에 너무 많이 넣지 않음
        self.max_cluster_input = max_cluster_input

    async def _cluster(self, memories: list[Memory]) -> list[dict]:
        """LLM 으로 topic 별 그룹화. 실패 시 단일 클러스터 폴백."""
        if not memories:
            return []
        sample = memories[: self.max_cluster_input]
        listing = "\n".join(
            f"[{i}] id={m.id} :: {m.content[:200]}" for i, m in enumerate(sample)
        )
        prompt = (
            f"다음 {len(sample)}개 메모리를 주제별로 그룹화하세요.\n\n"
            f"{listing}\n\n"
            'JSON 형식: {"clusters": [{"topic": "주제명", "memory_ids": ["id1","id2"]}]}'
        )
        resp = await _chat(prompt, system=self.CLUSTER_SYSTEM, max_tokens=900)
        data = _safe_json_extract(resp)
        if isinstance(data, dict):
            clusters = data.get("clusters") or []
            if isinstance(clusters, list):
                # 유효한 항목만
                out = []
                valid_ids = {m.id for m in memories}
                for c in clusters:
                    if not isinstance(c, dict):
                        continue
                    topic = str(c.get("topic", "")).strip()
                    ids = c.get("memory_ids") or []
                    ids = [str(x) for x in ids if str(x) in valid_ids]
                    if topic and ids:
                        out.append({"topic": topic, "memory_ids": ids})
                if out:
                    return out
        # 폴백: 전부 한 묶음
        logger.info("LLM 클러스터링 폴백 — 단일 그룹")
        return [
            {
                "topic": "general",
                "memory_ids": [m.id for m in memories],
            }
        ]

    async def _extract_rule(
        self, topic: str, members: list[Memory]
    ) -> dict | None:
        """클러스터에서 규칙 1 개 추출."""
        if not members:
            return None
        listing = "\n".join(f"- {m.content[:250]}" for m in members[:20])
        prompt = (
            f"주제: {topic}\n\n"
            f"이 그룹의 episode 들:\n{listing}\n\n"
            "이들의 핵심 일반화 규칙을 추출하세요.\n"
            'JSON: {"rule": "한 문장 규칙", "confidence": 0.0~1.0, '
            '"exceptions": ["예외 케이스1", ...]}'
        )
        resp = await _chat(prompt, system=self.RULE_SYSTEM, max_tokens=400)
        data = _safe_json_extract(resp)
        if not isinstance(data, dict):
            return None
        rule_text = str(data.get("rule", "")).strip()
        if not rule_text:
            return None
        try:
            conf = float(data.get("confidence", 0.5))
        except Exception:
            conf = 0.5
        conf = max(0.0, min(1.0, conf))
        exceptions = data.get("exceptions") or []
        if not isinstance(exceptions, list):
            exceptions = [str(exceptions)]
        exceptions = [str(x) for x in exceptions][:10]
        return {
            "topic": topic,
            "rule": rule_text,
            "confidence": conf,
            "exceptions": exceptions,
            "sourceCount": len(members),
        }

    async def _upsert_rule(self, rule: dict, from_dream: bool = False) -> str:
        """topic 별 SemanticRule upsert. 'created' / 'updated' / 'failed' 반환."""
        topic = rule["topic"]
        try:
            existing = await prisma.semanticrule.find_first(
                where={"topic": topic}
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("SemanticRule 조회 실패 (모델 미마이그레이션?): %s", exc)
            return "failed"

        try:
            if existing is not None:
                old_conf = float(getattr(existing, "confidence", 0.5) or 0.5)
                new_conf = (old_conf + float(rule["confidence"])) / 2.0
                old_count = int(getattr(existing, "sourceCount", 0) or 0)
                await prisma.semanticrule.update(
                    where={"id": getattr(existing, "id")},
                    data={
                        "rule": rule["rule"],
                        "confidence": new_conf,
                        "exceptions": json.dumps(rule.get("exceptions", [])),
                        "sourceCount": old_count + int(rule["sourceCount"]),
                        "lastReinforced": datetime.now(timezone.utc),
                        "fromDream": bool(
                            getattr(existing, "fromDream", False)
                            or from_dream
                        ),
                    },
                )
                return "updated"
            await prisma.semanticrule.create(
                data={
                    "topic": topic,
                    "rule": rule["rule"],
                    "confidence": float(rule["confidence"]),
                    "exceptions": json.dumps(rule.get("exceptions", [])),
                    "sourceCount": int(rule["sourceCount"]),
                    "lastReinforced": datetime.now(timezone.utc),
                    "fromDream": bool(from_dream),
                }
            )
            return "created"
        except Exception as exc:  # noqa: BLE001
            logger.warning("SemanticRule upsert 실패: %s", exc)
            return "failed"

    async def consolidate_batch(
        self, memories: list[Memory]
    ) -> ConsolidationResult:
        """전체 파이프라인 — 입력 비어있으면 0-결과."""
        result = ConsolidationResult()
        if not memories:
            return result

        clusters = await self._cluster(memories)
        result.clusters_processed = len(clusters)

        by_id: dict[str, Memory] = {m.id: m for m in memories}
        consolidated_ids: set[str] = set()

        for c in clusters:
            members = [by_id[i] for i in c["memory_ids"] if i in by_id]
            if not members:
                continue
            rule = await self._extract_rule(c["topic"], members)
            if not rule:
                result.errors += 1
                continue
            status = await self._upsert_rule(rule, from_dream=False)
            if status == "created":
                result.rules_created += 1
            elif status == "updated":
                result.rules_updated += 1
            else:
                result.errors += 1
            for m in members:
                consolidated_ids.add(m.id)

        result.total_memories_consolidated = len(consolidated_ids)
        return result


__all__ = ["MemoryConsolidator", "ConsolidationResult"]
