"""HLKM (Hwarang Living Knowledge Mesh) REST API.

FastAPI 라우터 — 검색, 그래프 순회, 수집/큐레이션, 모순 해결, 예측,
기여 보상, 대시보드 통계, 설정, 관리자 트리거 엔드포인트를 통합 노출한다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from hwarang_api.knowledge import (
    KnowledgeFact,
    SearchQuery,
    SearchResult,
    curate_batch,
    detect_contradiction,
    encrypt_for_user,
    explain_conflict,
    find_related,
    ingest_fact,
    predict_fact_outcome,
    run_daily_verification,
    sync_from_hrag,
    temporal_search,
    time_travel_search,
    traverse_causal_chain,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge")


# ---------------------------------------------------------------------------
# 인증 의존성 (middleware.auth 에 require_admin 이 없으므로 로컬 구현)
# ---------------------------------------------------------------------------
async def require_admin(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """관리자 전용 엔드포인트 가드.

    현재는 ``admin-`` 프리픽스로 시작하는 키만 허용. 운영 환경에서는
    DB 검증 + 스코프 체크로 교체 예정.
    """
    if not x_api_key or not x_api_key.startswith("admin-"):
        raise HTTPException(status_code=401, detail="admin API key required")
    return x_api_key


async def require_user(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """일반 사용자 인증. 비어있지 않으면 통과."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    return x_api_key


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
async def _get_prisma():
    """지연 임포트로 prisma 클라이언트 획득. 실패 시 HTTP 503."""
    try:
        from hwarang_api.db import prisma  # type: ignore

        if hasattr(prisma, "is_connected") and not prisma.is_connected():
            try:
                await prisma.connect()  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=503, detail=f"DB unavailable: {exc}"
                ) from exc
        return prisma
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="prisma not installed") from exc


# ---------------------------------------------------------------------------
# 검색
# ---------------------------------------------------------------------------
@router.post(
    "/search",
    response_model=SearchResult,
    summary="시간 인식 검색",
    description="SearchQuery 를 받아 시간/도메인/가시성 필터를 적용한 검색 결과를 반환.",
)
async def api_search(body: SearchQuery) -> SearchResult:
    try:
        return await temporal_search(body)
    except Exception as exc:  # noqa: BLE001
        logger.exception("search failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/time-travel",
    response_model=SearchResult,
    summary="시간 여행 검색",
    description="특정 시점(as_of) 기준으로 유효했던 사실들을 조회.",
)
async def api_time_travel(
    query: str = Query(..., min_length=1),
    as_of: datetime = Query(...),
    domain: str | None = None,
) -> SearchResult:
    try:
        kwargs: dict[str, Any] = {}
        if domain:
            kwargs["domain"] = domain
        return await time_travel_search(query, as_of, **kwargs)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/entity/{entity}/timeline",
    summary="엔티티 버전 이력",
    description="동일 엔티티 키에 묶인 팩트들의 시간순 버전 체인.",
)
async def api_entity_timeline(entity: str) -> dict:
    prisma = await _get_prisma()
    try:
        rows = await prisma.knowledgefact.find_many(
            where={"entity": entity},
            order={"validFrom": "asc"},
            take=200,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "entity": entity,
        "count": len(rows),
        "versions": [
            {
                "id": r.id,
                "content": r.content,
                "status": r.status,
                "valid_from": r.validFrom.isoformat() if r.validFrom else None,
                "valid_to": r.validTo.isoformat() if r.validTo else None,
                "source": r.source,
                "confidence_t0": float(r.confidenceT0),
                "supersedes_id": r.supersedesId,
            }
            for r in rows
        ],
    }


@router.get(
    "/fact/{fact_id}",
    summary="단일 팩트 상세",
    description="팩트 본문 + 인/아웃 엣지 요약을 함께 반환.",
)
async def api_fact_detail(fact_id: str) -> dict:
    prisma = await _get_prisma()
    row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if row is None:
        raise HTTPException(status_code=404, detail="fact not found")
    out_edges = await prisma.knowledgeedge.find_many(where={"fromFactId": fact_id})
    in_edges = await prisma.knowledgeedge.find_many(where={"toFactId": fact_id})
    return {
        "fact": {
            "id": row.id,
            "content": row.content,
            "domain": row.domain,
            "entity": row.entity,
            "tags": list(row.tags or []),
            "valid_from": row.validFrom.isoformat() if row.validFrom else None,
            "valid_to": row.validTo.isoformat() if row.validTo else None,
            "status": row.status,
            "source": row.source,
            "source_url": row.sourceUrl,
            "confidence_t0": float(row.confidenceT0),
            "half_life_days": row.halfLifeDays,
            "visibility": row.visibility,
        },
        "outgoing": [
            {"id": e.id, "to": e.toFactId, "relation": e.relationType, "strength": float(e.strength)}
            for e in out_edges
        ],
        "incoming": [
            {"id": e.id, "from": e.fromFactId, "relation": e.relationType, "strength": float(e.strength)}
            for e in in_edges
        ],
    }


# ---------------------------------------------------------------------------
# 그래프
# ---------------------------------------------------------------------------
@router.get(
    "/graph/{fact_id}/causal",
    summary="인과 체인 순회",
    description="주어진 팩트에서 CAUSES/ENABLES 관계로 max_depth 만큼 순회.",
)
async def api_graph_causal(fact_id: str, max_depth: int = Query(3, ge=1, le=10)) -> dict:
    try:
        chain = await traverse_causal_chain(fact_id, max_depth=max_depth)
        return {"fact_id": fact_id, "chain": chain}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/graph/{fact_id}/related",
    summary="관련 엣지 조회",
    description="strength ≥ min_strength 인 모든 관계 엣지를 반환.",
)
async def api_graph_related(
    fact_id: str, min_strength: float = Query(0.5, ge=0.0, le=1.0)
) -> dict:
    try:
        edges = await find_related(fact_id, min_strength=min_strength)
        return {
            "fact_id": fact_id,
            "edges": [e.model_dump(mode="json") for e in edges],
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/graph/subgraph",
    summary="시각화용 서브그래프",
    description="쉼표로 구분된 팩트 ID 들을 중심으로 max_hops 홉 서브그래프 구축.",
)
async def api_graph_subgraph(
    fact_ids: str = Query(..., description="comma separated fact ids"),
    max_hops: int = Query(2, ge=1, le=5),
) -> dict:
    from hwarang_api.knowledge.graph import build_subgraph

    ids = [s.strip() for s in fact_ids.split(",") if s.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="fact_ids empty")
    try:
        return await build_subgraph(ids, max_hops=max_hops)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class CounterfactualBody(BaseModel):
    removed_fact_id: str
    target_fact_id: str


@router.post(
    "/graph/counterfactual",
    summary="반사실 질의",
    description="removed_fact_id 가 없었다면 target_fact_id 에 여전히 도달 가능한가?",
)
async def api_graph_counterfactual(body: CounterfactualBody) -> dict:
    from hwarang_api.knowledge.graph import counterfactual_query

    try:
        return await counterfactual_query(body.removed_fact_id, body.target_fact_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# 수집 / 큐레이션 (admin)
# ---------------------------------------------------------------------------
@router.post(
    "/facts/ingest",
    status_code=201,
    summary="팩트 수집",
    description="단일 팩트를 파이프라인에 주입. action ∈ inserted/superseded/disputed/duplicate.",
)
async def api_ingest_fact(
    fact: KnowledgeFact, _: str = Depends(require_admin)
) -> dict:
    try:
        return await ingest_fact(fact)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ingest failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class CurateBatchBody(BaseModel):
    file_path: str
    auto_approve_threshold: float = 0.9


@router.post(
    "/facts/batch/curate",
    summary="배치 큐레이션",
    description="JSONL 파일을 읽어 품질 점수에 따라 자동 승인/검토 큐 분리.",
)
async def api_curate_batch(
    body: CurateBatchBody, _: str = Depends(require_admin)
) -> dict:
    try:
        return await curate_batch(body.file_path, body.auto_approve_threshold)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/facts/pending",
    summary="검토 대기 팩트 목록",
    description="status=PENDING 또는 DISPUTED 상태 팩트.",
)
async def api_facts_pending(
    limit: int = Query(50, ge=1, le=500), _: str = Depends(require_admin)
) -> dict:
    prisma = await _get_prisma()
    rows = await prisma.knowledgefact.find_many(
        where={"status": {"in": ["PENDING", "DISPUTED"]}},
        take=limit,
        order={"createdAt": "desc"},
    )
    return {
        "count": len(rows),
        "facts": [
            {
                "id": r.id,
                "content": r.content[:200],
                "status": r.status,
                "domain": r.domain,
                "source": r.source,
                "created_at": r.createdAt.isoformat() if r.createdAt else None,
            }
            for r in rows
        ],
    }


@router.post(
    "/facts/{fact_id}/approve",
    summary="팩트 승인 (관리자)",
    description="PENDING/DISPUTED → CONFIRMED 전환.",
)
async def api_fact_approve(fact_id: str, _: str = Depends(require_admin)) -> dict:
    prisma = await _get_prisma()
    row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if row is None:
        raise HTTPException(status_code=404, detail="fact not found")
    await prisma.knowledgefact.update(
        where={"id": fact_id},
        data={"status": "CONFIRMED", "lastVerifiedAt": datetime.now(timezone.utc)},
    )
    return {"fact_id": fact_id, "status": "CONFIRMED"}


@router.post(
    "/facts/{fact_id}/reject",
    summary="팩트 반려 (관리자)",
    description="RETRACTED 로 전환하고 supersedes 체인에서 격리.",
)
async def api_fact_reject(fact_id: str, _: str = Depends(require_admin)) -> dict:
    prisma = await _get_prisma()
    row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if row is None:
        raise HTTPException(status_code=404, detail="fact not found")
    await prisma.knowledgefact.update(
        where={"id": fact_id},
        data={"status": "RETRACTED", "validTo": datetime.now(timezone.utc)},
    )
    return {"fact_id": fact_id, "status": "RETRACTED"}


# ---------------------------------------------------------------------------
# 모순
# ---------------------------------------------------------------------------
@router.get(
    "/conflicts",
    summary="모순 사건 목록",
    description="resolutionState 로 필터링. 기본 open.",
)
async def api_conflicts(
    state: str = Query("open"), limit: int = Query(50, ge=1, le=200)
) -> dict:
    prisma = await _get_prisma()
    rows = await prisma.knowledgeconflict.find_many(
        where={"resolutionState": state},
        order={"detectedAt": "desc"},
        take=limit,
    )
    return {
        "count": len(rows),
        "conflicts": [
            {
                "id": c.id,
                "fact_a_id": c.factAId,
                "fact_b_id": c.factBId,
                "state": c.resolutionState,
                "detected_at": c.detectedAt.isoformat() if c.detectedAt else None,
                "note": c.resolutionNote,
            }
            for c in rows
        ],
    }


@router.get(
    "/conflicts/{conflict_id}",
    summary="모순 상세 + LLM 설명",
    description="두 팩트를 대조해 사람이 읽을 수 있는 설명 텍스트 포함.",
)
async def api_conflict_detail(conflict_id: str) -> dict:
    prisma = await _get_prisma()
    row = await prisma.knowledgeconflict.find_unique(where={"id": conflict_id})
    if row is None:
        raise HTTPException(status_code=404, detail="conflict not found")
    try:
        explanation = await explain_conflict(row.factAId, row.factBId)
    except Exception as exc:  # noqa: BLE001
        logger.warning("explain_conflict failed: %s", exc)
        explanation = row.resolutionNote or ""
    return {
        "id": row.id,
        "fact_a_id": row.factAId,
        "fact_b_id": row.factBId,
        "state": row.resolutionState,
        "detected_at": row.detectedAt.isoformat() if row.detectedAt else None,
        "explanation": explanation,
    }


class ResolveBody(BaseModel):
    resolution: Literal["resolved_A", "resolved_B", "coexist", "escalated"]
    note: str = ""


@router.post(
    "/conflicts/{conflict_id}/resolve",
    summary="모순 해결 (관리자)",
    description="관리자가 내린 판정을 기록.",
)
async def api_conflict_resolve(
    conflict_id: str,
    body: ResolveBody,
    admin_key: str = Depends(require_admin),
) -> dict:
    from hwarang_api.knowledge.contradiction import resolve_conflict

    try:
        await resolve_conflict(conflict_id, body.resolution, admin_key, body.note)
        return {"conflict_id": conflict_id, "resolution": body.resolution}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# 예측
# ---------------------------------------------------------------------------
@router.get(
    "/predictions/pending",
    summary="PENDING 예측 목록",
    description="아직 확정되지 않았지만 예측된 발효일이 기록된 사실들.",
)
async def api_predictions_pending(limit: int = Query(50, ge=1, le=500)) -> dict:
    prisma = await _get_prisma()
    rows = await prisma.knowledgefact.find_many(
        where={"status": "PENDING"},
        take=limit,
        order={"predictedValidFrom": "asc"},
    )
    return {
        "count": len(rows),
        "predictions": [
            {
                "fact_id": r.id,
                "content": r.content[:200],
                "predicted_valid_from": r.predictedValidFrom.isoformat()
                if r.predictedValidFrom
                else None,
                "prediction_confidence": r.predictionConfidence,
            }
            for r in rows
        ],
    }


class ConfirmPredictionBody(BaseModel):
    actual_valid_from: datetime | None = None


@router.post(
    "/predictions/{fact_id}/confirm",
    summary="PENDING → CONFIRMED",
)
async def api_prediction_confirm(
    fact_id: str,
    body: ConfirmPredictionBody | None = None,
    _: str = Depends(require_admin),
) -> dict:
    from hwarang_api.knowledge.prediction import transition_pending_to_confirmed

    ts = (body.actual_valid_from if body else None) or datetime.now(timezone.utc)
    try:
        await transition_pending_to_confirmed(fact_id, ts)
        # 예측 정확도에 따라 보상 재계산 가능 (추후 확장)
        return {"fact_id": fact_id, "status": "CONFIRMED", "valid_from": ts.isoformat()}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class ExpirePredictionBody(BaseModel):
    reason: str = "manual_expire"


@router.post(
    "/predictions/{fact_id}/expire",
    summary="PENDING → EXPIRED",
)
async def api_prediction_expire(
    fact_id: str,
    body: ExpirePredictionBody,
    _: str = Depends(require_admin),
) -> dict:
    from hwarang_api.knowledge.prediction import transition_pending_to_expired

    try:
        await transition_pending_to_expired(fact_id, body.reason)
        return {"fact_id": fact_id, "status": "EXPIRED", "reason": body.reason}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# 기여 / 보상
# ---------------------------------------------------------------------------
@router.get(
    "/contributions/leaderboard",
    summary="상위 기여자 리더보드",
    description="최근 N 일 간 보상/품질 기준 상위 기여자.",
)
async def api_contrib_leaderboard(
    days: int = Query(30, ge=1, le=365), limit: int = Query(20, ge=1, le=100)
) -> dict:
    from hwarang_api.knowledge.rewards import get_top_contributors

    try:
        rows = await get_top_contributors(days=days, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"days": days, "entries": rows}


class VoteBody(BaseModel):
    up: bool


@router.post(
    "/contributions/{fact_id}/vote",
    summary="기여 찬반 투표",
)
async def api_contrib_vote(
    fact_id: str, body: VoteBody, user_key: str = Depends(require_user)
) -> dict:
    from hwarang_api.knowledge.rewards import vote_on_contribution

    try:
        await vote_on_contribution(fact_id, user_key, body.up)
        return {"fact_id": fact_id, "vote": "up" if body.up else "down"}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/contributions/user/{user_id}",
    summary="사용자 기여 이력",
)
async def api_contrib_user(
    user_id: str, limit: int = Query(100, ge=1, le=500)
) -> dict:
    prisma = await _get_prisma()
    rows = await prisma.knowledgecontribution.find_many(
        where={"contributorId": user_id},
        order={"acceptedAt": "desc"},
        take=limit,
    )
    total = sum(r.reward for r in rows)
    return {
        "user_id": user_id,
        "total_reward": total,
        "count": len(rows),
        "contributions": [
            {
                "fact_id": r.factId,
                "reward": r.reward,
                "quality": r.qualityScore,
                "uniqueness": r.uniquenessScore,
                "votes_up": r.votesUp,
                "votes_down": r.votesDown,
                "accepted_at": r.acceptedAt.isoformat() if r.acceptedAt else None,
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# 통계 / 대시보드
# ---------------------------------------------------------------------------
@router.get("/stats/overview", summary="전체 현황")
async def api_stats_overview() -> dict:
    prisma = await _get_prisma()
    statuses = ["CONFIRMED", "PENDING", "PREDICTED", "EXPIRED", "RETRACTED", "DISPUTED"]
    by_status: dict[str, int] = {}
    for s in statuses:
        by_status[s] = await prisma.knowledgefact.count(where={"status": s})

    all_rows = await prisma.knowledgefact.find_many(take=5000)
    by_domain: dict[str, int] = {}
    for r in all_rows:
        by_domain[r.domain] = by_domain.get(r.domain, 0) + 1

    since = datetime.now(timezone.utc) - timedelta(days=7)
    recent = await prisma.knowledgefact.count(where={"createdAt": {"gte": since}})
    return {
        "total": sum(by_status.values()),
        "by_status": by_status,
        "by_domain": by_domain,
        "recent_7d": recent,
    }


@router.get("/stats/verification", summary="최근 7일 검증 통계")
async def api_stats_verification() -> dict:
    prisma = await _get_prisma()
    since = datetime.now(timezone.utc) - timedelta(days=7)
    rows = await prisma.knowledgeverification.find_many(
        where={"verifiedAt": {"gte": since}}, take=10000
    )
    counts = {"unchanged": 0, "updated": 0, "invalidated": 0, "source_gone": 0}
    for v in rows:
        counts[v.result] = counts.get(v.result, 0) + 1
    return {"since": since.isoformat(), "total": len(rows), "by_result": counts}


@router.get("/stats/conflicts", summary="모순 현황")
async def api_stats_conflicts() -> dict:
    prisma = await _get_prisma()
    states = ["open", "resolved_A", "resolved_B", "coexist", "escalated"]
    counts = {}
    for s in states:
        counts[s] = await prisma.knowledgeconflict.count(where={"resolutionState": s})
    return {"by_state": counts, "total": sum(counts.values())}


@router.get("/stats/gaps", summary="지식 공백 랭킹")
async def api_stats_gaps(limit: int = Query(20, ge=1, le=100)) -> dict:
    prisma = await _get_prisma()
    rows = await prisma.knowledgegap.find_many(
        where={"status": "open"},
        order={"failureCount": "desc"},
        take=limit,
    )
    return {
        "gaps": [
            {
                "topic": r.topic,
                "failure_count": r.failureCount,
                "first_seen": r.firstSeenAt.isoformat() if r.firstSeenAt else None,
                "last_seen": r.lastSeenAt.isoformat() if r.lastSeenAt else None,
            }
            for r in rows
        ]
    }


@router.get("/stats/health", summary="시스템 헬스")
async def api_stats_health() -> dict:
    from hwarang_api.knowledge.self_verify import detect_aging_facts

    prisma = await _get_prisma()
    try:
        aged = await detect_aging_facts()
    except Exception as exc:  # noqa: BLE001
        logger.warning("aging detect failed: %s", exc)
        aged = []

    broken = await prisma.knowledgeverification.count(where={"result": "source_gone"})
    open_conflicts = await prisma.knowledgeconflict.count(
        where={"resolutionState": "open"}
    )
    now = datetime.now(timezone.utc)
    overdue = await prisma.knowledgefact.count(
        where={"status": "CONFIRMED", "nextCheckAt": {"lte": now}}
    )
    return {
        "aging_facts": len(aged),
        "broken_sources": broken,
        "open_conflicts": open_conflicts,
        "verification_overdue": overdue,
        "checked_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
@router.get("/settings", summary="현재 HLKM 설정 조회")
async def api_settings_get(_: str = Depends(require_admin)) -> dict:
    from hwarang_api.knowledge.settings import get_settings

    s = await get_settings()
    return s.model_dump(mode="json")


@router.put("/settings", summary="HLKM 설정 업데이트")
async def api_settings_put(
    payload: dict[str, Any], _: str = Depends(require_admin)
) -> dict:
    from hwarang_api.knowledge.settings import HLKMSettings, get_settings, save_settings

    current = await get_settings()
    try:
        merged = HLKMSettings(**{**current.model_dump(), **payload})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid settings: {exc}") from exc
    await save_settings(merged)
    return merged.model_dump(mode="json")


# ---------------------------------------------------------------------------
# 관리자 트리거
# ---------------------------------------------------------------------------
@router.post("/admin/verify/run", summary="일일 자가 검증 즉시 실행")
async def api_admin_verify_run(
    limit: int = Query(500, ge=1, le=5000), _: str = Depends(require_admin)
) -> dict:
    try:
        return await run_daily_verification(limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class HragSyncBody(BaseModel):
    domain: Literal["law", "weather", "news"]


@router.post("/admin/hrag/sync", summary="HRAG 동기화 수동 트리거")
async def api_admin_hrag_sync(
    body: HragSyncBody, _: str = Depends(require_admin)
) -> dict:
    try:
        return await sync_from_hrag(body.domain)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/admin/halflife/retrain", summary="반감기 ML 모델 재학습")
async def api_admin_halflife_retrain(_: str = Depends(require_admin)) -> dict:
    from hwarang_api.knowledge.half_life import HalfLifeModel

    try:
        model = HalfLifeModel()
        await model.train()
        return {"status": "trained"}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# 내부 import 의존성 확인용 (lint)
# ---------------------------------------------------------------------------
_ = (
    detect_contradiction,
    predict_fact_outcome,
    encrypt_for_user,
)
