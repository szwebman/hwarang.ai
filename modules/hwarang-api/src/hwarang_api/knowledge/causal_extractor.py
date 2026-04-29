"""HSEE Phase 5 — Causal Graph Builder.

텍스트에서 **인과 관계** 를 자동 추출해 KnowledgeEdge 로 적재한다.

흐름:
  1) 텍스트에서 LLM 으로 cause→effect 후보 추출 (CAUSES/ENABLES/CONTRADICTS/SUPPORTS).
  2) 각 cause/effect 표현을 의미 검색으로 기존 KnowledgeFact 와 매칭 (없으면 skip).
  3) self-edge / 중복 edge 차단 후 KnowledgeEdge 생성 (verifiedBy='ai').

또한:
  * `auto_extract_recent` — 최근 ingest 된 사실에서 일괄 추출 (cron).
  * `trace_causal_chain` — 시작 fact 에서 CAUSES/ENABLES BFS 로 인과 사슬 펼치기.
  * `explain_with_causal_chain` — 자연어 질문 → 의미 검색 → 인과 사슬 자연어 설명.

Prisma 스키마 매핑(중요):
  KnowledgeEdge: `relationType` / `strength` / `verifiedBy` / `evidence`
  (프롬프트의 edgeType/weight 가 아니다.)
"""

from __future__ import annotations

import json
import logging
import re
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as llm_chat
from hwarang_api.knowledge.types import KnowledgeRelation, SearchQuery

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 프롬프트
# ---------------------------------------------------------------------------
_CAUSAL_EXTRACT_SYSTEM = (
    "You are a Korean causal-relation extractor. Output ONLY a JSON array. "
    "No prose, no markdown fences."
)

_CAUSAL_EXTRACT_PROMPT = """다음 한국어 문장에서 인과 관계를 추출해라.

형식: JSON 배열
[{{"cause": "원인 짧은 명사구", "effect": "결과 짧은 명사구", "confidence": 0~1, "type": "CAUSES|ENABLES|CONTRADICTS|SUPPORTS"}}]

인과 표현 단서: "→", "때문에", "로 인해", "결과", "원인", "초래", "유발", "촉진", "야기", "이끌어".
관계가 없으면 빈 배열 [].

문장:
{text}

JSON 만 출력:"""


_VALID_TYPES = {
    KnowledgeRelation.CAUSES.value,
    KnowledgeRelation.ENABLES.value,
    KnowledgeRelation.CONTRADICTS.value,
    KnowledgeRelation.SUPPORTS.value,
}

# fact 매칭 임계치 — 의미 검색 점수가 이 값 이상이어야 동일 fact 로 인정.
_FACT_MATCH_THRESHOLD = 0.6


# ---------------------------------------------------------------------------
# 추출 본체
# ---------------------------------------------------------------------------
async def extract_causal_edges_from_text(
    text: str,
    source_fact_id: str | None = None,
) -> list[dict]:
    """단일 텍스트에서 인과 관계 추출 → KnowledgeEdge 적재.

    반환: 새로 만들어진 edge 의 dict 리스트 (`{id, from, to, relation, strength}`).
    너무 짧거나 LLM 실패 시 빈 리스트 반환.
    """
    if not text or len(text.strip()) < 30:
        return []

    raw = await llm_chat(
        _CAUSAL_EXTRACT_PROMPT.format(text=text[:1500]),
        system=_CAUSAL_EXTRACT_SYSTEM,
        max_tokens=400,
    )
    relations = _parse_relations(raw)
    if not relations:
        return []

    created: list[dict] = []
    for r in relations:
        cause_txt = (r.get("cause") or "").strip()
        effect_txt = (r.get("effect") or "").strip()
        if not cause_txt or not effect_txt:
            continue

        try:
            confidence = float(r.get("confidence", 0.5))
        except (TypeError, ValueError):
            continue
        if confidence < 0.5:
            continue

        rel_type = (r.get("type") or "CAUSES").upper()
        if rel_type not in _VALID_TYPES:
            rel_type = KnowledgeRelation.CAUSES.value

        cause_fact = await _match_fact(cause_txt)
        effect_fact = await _match_fact(effect_txt)
        if cause_fact is None or effect_fact is None:
            continue

        # self-edge 방지
        if cause_fact.id == effect_fact.id:
            continue

        # source_fact_id 만 있을 때 cause/effect 둘 다 그것과 무관하면 약한 추론.
        # 그래도 매칭이 임계치를 넘으면 적재. (관대 정책)

        # 동일 (from,to,relation) 중복 차단 — schema 의 @@unique 와 일치.
        existing = await prisma.knowledgeedge.find_first(
            where={
                "fromFactId": cause_fact.id,
                "toFactId": effect_fact.id,
                "relationType": rel_type,
            }
        )
        if existing is not None:
            continue

        try:
            edge = await prisma.knowledgeedge.create(
                data={
                    "fromFactId": cause_fact.id,
                    "toFactId": effect_fact.id,
                    "relationType": rel_type,
                    "strength": max(0.0, min(1.0, confidence)),
                    "evidence": text[:500],
                    "verifiedBy": "ai",
                }
            )
        except Exception as exc:  # noqa: BLE001
            # @@unique race-condition 등은 무시
            logger.debug("edge create failed: %s", exc)
            continue

        created.append(
            {
                "id": edge.id,
                "from": cause_fact.id,
                "to": effect_fact.id,
                "relation": rel_type,
                "strength": float(edge.strength),
            }
        )

    if created and source_fact_id is not None:
        logger.info(
            "causal_extractor: %d edges from fact %s", len(created), source_fact_id
        )
    return created


async def _match_fact(text: str) -> Any:
    """짧은 명사구를 의미 검색으로 기존 KnowledgeFact 에 매칭.

    None 을 반환할 수 있다 — 매칭이 약하면 새 fact 를 만들지 않는다 (보수적).
    """
    if not text:
        return None
    try:
        from hwarang_api.knowledge.search import temporal_search

        sq = SearchQuery(query=text, limit=1)
        result = await temporal_search(sq)
    except Exception:
        return None

    if not result or not result.facts:
        return None

    # current_confidences 와 facts 를 묶어서 평가 (search 의 쿼리 점수가 직접 노출되지
    # 않으므로 confidence 를 proxy 로 사용 — 너무 낮은 노이즈 매칭 차단).
    top_fact = result.facts[0]
    top_conf = result.current_confidences[0] if result.current_confidences else 0.0
    if top_conf < _FACT_MATCH_THRESHOLD:
        return None
    if not top_fact.id:
        return None

    return await prisma.knowledgefact.find_unique(where={"id": top_fact.id})


# ---------------------------------------------------------------------------
# 배치 잡 (cron)
# ---------------------------------------------------------------------------
async def auto_extract_recent(window_hours: int = 2, limit: int = 200) -> dict:
    """최근 N 시간 내 추가된 사실에 대해 일괄 인과 추출 (매 시간 cron)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    facts = await prisma.knowledgefact.find_many(
        where={"createdAt": {"gte": cutoff}},
        order={"createdAt": "desc"},
        take=limit,
    )

    total_edges = 0
    analyzed = 0
    for f in facts:
        try:
            edges = await extract_causal_edges_from_text(f.content, source_fact_id=f.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("extract failed for fact %s: %s", f.id, exc)
            continue
        total_edges += len(edges)
        analyzed += 1

    return {
        "facts_analyzed": analyzed,
        "edges_created": total_edges,
        "window_hours": window_hours,
    }


# ---------------------------------------------------------------------------
# 인과 사슬 추적
# ---------------------------------------------------------------------------
async def trace_causal_chain(
    start_fact_id: str,
    max_depth: int = 5,
    max_paths: int = 20,
) -> dict:
    """`start_fact_id` 에서 CAUSES/ENABLES 따라 BFS — 답변용 인과 사슬 추적.

    `graph.traverse_causal_chain` 은 단일 relation 에 한정되므로, 여기서는
    CAUSES + ENABLES 를 동시에 따라 가는 멀티 릴레이션 버전을 제공.

    반환: `{start, chain_count, chains[{depth, path:[{id,content}]}]}`
    """
    chains: list[dict] = []
    visited: set[str] = set()
    queue: deque[tuple[str, int, list[dict]]] = deque([(start_fact_id, 0, [])])

    while queue and len(chains) < max_paths:
        fact_id, depth, path = queue.popleft()
        if depth > max_depth:
            continue
        if fact_id in visited:
            continue
        visited.add(fact_id)

        fact = await prisma.knowledgefact.find_unique(where={"id": fact_id})
        if fact is None:
            continue

        new_path = path + [
            {"id": fact.id, "content": (fact.content or "")[:120]}
        ]
        chains.append({"depth": depth, "path": new_path})

        if depth >= max_depth:
            continue

        next_edges = await prisma.knowledgeedge.find_many(
            where={
                "fromFactId": fact_id,
                "relationType": {
                    "in": [
                        KnowledgeRelation.CAUSES.value,
                        KnowledgeRelation.ENABLES.value,
                    ]
                },
            },
            order={"strength": "desc"},
            take=5,
        )
        for e in next_edges:
            if e.toFactId in visited:
                continue
            queue.append((e.toFactId, depth + 1, new_path))

    return {
        "start": start_fact_id,
        "chain_count": len(chains),
        "chains": chains,
    }


# ---------------------------------------------------------------------------
# 자연어 설명 (chat 통합용)
# ---------------------------------------------------------------------------
async def explain_with_causal_chain(question: str) -> dict:
    """질문 → 의미 검색 → 인과 사슬 → 자연어 설명.

    chat/route.ts 가 "왜?" 류 질문에서 호출. 실패해도 빈 dict 반환.
    """
    if not question or len(question.strip()) < 2:
        return {"explanation": None}

    try:
        from hwarang_api.knowledge.search import temporal_search

        sq = SearchQuery(query=question, limit=3)
        seeds = await temporal_search(sq)
    except Exception as exc:  # noqa: BLE001
        logger.debug("explain seed search failed: %s", exc)
        return {"explanation": None}

    if not seeds.facts:
        return {"explanation": None}

    # 각 시드에서 사슬 펼친 뒤 가장 깊은 것을 채택.
    best_chain: dict | None = None
    best_depth = 0
    for s in seeds.facts:
        if not s.id:
            continue
        try:
            traced = await trace_causal_chain(s.id, max_depth=3, max_paths=10)
        except Exception:
            continue
        if not traced["chains"]:
            continue
        # 가장 깊은 path
        deepest = max(traced["chains"], key=lambda c: c["depth"])
        if deepest["depth"] > best_depth:
            best_depth = deepest["depth"]
            best_chain = deepest

    if best_chain is None or best_chain["depth"] == 0:
        return {"explanation": None}

    steps = " → ".join(p["content"] for p in best_chain["path"])
    return {
        "explanation": f"인과 체인: {steps}",
        "chain": best_chain,
        "depth": best_chain["depth"],
    }


# ---------------------------------------------------------------------------
# 파서
# ---------------------------------------------------------------------------
def _parse_relations(raw: str) -> list[dict]:
    """LLM 응답 → JSON 배열. 코드펜스/노이즈 허용."""
    if not raw:
        return []
    # 코드펜스 제거
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
    out: list[dict] = []
    for item in parsed:
        if isinstance(item, dict):
            out.append(item)
    return out


__all__ = [
    "extract_causal_edges_from_text",
    "auto_extract_recent",
    "trace_causal_chain",
    "explain_with_causal_chain",
]
