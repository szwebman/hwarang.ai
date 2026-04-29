"""반사실 추론 — "만약 X 가 다르게 일어났으면 Y 는 어떻게 됐을까?"

LLM 기반 추론 + 그래프 구조 결합.
* reason_counterfactual(cause_id, effect_id) — 두 fact 사이 반사실
* explain_what_if(question)                  — 사용자 자연어 "만약~" 질문 핸들러
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as llm_chat
from hwarang_api.knowledge.types import SearchQuery

from .causal_graph import find_confounders, find_mediators, get_causal_edge

logger = logging.getLogger(__name__)


_COUNTERFACTUAL_PROMPT = """반사실 추론 작업:

## 실제 일어난 일
{actual}

## 원인 (X)
{cause}

## 결과 (Y)
{effect}

## 인과 그래프 정보
- 직접 인과 강도: {weight}
- 매개 변수: {mediators}
- 혼란 변수: {confounders}

질문: 만약 X 가 일어나지 않았다면 Y 는 어떻게 됐을 것인가?

JSON 답변:
{{
  "would_y_happen": "true|false|likely|unlikely",
  "alternative_outcome": "Y 대신 어떤 일이 있었을지",
  "confidence": 0.0~1.0,
  "reasoning": "추론 근거",
  "what_would_change_too": ["다른 영향 받는 것들"]
}}
JSON 만 출력:"""


_WHAT_IF_EXTRACT_PROMPT = """다음 '만약~' 질문에서 가정 X 와 관심사 Y 를 추출해라.

질문: {question}

JSON: {{"hypothesis": "X 가정", "concern": "Y 관심사"}}
JSON 만 출력:"""


@dataclass
class CounterfactualResult:
    cause_id: str
    effect_id: str
    would_y_happen: str  # true | false | likely | unlikely | unknown
    alternative_outcome: str
    confidence: float
    reasoning: str
    cascading_changes: list[str] = field(default_factory=list)


async def reason_counterfactual(
    cause_id: str,
    effect_id: str,
) -> CounterfactualResult:
    """그래프에서 cause→effect 가 존재할 때, X 가 안 일어났으면? 을 LLM 에 묻는다."""
    edge = await get_causal_edge(cause_id, effect_id)
    if edge is None:
        return CounterfactualResult(
            cause_id=cause_id,
            effect_id=effect_id,
            would_y_happen="unknown",
            alternative_outcome="인과 관계 없음 — 반사실 추론 불가",
            confidence=0.0,
            reasoning="",
            cascading_changes=[],
        )

    mediators = await find_mediators(cause_id, effect_id)
    confounders = await find_confounders(cause_id, effect_id)

    mediator_texts = await _fact_summaries(mediators[:3])
    confounder_texts = await _fact_summaries(confounders[:3])

    prompt = _COUNTERFACTUAL_PROMPT.format(
        actual=f"X={edge.cause_text} → Y={edge.effect_text}",
        cause=edge.cause_text,
        effect=edge.effect_text,
        weight=f"{edge.weight:.2f}",
        mediators=", ".join(mediator_texts) or "없음",
        confounders=", ".join(confounder_texts) or "없음",
    )

    try:
        raw = await llm_chat(prompt, max_tokens=400)
        parsed = _parse_json_object(raw)
        if parsed is not None:
            return CounterfactualResult(
                cause_id=cause_id,
                effect_id=effect_id,
                would_y_happen=str(parsed.get("would_y_happen", "unknown"))[:20],
                alternative_outcome=str(parsed.get("alternative_outcome", ""))[:500],
                confidence=_safe_float(parsed.get("confidence"), 0.5),
                reasoning=str(parsed.get("reasoning", ""))[:1000],
                cascading_changes=_str_list(parsed.get("what_would_change_too"))[:5],
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("counterfactual reasoning failed: %s", exc)

    return CounterfactualResult(
        cause_id=cause_id,
        effect_id=effect_id,
        would_y_happen="unknown",
        alternative_outcome="추론 실패",
        confidence=0.0,
        reasoning="",
        cascading_changes=[],
    )


async def explain_what_if(question: str) -> dict:
    """사용자 '만약 X 였다면?' 자연어 질문 처리.

    chat/route.ts 의 _meta.counterfactual 보강에 사용.
    """
    if not question or len(question.strip()) < 2:
        return {"error": "empty_question"}

    extract_prompt = _WHAT_IF_EXTRACT_PROMPT.format(question=question[:600])
    try:
        raw = await llm_chat(extract_prompt, max_tokens=200)
    except Exception:
        return {"error": "extraction_failed"}

    parts = _parse_json_object(raw)
    if not parts:
        return {"error": "parse_failed"}

    hypothesis = str(parts.get("hypothesis", "")).strip()
    concern = str(parts.get("concern", "")).strip()
    if not hypothesis or not concern:
        return {"error": "incomplete_extraction"}

    # HLKM temporal_search 로 두 측의 핵심 fact 가져오기
    try:
        from hwarang_api.knowledge.search import temporal_search

        cause_res = await temporal_search(SearchQuery(query=hypothesis, limit=3))
        effect_res = await temporal_search(SearchQuery(query=concern, limit=3))
    except Exception as exc:  # noqa: BLE001
        logger.debug("what_if search failed: %s", exc)
        return {"error": "search_failed"}

    if not cause_res.facts or not effect_res.facts:
        return {"error": "no_related_facts", "hypothesis": hypothesis, "concern": concern}

    cause_id = cause_res.facts[0].id
    effect_id = effect_res.facts[0].id
    if not cause_id or not effect_id:
        return {"error": "fact_id_missing"}

    result = await reason_counterfactual(cause_id, effect_id)

    return {
        "hypothesis": hypothesis,
        "concern": concern,
        "would_y_happen": result.would_y_happen,
        "alternative_outcome": result.alternative_outcome,
        "reasoning": result.reasoning,
        "cascading_changes": result.cascading_changes,
        "confidence": result.confidence,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _fact_summaries(fact_ids: list[str]) -> list[str]:
    out: list[str] = []
    for fid in fact_ids:
        try:
            f = await prisma.knowledgefact.find_unique(where={"id": fid})
        except Exception:
            f = None
        if f and f.content:
            out.append(f.content[:100])
    return out


def _parse_json_object(raw: str) -> dict | None:
    if not raw:
        return None
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "")
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m is None:
        return None
    try:
        obj = json.loads(m.group())
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _safe_float(v, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _str_list(v) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(x) for x in v if x is not None]


__all__ = [
    "CounterfactualResult",
    "explain_what_if",
    "reason_counterfactual",
]
