"""HSEE Phase 5 — Hypothesis Engine.

`hypothesis.py` 가 그래프 구조(2-hop 전이/임베딩 유사도/반사실) 기반 가설을 생성한다면,
이 모듈은 **반복 인과 패턴** 으로부터 **일반화 가설** 을 만들어 검증·승격까지 닫힌
루프로 운영한다.

흐름:
  1. KnowledgeEdge 에서 자주 반복되는 (cause-prefix → effect-prefix) 패턴 카운트
  2. LLM 으로 "이번에도 같을 것" 일반화 가설 1~3개 생성
  3. KnowledgeHypothesis(status='pending') 저장
  4. 새 사실들로 가설 confidence 업데이트 (LLM supports/refutes 분류)
  5. 임계치 도달 시 status 전이:
       confidence ≥ 0.85 & ≥5 supporting facts → 'validated'
       confidence ≤ 0.30 & ≥3 refuting facts   → 'rejected'
  6. validated → KnowledgeFact 로 승격 (status='promoted')

Prisma 스키마 매핑(중요):
  KnowledgeHypothesis 는 `domain`/`evidenceFor`/`evidenceAgainst`/`promoted`
  컬럼이 없다. 따라서 다음과 같이 기존 필드를 재활용한다:
    - pathFactIds   : 첫 번째 원소는 도메인 라벨 prefix `domain:<x>`, 그 다음은
                      supporting / refuting fact id 들이 prefix 와 함께 들어간다
                      (예: ``["domain:law", "+factA", "+factB", "-factC"]``).
    - rationale      : 사람이 읽는 근거 + JSON 카운터 (`{"pro": N, "con": M}`).
    - status         : 'pending' | 'validated' | 'rejected' | 'promoted'.
    - fromFactId/toFactId : 패턴의 대표 cause/effect fact (LLM 매칭).

이 인코딩은 Prisma 마이그레이션 없이 즉시 동작한다. 추후 schema 에
``domain`` 컬럼 + ``promoted`` Boolean 을 추가하면 자연스럽게 마이그레이션 가능.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as llm_chat
from hwarang_api.knowledge.types import KnowledgeRelation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 임계치
# ---------------------------------------------------------------------------
_VALIDATE_CONF = 0.85
_VALIDATE_MIN_PRO = 5
_REJECT_CONF = 0.30
_REJECT_MIN_CON = 3
_MIN_PATTERN_REPEAT = 3

_DOMAIN_PREFIX = "domain:"
_PRO_PREFIX = "+"
_CON_PREFIX = "-"


# ---------------------------------------------------------------------------
# 프롬프트
# ---------------------------------------------------------------------------
_HYPOTHESIS_SYSTEM = (
    "You are a Korean knowledge-graph reasoner that proposes falsifiable hypotheses. "
    "Output ONLY a JSON array. No prose."
)

_HYPOTHESIS_PROMPT = """다음 인과 관계 패턴들을 보고 새로운 가설을 1~3개 생성해라.

기존 패턴:
{patterns}

조건:
- 패턴이 N번 이상 반복되면 일반화 가능
- 시간/도메인 요소 고려
- 반증 가능한 형태로 작성 (구체 명사 + 검증 가능한 결과)

형식: JSON 배열
[{{"hypothesis": "가설 한국어 문장", "domain": "law|finance|tech|medical|general", "confidence": 0~1, "supporting_pattern_indexes": [정수배열]}}]

JSON 만 출력:"""


_CLASSIFY_SYSTEM = (
    "Classify the relation between a hypothesis and a fact. "
    "Reply with ONE word: supports, refutes, or unrelated."
)


# ---------------------------------------------------------------------------
# 1) 패턴 발굴
# ---------------------------------------------------------------------------
async def _find_repeating_patterns(min_count: int = _MIN_PATTERN_REPEAT) -> list[dict]:
    """KnowledgeEdge 에서 의미 유사 cause→effect 패턴 카운팅.

    실제로는 의미 클러스터링이 더 정확하지만(TODO), 우선 fact content 의 첫 30자
    + entity 를 키로 그룹화한다. 동일 entity-쌍이 여러 번 CAUSES 로 연결되면
    "반복 패턴" 으로 본다.
    """
    edges = await prisma.knowledgeedge.find_many(
        where={"relationType": KnowledgeRelation.CAUSES.value},
        take=2000,
    )
    if not edges:
        return []

    fact_ids: set[str] = set()
    for e in edges:
        fact_ids.add(e.fromFactId)
        fact_ids.add(e.toFactId)

    facts = await prisma.knowledgefact.find_many(
        where={"id": {"in": list(fact_ids)}}
    )
    fact_map = {f.id: f for f in facts}

    groups: dict[tuple[str, str], dict] = {}
    for e in edges:
        cf = fact_map.get(e.fromFactId)
        ef = fact_map.get(e.toFactId)
        if cf is None or ef is None:
            continue
        cause_key = (cf.entity or (cf.content or "")[:30]).strip().lower()
        effect_key = (ef.entity or (ef.content or "")[:30]).strip().lower()
        if not cause_key or not effect_key:
            continue
        key = (cause_key, effect_key)
        bucket = groups.setdefault(
            key,
            {
                "count": 0,
                "edge_ids": [],
                "from_fact_ids": [],
                "to_fact_ids": [],
                "domain": cf.domain or ef.domain or "general",
                "cause_label": cf.entity or (cf.content or "")[:60],
                "effect_label": ef.entity or (ef.content or "")[:60],
            },
        )
        bucket["count"] += 1
        bucket["edge_ids"].append(e.id)
        bucket["from_fact_ids"].append(e.fromFactId)
        bucket["to_fact_ids"].append(e.toFactId)

    return [
        {
            "cause": v["cause_label"],
            "effect": v["effect_label"],
            "count": v["count"],
            "domain": v["domain"],
            "from_fact_ids": v["from_fact_ids"],
            "to_fact_ids": v["to_fact_ids"],
        }
        for v in groups.values()
        if v["count"] >= min_count
    ]


# ---------------------------------------------------------------------------
# 2) 가설 생성
# ---------------------------------------------------------------------------
async def generate_hypotheses_from_patterns(max_patterns: int = 20) -> dict:
    """반복 인과 패턴 → LLM 일반화 → KnowledgeHypothesis 저장."""
    patterns = await _find_repeating_patterns()
    if not patterns:
        return {"hypotheses_saved": 0, "reason": "no_patterns"}

    patterns.sort(key=lambda p: p["count"], reverse=True)
    patterns = patterns[:max_patterns]

    pattern_text = "\n".join(
        f"[{i}] {p['cause']} → {p['effect']} ({p['count']}회, domain={p['domain']})"
        for i, p in enumerate(patterns)
    )

    raw = await llm_chat(
        _HYPOTHESIS_PROMPT.format(patterns=pattern_text),
        system=_HYPOTHESIS_SYSTEM,
        max_tokens=600,
    )
    items = _parse_hypotheses(raw)
    if not items:
        return {"patterns_analyzed": len(patterns), "hypotheses_saved": 0}

    saved = 0
    for h in items:
        statement = (h.get("hypothesis") or "").strip()
        if not statement:
            continue

        # 중복 가설 차단
        existing = await prisma.knowledgehypothesis.find_first(
            where={"statement": statement}
        )
        if existing is not None:
            continue

        # 도메인
        domain = (h.get("domain") or "general").strip().lower()

        # 지지 패턴 인덱스 → 대표 from/to fact 선택
        supporting_idxs = h.get("supporting_pattern_indexes") or []
        if not isinstance(supporting_idxs, list):
            supporting_idxs = []
        from_fact_id: str | None = None
        to_fact_id: str | None = None
        path_seed: list[str] = [f"{_DOMAIN_PREFIX}{domain}"]
        for idx in supporting_idxs:
            try:
                p = patterns[int(idx)]
            except (ValueError, IndexError, TypeError):
                continue
            if from_fact_id is None and p["from_fact_ids"]:
                from_fact_id = p["from_fact_ids"][0]
            if to_fact_id is None and p["to_fact_ids"]:
                to_fact_id = p["to_fact_ids"][0]
            for fid in p["from_fact_ids"] + p["to_fact_ids"]:
                tag = f"{_PRO_PREFIX}{fid}"
                if tag not in path_seed:
                    path_seed.append(tag)
        # fallback — 첫 패턴 사용
        if from_fact_id is None or to_fact_id is None:
            p0 = patterns[0]
            from_fact_id = from_fact_id or p0["from_fact_ids"][0]
            to_fact_id = to_fact_id or p0["to_fact_ids"][0]

        try:
            confidence = max(0.0, min(1.0, float(h.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5

        rationale_payload = {
            "rationale": f"{len(supporting_idxs) or 1} 개 패턴 일반화",
            "tally": {"pro": 0, "con": 0},
        }

        try:
            await prisma.knowledgehypothesis.create(
                data={
                    "statement": statement,
                    "relation": KnowledgeRelation.CAUSES.value,
                    "fromFactId": from_fact_id,
                    "toFactId": to_fact_id,
                    "pathFactIds": path_seed,
                    "confidence": confidence,
                    "rationale": json.dumps(rationale_payload, ensure_ascii=False)[
                        :1000
                    ],
                    "status": "pending",
                }
            )
            saved += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("hypothesis create failed: %s", exc)

    return {
        "patterns_analyzed": len(patterns),
        "hypotheses_saved": saved,
    }


# ---------------------------------------------------------------------------
# 3) 검증 — pro/con 카운트 업데이트
# ---------------------------------------------------------------------------
async def verify_hypothesis(hypothesis_id: str) -> dict:
    """새 사실들로 가설을 LLM 분류해 confidence + 상태 업데이트."""
    h = await prisma.knowledgehypothesis.find_unique(where={"id": hypothesis_id})
    if h is None:
        return {"error": "not_found"}
    if h.status not in ("pending", "validated", "rejected"):
        return {"error": f"unsupported_status:{h.status}"}

    domain = _decode_domain(h.pathFactIds or [])
    pro, con = _decode_evidence(h.pathFactIds or [])

    where: dict[str, Any] = {"createdAt": {"gte": h.createdAt}}
    if domain and domain != "general":
        where["domain"] = domain

    recent = await prisma.knowledgefact.find_many(where=where, take=50)

    new_pro = list(pro)
    new_con = list(con)
    pro_set = set(pro)
    con_set = set(con)

    classified = 0
    for f in recent:
        if f.id in pro_set or f.id in con_set:
            continue
        verdict = await _classify_evidence(h.statement, f.content)
        classified += 1
        if verdict == "supports":
            new_pro.append(f.id)
            pro_set.add(f.id)
        elif verdict == "refutes":
            new_con.append(f.id)
            con_set.add(f.id)

    total = len(new_pro) + len(new_con)
    new_conf = (len(new_pro) / total) if total > 0 else float(h.confidence)

    if new_conf >= _VALIDATE_CONF and len(new_pro) >= _VALIDATE_MIN_PRO:
        new_status = "validated"
    elif new_conf <= _REJECT_CONF and len(new_con) >= _REJECT_MIN_CON:
        new_status = "rejected"
    else:
        new_status = h.status if h.status in ("pending",) else "pending"

    new_path = _encode_path(domain, new_pro, new_con)
    rationale_payload = {
        "rationale": _extract_rationale_text(h.rationale),
        "tally": {"pro": len(new_pro), "con": len(new_con)},
    }

    await prisma.knowledgehypothesis.update(
        where={"id": hypothesis_id},
        data={
            "confidence": new_conf,
            "pathFactIds": new_path,
            "rationale": json.dumps(rationale_payload, ensure_ascii=False)[:1000],
            "status": new_status,
        },
    )

    return {
        "id": hypothesis_id,
        "old_confidence": float(h.confidence),
        "new_confidence": new_conf,
        "status": new_status,
        "pro": len(new_pro),
        "con": len(new_con),
        "classified": classified,
    }


async def verify_pending_hypotheses(limit: int = 50) -> dict:
    """모든 pending 가설을 일괄 재검증 (cron)."""
    pending = await prisma.knowledgehypothesis.find_many(
        where={"status": "pending"}, take=limit, order={"createdAt": "asc"}
    )
    results = {"checked": 0, "validated": 0, "rejected": 0, "still_pending": 0}
    for h in pending:
        try:
            r = await verify_hypothesis(h.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("verify failed for %s: %s", h.id, exc)
            continue
        results["checked"] += 1
        st = r.get("status")
        if st == "validated":
            results["validated"] += 1
        elif st == "rejected":
            results["rejected"] += 1
        else:
            results["still_pending"] += 1
    return results


# ---------------------------------------------------------------------------
# 4) 승격 — validated → KnowledgeFact
# ---------------------------------------------------------------------------
async def promote_validated_hypotheses(limit: int = 50) -> dict:
    """validated 가설을 사실로 승격하고 status='promoted' 로 마킹."""
    validated = await prisma.knowledgehypothesis.find_many(
        where={"status": "validated"}, take=limit
    )
    if not validated:
        return {"promoted": 0}

    from hwarang_api.knowledge.pipeline import ingest_fact
    from hwarang_api.knowledge.types import (
        KnowledgeFact,
        KnowledgeVisibility,
    )

    promoted = 0
    for h in validated:
        domain = _decode_domain(h.pathFactIds or []) or "general"
        try:
            new_fact = KnowledgeFact(
                content=h.statement,
                domain=domain,
                source="hypothesis_engine",
                source_type="agent",
                confidence_t0=float(h.confidence),
                valid_from=datetime.now(timezone.utc),
                visibility=KnowledgeVisibility.PUBLIC,
            )
            await ingest_fact(new_fact, bypass_gate=True)
            await prisma.knowledgehypothesis.update(
                where={"id": h.id},
                data={
                    "status": "promoted",
                    "reviewedBy": "system:hypothesis_engine",
                    "reviewedAt": datetime.now(timezone.utc),
                    "reviewNote": "auto-promoted from validated hypothesis",
                },
            )
            promoted += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("promote failed for %s: %s", h.id, exc)

    return {"promoted": promoted, "candidates": len(validated)}


# ---------------------------------------------------------------------------
# LLM 헬퍼
# ---------------------------------------------------------------------------
async def _classify_evidence(hypothesis: str, fact_content: str) -> str:
    """가설-사실 supports/refutes/unrelated 분류."""
    if not fact_content:
        return "unrelated"
    prompt = (
        f"가설: {hypothesis[:300]}\n"
        f"사실: {fact_content[:300]}\n"
        "이 사실은 가설을 지지/반박/무관 중 무엇인가? "
        "한 단어로만 답해라: supports | refutes | unrelated"
    )
    resp = await llm_chat(prompt, system=_CLASSIFY_SYSTEM, max_tokens=10)
    if not resp:
        return "unrelated"
    low = resp.strip().lower()
    if "support" in low:
        return "supports"
    if "refute" in low:
        return "refutes"
    return "unrelated"


# ---------------------------------------------------------------------------
# 인코딩 / 디코딩 (pathFactIds 재활용)
# ---------------------------------------------------------------------------
def _decode_domain(path: list[str]) -> str:
    for p in path or []:
        if isinstance(p, str) and p.startswith(_DOMAIN_PREFIX):
            return p[len(_DOMAIN_PREFIX) :].strip() or "general"
    return "general"


def _decode_evidence(path: list[str]) -> tuple[list[str], list[str]]:
    pro: list[str] = []
    con: list[str] = []
    for p in path or []:
        if not isinstance(p, str):
            continue
        if p.startswith(_PRO_PREFIX) and not p.startswith(_DOMAIN_PREFIX):
            pro.append(p[1:])
        elif p.startswith(_CON_PREFIX):
            con.append(p[1:])
    return pro, con


def _encode_path(domain: str, pro: list[str], con: list[str]) -> list[str]:
    out: list[str] = [f"{_DOMAIN_PREFIX}{domain or 'general'}"]
    for fid in pro:
        out.append(f"{_PRO_PREFIX}{fid}")
    for fid in con:
        out.append(f"{_CON_PREFIX}{fid}")
    return out


def _extract_rationale_text(rationale: str | None) -> str:
    """기존 rationale 이 JSON 페이로드면 안의 'rationale' 추출, 아니면 그대로."""
    if not rationale:
        return ""
    s = rationale.strip()
    if not s.startswith("{"):
        return s[:500]
    try:
        d = json.loads(s)
        return str(d.get("rationale", ""))[:500]
    except Exception:
        return s[:500]


# ---------------------------------------------------------------------------
# 파서
# ---------------------------------------------------------------------------
def _parse_hypotheses(raw: str) -> list[dict]:
    if not raw:
        return []
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "")
    m = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if m is None:
        return []
    try:
        parsed = json.loads(m.group())
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


__all__ = [
    "generate_hypotheses_from_patterns",
    "verify_hypothesis",
    "verify_pending_hypotheses",
    "promote_validated_hypotheses",
]
