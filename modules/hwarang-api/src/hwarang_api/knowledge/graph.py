"""HLKM B1 - Causal Graph Traversal.

KnowledgeEdge 위에서 BFS/경로 탐색을 수행해 인과사슬, 관련 팩트,
루트 원인(entry point), 서브그래프, 반사실(counterfactual) 질의를 제공한다.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from hwarang_api.db import prisma
from hwarang_api.knowledge.types import KnowledgeEdge, KnowledgeRelation


def _edge_from_row(row: Any) -> KnowledgeEdge:
    """Prisma row → Pydantic KnowledgeEdge."""
    return KnowledgeEdge(
        id=row.id,
        from_fact_id=row.fromFactId,
        to_fact_id=row.toFactId,
        relation_type=KnowledgeRelation(row.relationType),
        strength=float(row.strength),
        evidence=row.evidence,
        verified_by=row.verifiedBy,
        created_at=row.createdAt,
    )


async def traverse_causal_chain(
    from_fact_id: str,
    relation: KnowledgeRelation,
    max_depth: int = 3,
) -> list[dict]:
    """단방향 BFS 로 인과사슬을 펼친다.

    각 노드는 `{fact_id, depth, path, strength_product}` 로 반환되며,
    `strength_product` 는 루트→해당 노드까지 엣지 strength 의 곱이다.
    사이클은 `visited` 집합으로 차단.
    """
    if max_depth <= 0:
        return []

    visited: set[str] = {from_fact_id}
    out: list[dict] = []
    queue: deque[tuple[str, int, list[str], float]] = deque(
        [(from_fact_id, 0, [from_fact_id], 1.0)]
    )

    while queue:
        node, depth, path, strength = queue.popleft()
        if depth >= max_depth:
            continue
        edges = await prisma.knowledgeedge.find_many(
            where={"fromFactId": node, "relationType": relation.value}
        )
        for e in edges:
            child = e.toFactId
            if child in visited:
                continue
            visited.add(child)
            new_strength = strength * float(e.strength)
            new_path = path + [child]
            out.append(
                {
                    "fact_id": child,
                    "depth": depth + 1,
                    "parent": node,
                    "path": new_path,
                    "strength_product": new_strength,
                    "edge_strength": float(e.strength),
                }
            )
            queue.append((child, depth + 1, new_path, new_strength))

    return out


async def find_related(
    fact_id: str,
    relation_types: list[KnowledgeRelation] | None = None,
    min_strength: float = 0.5,
) -> list[KnowledgeEdge]:
    """팩트의 직접 이웃 엣지 (in/out 양방향)를 필터링해서 돌려준다."""
    base_filter: dict[str, Any] = {"strength": {"gte": min_strength}}
    if relation_types:
        base_filter["relationType"] = {"in": [r.value for r in relation_types]}

    outgoing = await prisma.knowledgeedge.find_many(
        where={**base_filter, "fromFactId": fact_id}
    )
    incoming = await prisma.knowledgeedge.find_many(
        where={**base_filter, "toFactId": fact_id}
    )

    merged: dict[str, Any] = {}
    for r in list(outgoing) + list(incoming):
        merged[r.id] = r
    return [_edge_from_row(r) for r in merged.values()]


async def find_entry_points(entity: str) -> list[str]:
    """엔티티에 속한 팩트 중 들어오는 엣지가 없는 '루트 원인' id 를 찾는다."""
    facts = await prisma.knowledgefact.find_many(
        where={"entity": entity}, order={"validFrom": "asc"}
    )
    ids = [f.id for f in facts]
    if not ids:
        return []

    incoming = await prisma.knowledgeedge.find_many(
        where={"toFactId": {"in": ids}}
    )
    has_incoming = {e.toFactId for e in incoming}
    return [i for i in ids if i not in has_incoming]


async def build_subgraph(fact_ids: list[str], max_hops: int = 2) -> dict:
    """시각화용 서브그래프 구축.

    입력 노드들로부터 `max_hops` 홉까지 확장해 `{nodes, edges}` 를 만든다.
    """
    if not fact_ids:
        return {"nodes": [], "edges": []}

    frontier: set[str] = set(fact_ids)
    all_nodes: set[str] = set(fact_ids)
    collected_edges: dict[str, Any] = {}

    for _ in range(max_hops):
        if not frontier:
            break
        edges = await prisma.knowledgeedge.find_many(
            where={
                "OR": [
                    {"fromFactId": {"in": list(frontier)}},
                    {"toFactId": {"in": list(frontier)}},
                ]
            }
        )
        next_frontier: set[str] = set()
        for e in edges:
            collected_edges[e.id] = e
            for nid in (e.fromFactId, e.toFactId):
                if nid not in all_nodes:
                    next_frontier.add(nid)
                    all_nodes.add(nid)
        frontier = next_frontier

    node_rows = (
        await prisma.knowledgefact.find_many(where={"id": {"in": list(all_nodes)}})
        if all_nodes
        else []
    )
    nodes = [
        {
            "id": n.id,
            "entity": n.entity,
            "domain": n.domain,
            "status": n.status,
            "content_preview": (n.content[:80] + "…") if len(n.content) > 80 else n.content,
        }
        for n in node_rows
    ]
    edges = [
        {
            "id": e.id,
            "from": e.fromFactId,
            "to": e.toFactId,
            "relation": e.relationType,
            "strength": float(e.strength),
        }
        for e in collected_edges.values()
    ]
    return {"nodes": nodes, "edges": edges}


async def counterfactual_query(removed_fact_id: str, target_fact_id: str) -> dict:
    """반사실 질의.

    "removed_fact 가 없었다면 target 에 여전히 도달 가능한가?"

    알고리즘:
      1) target 으로 향하는 모든 경로를 역-BFS 로 수집 (깊이 제한).
      2) `removed_fact_id` 를 거치지 않는 경로가 하나라도 있으면 still_reachable.
    """
    max_depth = 6
    # target 에서 역방향으로 BFS (to → from 방향).
    paths: list[list[str]] = []
    queue: deque[tuple[str, list[str]]] = deque([(target_fact_id, [target_fact_id])])
    seen_edges: set[tuple[str, str]] = set()

    while queue:
        node, path = queue.popleft()
        if len(path) > max_depth:
            continue
        incoming = await prisma.knowledgeedge.find_many(where={"toFactId": node})
        if not incoming:
            paths.append(list(reversed(path)))
            continue
        dead_end = True
        for e in incoming:
            key = (e.fromFactId, e.toFactId)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            if e.fromFactId in path:  # cycle
                continue
            dead_end = False
            queue.append((e.fromFactId, path + [e.fromFactId]))
        if dead_end:
            paths.append(list(reversed(path)))

    alternative_paths = [p for p in paths if removed_fact_id not in p]
    still_reachable = len(alternative_paths) > 0 and len(paths) > 0
    return {
        "still_reachable": still_reachable,
        "total_paths": len(paths),
        "blocked_paths": len([p for p in paths if removed_fact_id in p]),
        "alternative_paths": alternative_paths,
    }
