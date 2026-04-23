"""HLKM A2 - Temporal Search.

시간 인식 검색. `as_of_date` 기준 유효한 팩트만 반환하며,
카테고리 반감기에 따른 현재 신뢰도 감쇠를 적용한다.

외부에서 사용할 주요 진입점:
    - temporal_search(query): 풀 검색
    - time_travel_search(query, as_of): 특정 시점 검색 (편의)
    - search_by_entity(entity): 엔티티 버전 히스토리
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any

from hwarang_api.db import prisma
from hwarang_api.knowledge.embeddings import embed_text
from hwarang_api.knowledge.half_life import current_confidence
from hwarang_api.knowledge.types import (
    KnowledgeFact,
    KnowledgeRelation,
    KnowledgeStatus,
    KnowledgeVisibility,
    SearchQuery,
    SearchResult,
)

# pgvector 확장 존재 여부는 런타임에 한번만 감지.
_PGVECTOR_PROBED: bool | None = None


def _cosine_distance_sql() -> str:
    """pgvector 의 cosine distance 연산자 SQL 조각.

    예: `embedding <=> $1::vector` — 0에 가까울수록 유사.
    pgvector 미설치 환경에서는 별도 Python fallback 을 사용.
    """
    return "embedding <=> $1::vector"


def _cosine(a: list[float], b: list[float]) -> float:
    """순수 Python 코사인 유사도 (fallback)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _row_to_fact(row: Any) -> KnowledgeFact:
    """Prisma row 또는 dict 를 Pydantic 모델로 변환."""
    d = row if isinstance(row, dict) else row.model_dump()
    return KnowledgeFact(
        id=d.get("id"),
        content=d.get("content", ""),
        content_hash=d.get("contentHash") or d.get("content_hash"),
        embedding=None,  # 결과에 벡터는 실지 않음
        domain=d.get("domain", "general"),
        entity=d.get("entity"),
        tags=d.get("tags", []) or [],
        language=d.get("language", "ko"),
        valid_from=d.get("validFrom") or d.get("valid_from"),
        valid_to=d.get("validTo") or d.get("valid_to"),
        created_at=d.get("createdAt") or d.get("created_at"),
        last_verified_at=d.get("lastVerifiedAt") or d.get("last_verified_at"),
        next_check_at=d.get("nextCheckAt") or d.get("next_check_at"),
        confidence_t0=float(d.get("confidenceT0", d.get("confidence_t0", 1.0))),
        half_life_days=d.get("halfLifeDays") or d.get("half_life_days"),
        status=KnowledgeStatus(d.get("status", "CONFIRMED")),
        predicted_valid_from=d.get("predictedValidFrom"),
        prediction_confidence=d.get("predictionConfidence"),
        expired_reason=d.get("expiredReason"),
        source=d.get("source", ""),
        source_url=d.get("sourceUrl") or d.get("source_url"),
        source_type=d.get("sourceType", d.get("source_type", "user")),
        visibility=KnowledgeVisibility(d.get("visibility", "PUBLIC")),
        owner_user_id=d.get("ownerUserId") or d.get("owner_user_id"),
        supersedes_id=d.get("supersedesId") or d.get("supersedes_id"),
        contributed_by=d.get("contributedBy") or d.get("contributed_by"),
        reward_paid=int(d.get("rewardPaid", d.get("reward_paid", 0))),
    )


def _visibility_filter(query: SearchQuery) -> dict[str, Any]:
    """Public + (옵션) 본인 private 팩트만 노출."""
    if query.include_private and query.user_id:
        return {
            "OR": [
                {"visibility": "PUBLIC"},
                {"AND": [{"visibility": "PRIVATE"}, {"ownerUserId": query.user_id}]},
            ]
        }
    return {"visibility": "PUBLIC"}


async def temporal_search(query: SearchQuery) -> SearchResult:
    """시간 인식 검색.

    1) `as_of_date` 시점에 유효한 팩트만 (valid_from ≤ as_of < valid_to)
    2) 도메인/가시성 필터
    3) 임베딩 유사도 상위 N 선별
    4) 반감기 기반 현재 신뢰도 계산 + 임계치 필터
    5) 상위 결과 사이의 CONTRADICTS 엣지를 모아 반환
    """
    started = time.perf_counter()
    as_of = query.as_of_date or datetime.now(timezone.utc)

    q_vec = await embed_text(query.query)

    where: dict[str, Any] = {
        "validFrom": {"lte": as_of},
        "OR": [{"validTo": None}, {"validTo": {"gt": as_of}}],
    }
    if query.domain:
        where["domain"] = query.domain
    where.update(_visibility_filter(query))

    if not query.include_predicted:
        where["status"] = {"in": ["CONFIRMED", "PENDING"]}

    # 후보를 넉넉히 로드한 뒤 Python 단에서 벡터 정렬 (pgvector 없어도 동작).
    candidates = await prisma.knowledgefact.find_many(
        where=where, take=max(query.limit * 8, 50)
    )

    scored: list[tuple[float, KnowledgeFact, float]] = []
    for row in candidates:
        fact = _row_to_fact(row)
        emb_hex = getattr(row, "embeddingHex", None)
        emb = _hex_to_floats(emb_hex) if emb_hex else None
        sim = _cosine(q_vec, emb) if emb else 0.0
        # 반감기 감쇠
        conf = current_confidence(
            confidence_t0=fact.confidence_t0,
            created_at=fact.created_at or as_of,
            half_life_days=fact.half_life_days,
            as_of=as_of,
        )
        if conf < query.min_confidence:
            continue
        scored.append((sim, fact, conf))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[: query.limit]

    facts = [f for _, f, _ in top]
    confidences = [c for _, _, c in top]

    contradictions: list[tuple[str, str]] = []
    ids = [f.id for f in facts if f.id]
    if len(ids) >= 2:
        edges = await prisma.knowledgeedge.find_many(
            where={
                "relationType": KnowledgeRelation.CONTRADICTS.value,
                "fromFactId": {"in": ids},
                "toFactId": {"in": ids},
            }
        )
        seen: set[tuple[str, str]] = set()
        for e in edges:
            a, b = sorted((e.fromFactId, e.toFactId))
            if (a, b) not in seen:
                contradictions.append((a, b))
                seen.add((a, b))

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return SearchResult(
        facts=facts,
        current_confidences=confidences,
        contradictions=contradictions,
        as_of_date=as_of,
        query_time_ms=elapsed_ms,
    )


async def time_travel_search(query: str, as_of: datetime, **kw: Any) -> SearchResult:
    """특정 시점 기준 검색 편의 함수."""
    sq = SearchQuery(query=query, as_of_date=as_of, **kw)
    return await temporal_search(sq)


async def search_by_entity(
    entity: str, user_id: str | None = None
) -> list[KnowledgeFact]:
    """엔티티의 모든 버전을 시간 역순으로 반환 (히스토리)."""
    where: dict[str, Any] = {"entity": entity}
    if user_id:
        where["OR"] = [
            {"visibility": "PUBLIC"},
            {"AND": [{"visibility": "PRIVATE"}, {"ownerUserId": user_id}]},
        ]
    else:
        where["visibility"] = "PUBLIC"

    rows = await prisma.knowledgefact.find_many(
        where=where, order={"validFrom": "desc"}
    )
    return [_row_to_fact(r) for r in rows]


def _hex_to_floats(hex_str: str | None) -> list[float] | None:
    """embeddingHex(float32 little-endian hex) → list[float].

    DB 에 pgvector 가 없을 때 텍스트로 저장하는 백업 포맷을 역직렬화.
    """
    if not hex_str:
        return None
    try:
        import struct

        raw = bytes.fromhex(hex_str)
        count = len(raw) // 4
        if count == 0:
            return None
        return list(struct.unpack(f"<{count}f", raw))
    except Exception:
        return None
