"""인과 그래프 — 단순 edge 가 아닌 확률/시간/매개/혼란 포함.

기존 KnowledgeEdge 의 strength/relationType 을 그대로 활용하되,
런타임에 다음 메타를 추가 계산한다:

* conditional_prob — P(effect | cause) 의 휴리스틱 추정 (현재는 strength)
* time_lag_days    — cause.validFrom → effect.validFrom 평균 시간차
* confidence       — 인과 vs 상관 점수 (현재는 strength proxy)
* mediators        — 중간 매개 변수 (A → M → B) 의 fact id 들
* confounders      — A 와 B 둘 다 일으킨 공통 부모 (B → A, B → C)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


_CAUSAL_RELATIONS = ["CAUSES", "ENABLES", "TRIGGERS"]


@dataclass
class CausalEdge:
    """인과 edge + 메타.

    weight 는 KnowledgeEdge.strength 를 그대로 따른다.
    conditional_prob 는 현 단계에서 weight 와 동일 — 추후 빈도 기반 재추정 가능.
    """

    cause_id: str
    effect_id: str
    cause_text: str
    effect_text: str
    relation_type: str
    weight: float
    conditional_prob: float | None = None
    time_lag_days: int | None = None
    confidence: float = 0.5
    mediators: list[str] = field(default_factory=list)
    confounders: list[str] = field(default_factory=list)


async def get_causal_edge(cause_id: str, effect_id: str) -> CausalEdge | None:
    """edge + 메타 조회. 인과 관계가 없으면 None."""
    edge = await prisma.knowledgeedge.find_first(
        where={
            "fromFactId": cause_id,
            "toFactId": effect_id,
            "relationType": {"in": _CAUSAL_RELATIONS},
        },
    )
    if edge is None:
        return None

    cause = await prisma.knowledgefact.find_unique(where={"id": cause_id})
    effect = await prisma.knowledgefact.find_unique(where={"id": effect_id})
    if cause is None or effect is None:
        return None

    # 시간 차 — 음수면 None (effect 가 cause 이전이면 인과 시간 가정 위반)
    time_lag: int | None = None
    cause_t = getattr(cause, "validFrom", None)
    effect_t = getattr(effect, "validFrom", None)
    if cause_t and effect_t:
        try:
            delta = (effect_t - cause_t).days
            time_lag = delta if delta >= 0 else None
        except Exception:  # noqa: BLE001
            time_lag = None

    weight = float(edge.strength) if edge.strength is not None else 0.5

    return CausalEdge(
        cause_id=cause_id,
        effect_id=effect_id,
        cause_text=(cause.content or "")[:300],
        effect_text=(effect.content or "")[:300],
        relation_type=edge.relationType,
        weight=weight,
        conditional_prob=weight,
        time_lag_days=time_lag,
        confidence=weight,
    )


async def find_confounders(cause_id: str, effect_id: str) -> list[str]:
    """A → C 처럼 보이지만 B 가 A 와 C 둘 다 유발한 경우의 B 들.

    그래프 상에서 fromFactId=B 가 toFactId in {A, C} 두 케이스를 동시에 만족.
    """
    cause_parents = await prisma.knowledgeedge.find_many(
        where={
            "toFactId": cause_id,
            "relationType": {"in": ["CAUSES", "ENABLES"]},
        },
        take=50,
    )
    effect_parents = await prisma.knowledgeedge.find_many(
        where={
            "toFactId": effect_id,
            "relationType": {"in": ["CAUSES", "ENABLES"]},
        },
        take=50,
    )

    cause_parent_ids = {e.fromFactId for e in cause_parents}
    effect_parent_ids = {e.fromFactId for e in effect_parents}

    # cause 자체가 effect 의 부모이면 그건 직접 인과 — 혼란 변수 아님.
    common = cause_parent_ids & effect_parent_ids
    common.discard(cause_id)
    common.discard(effect_id)
    return list(common)


async def find_mediators(
    cause_id: str,
    effect_id: str,
    max_depth: int = 3,
) -> list[str]:
    """A → M → C 형태의 매개 변수.

    cause 에서 effect 까지 도달하는 가장 짧은 경로의 중간 노드들 (cause/effect 제외).
    BFS — depth 제한.
    """
    if cause_id == effect_id:
        return []

    visited: set[str] = {cause_id}
    queue: list[tuple[str, list[str]]] = [(cause_id, [])]
    paths: list[list[str]] = []

    while queue:
        node, path = queue.pop(0)
        if len(path) >= max_depth:
            continue

        edges = await prisma.knowledgeedge.find_many(
            where={
                "fromFactId": node,
                "relationType": {"in": ["CAUSES", "ENABLES"]},
            },
            take=10,
        )
        for e in edges:
            if e.toFactId == effect_id:
                if path:
                    # 직접 edge 는 매개 아님 — path 가 비어있으면 중간 노드 없음
                    paths.append(list(path))
                continue
            if e.toFactId in visited:
                continue
            visited.add(e.toFactId)
            queue.append((e.toFactId, path + [e.toFactId]))

    if not paths:
        return []
    shortest = min(paths, key=len)
    return shortest


__all__ = [
    "CausalEdge",
    "find_confounders",
    "find_mediators",
    "get_causal_edge",
]
