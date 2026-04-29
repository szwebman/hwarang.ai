"""다단계 인과 체인 — A → B → C → D.

각 단계의 strength 를 곱해 누적 확률 (cumulative_prob) 을 만들고,
그 중 가장 약한 연결 (weakest_link) 도 함께 반환한다.
이는 체인 신뢰도의 보수적 하한이다.

BFS 로 모든 경로를 탐색하되, 사이클 방지 + 최대 깊이 제한.
가장 강한 (cumulative_prob 최대) 경로를 best 로 선택.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


@dataclass
class CausalChain:
    nodes: list[str]
    edges: list[dict]
    cumulative_prob: float
    weakest_link: float
    confidence: float
    depth: int = 0
    contents: list[str] = field(default_factory=list)


async def trace_chain(
    start_id: str,
    end_id: str,
    max_depth: int = 5,
) -> CausalChain | None:
    """start → end 까지 인과 체인 + 누적 확률.

    동일 노드면 trivially 1.0 반환.
    경로 없으면 None.
    """
    if start_id == end_id:
        return CausalChain(
            nodes=[start_id],
            edges=[],
            cumulative_prob=1.0,
            weakest_link=1.0,
            confidence=1.0,
            depth=0,
            contents=[],
        )

    queue: list[tuple[str, list[str], float, float]] = [
        (start_id, [start_id], 1.0, 1.0),
    ]
    best: tuple[list[str], float, float] | None = None

    while queue:
        current, path, cum_prob, weakest = queue.pop(0)
        if len(path) > max_depth:
            continue

        edges = await prisma.knowledgeedge.find_many(
            where={
                "fromFactId": current,
                "relationType": {"in": ["CAUSES", "ENABLES"]},
            },
            order={"strength": "desc"},
            take=10,
        )

        for e in edges:
            if e.toFactId in path:  # 사이클 방지
                continue
            edge_weight = float(e.strength) if e.strength is not None else 0.5
            new_prob = cum_prob * edge_weight
            new_weakest = min(weakest, edge_weight)
            new_path = path + [e.toFactId]

            if e.toFactId == end_id:
                if best is None or new_prob > best[1]:
                    best = (new_path, new_prob, new_weakest)
                continue

            if len(new_path) <= max_depth:
                queue.append((e.toFactId, new_path, new_prob, new_weakest))

    if best is None:
        return None

    nodes, cum_prob, weakest = best
    edges_out = [
        {"from": nodes[i], "to": nodes[i + 1]} for i in range(len(nodes) - 1)
    ]

    contents = await _fetch_contents(nodes)

    return CausalChain(
        nodes=nodes,
        edges=edges_out,
        cumulative_prob=cum_prob,
        weakest_link=weakest,
        confidence=cum_prob,  # 단순화 — 누적 prob 을 신뢰도로 사용
        depth=len(nodes) - 1,
        contents=contents,
    )


async def _fetch_contents(fact_ids: list[str]) -> list[str]:
    out: list[str] = []
    for fid in fact_ids:
        try:
            f = await prisma.knowledgefact.find_unique(where={"id": fid})
        except Exception:
            f = None
        out.append((f.content or "")[:120] if f else "")
    return out


__all__ = ["CausalChain", "trace_chain"]
