"""HLKM ② - Community Detection & Summarization.

KnowledgeEdge 그래프 위에서 커뮤니티(주제 클러스터)를 탐지하고,
각 커뮤니티에 대해 LLM 으로 한국어 요약을 생성해 KnowledgeCommunity 에 저장한다.

알고리즘:
    - Louvain (networkx 설치 시): 모듈러리티 기반 표준
    - Label Propagation (fallback): 의존성 없는 greedy 근사

CONTRADICTS 관계는 응집성을 저해하므로 그래프 구축 시 제외한다.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma
from hwarang_api.knowledge.types import KnowledgeRelation

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fingerprint(fact_ids: list[str]) -> str:
    """멤버 fact_ids 의 정렬 해시 — upsert key."""
    joined = ",".join(sorted(fact_ids))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]


async def _llm_summarize_community(
    contents: list[str], domain: str | None, model_hint: str = "hwarang"
) -> tuple[str, str]:
    """커뮤니티 멤버 본문들을 한국어 주제 설명으로 요약.

    llm.py 에 전용 함수가 없어 llm_summarize_changes 를 prompt-level 로 재활용한다.
    반환: (summary_text, model_version).
    """
    try:
        from hwarang_api.knowledge.llm import _chat, _LLM_MODEL  # type: ignore
    except Exception:
        return ("", model_hint)

    if not contents:
        return ("", _LLM_MODEL)

    head = "\n".join(f"- {c[:180]}" for c in contents[:20])
    system = (
        "You are a Korean knowledge-graph topic summarizer. "
        "Given a list of facts, return one concise Korean sentence (<=60자) "
        "describing the shared topic. No prefix, no bullet, just the sentence."
    )
    domain_hint = f" (도메인: {domain})" if domain else ""
    prompt = f"다음 사실들{domain_hint}의 공통 주제를 한 문장으로 요약:\n{head}"
    try:
        resp = await _chat(prompt, system=system, max_tokens=120)
    except Exception as exc:  # noqa: BLE001
        logger.debug("community summary LLM failed: %s", exc)
        resp = ""
    return (resp.strip(), _LLM_MODEL)


# ─────────────────────────────────────────────
# 그래프 빌드
# ─────────────────────────────────────────────
def _build_graph_from_edges(
    edges: list[Any],
    facts: list[Any],
    exclude_relations: list[str],
) -> dict[str, list[tuple[str, float]]]:
    """KnowledgeEdge 목록으로부터 무방향 가중 인접 리스트 구축."""
    fact_ids = {f.id for f in facts}
    adj: dict[str, list[tuple[str, float]]] = {fid: [] for fid in fact_ids}

    agg: dict[tuple[str, str], float] = defaultdict(float)
    for e in edges:
        if e.relationType in exclude_relations:
            continue
        if e.fromFactId not in fact_ids or e.toFactId not in fact_ids:
            continue
        if e.fromFactId == e.toFactId:
            continue
        a, b = sorted((e.fromFactId, e.toFactId))
        agg[(a, b)] += max(0.0, float(e.strength))

    for (a, b), w in agg.items():
        adj[a].append((b, w))
        adj[b].append((a, w))
    return adj


# ─────────────────────────────────────────────
# Louvain (networkx) or Label Propagation fallback
# ─────────────────────────────────────────────
def _louvain_partition(
    adjacency: dict[str, list[tuple[str, float]]],
) -> dict[str, int]:
    """커뮤니티 라벨 할당 — networkx 가 있으면 louvain, 없으면 LPA."""
    if not adjacency:
        return {}

    # 1) networkx 사용 시도
    try:
        import networkx as nx
        from networkx.algorithms.community import louvain_communities

        g = nx.Graph()
        for node, neighbours in adjacency.items():
            g.add_node(node)
            for nb, w in neighbours:
                # 무방향이므로 양방향 중복은 set_edge 로 자동 병합
                if g.has_edge(node, nb):
                    continue
                g.add_edge(node, nb, weight=w)
        try:
            partitions = louvain_communities(g, weight="weight", seed=42)
        except TypeError:
            partitions = louvain_communities(g, weight="weight")
        labels: dict[str, int] = {}
        for idx, comm in enumerate(partitions):
            for n in comm:
                labels[n] = idx
        # 고립 노드 처리
        next_label = len(partitions)
        for n in adjacency:
            if n not in labels:
                labels[n] = next_label
                next_label += 1
        return labels
    except Exception:
        pass

    # 2) Label Propagation fallback (결정적·2-pass)
    labels = {n: i for i, n in enumerate(adjacency.keys())}
    nodes_sorted = sorted(adjacency.keys())
    for _pass in range(5):
        changed = 0
        for node in nodes_sorted:
            neigh = adjacency.get(node, [])
            if not neigh:
                continue
            score: dict[int, float] = defaultdict(float)
            for nb, w in neigh:
                score[labels[nb]] += w
            if not score:
                continue
            # 최대 라벨 — 동률 시 라벨 번호 작은 쪽
            best = max(score.items(), key=lambda kv: (kv[1], -kv[0]))[0]
            if labels[node] != best:
                labels[node] = best
                changed += 1
        if changed == 0:
            break
    # 라벨 리넘버링(0, 1, 2, ...)
    uniq = {old: i for i, old in enumerate(sorted(set(labels.values())))}
    return {n: uniq[lb] for n, lb in labels.items()}


# ─────────────────────────────────────────────
# 응집도/중심 노드
# ─────────────────────────────────────────────
def _cohesion_and_central(
    members: list[str],
    adjacency: dict[str, list[tuple[str, float]]],
) -> tuple[float, str | None]:
    """커뮤니티 내부 평균 엣지 strength + 가중 degree 가 가장 큰 fact_id."""
    member_set = set(members)
    internal_w = 0.0
    internal_cnt = 0
    deg: dict[str, float] = defaultdict(float)

    for m in members:
        for nb, w in adjacency.get(m, []):
            if nb in member_set:
                deg[m] += w
                # 무방향 양쪽 카운트되므로 /2 는 아래서 처리
                internal_w += w
                internal_cnt += 1

    cohesion = (internal_w / internal_cnt) if internal_cnt else 0.0
    central = max(deg.items(), key=lambda kv: kv[1])[0] if deg else (members[0] if members else None)
    return (cohesion, central)


# ─────────────────────────────────────────────
# 메인 API
# ─────────────────────────────────────────────
async def detect_communities(
    algorithm: str = "louvain",
    domain: str | None = None,
    min_size: int = 3,
) -> list[dict]:
    """커뮤니티 탐지 → DB 업서트 → 요약 목록 반환.

    CONTRADICTS 는 제외하며, `min_size` 미만 커뮤니티는 폐기한다.
    """
    fact_where: dict[str, Any] = {}
    if domain:
        fact_where["domain"] = domain
    facts = await prisma.knowledgefact.find_many(where=fact_where, take=5000)
    if not facts:
        return []

    fact_ids = [f.id for f in facts]
    edges = await prisma.knowledgeedge.find_many(
        where={
            "OR": [
                {"fromFactId": {"in": fact_ids}},
                {"toFactId": {"in": fact_ids}},
            ]
        },
        take=20000,
    )

    adjacency = _build_graph_from_edges(
        edges, facts, exclude_relations=[KnowledgeRelation.CONTRADICTS.value]
    )
    labels = _louvain_partition(adjacency)

    # 라벨별 그룹핑
    grouped: dict[int, list[str]] = defaultdict(list)
    for node, lb in labels.items():
        grouped[lb].append(node)

    fact_by_id = {f.id: f for f in facts}
    results: list[dict] = []

    for lb, members in grouped.items():
        if len(members) < min_size:
            continue
        cohesion, central_id = _cohesion_and_central(members, adjacency)
        dominant_domain = _dominant_domain([fact_by_id[m] for m in members])
        fp = _fingerprint(members)
        name = f"C-{dominant_domain or 'general'}-{fp[:8]}"

        existing = await prisma.knowledgecommunity.find_first(where={"name": name})
        payload: dict[str, Any] = {
            "name": name,
            "algorithm": algorithm,
            "domain": dominant_domain,
            "factIds": members,
            "size": len(members),
            "cohesion": float(cohesion),
            "centralFactId": central_id,
        }

        if existing is None:
            row = await prisma.knowledgecommunity.create(data=payload)
            community_id = row.id
        else:
            payload["version"] = existing.version + 1
            row = await prisma.knowledgecommunity.update(
                where={"id": existing.id}, data=payload
            )
            community_id = row.id

        results.append(
            {
                "community_id": community_id,
                "name": name,
                "size": len(members),
                "fact_ids": members,
                "cohesion": float(cohesion),
                "central_fact_id": central_id,
                "domain": dominant_domain,
            }
        )

    results.sort(key=lambda c: c["size"], reverse=True)
    logger.info("detect_communities: %d communities (algo=%s)", len(results), algorithm)
    return results


def _dominant_domain(facts: list[Any]) -> str | None:
    counter: dict[str, int] = defaultdict(int)
    for f in facts:
        if f.domain:
            counter[f.domain] += 1
    if not counter:
        return None
    return max(counter.items(), key=lambda kv: kv[1])[0]


# ─────────────────────────────────────────────
# 요약
# ─────────────────────────────────────────────
async def summarize_community(community_id: str, model_hint: str = "hwarang") -> str:
    """한 커뮤니티의 LLM 요약을 재생성해 DB 에 저장 후 반환."""
    comm = await prisma.knowledgecommunity.find_unique(where={"id": community_id})
    if comm is None:
        raise ValueError(f"community not found: {community_id}")

    facts = await prisma.knowledgefact.find_many(where={"id": {"in": comm.factIds}})
    contents = [f.content for f in facts if f.content]
    summary, model_ver = await _llm_summarize_community(
        contents, comm.domain, model_hint=model_hint
    )
    if not summary:
        # fallback: 첫 2 팩트의 앞부분을 이어붙임
        summary = " / ".join(c[:60] for c in contents[:2])[:200]

    await prisma.knowledgecommunity.update(
        where={"id": community_id},
        data={"summary": summary, "summaryModel": model_ver},
    )
    return summary


# ─────────────────────────────────────────────
# 역-조회
# ─────────────────────────────────────────────
async def get_community_for_fact(fact_id: str) -> dict | None:
    """특정 팩트가 속한 커뮤니티 (가장 큰 것 1 개) 반환."""
    comms = await prisma.knowledgecommunity.find_many(
        where={"factIds": {"has": fact_id}},
        order={"size": "desc"},
        take=1,
    )
    if not comms:
        return None
    c = comms[0]
    return {
        "community_id": c.id,
        "name": c.name,
        "size": c.size,
        "domain": c.domain,
        "summary": c.summary,
        "cohesion": float(c.cohesion),
        "central_fact_id": c.centralFactId,
    }


# ─────────────────────────────────────────────
# 관련 커뮤니티 추천
# ─────────────────────────────────────────────
async def suggest_related_communities(community_id: str, top_k: int = 5) -> list[dict]:
    """`community_id` 와 멤버가 겹치거나 크로스-엣지가 많은 커뮤니티 랭킹."""
    source = await prisma.knowledgecommunity.find_unique(where={"id": community_id})
    if source is None:
        return []
    source_set = set(source.factIds)
    if not source_set:
        return []

    others = await prisma.knowledgecommunity.find_many(
        where={"id": {"not": community_id}}, take=500
    )

    # 크로스-엣지 집계
    cross_edges = await prisma.knowledgeedge.find_many(
        where={
            "OR": [
                {"fromFactId": {"in": list(source_set)}},
                {"toFactId": {"in": list(source_set)}},
            ],
            "relationType": {"not": KnowledgeRelation.CONTRADICTS.value},
        },
        take=10000,
    )
    # dest fact → strength sum
    dest_strength: dict[str, float] = defaultdict(float)
    for e in cross_edges:
        other = e.toFactId if e.fromFactId in source_set else e.fromFactId
        if other in source_set:
            continue
        dest_strength[other] += float(e.strength)

    scored: list[dict] = []
    for c in others:
        member_set = set(c.factIds)
        shared = len(source_set & member_set)
        bridge = sum(dest_strength.get(fid, 0.0) for fid in member_set)
        score = shared * 2.0 + bridge
        if score <= 0:
            continue
        scored.append(
            {
                "community_id": c.id,
                "name": c.name,
                "size": c.size,
                "shared_facts": shared,
                "bridge_strength": round(bridge, 3),
                "score": round(score, 3),
            }
        )

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# ─────────────────────────────────────────────
# 타임라인
# ─────────────────────────────────────────────
async def community_timeline(community_id: str) -> list[dict]:
    """커뮤니티 구성원을 valid_from 오름차순으로 정렬한 진화 타임라인."""
    comm = await prisma.knowledgecommunity.find_unique(where={"id": community_id})
    if comm is None:
        return []
    facts = await prisma.knowledgefact.find_many(
        where={"id": {"in": comm.factIds}},
        order={"validFrom": "asc"},
    )
    return [
        {
            "fact_id": f.id,
            "valid_from": f.validFrom,
            "entity": f.entity,
            "status": f.status,
            "content_preview": (f.content[:120] + "…") if len(f.content) > 120 else f.content,
        }
        for f in facts
    ]


# ─────────────────────────────────────────────
# 배치 요약 갱신
# ─────────────────────────────────────────────
async def refresh_all_summaries(age_days: int = 7) -> int:
    """최근 `age_days` 내 업데이트된 커뮤니티에 대해 요약 재생성."""
    cutoff = _utcnow() - timedelta(days=age_days)
    comms = await prisma.knowledgecommunity.find_many(
        where={"updatedAt": {"gte": cutoff}},
        take=500,
    )
    updated = 0
    for c in comms:
        try:
            await summarize_community(c.id)
            updated += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("refresh summary failed for %s: %s", c.id, exc)
    logger.info("refresh_all_summaries: %d updated", updated)
    return updated


__all__ = [
    "detect_communities",
    "summarize_community",
    "get_community_for_fact",
    "suggest_related_communities",
    "community_timeline",
    "refresh_all_summaries",
]
