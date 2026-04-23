"""HLKM ⑥ Active Learning Loop.

지식 공백을 자동 탐지·검색·제안·승인하는 루프. 흐름:
질의 클러스터링 → 공백 선언 → web_search → LLM 추출 → JSONL 큐 →
관리자 승인(accept) → ingest_fact → filled, 5회 실패/60일 방치는 abandoned.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import llm_extract_entity_candidates
from hwarang_api.knowledge.pipeline import ingest_fact, record_knowledge_gap
from hwarang_api.knowledge.types import KnowledgeFact, KnowledgeStatus
from hwarang_api.knowledge.web import fetch_and_extract_text, web_search

logger = logging.getLogger(__name__)

_PROPOSAL_DIR = Path(os.getenv("HLKM_GAP_PROPOSAL_DIR", "/tmp/gap_proposals"))
_PROPOSAL_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────
# 내부 유틸
# ──────────────────────────────────────────────
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _proposal_path(gap_id: str) -> Path:
    return _PROPOSAL_DIR / f"{gap_id}.jsonl"


def _load_proposals(gap_id: str) -> list[dict]:
    path = _proposal_path(gap_id)
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _write_proposals(gap_id: str, proposals: list[dict]) -> None:
    path = _proposal_path(gap_id)
    with path.open("w", encoding="utf-8") as f:
        for item in proposals:
            f.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")


def _append_proposals(gap_id: str, proposals: list[dict]) -> None:
    path = _proposal_path(gap_id)
    with path.open("a", encoding="utf-8") as f:
        for item in proposals:
            f.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")


# ──────────────────────────────────────────────
# 클러스터링 (⑥-a)
# ──────────────────────────────────────────────
def cluster_queries(queries: list[dict], threshold: float = 0.85) -> list[list[dict]]:
    """유사한 질의끼리 하나의 버킷으로 묶는다.

    - 임베딩이 동작하면 코사인 유사도 기반으로 클러스터링.
    - embed_text 가 동기적으로 돌지 않으므로 여기서는 간단한 difflib 기반
      문자열 유사도로 대체한다 (평균 O(N^2) 이지만 N<=수백 가정).
    threshold 는 SequenceMatcher ratio 기준 (0~1).
    """
    clusters: list[list[dict]] = []
    seen_texts: list[str] = []
    for q in queries:
        text = (q.get("text") or "").strip().lower()
        if not text:
            continue
        placed = False
        for idx, rep in enumerate(seen_texts):
            ratio = difflib.SequenceMatcher(None, text, rep).ratio()
            if ratio >= threshold:
                clusters[idx].append(q)
                placed = True
                break
        if not placed:
            clusters.append([q])
            seen_texts.append(text)
    return clusters


# ──────────────────────────────────────────────
# 공백 탐지 (⑥-b)
# ──────────────────────────────────────────────
async def detect_new_gaps_from_queries(
    queries: list[dict], failure_threshold: int = 2
) -> list[str]:
    """실패한 질의 로그에서 신규 지식 공백을 탐지·기록한다.

    Args:
        queries: [{"text", "result_count", "user_satisfaction"}, ...]
                 user_satisfaction 는 사용자 피드백에서 얻은 0~1 점수.
        failure_threshold: 클러스터 최소 크기. 이 수치 이상이고
                           평균 만족도 < 0.3 이면 공백 선언.

    Returns:
        새로 생성되었거나 failureCount 가 증가한 공백 topic 목록.
    """
    if not queries:
        return []

    clusters = cluster_queries(queries)
    created_topics: list[str] = []

    for cluster in clusters:
        if len(cluster) < failure_threshold:
            continue
        satis = [float(q.get("user_satisfaction", 0.0)) for q in cluster]
        mean_sat = sum(satis) / len(satis) if satis else 0.0
        result_counts = [int(q.get("result_count", 0)) for q in cluster]
        mean_results = sum(result_counts) / len(result_counts)

        # 만족도가 충분히 낮거나, 결과 수가 0 에 가까우면 공백 후보.
        if not (mean_sat < 0.3 or mean_results < 1.0):
            continue

        # 클러스터 대표 토픽: 가장 짧은 질의 (핵심 키워드 위주).
        topic = min((q.get("text", "") for q in cluster), key=len).strip()
        if not topic:
            continue

        # failureCount 는 클러스터 크기만큼 증가시켜 우선순위 반영.
        for _ in range(len(cluster)):
            await record_knowledge_gap(topic)
        created_topics.append(topic)
        logger.info(
            "gap detected: %r (size=%d, mean_sat=%.2f)", topic, len(cluster), mean_sat
        )

    return created_topics


# ──────────────────────────────────────────────
# 제안 생성 (⑥-c)
# ──────────────────────────────────────────────
async def propose_fact_from_source(
    source_url: str, topic: str
) -> list[KnowledgeFact]:
    """단일 URL 에서 팩트 후보를 뽑아 KnowledgeFact 리스트로 반환.

    LLM 이 엔티티 후보를 뽑고, 본문 앞부분을 각 엔티티와 결합해 사실 문장을 생성.
    content 길이 < 20 이거나 비어있는 후보는 버린다.
    """
    try:
        text = await fetch_and_extract_text(source_url)
    except Exception as exc:
        logger.warning("fetch failed for %s: %s", source_url, exc)
        return []
    if not text or len(text) < 40:
        return []

    snippet = text[:1200]
    entities = await llm_extract_entity_candidates(snippet)
    proposals: list[KnowledgeFact] = []
    now = _utcnow()

    # 엔티티가 하나도 없으면 본문 자체를 하나의 팩트로 (보수적 신뢰도).
    if not entities:
        entities = [topic]

    for ent in entities[:3]:
        content = f"[{topic}] {ent}: {snippet[:400]}".strip()
        if len(content) < 20:
            continue
        # 출처 타입으로 기본 신뢰도 조정.
        is_official = any(
            kw in source_url for kw in (".go.kr", ".gov", "law.go.kr", "assembly.go.kr")
        )
        src_type: Any = "official" if is_official else "crawl"
        confidence = 0.85 if is_official else 0.6

        proposals.append(
            KnowledgeFact(
                content=content,
                domain="general",
                entity=ent,
                tags=[topic],
                valid_from=now,
                source=source_url,
                source_url=source_url,
                source_type=src_type,
                confidence_t0=confidence,
                status=KnowledgeStatus.PENDING,
            )
        )
    return proposals


async def search_for_gap(gap_id: str, max_sources: int = 5) -> dict:
    """공백에 대해 web_search → 각 URL 에서 팩트 후보 추출 → 큐에 적재.

    searchAttempts 를 1 증가시키고 status 를 "proposed" 로 전환한다.
    """
    gap = await prisma.knowledgegap.find_unique(where={"id": gap_id})
    if gap is None:
        raise ValueError(f"gap not found: {gap_id}")

    topic = gap.topic
    results = await web_search(topic, top_k=max_sources)

    candidates: list[dict] = []
    sources_searched = 0

    for r in results:
        url = r.get("url") or ""
        if not url:
            continue
        sources_searched += 1
        try:
            proposals = await propose_fact_from_source(url, topic)
        except Exception as exc:
            logger.warning("propose failed for %s: %s", url, exc)
            continue
        for p in proposals:
            candidates.append(
                {
                    "fact": p.model_dump(mode="json"),
                    "review_status": "pending",
                    "proposed_at": _utcnow().isoformat(),
                    "source_url": url,
                }
            )

    if candidates:
        _append_proposals(gap_id, candidates)
        # 동시에 pipeline 에도 흔적 남겨 중복 집계 방지.
        try:
            await record_knowledge_gap(topic)
        except Exception:
            pass

    new_status = "proposed" if candidates else "searching"
    await prisma.knowledgegap.update(
        where={"id": gap_id},
        data={
            "status": new_status,
            "searchAttempts": (gap.searchAttempts or 0) + 1,
            "lastSearchAt": _utcnow(),
        },
    )

    return {
        "gap_id": gap_id,
        "candidates": len(candidates),
        "sources_searched": sources_searched,
    }


# ──────────────────────────────────────────────
# 스케줄러 (⑥-d)
# ──────────────────────────────────────────────
async def run_daily_gap_loop(max_gaps_per_run: int = 20) -> dict:
    """하루 한 번 돌며 상위 실패 공백들을 검색.

    - searchAttempts > 5 인 것은 자동 abandoned.
    - 그 외에는 failureCount 내림차순으로 최대 max_gaps_per_run 건 처리.
    """
    # 포기 대상 선정
    stale = await prisma.knowledgegap.find_many(
        where={"status": {"in": ["open", "searching"]}, "searchAttempts": {"gt": 5}},
        take=100,
    )
    abandoned = 0
    for g in stale:
        await prisma.knowledgegap.update(
            where={"id": g.id}, data={"status": "abandoned"}
        )
        abandoned += 1

    # 처리 대상
    gaps = await prisma.knowledgegap.find_many(
        where={"status": {"in": ["open", "searching"]}},
        order={"failureCount": "desc"},
        take=max_gaps_per_run,
    )
    processed = 0
    total_candidates = 0
    for g in gaps:
        try:
            res = await search_for_gap(g.id)
            processed += 1
            total_candidates += int(res.get("candidates", 0))
        except Exception as exc:
            logger.warning("search_for_gap failed for %s: %s", g.id, exc)

    return {
        "processed": processed,
        "abandoned": abandoned,
        "total_candidates": total_candidates,
    }


# ──────────────────────────────────────────────
# 관리자 검토 API (⑥-e)
# ──────────────────────────────────────────────
async def list_pending_proposals(gap_id: str | None = None) -> list[dict]:
    """관리자 UI 용: 아직 승인/거부되지 않은 제안 목록."""
    if gap_id is not None:
        items = _load_proposals(gap_id)
        return [
            {**it, "gap_id": gap_id, "index": idx}
            for idx, it in enumerate(items)
            if it.get("review_status") == "pending"
        ]
    out: list[dict] = []
    for path in _PROPOSAL_DIR.glob("*.jsonl"):
        gid = path.stem
        for idx, it in enumerate(_load_proposals(gid)):
            if it.get("review_status") == "pending":
                out.append({**it, "gap_id": gid, "index": idx})
    return out


async def accept_proposal(
    gap_id: str, proposal_json: dict, reviewer_id: str
) -> str:
    """제안을 실제 KnowledgeFact 로 승격."""
    fact_payload = proposal_json.get("fact") or proposal_json
    fact = KnowledgeFact(**fact_payload)
    fact.contributed_by = reviewer_id
    # 관리자가 승인했으므로 CONFIRMED 로 전환.
    fact.status = KnowledgeStatus.CONFIRMED
    if fact.confidence_t0 < 0.7:
        fact.confidence_t0 = 0.75

    result = await ingest_fact(fact)
    fact_id = result.get("fact_id")
    if not fact_id:
        raise RuntimeError(f"ingest_fact 실패: {result}")

    # 제안 파일에서 해당 항목을 accepted 로 표시.
    items = _load_proposals(gap_id)
    for it in items:
        if it.get("fact", {}).get("content") == fact.content:
            it["review_status"] = "accepted"
            it["reviewer_id"] = reviewer_id
            it["fact_id"] = fact_id
            it["reviewed_at"] = _utcnow().isoformat()
            break
    _write_proposals(gap_id, items)

    # 공백 상태 업데이트
    await prisma.knowledgegap.update(
        where={"id": gap_id},
        data={"status": "filled", "filledByFactId": fact_id},
    )
    return fact_id


async def reject_proposal(
    gap_id: str, proposal_index: int, reason: str
) -> None:
    """제안을 거부 표시. 파일에는 유지(감사 로그용)."""
    items = _load_proposals(gap_id)
    if proposal_index < 0 or proposal_index >= len(items):
        raise IndexError(f"proposal_index out of range: {proposal_index}")
    items[proposal_index]["review_status"] = "rejected"
    items[proposal_index]["reject_reason"] = reason
    items[proposal_index]["reviewed_at"] = _utcnow().isoformat()
    _write_proposals(gap_id, items)

    # 남은 pending 이 하나도 없고 accepted 도 없으면 다시 검색 대기 상태로.
    remaining = [
        x for x in items if x.get("review_status") == "pending"
    ]
    has_accepted = any(x.get("review_status") == "accepted" for x in items)
    if not remaining and not has_accepted:
        await prisma.knowledgegap.update(
            where={"id": gap_id}, data={"status": "searching"}
        )


# ──────────────────────────────────────────────
# 청소 (⑥-f)
# ──────────────────────────────────────────────
async def abandon_old_gaps(stale_days: int = 60) -> int:
    """status=searching 상태로 stale_days 이상 성공 없이 방치된 공백을 abandoned 로."""
    cutoff = _utcnow() - timedelta(days=stale_days)
    rows = await prisma.knowledgegap.find_many(
        where={
            "status": {"in": ["searching", "open"]},
            "lastSeenAt": {"lt": cutoff},
        },
        take=500,
    )
    updated = 0
    for r in rows:
        await prisma.knowledgegap.update(
            where={"id": r.id}, data={"status": "abandoned"}
        )
        updated += 1
    return updated


__all__ = [
    "cluster_queries",
    "detect_new_gaps_from_queries",
    "propose_fact_from_source",
    "search_for_gap",
    "run_daily_gap_loop",
    "list_pending_proposals",
    "accept_proposal",
    "reject_proposal",
    "abandon_old_gaps",
]
