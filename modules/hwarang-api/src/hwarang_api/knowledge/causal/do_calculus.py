"""Pearl's do-calculus 단순화 구현.

진짜 do-calculus 는 backdoor/frontdoor adjustment, identifiability 판정 등
복잡하다. 여기선 가장 흔한 케이스만 휴리스틱으로 처리:

* observed_prob       — 관찰 P(Y | X) — KnowledgeEdge.strength 그대로.
* intervention_prob   — P(Y | do(X)) — backdoor 후보 (혼란 변수) 영향 차감.
* mediators           — 인과 경로의 일부이므로 차감하지 않는다.

휴리스틱:
    intervention = max(0, observed - 0.5 * mean(P(Y|confounder)))

이는 진짜 backdoor adjustment 가 아니라 "혼란 변수 절반 영향 제거" 라는
보수적 근사이다. 한계는 explanation 에 명시된다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .causal_graph import (
    CausalEdge,
    find_confounders,
    find_mediators,
    get_causal_edge,
)

logger = logging.getLogger(__name__)


@dataclass
class InterventionResult:
    cause_id: str
    effect_id: str
    observed_prob: float
    intervention_prob: float
    blocked_confounders: list[str] = field(default_factory=list)
    mediators: list[str] = field(default_factory=list)
    explanation: str = ""
    confidence: float = 0.0


async def estimate_intervention(
    cause_id: str,
    effect_id: str,
) -> InterventionResult:
    """do(cause) 시 effect 발생 확률 추정.

    direct edge 가 없으면 0 반환. 혼란 변수가 있으면 그 영향만큼 차감해
    "관찰 vs 개입" 차이를 노출한다.
    """
    edge = await get_causal_edge(cause_id, effect_id)
    if edge is None:
        return InterventionResult(
            cause_id=cause_id,
            effect_id=effect_id,
            observed_prob=0.0,
            intervention_prob=0.0,
            blocked_confounders=[],
            mediators=[],
            explanation="직접 인과 관계 없음",
            confidence=0.0,
        )

    observed = edge.weight
    confounders = await find_confounders(cause_id, effect_id)
    mediators = await find_mediators(cause_id, effect_id)

    # backdoor adjustment 휴리스틱 — 혼란 변수의 effect 측 영향력 평균을 절반 차감.
    if confounders:
        confounder_effects: list[float] = []
        for cid in confounders:
            ce = await get_causal_edge(cid, effect_id)
            if ce is not None:
                confounder_effects.append(ce.weight)
        if confounder_effects:
            avg = sum(confounder_effects) / len(confounder_effects)
            intervention = max(0.0, observed - avg * 0.5)
        else:
            intervention = observed
    else:
        intervention = observed

    explanation = _build_explanation(edge, confounders, mediators, observed, intervention)

    return InterventionResult(
        cause_id=cause_id,
        effect_id=effect_id,
        observed_prob=observed,
        intervention_prob=intervention,
        blocked_confounders=confounders,
        mediators=mediators,
        explanation=explanation,
        confidence=edge.confidence,
    )


def _build_explanation(
    edge: CausalEdge,
    confounders: list[str],
    mediators: list[str],
    observed: float,
    intervention: float,
) -> str:
    parts: list[str] = [f"관찰 확률 P(Y|X) = {observed:.2f}"]

    if confounders:
        parts.append(
            f"혼란 변수 {len(confounders)}개 발견 — "
            f"개입 후 확률 P(Y|do(X)) = {intervention:.2f}"
        )
    else:
        parts.append("혼란 변수 없음 — 관찰 ≈ 개입")

    if mediators:
        parts.append(
            f"매개 변수 {len(mediators)}개 — 인과 경로 일부는 우회 가능"
        )

    return ". ".join(parts)


__all__ = ["InterventionResult", "estimate_intervention"]
