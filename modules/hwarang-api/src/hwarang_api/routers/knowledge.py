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


# ===========================================================================
# v2 엔드포인트 — 10대 개선 기능 (XAI / NL / 평판 / 합의 / 커뮤니티 /
# 가설 / 능동학습 / TGNN / 감사 / GDPR)
# ===========================================================================
from hwarang_api.knowledge import (  # noqa: E402
    # XAI (①)
    build_evidence_chain,
    cite_facts_inline,
    compute_question_hash,
    explain_answer_markdown,
    get_saved_evidence,
    # NL Query (③)
    detect_time_range,
    parse_temporal_query,
    # Reputation (④)
    bulk_update_reputations_from_history,
    get_reputation,
    list_reputations,
    penalize_source,
    # Consensus (⑤)
    DOMAIN_CONSENSUS_POLICY,
    evaluate_consensus,
    find_corroborating_facts,
    promote_when_consensus_met,
    # Community (②)
    community_timeline,
    detect_communities,
    summarize_community,
    suggest_related_communities,
    # Hypothesis (⑦)
    auto_accept_high_confidence,
    generate_hypotheses,
    list_pending_hypotheses,
    review_hypothesis,
    # Active Learning (⑥)
    accept_proposal,
    list_pending_proposals,
    reject_proposal,
    run_daily_gap_loop,
    search_for_gap,
    # TGNN (⑧)
    predict_pending_fact_outcome,
    train_tgnn,
    # Audit (⑨)
    audit_trail_for_fact,
    daily_anchor,
    retry_failed_anchors,
    verify_event,
    # GDPR (⑩)
    approve_request,
    list_pending_requests,
    reject_request,
    right_of_access,
    submit_forget_request,
)


# ---------------------------------------------------------------------------
# 공용 헬퍼 (v2 전용)
# ---------------------------------------------------------------------------
def _fact_to_dict(f) -> dict:
    """KnowledgeFact ORM 행을 API 응답용 dict 로 변환."""
    if f is None:
        return {}
    return {
        "id": getattr(f, "id", None),
        "content": getattr(f, "content", None),
        "domain": getattr(f, "domain", None),
        "entity": getattr(f, "entity", None),
        "tags": list(getattr(f, "tags", None) or []),
        "valid_from": f.validFrom.isoformat() if getattr(f, "validFrom", None) else None,
        "valid_to": f.validTo.isoformat() if getattr(f, "validTo", None) else None,
        "status": getattr(f, "status", None),
        "source": getattr(f, "source", None),
        "source_url": getattr(f, "sourceUrl", None),
        "confidence_t0": float(getattr(f, "confidenceT0", 0.0) or 0.0),
        "visibility": getattr(f, "visibility", None),
    }


def _edge_to_dict(e) -> dict:
    """KnowledgeEdge ORM 행을 API 응답용 dict 로 변환."""
    if e is None:
        return {}
    return {
        "id": getattr(e, "id", None),
        "from_fact_id": getattr(e, "fromFactId", None),
        "to_fact_id": getattr(e, "toFactId", None),
        "relation": getattr(e, "relationType", None),
        "strength": float(getattr(e, "strength", 0.0) or 0.0),
        "evidence": getattr(e, "evidence", None),
        "verified_by": getattr(e, "verifiedBy", None),
    }


# ---------------------------------------------------------------------------
# XAI (①) — 근거 사슬 / 설명
# ---------------------------------------------------------------------------
class BuildEvidenceBody(BaseModel):
    question: str
    used_fact_ids: list[str]
    as_of: datetime | None = None
    user_id: str | None = None


@router.post(
    "/evidence/build",
    summary="근거 사슬 생성",
    description="질문과 인용된 팩트 ID 목록을 받아 검증 가능한 근거 사슬을 구축.",
)
async def api_evidence_build(body: BuildEvidenceBody) -> dict:
    if not body.used_fact_ids:
        raise HTTPException(status_code=400, detail="used_fact_ids empty")
    try:
        return await build_evidence_chain(
            body.question,
            body.used_fact_ids,
            as_of=body.as_of,
            user_id=body.user_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("evidence build failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/evidence/{question_hash}",
    summary="저장된 근거 조회",
    description="질문 해시로 저장된 AnswerEvidence 의 최신 레코드를 반환.",
)
async def api_evidence_get(question_hash: str) -> dict:
    try:
        ev = await get_saved_evidence(question_hash)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if ev is None:
        raise HTTPException(status_code=404, detail="evidence not found")
    return ev


class ExplainEvidenceBody(BaseModel):
    evidence: dict[str, Any]


@router.post(
    "/evidence/explain",
    summary="근거 사슬 → 마크다운 설명",
    description="build_evidence_chain 결과 dict 를 사람 친화적 마크다운으로 렌더링.",
)
async def api_evidence_explain(body: ExplainEvidenceBody) -> dict:
    if not body.evidence:
        raise HTTPException(status_code=400, detail="evidence required")
    try:
        md = await explain_answer_markdown(body.evidence)
        return {"markdown": md}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# NL Query (③) — 자연어 → SearchQuery
# ---------------------------------------------------------------------------
class NLParseBody(BaseModel):
    question: str
    current_time: datetime | None = None


@router.post(
    "/nl/parse",
    response_model=SearchQuery,
    summary="자연어 질문을 SearchQuery 로 파싱",
    description="한국어/영어 시간 표현, 도메인/엔티티 힌트를 추출해 SearchQuery 생성.",
)
async def api_nl_parse(body: NLParseBody) -> SearchQuery:
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question empty")
    try:
        return await parse_temporal_query(body.question, body.current_time)
    except Exception as exc:  # noqa: BLE001
        logger.exception("nl parse failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class NLRangeBody(BaseModel):
    text: str
    now: datetime | None = None


@router.post(
    "/nl/range",
    summary="시간 범위 감지",
    description="텍스트에서 '지난주', '2024년 3월부터 6월까지' 같은 범위를 추출.",
)
async def api_nl_range(body: NLRangeBody) -> dict:
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text empty")
    now = body.now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    try:
        span = detect_time_range(body.text, now)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if span is None:
        return {"range": None}
    start, end = span
    return {
        "range": [start.isoformat(), end.isoformat()],
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
    }


# ---------------------------------------------------------------------------
# Source Reputation (④) — admin
# ---------------------------------------------------------------------------
@router.get(
    "/reputation",
    summary="출처 평판 랭킹",
    description="min_facts 이상의 팩트를 가진 출처들을 order_by 기준으로 정렬.",
)
async def api_reputation_list(
    min_facts: int = Query(5, ge=0, le=10000),
    order_by: str = Query("reputation"),
    _: str = Depends(require_admin),
) -> dict:
    try:
        rows = await list_reputations(min_facts=min_facts, order_by=order_by)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"count": len(rows), "sources": rows}


@router.get(
    "/reputation/{source}",
    summary="단일 출처 평판",
    description="평판 점수만 단순 조회. 없으면 기본값(0.7) 반환.",
)
async def api_reputation_single(
    source: str, _: str = Depends(require_admin)
) -> dict:
    try:
        rep = await get_reputation(source)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"source": source, "reputation": float(rep)}


class PenalizeBody(BaseModel):
    reason: str
    magnitude: float = 0.1


@router.post(
    "/reputation/{source}/penalize",
    summary="출처 패널티 적용",
    description="reputation -= magnitude. 0~1 범위로 클램프.",
)
async def api_reputation_penalize(
    source: str, body: PenalizeBody, _: str = Depends(require_admin)
) -> dict:
    if not body.reason:
        raise HTTPException(status_code=400, detail="reason required")
    try:
        new_rep = await penalize_source(source, body.reason, body.magnitude)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"source": source, "new_reputation": float(new_rep), "reason": body.reason}


class BulkUpdateBody(BaseModel):
    days: int = 30


@router.post(
    "/reputation/bulk-update",
    summary="평판 일괄 재집계",
    description="최근 N 일 검증 이력을 재집계하여 EMA 로 평판 갱신.",
)
async def api_reputation_bulk(
    body: BulkUpdateBody, _: str = Depends(require_admin)
) -> dict:
    if body.days < 1 or body.days > 365:
        raise HTTPException(status_code=400, detail="days must be 1..365")
    try:
        result = await bulk_update_reputations_from_history(days=body.days)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "updated": result.get("updated", 0),
        "changed_significantly": [
            {"source": s, "old": o, "new": n}
            for (s, o, n) in result.get("changed_significantly", [])
        ],
    }


# ---------------------------------------------------------------------------
# Consensus (⑤)
# ---------------------------------------------------------------------------
@router.get(
    "/consensus/policy",
    summary="도메인별 합의 정책 조회",
    description="DOMAIN_CONSENSUS_POLICY 원문 반환. (min_sources, require_official 등)",
)
async def api_consensus_policy() -> dict:
    return {"policy": DOMAIN_CONSENSUS_POLICY}


class ConsensusEvaluateBody(BaseModel):
    fact_id: str


@router.post(
    "/consensus/evaluate",
    summary="합의 정책 충족 여부 평가",
    description="특정 팩트에 대해 보강 팩트를 탐색하고 도메인 정책 충족 여부 반환.",
)
async def api_consensus_evaluate(body: ConsensusEvaluateBody) -> dict:
    prisma = await _get_prisma()
    row = await prisma.knowledgefact.find_unique(where={"id": body.fact_id})
    if row is None:
        raise HTTPException(status_code=404, detail="fact not found")
    # ORM 행(camelCase)을 Pydantic KnowledgeFact(snake_case)로 매핑
    try:
        fact = KnowledgeFact(
            id=row.id,
            content=row.content,
            content_hash=getattr(row, "contentHash", None),
            domain=row.domain,
            entity=row.entity,
            tags=list(getattr(row, "tags", None) or []),
            valid_from=row.validFrom or datetime.now(timezone.utc),
            valid_to=row.validTo,
            confidence_t0=float(row.confidenceT0 or 0.7),
            status=row.status,
            source=row.source,
            source_url=row.sourceUrl,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"fact schema mismatch: {exc}"
        ) from exc
    try:
        similar = await find_corroborating_facts(fact)
        result = await evaluate_consensus(fact, similar)
    except Exception as exc:  # noqa: BLE001
        logger.exception("consensus evaluate failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"fact_id": body.fact_id, **result}


@router.post(
    "/consensus/promote-pending",
    summary="합의 충족된 pending 팩트 승격 (관리자)",
    description="AWAITING_CONSENSUS 상태에서 정책 충족한 것을 CONFIRMED 로 일괄 전환.",
)
async def api_consensus_promote(_: str = Depends(require_admin)) -> dict:
    try:
        promoted = await promote_when_consensus_met()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"promoted": int(promoted)}


# ---------------------------------------------------------------------------
# Community (②) — admin
# ---------------------------------------------------------------------------
class DetectCommunityBody(BaseModel):
    algorithm: str = "louvain"
    domain: str | None = None
    min_size: int = 3


@router.post(
    "/communities/detect",
    summary="커뮤니티 탐지 실행 (관리자)",
    description="Louvain/Leiden 알고리즘으로 지식 그래프 커뮤니티 재탐지 → DB 업서트.",
)
async def api_communities_detect(
    body: DetectCommunityBody, _: str = Depends(require_admin)
) -> dict:
    if body.min_size < 1:
        raise HTTPException(status_code=400, detail="min_size must be ≥1")
    try:
        rows = await detect_communities(
            algorithm=body.algorithm,
            domain=body.domain,
            min_size=body.min_size,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("detect_communities failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"count": len(rows), "communities": rows}


@router.get(
    "/communities",
    summary="커뮤니티 목록",
    description="도메인 필터 지원. 크기(size) 내림차순.",
)
async def api_communities_list(
    domain: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    _: str = Depends(require_admin),
) -> dict:
    prisma = await _get_prisma()
    where: dict[str, Any] = {}
    if domain:
        where["domain"] = domain
    rows = await prisma.knowledgecommunity.find_many(
        where=where, order={"size": "desc"}, take=limit
    )
    return {
        "count": len(rows),
        "communities": [
            {
                "community_id": c.id,
                "name": c.name,
                "size": c.size,
                "domain": c.domain,
                "cohesion": float(c.cohesion or 0.0),
                "summary": c.summary,
                "central_fact_id": c.centralFactId,
            }
            for c in rows
        ],
    }


@router.get(
    "/communities/{community_id}",
    summary="커뮤니티 상세 (멤버 팩트 포함)",
    description="커뮤니티 + 멤버 팩트의 간단 정보까지 한 번에 반환.",
)
async def api_community_detail(
    community_id: str, _: str = Depends(require_admin)
) -> dict:
    prisma = await _get_prisma()
    c = await prisma.knowledgecommunity.find_unique(where={"id": community_id})
    if c is None:
        raise HTTPException(status_code=404, detail="community not found")
    member_ids = list(c.factIds or [])
    facts = []
    if member_ids:
        facts_rows = await prisma.knowledgefact.find_many(
            where={"id": {"in": member_ids}}, take=500
        )
        facts = [_fact_to_dict(f) for f in facts_rows]
    return {
        "community_id": c.id,
        "name": c.name,
        "domain": c.domain,
        "size": c.size,
        "cohesion": float(c.cohesion or 0.0),
        "summary": c.summary,
        "central_fact_id": c.centralFactId,
        "members": facts,
    }


@router.post(
    "/communities/{community_id}/summarize",
    summary="커뮤니티 요약 재생성",
    description="LLM 으로 요약을 새로 생성해 DB 저장.",
)
async def api_community_summarize(
    community_id: str, _: str = Depends(require_admin)
) -> dict:
    try:
        summary = await summarize_community(community_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"community_id": community_id, "summary": summary}


@router.get(
    "/communities/{community_id}/timeline",
    summary="커뮤니티 타임라인",
    description="멤버 팩트를 valid_from 오름차순으로 정렬한 진화 기록.",
)
async def api_community_timeline(
    community_id: str, _: str = Depends(require_admin)
) -> dict:
    try:
        items = await community_timeline(community_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"community_id": community_id, "count": len(items), "timeline": items}


@router.get(
    "/communities/{community_id}/related",
    summary="연관 커뮤니티 추천",
    description="크로스-엣지와 공통 멤버 기반 유사 커뮤니티 top-k.",
)
async def api_community_related(
    community_id: str,
    top_k: int = Query(5, ge=1, le=50),
    _: str = Depends(require_admin),
) -> dict:
    try:
        items = await suggest_related_communities(community_id, top_k=top_k)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"community_id": community_id, "related": items}


# ---------------------------------------------------------------------------
# Hypothesis (⑦) — admin
# ---------------------------------------------------------------------------
class GenerateHypothesesBody(BaseModel):
    max_count: int = 20
    confidence_threshold: float = 0.5


@router.post(
    "/hypotheses/generate",
    summary="가설 자동 생성 (관리자)",
    description="2-hop 경로 스캔으로 누락된 전이 관계 가설 제안.",
)
async def api_hypotheses_generate(
    body: GenerateHypothesesBody, _: str = Depends(require_admin)
) -> dict:
    if body.max_count < 1 or body.max_count > 500:
        raise HTTPException(status_code=400, detail="max_count must be 1..500")
    try:
        rows = await generate_hypotheses(
            max_count=body.max_count,
            confidence_threshold=body.confidence_threshold,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("generate_hypotheses failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"count": len(rows), "hypotheses": rows}


@router.get(
    "/hypotheses",
    summary="가설 목록 (pending 기본)",
    description="status + min_confidence + domain 필터.",
)
async def api_hypotheses_list(
    status: str = Query("pending"),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    domain: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    _: str = Depends(require_admin),
) -> dict:
    if status == "pending":
        try:
            rows = await list_pending_hypotheses(
                limit=limit, min_confidence=min_confidence, domain=domain
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"status": "pending", "count": len(rows), "hypotheses": rows}

    # 그 외 상태는 DB 직접 조회
    prisma = await _get_prisma()
    where: dict[str, Any] = {"status": status, "confidence": {"gte": min_confidence}}
    rows = await prisma.knowledgehypothesis.find_many(
        where=where, order={"createdAt": "desc"}, take=limit
    )
    return {
        "status": status,
        "count": len(rows),
        "hypotheses": [
            {
                "hypothesis_id": h.id,
                "statement": h.statement,
                "relation": h.relation,
                "confidence": float(h.confidence),
                "status": h.status,
                "reviewed_by": h.reviewedBy,
                "review_note": h.reviewNote,
            }
            for h in rows
        ],
    }


class ReviewHypothesisBody(BaseModel):
    decision: Literal["accepted", "rejected"]
    note: str | None = None


@router.post(
    "/hypotheses/{hypothesis_id}/review",
    summary="가설 승인/거절 (관리자)",
    description="승인 시 KnowledgeEdge 생성, 거절 시 상태만 업데이트.",
)
async def api_hypothesis_review(
    hypothesis_id: str,
    body: ReviewHypothesisBody,
    admin_key: str = Depends(require_admin),
) -> dict:
    try:
        await review_hypothesis(
            hypothesis_id, admin_key, body.decision, body.note
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"hypothesis_id": hypothesis_id, "decision": body.decision}


class AutoAcceptBody(BaseModel):
    threshold: float = 0.85


@router.post(
    "/hypotheses/auto-accept",
    summary="고신뢰도 가설 자동 승인",
    description="confidence > threshold 인 pending 가설 일괄 승인.",
)
async def api_hypotheses_auto_accept(
    body: AutoAcceptBody, _: str = Depends(require_admin)
) -> dict:
    if body.threshold < 0.5 or body.threshold > 1.0:
        raise HTTPException(status_code=400, detail="threshold must be 0.5..1.0")
    try:
        n = await auto_accept_high_confidence(threshold=body.threshold)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"accepted": int(n), "threshold": body.threshold}


# ---------------------------------------------------------------------------
# Active Learning (⑥) — admin
# ---------------------------------------------------------------------------
@router.post(
    "/gaps/{gap_id}/search",
    summary="공백에 대한 웹 검색 트리거",
    description="web_search → 소스별 팩트 후보 추출 → 제안 큐에 적재.",
)
async def api_gap_search(
    gap_id: str,
    max_sources: int = Query(5, ge=1, le=20),
    _: str = Depends(require_admin),
) -> dict:
    try:
        return await search_for_gap(gap_id, max_sources=max_sources)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("search_for_gap failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/gaps/{gap_id}/proposals",
    summary="공백 제안 목록",
    description="해당 공백에 대해 AI 가 제안한 팩트 후보 목록.",
)
async def api_gap_proposals(
    gap_id: str, _: str = Depends(require_admin)
) -> dict:
    try:
        items = await list_pending_proposals(gap_id=gap_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"gap_id": gap_id, "count": len(items), "proposals": items}


@router.post(
    "/gaps/{gap_id}/proposals/{idx}/accept",
    summary="공백 제안 승인 → 팩트 승격",
    description="제안을 CONFIRMED KnowledgeFact 로 승격하고 gap 상태를 filled 로 전환.",
)
async def api_gap_proposal_accept(
    gap_id: str, idx: int, admin_key: str = Depends(require_admin)
) -> dict:
    try:
        items = await list_pending_proposals(gap_id=gap_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    target = None
    for it in items:
        if it.get("index") == idx:
            target = it
            break
    if target is None:
        raise HTTPException(status_code=404, detail=f"proposal idx {idx} not found")

    try:
        fact_id = await accept_proposal(gap_id, target, admin_key)
    except Exception as exc:  # noqa: BLE001
        logger.exception("accept_proposal failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"gap_id": gap_id, "index": idx, "fact_id": fact_id, "status": "accepted"}


class RejectProposalBody(BaseModel):
    reason: str


@router.post(
    "/gaps/{gap_id}/proposals/{idx}/reject",
    summary="공백 제안 거부",
    description="제안을 rejected 로 표시. 파일은 감사 로그로 유지.",
)
async def api_gap_proposal_reject(
    gap_id: str,
    idx: int,
    body: RejectProposalBody,
    _: str = Depends(require_admin),
) -> dict:
    if not body.reason:
        raise HTTPException(status_code=400, detail="reason required")
    try:
        await reject_proposal(gap_id, idx, body.reason)
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"gap_id": gap_id, "index": idx, "status": "rejected"}


@router.post(
    "/gaps/scan",
    summary="일일 공백 탐색 루프 실행",
    description="실패 빈도 상위 공백들을 순회하며 웹 검색으로 제안 생성.",
)
async def api_gaps_scan(
    max_gaps: int = Query(20, ge=1, le=200),
    _: str = Depends(require_admin),
) -> dict:
    try:
        return await run_daily_gap_loop(max_gaps_per_run=max_gaps)
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_daily_gap_loop failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# TGNN (⑧) — admin
# ---------------------------------------------------------------------------
class TGNNTrainBody(BaseModel):
    impl: Literal["simple", "pyg"] = "simple"


@router.post(
    "/tgnn/train",
    summary="Temporal GNN 학습",
    description="PENDING 팩트 결과 예측용 모델 학습 → 홀드아웃 평가 → 저장.",
)
async def api_tgnn_train(
    body: TGNNTrainBody, _: str = Depends(require_admin)
) -> dict:
    try:
        return await train_tgnn(impl=body.impl)
    except Exception as exc:  # noqa: BLE001
        logger.exception("train_tgnn failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class TGNNPredictBody(BaseModel):
    fact_id: str


@router.post(
    "/tgnn/predict",
    summary="PENDING 팩트 결과 예측",
    description="저장된 TGNN 모델로 확률/예상발효일을 반환.",
)
async def api_tgnn_predict(body: TGNNPredictBody) -> dict:
    try:
        prob, expected = await predict_pending_fact_outcome(body.fact_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("tgnn predict failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "fact_id": body.fact_id,
        "probability": float(prob),
        "expected_date": expected.isoformat() if expected else None,
    }


# ---------------------------------------------------------------------------
# Audit (⑨) — admin
# ---------------------------------------------------------------------------
@router.post(
    "/audit/anchor",
    summary="일일 앵커 수동 실행",
    description="어제 발생한 AuditEvent 들을 merkle root 로 묶어 체인 앵커링.",
)
async def api_audit_anchor(_: str = Depends(require_admin)) -> dict:
    try:
        return await daily_anchor()
    except Exception as exc:  # noqa: BLE001
        logger.exception("daily_anchor failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/audit/retry-failed",
    summary="미앵커링 실패분 재시도",
    description="anchoredAt 이 비어있는 AuditAnchor 들을 체인에 재제출.",
)
async def api_audit_retry(_: str = Depends(require_admin)) -> dict:
    try:
        n = await retry_failed_anchors()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"succeeded": int(n)}


@router.get(
    "/audit/events/{target_id}",
    summary="대상 ID 의 감사 추적",
    description="팩트/요청 ID 에 연결된 이벤트 타임라인 + anchor 정보.",
)
async def api_audit_trail(
    target_id: str, _: str = Depends(require_admin)
) -> dict:
    try:
        rows = await audit_trail_for_fact(target_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"target_id": target_id, "count": len(rows), "events": rows}


@router.post(
    "/audit/verify/{event_id}",
    summary="단일 이벤트 무결성 검증",
    description="DB 재해시 + merkle proof + 체인 앵커 검증.",
)
async def api_audit_verify(
    event_id: str, _: str = Depends(require_admin)
) -> dict:
    try:
        result = await verify_event(event_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not result.get("currently_valid") and not result.get("in_anchor"):
        # 존재하지 않는 이벤트
        raise HTTPException(status_code=404, detail="event not found")
    return result


@router.get(
    "/audit/anchors",
    summary="앵커 목록",
    description="AuditAnchor 최신순 목록 (체인 TX 포함).",
)
async def api_audit_anchors(
    limit: int = Query(30, ge=1, le=200),
    _: str = Depends(require_admin),
) -> dict:
    prisma = await _get_prisma()
    try:
        rows = await prisma.auditanchor.find_many(
            order={"anchorDate": "desc"}, take=limit
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "count": len(rows),
        "anchors": [
            {
                "id": a.id,
                "anchor_date": a.anchorDate.isoformat() if a.anchorDate else None,
                "merkle_root": a.merkleRoot,
                "event_count": int(a.eventCount or 0),
                "chain_tx_hash": a.chainTxHash,
                "chain_block_id": a.chainBlockId,
                "anchored_at": a.anchoredAt.isoformat() if a.anchoredAt else None,
            }
            for a in rows
        ],
    }


# ---------------------------------------------------------------------------
# GDPR (⑩)
# ---------------------------------------------------------------------------
class ForgetRequestBody(BaseModel):
    user_id: str
    scope: Literal["all_private", "contributions", "specific_facts", "all"]
    target_fact_ids: list[str] | None = None
    reason: str | None = None


@router.post(
    "/gdpr/forget-request",
    status_code=201,
    summary="잊힐 권리 요청 제출",
    description="사용자가 직접 제출. scope ∈ all_private/contributions/specific_facts/all.",
)
async def api_gdpr_submit(
    body: ForgetRequestBody, user_key: str = Depends(require_user)
) -> dict:
    if body.scope == "specific_facts" and not body.target_fact_ids:
        raise HTTPException(
            status_code=400, detail="specific_facts scope requires target_fact_ids"
        )
    try:
        req_id = await submit_forget_request(
            body.user_id,
            body.scope,
            target_fact_ids=body.target_fact_ids,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not req_id:
        raise HTTPException(status_code=500, detail="failed to persist request")
    _ = user_key  # 인증만 확인
    return {"request_id": req_id, "status": "pending"}


@router.get(
    "/gdpr/requests",
    summary="잊힐 권리 요청 목록 (관리자)",
    description="status 필터. 기본 pending.",
)
async def api_gdpr_list(
    status: str = Query("pending"), _: str = Depends(require_admin)
) -> dict:
    try:
        rows = await list_pending_requests(status=status)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"status": status, "count": len(rows), "requests": rows}


@router.post(
    "/gdpr/requests/{request_id}/approve",
    summary="요청 승인 + 삭제 실행 (관리자)",
    description="scope 에 따라 crypto-shred / hard delete / anonymize 를 수행하고 보고서 URL 반환.",
)
async def api_gdpr_approve(
    request_id: str, admin_key: str = Depends(require_admin)
) -> dict:
    try:
        result = await approve_request(request_id, admin_key)
    except Exception as exc:  # noqa: BLE001
        logger.exception("gdpr approve failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="request not found")
    if isinstance(result.get("error"), str) and result["error"].startswith("invalid_status"):
        raise HTTPException(status_code=400, detail=result["error"])
    return {"request_id": request_id, **result}


class RejectRequestBody(BaseModel):
    reason: str


@router.post(
    "/gdpr/requests/{request_id}/reject",
    summary="요청 반려 (관리자)",
    description="사유와 함께 반려 상태로 전환. 감사 이벤트 기록.",
)
async def api_gdpr_reject(
    request_id: str,
    body: RejectRequestBody,
    admin_key: str = Depends(require_admin),
) -> dict:
    if not body.reason:
        raise HTTPException(status_code=400, detail="reason required")
    try:
        await reject_request(request_id, admin_key, body.reason)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"request_id": request_id, "status": "rejected"}


@router.get(
    "/gdpr/export/{user_id}",
    summary="접근권 — 사용자 데이터 export",
    description="GDPR Art.15. 사용자 본인 또는 관리자만 호출 가능.",
)
async def api_gdpr_export(
    user_id: str,
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> dict:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    # admin 이거나 user_id 와 동일 키여야 통과. (실 운영에서는 키→userId 매핑 테이블 필요)
    is_admin = x_api_key.startswith("admin-")
    if not is_admin and x_api_key != user_id:
        raise HTTPException(status_code=403, detail="forbidden: not admin nor owner")
    try:
        return await right_of_access(user_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("right_of_access failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# v2 lint keepalive — 공용 헬퍼/상수가 사용되었는지 명시
_ = (
    _fact_to_dict,
    _edge_to_dict,
    compute_question_hash,
    cite_facts_inline,
)


# ===========================================================================
# v3 — Truth Arbitration Layer (TAL) — 진실 판단 엔진
# ① Hierarchy   ② Provenance       ③ Retraction        ④ Primary Source
# ⑤ Claim Decomp ⑥ Stance          ⑦ Counter-Evidence  ⑧ Falsifiability
# ⑨ Arbitrator  (종합 중재)
# ===========================================================================
from hwarang_api.knowledge import (  # noqa: E402
    # ① Hierarchy
    add_hierarchy_rule,
    apply_hierarchy_to_fact,
    bulk_apply_hierarchy,
    deactivate_rule,
    list_rules,
    lookup_authority,
    seed_default_hierarchy,
    update_hierarchy_rule,
    # ② Provenance
    build_propagation_timeline,
    count_independent_sources,
    detect_provenance as _detect_provenance,
    find_original_of,
    list_copies_of,
    scan_and_link_new_fact,
    # ③ Retraction
    cascade_retraction_to_copies,
    list_pending_retractions,
    list_retracted_facts,
    record_retraction,
    run_retraction_scan,
    scan_source_for_retraction,
    undo_retraction,
    verify_retraction,
    # ④ Primary Source
    domain_primary_source_coverage,
    find_better_source,
    promote_primary_in_results,
    rank_facts_by_tier,
    suggest_source_upgrade,
    # ⑤ Claim Decomposition
    aggregate_parent_confidence,
    batch_decompose,
    decompose_fact,
    list_claims_for_fact,
    mark_claim_unverifiable,
    verify_atomic_claim,
    # ⑥ Stance
    apply_stance,
    batch_apply_stance,
    classify_stance,
    find_contested_facts,
    # ⑧ Falsifiability
    apply_falsifiability,
    batch_apply_falsifiability,
    classify_falsifiability,
    list_time_dependent_upcoming,
    list_unfalsifiable,
    # ⑦ Counter-Evidence
    build_balanced_answer,
    detect_echo_chamber,
    find_stance_diverse_facts,
    gather_counter_evidence,
    summarize_perspectives,
    warn_if_minority_view,
    # ⑨ Arbitrator
    arbitrate_answer,
    arbitrated_confidence,
    batch_arbitrate,
    explain_arbitration,
    full_trust_audit,
)


# ---------------------------------------------------------------------------
# v3 공용 헬퍼
# ---------------------------------------------------------------------------
async def _load_fact_pydantic(fact_id: str) -> KnowledgeFact:
    """DB 행 → ``KnowledgeFact`` Pydantic 모델. 없으면 404."""
    prisma = await _get_prisma()
    row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if row is None:
        raise HTTPException(status_code=404, detail="fact not found")
    try:
        return KnowledgeFact(
            id=row.id,
            content=row.content,
            content_hash=getattr(row, "contentHash", None),
            domain=row.domain,
            entity=row.entity,
            tags=list(getattr(row, "tags", None) or []),
            valid_from=row.validFrom or datetime.now(timezone.utc),
            valid_to=row.validTo,
            confidence_t0=float(row.confidenceT0 or 0.7),
            status=row.status,
            source=row.source,
            source_url=row.sourceUrl,
            language=getattr(row, "language", "ko") or "ko",
            half_life_days=getattr(row, "halfLifeDays", None),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500, detail=f"fact schema mismatch: {exc}"
        ) from exc


async def _load_facts_pydantic(fact_ids: list[str]) -> list[KnowledgeFact]:
    """ID 목록 → ``KnowledgeFact`` 리스트. 찾지 못한 ID 는 조용히 건너뜀."""
    if not fact_ids:
        return []
    prisma = await _get_prisma()
    rows = await prisma.knowledgefact.find_many(
        where={"id": {"in": list(fact_ids)}}, take=len(fact_ids)
    )
    out: list[KnowledgeFact] = []
    for r in rows:
        try:
            out.append(
                KnowledgeFact(
                    id=r.id,
                    content=r.content,
                    content_hash=getattr(r, "contentHash", None),
                    domain=r.domain,
                    entity=r.entity,
                    tags=list(getattr(r, "tags", None) or []),
                    valid_from=r.validFrom or datetime.now(timezone.utc),
                    valid_to=r.validTo,
                    confidence_t0=float(r.confidenceT0 or 0.7),
                    status=r.status,
                    source=r.source,
                    source_url=r.sourceUrl,
                    language=getattr(r, "language", "ko") or "ko",
                    half_life_days=getattr(r, "halfLifeDays", None),
                )
            )
        except Exception:  # noqa: BLE001
            logger.debug("skip fact during conversion: %s", getattr(r, "id", None))
    return out


# ---------------------------------------------------------------------------
# ① Hierarchy — 출처 위계 (admin)
# ---------------------------------------------------------------------------
@router.post(
    "/hierarchy/seed",
    summary="기본 위계 시드",
    description="DEFAULT_HIERARCHY 정의를 SourceHierarchyRule 테이블에 삽입. "
                "이미 존재하는 도메인/패턴 쌍은 스킵하고 신규만 등록한다.",
)
async def api_hierarchy_seed(_: str = Depends(require_admin)) -> dict:
    try:
        created = await seed_default_hierarchy()
    except Exception as exc:  # noqa: BLE001
        logger.exception("seed_default_hierarchy failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"created": int(created)}


@router.get(
    "/hierarchy/rules",
    summary="위계 규칙 목록",
    description="도메인/티어로 필터링한 활성 규칙 목록을 반환 (level 오름차순).",
)
async def api_hierarchy_rules_list(
    domain: str | None = None,
    tier: str | None = None,
    _: str = Depends(require_admin),
) -> dict:
    try:
        rows = await list_rules(domain=domain, tier=tier)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"count": len(rows), "rules": rows}


class HierarchyRuleCreateBody(BaseModel):
    domain: str
    level: int
    pattern: str
    tier: str
    authority: float
    note: str | None = None


@router.post(
    "/hierarchy/rules",
    status_code=201,
    summary="위계 규칙 추가",
    description="새 SourceHierarchyRule 삽입. 패턴은 서버에서 regex 컴파일 검증된다.",
)
async def api_hierarchy_rule_create(
    body: HierarchyRuleCreateBody, _: str = Depends(require_admin)
) -> dict:
    if not body.domain or not body.pattern or not body.tier:
        raise HTTPException(status_code=400, detail="domain/pattern/tier required")
    if not (0.0 <= body.authority <= 1.0):
        raise HTTPException(status_code=400, detail="authority must be 0..1")
    try:
        rule_id = await add_hierarchy_rule(
            domain=body.domain,
            level=body.level,
            pattern=body.pattern,
            tier=body.tier,
            authority=body.authority,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"id": rule_id, "status": "created"}


class HierarchyRuleUpdateBody(BaseModel):
    domain: str | None = None
    level: int | None = None
    pattern: str | None = None
    tier: str | None = None
    authority: float | None = None
    note: str | None = None
    active: bool | None = None


@router.patch(
    "/hierarchy/rules/{rule_id}",
    summary="위계 규칙 수정",
    description="주어진 필드만 부분 업데이트. 허용 필드: "
                "domain/level/pattern/tier/authority/note/active.",
)
async def api_hierarchy_rule_update(
    rule_id: str,
    body: HierarchyRuleUpdateBody,
    _: str = Depends(require_admin),
) -> dict:
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="no fields to update")
    try:
        await update_hierarchy_rule(rule_id, **data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"id": rule_id, "updated": list(data.keys())}


@router.post(
    "/hierarchy/rules/{rule_id}/deactivate",
    summary="위계 규칙 비활성화",
    description="active=False 로 soft-disable. 삭제하지 않고 감사 이력을 유지.",
)
async def api_hierarchy_rule_deactivate(
    rule_id: str, _: str = Depends(require_admin)
) -> dict:
    try:
        await deactivate_rule(rule_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"id": rule_id, "active": False}


@router.post(
    "/hierarchy/apply/{fact_id}",
    summary="단일 사실에 위계 적용",
    description="fact 의 source/sourceUrl 로 tier/authority 를 매칭해 DB 업데이트.",
)
async def api_hierarchy_apply(
    fact_id: str, _: str = Depends(require_admin)
) -> dict:
    try:
        result = await apply_hierarchy_to_fact(fact_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not result.get("updated"):
        raise HTTPException(status_code=404, detail="fact not found")
    return result


class HierarchyBulkApplyBody(BaseModel):
    domain: str | None = None
    batch: int = 500


@router.post(
    "/hierarchy/bulk-apply",
    summary="위계 일괄 적용",
    description="도메인 필터를 받아 배치 크기 단위로 모든 사실에 tier/authority 재계산.",
)
async def api_hierarchy_bulk_apply(
    body: HierarchyBulkApplyBody, _: str = Depends(require_admin)
) -> dict:
    if body.batch < 1 or body.batch > 5000:
        raise HTTPException(status_code=400, detail="batch must be 1..5000")
    try:
        return await bulk_apply_hierarchy(domain=body.domain, batch=body.batch)
    except Exception as exc:  # noqa: BLE001
        logger.exception("bulk_apply_hierarchy failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class HierarchyLookupBody(BaseModel):
    source: str
    domain: str


@router.post(
    "/hierarchy/lookup",
    summary="출처 위계 조회",
    description="source(도메인 URL/이름) + domain 로 (tier, authority) 를 반환.",
)
async def api_hierarchy_lookup(
    body: HierarchyLookupBody, _: str = Depends(require_admin)
) -> dict:
    if not body.source or not body.domain:
        raise HTTPException(status_code=400, detail="source/domain required")
    try:
        tier, authority = await lookup_authority(body.source, body.domain)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "source": body.source,
        "domain": body.domain,
        "tier": str(tier),
        "authority": float(authority),
    }


# ---------------------------------------------------------------------------
# ② Provenance — 출처 추적/원본 링크 (admin)
# ---------------------------------------------------------------------------
@router.post(
    "/provenance/scan/{fact_id}",
    summary="신규 사실에 대한 출처 스캔",
    description="같은 entity 범위의 기존 사실들과 비교해 COPY/TRANSLATION/SUMMARY "
                "관계를 감지하고 ProvenanceEdge 로 연결.",
)
async def api_provenance_scan(
    fact_id: str, _: str = Depends(require_admin)
) -> dict:
    fact = await _load_fact_pydantic(fact_id)
    try:
        return await scan_and_link_new_fact(fact, same_entity_only=True)
    except Exception as exc:  # noqa: BLE001
        logger.exception("scan_and_link_new_fact failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/provenance/original/{fact_id}",
    summary="원본 사실 추적",
    description="이 사실이 복사본이라면, 체인을 거슬러 올라간 최종 원본 ID를 반환.",
)
async def api_provenance_original(
    fact_id: str, _: str = Depends(require_admin)
) -> dict:
    try:
        orig = await find_original_of(fact_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"fact_id": fact_id, "original_id": orig}


@router.get(
    "/provenance/copies/{fact_id}",
    summary="복사본 목록",
    description="이 원본을 참조하는 복사본 사실들의 리스트 (type/similarity 포함).",
)
async def api_provenance_copies(
    fact_id: str, _: str = Depends(require_admin)
) -> dict:
    try:
        copies = await list_copies_of(fact_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"original_id": fact_id, "count": len(copies), "copies": copies}


@router.get(
    "/provenance/timeline",
    summary="전파 타임라인",
    description="특정 entity 의 최초 보도 시점과 이후 복사/요약 파생을 시간순 정렬.",
)
async def api_provenance_timeline(
    entity: str = Query(..., min_length=1),
    _: str = Depends(require_admin),
) -> dict:
    try:
        items = await build_propagation_timeline(entity)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"entity": entity, "count": len(items), "timeline": items}


class ProvenanceDetectBody(BaseModel):
    fact_a_id: str
    fact_b_id: str


@router.post(
    "/provenance/detect",
    summary="두 사실의 관계 감지",
    description="임의의 두 사실 사이에 COPY/TRANSLATION/QUOTATION 여부를 평가.",
)
async def api_provenance_detect(
    body: ProvenanceDetectBody, _: str = Depends(require_admin)
) -> dict:
    fa = await _load_fact_pydantic(body.fact_a_id)
    fb = await _load_fact_pydantic(body.fact_b_id)
    try:
        return await _detect_provenance(fa, [fb])
    except Exception as exc:  # noqa: BLE001
        logger.exception("detect_provenance failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# ③ Retraction — 정정/철회
# ---------------------------------------------------------------------------
@router.post(
    "/retraction/scan/{fact_id}",
    summary="사실 정정 자동 감지",
    description="해당 사실의 출처 페이지를 스캔하여 RETRACTED/CORRECTED 패턴을 찾는다.",
)
async def api_retraction_scan(
    fact_id: str, _: str = Depends(require_admin)
) -> dict:
    try:
        result = await scan_source_for_retraction(fact_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("scan_source_for_retraction failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result or {"fact_id": fact_id, "detected": False}


class RetractionRecordBody(BaseModel):
    fact_id: str
    retracted_by: str
    retraction_url: str | None = None
    retraction_type: str
    reason: str


@router.post(
    "/retraction/record",
    status_code=201,
    summary="정정/철회 수동 등록",
    description="관리자가 수동으로 사실을 철회 처리. RetractionEvent + KnowledgeFact 갱신.",
)
async def api_retraction_record(
    body: RetractionRecordBody, _: str = Depends(require_admin)
) -> dict:
    if not body.fact_id or not body.retracted_by or not body.reason:
        raise HTTPException(
            status_code=400, detail="fact_id/retracted_by/reason required"
        )
    try:
        event_id = await record_retraction(
            fact_id=body.fact_id,
            retracted_by=body.retracted_by,
            retraction_url=body.retraction_url,
            retraction_type=body.retraction_type,
            reason=body.reason,
            detected_by="manual",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("record_retraction failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"event_id": event_id, "fact_id": body.fact_id, "status": "retracted"}


class RetractionVerifyBody(BaseModel):
    is_valid: bool


@router.post(
    "/retraction/verify/{retraction_id}",
    summary="정정 이벤트 검증",
    description="is_valid=False 면 해당 사실의 정정을 롤백하고 CONFIRMED 복구.",
)
async def api_retraction_verify(
    retraction_id: str,
    body: RetractionVerifyBody,
    admin_key: str = Depends(require_admin),
) -> dict:
    try:
        await verify_retraction(retraction_id, admin_key, body.is_valid)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"retraction_id": retraction_id, "is_valid": body.is_valid}


@router.post(
    "/retraction/cascade/{original_fact_id}",
    summary="원본 정정 → 복사본 cascade",
    description="이 원본을 참조하는 복사본들에게 정정을 전파. stance=OPINION 은 제외.",
)
async def api_retraction_cascade(
    original_fact_id: str, _: str = Depends(require_admin)
) -> dict:
    try:
        cnt = await cascade_retraction_to_copies(original_fact_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"original_fact_id": original_fact_id, "cascaded": int(cnt)}


@router.post(
    "/retraction/scan-batch",
    summary="일일 정정 스캔 배치",
    description="7일 이상 된 CONFIRMED 사실을 샘플링해 자동 정정 감지를 실행.",
)
async def api_retraction_scan_batch(
    batch: int = Query(100, ge=1, le=2000),
    older_than_days: int = Query(7, ge=1, le=365),
    _: str = Depends(require_admin),
) -> dict:
    try:
        return await run_retraction_scan(batch=batch, older_than_days=older_than_days)
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_retraction_scan failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/retraction/pending",
    summary="검증 대기 정정 목록",
    description="verified=False 인 RetractionEvent (자동 감지 후 검증 대기).",
)
async def api_retraction_pending(
    limit: int = Query(50, ge=1, le=500),
    _: str = Depends(require_admin),
) -> dict:
    try:
        rows = await list_pending_retractions(limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"count": len(rows), "pending": rows}


@router.get(
    "/retraction/list",
    summary="철회된 사실 목록",
    description="retracted=True 인 KnowledgeFact. 도메인 필터 지원.",
)
async def api_retraction_list(
    domain: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    try:
        rows = await list_retracted_facts(domain=domain, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"count": len(rows), "retracted": rows}


class RetractionUndoBody(BaseModel):
    reason: str


@router.post(
    "/retraction/undo/{fact_id}",
    summary="정정 되돌리기",
    description="잘못된 정정을 롤백. retracted=False, status=CONFIRMED 복구.",
)
async def api_retraction_undo(
    fact_id: str,
    body: RetractionUndoBody,
    admin_key: str = Depends(require_admin),
) -> dict:
    if not body.reason:
        raise HTTPException(status_code=400, detail="reason required")
    try:
        await undo_retraction(fact_id, admin_key, body.reason)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"fact_id": fact_id, "status": "undone"}


# ---------------------------------------------------------------------------
# ④ Primary Source — 1차 출처 정책
# ---------------------------------------------------------------------------
@router.get(
    "/primary/rank-facts",
    summary="사실 목록 tier 정렬",
    description="쉼표로 구분한 fact_ids 를 tier × authority × recency 로 재랭킹.",
)
async def api_primary_rank_facts(
    fact_ids: str = Query(..., description="comma separated fact ids"),
) -> dict:
    ids = [s.strip() for s in fact_ids.split(",") if s.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="fact_ids empty")
    facts = await _load_facts_pydantic(ids)
    try:
        ranked = await rank_facts_by_tier(facts)
        promoted = await promote_primary_in_results({"facts": ranked})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "count": len(ranked),
        "primary": [_fact_to_dict(f) for f in promoted.get("primary", [])],
        "secondary": [_fact_to_dict(f) for f in promoted.get("secondary", [])],
        "warnings": promoted.get("warnings", []),
        "ranked": [_fact_to_dict(f) for f in ranked],
    }


class PrimaryCoverageBody(BaseModel):
    domain: str


@router.post(
    "/primary/coverage",
    summary="도메인 1차 출처 커버리지",
    description="해당 도메인에서 PRIMARY_OFFICIAL / PEER_REVIEWED 비율 통계.",
)
async def api_primary_coverage(body: PrimaryCoverageBody) -> dict:
    if not body.domain:
        raise HTTPException(status_code=400, detail="domain required")
    try:
        return await domain_primary_source_coverage(body.domain)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/primary/better-source/{fact_id}",
    summary="더 권위 있는 대체 출처",
    description="같은 entity/domain 에서 더 상위 tier 의 유사 사실 검색.",
)
async def api_primary_better_source(fact_id: str) -> dict:
    fact = await _load_fact_pydantic(fact_id)
    try:
        better = await find_better_source(fact)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if better is None:
        return {"fact_id": fact_id, "better": None}
    return {"fact_id": fact_id, "better": _fact_to_dict(better)}


@router.get(
    "/primary/suggest-upgrade/{fact_id}",
    summary="출처 상향 추천",
    description="도메인별 친화적 메시지와 함께 대체안을 안내.",
)
async def api_primary_suggest_upgrade(fact_id: str) -> dict:
    try:
        result = await suggest_source_upgrade(fact_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if result is None:
        return {"fact_id": fact_id, "suggestion": None}
    return result


# ---------------------------------------------------------------------------
# ⑤ Claim Decomposition — 원자 주장 분해 (admin)
# ---------------------------------------------------------------------------
@router.post(
    "/claims/decompose/{fact_id}",
    summary="사실을 원자 주장으로 분해",
    description="LLM(+regex fallback)으로 긴 사실을 원자적 주장 리스트로 분해.",
)
async def api_claims_decompose(
    fact_id: str, _: str = Depends(require_admin)
) -> dict:
    fact = await _load_fact_pydantic(fact_id)
    try:
        claims = await decompose_fact(fact)
    except Exception as exc:  # noqa: BLE001
        logger.exception("decompose_fact failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"fact_id": fact_id, "count": len(claims), "claims": claims}


@router.post(
    "/claims/{claim_id}/verify",
    summary="원자 주장 검증",
    description="HLKM 검색으로 지지/반박 사실을 찾아 verified/refuted 판정.",
)
async def api_claim_verify(
    claim_id: str, _: str = Depends(require_admin)
) -> dict:
    try:
        result = await verify_atomic_claim(claim_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    # 검증 후 부모 신뢰도 재집계도 트리거
    try:
        prisma = await _get_prisma()
        row = await prisma.decomposedclaim.find_unique(where={"id": claim_id})
        if row is not None:
            await aggregate_parent_confidence(row.parentFactId)
    except Exception as exc:  # noqa: BLE001
        logger.debug("aggregate_parent_confidence skipped: %s", exc)
    return {"claim_id": claim_id, **result}


@router.get(
    "/claims/for-fact/{fact_id}",
    summary="부모 사실의 원자 주장 목록",
    description="DecomposedClaim 테이블에서 parentFactId=fact_id 인 항목을 반환.",
)
async def api_claims_for_fact(
    fact_id: str, _: str = Depends(require_admin)
) -> dict:
    try:
        claims = await list_claims_for_fact(fact_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"fact_id": fact_id, "count": len(claims), "claims": claims}


class ClaimBatchDecomposeBody(BaseModel):
    domain: str | None = None
    limit: int = 50


@router.post(
    "/claims/batch-decompose",
    summary="분해되지 않은 긴 사실 일괄 분해",
    description="isAtomic=True 이면서 200자 초과인 사실을 대상으로 배치 처리.",
)
async def api_claims_batch_decompose(
    body: ClaimBatchDecomposeBody, _: str = Depends(require_admin)
) -> dict:
    if body.limit < 1 or body.limit > 500:
        raise HTTPException(status_code=400, detail="limit must be 1..500")
    try:
        return await batch_decompose(domain=body.domain, limit=body.limit)
    except Exception as exc:  # noqa: BLE001
        logger.exception("batch_decompose failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class ClaimUnverifiableBody(BaseModel):
    reason: str


@router.post(
    "/claims/{claim_id}/unverifiable",
    summary="주장을 검증 불가능 처리",
    description="출처가 사라졌거나 주관적이라 검증 무의미한 경우 unverifiable 로 마크.",
)
async def api_claim_unverifiable(
    claim_id: str,
    body: ClaimUnverifiableBody,
    _: str = Depends(require_admin),
) -> dict:
    if not body.reason:
        raise HTTPException(status_code=400, detail="reason required")
    try:
        await mark_claim_unverifiable(claim_id, body.reason)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"claim_id": claim_id, "status": "unverifiable"}


# ---------------------------------------------------------------------------
# ⑥ Stance — 입장 분류
# ---------------------------------------------------------------------------
@router.post(
    "/stance/classify/{fact_id}",
    summary="사실의 stance 분류 (DB 저장 없음)",
    description="휴리스틱+LLM 로 FACTUAL/INTERPRETATION/OPINION/PROPAGANDA 분류 결과만 반환.",
)
async def api_stance_classify(fact_id: str) -> dict:
    fact = await _load_fact_pydantic(fact_id)
    try:
        stance, confidence = await classify_stance(fact)
    except Exception as exc:  # noqa: BLE001
        logger.exception("classify_stance failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "fact_id": fact_id,
        "stance": stance,
        "confidence": float(confidence),
    }


@router.post(
    "/stance/apply/{fact_id}",
    summary="사실의 stance 판정 후 DB 저장",
    description="classify_stance 결과를 KnowledgeFact.stance/stanceConfidence 로 기록.",
)
async def api_stance_apply(
    fact_id: str, _: str = Depends(require_admin)
) -> dict:
    try:
        return await apply_stance(fact_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("apply_stance failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class StanceBatchBody(BaseModel):
    domain: str | None = None
    limit: int = 200


@router.post(
    "/stance/batch-apply",
    summary="stance 미지정 사실 일괄 분류",
    description="stance=null 인 사실들에 apply_stance 를 일괄 실행.",
)
async def api_stance_batch_apply(
    body: StanceBatchBody, _: str = Depends(require_admin)
) -> dict:
    if body.limit < 1 or body.limit > 2000:
        raise HTTPException(status_code=400, detail="limit must be 1..2000")
    try:
        return await batch_apply_stance(domain=body.domain, limit=body.limit)
    except Exception as exc:  # noqa: BLE001
        logger.exception("batch_apply_stance failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/stance/contested",
    summary="논쟁 중인 사실 검색",
    description="같은 entity 에 FACTUAL 과 OPINION/PROPAGANDA 가 공존하는 경우 반환.",
)
async def api_stance_contested(
    entity: str = Query(..., min_length=1),
) -> dict:
    try:
        items = await find_contested_facts(entity)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"entity": entity, "count": len(items), "contested": items}


# ---------------------------------------------------------------------------
# ⑧ Falsifiability — 반증 가능성
# ---------------------------------------------------------------------------
@router.post(
    "/falsifiability/classify/{fact_id}",
    summary="반증가능성 분류 (DB 저장 없음)",
    description="FALSIFIABLE / UNFALSIFIABLE / TIME_DEPENDENT / VALUE_JUDGMENT / UNCLEAR 중 하나.",
)
async def api_falsifiability_classify(fact_id: str) -> dict:
    fact = await _load_fact_pydantic(fact_id)
    try:
        label = await classify_falsifiability(fact)
    except Exception as exc:  # noqa: BLE001
        logger.exception("classify_falsifiability failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"fact_id": fact_id, "falsifiability": label}


@router.post(
    "/falsifiability/apply/{fact_id}",
    summary="반증가능성 판정 후 DB 저장",
    description="UNFALSIFIABLE/VALUE_JUDGMENT 는 nextCheckAt=NULL 로 세팅되어 재검증 큐에서 제외된다.",
)
async def api_falsifiability_apply(
    fact_id: str, _: str = Depends(require_admin)
) -> dict:
    try:
        return await apply_falsifiability(fact_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("apply_falsifiability failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class FalsifiabilityBatchBody(BaseModel):
    limit: int = 200


@router.post(
    "/falsifiability/batch-apply",
    summary="반증가능성 일괄 분류",
    description="falsifiability=null 인 사실들에 apply_falsifiability 를 실행.",
)
async def api_falsifiability_batch_apply(
    body: FalsifiabilityBatchBody, _: str = Depends(require_admin)
) -> dict:
    if body.limit < 1 or body.limit > 2000:
        raise HTTPException(status_code=400, detail="limit must be 1..2000")
    try:
        return await batch_apply_falsifiability(limit=body.limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/falsifiability/unfalsifiable",
    summary="영속(UNFALSIFIABLE) 사실 목록",
    description="수학 정리 등 반증 자체가 불가능한 사실 — 재검증 스케줄에서 제외된다.",
)
async def api_falsifiability_unfalsifiable(domain: str | None = None) -> dict:
    try:
        rows = await list_unfalsifiable(domain=domain)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"count": len(rows), "facts": rows}


@router.get(
    "/falsifiability/time-dependent",
    summary="시간 종속(TIME_DEPENDENT) 예정 사실",
    description="within_days 이내에 예측 시점이 도래하는 사실 — 자동 재평가 대기열.",
)
async def api_falsifiability_time_dependent(
    within_days: int = Query(90, ge=1, le=365),
) -> dict:
    try:
        rows = await list_time_dependent_upcoming(within_days=within_days)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"within_days": within_days, "count": len(rows), "facts": rows}


# ---------------------------------------------------------------------------
# ⑦ Counter-Evidence — 반대 증거 / 균형 답변
# ---------------------------------------------------------------------------
class CounterGatherBody(BaseModel):
    fact_ids: list[str]
    domain: str | None = None
    top_k: int = 5
    min_tier: str = "SPECIALIZED_MEDIA"


@router.post(
    "/counter/gather",
    summary="반대 증거 수집",
    description="CONTRADICTS 엣지 + 동일 entity 시간중첩 + 임베딩 유사 모순 기반으로 반박 사실 수집.",
)
async def api_counter_gather(body: CounterGatherBody) -> dict:
    if not body.fact_ids:
        raise HTTPException(status_code=400, detail="fact_ids empty")
    if body.top_k < 1 or body.top_k > 50:
        raise HTTPException(status_code=400, detail="top_k must be 1..50")
    facts = await _load_facts_pydantic(body.fact_ids)
    try:
        counters = await gather_counter_evidence(
            facts,
            domain=body.domain,
            top_k=body.top_k,
            min_tier=body.min_tier,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("gather_counter_evidence failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "count": len(counters),
        "counter_evidence": [_fact_to_dict(f) for f in counters],
    }


class CounterBalancedBody(BaseModel):
    question: str
    supporting_ids: list[str]
    opposing_ids: list[str]


@router.post(
    "/counter/balanced",
    summary="균형 답변 번들",
    description="지지/반대 증거를 받아 main_claim + display_mode(consensus/balanced/contested) 를 계산.",
)
async def api_counter_balanced(body: CounterBalancedBody) -> dict:
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question empty")
    supporting = await _load_facts_pydantic(body.supporting_ids)
    opposing = await _load_facts_pydantic(body.opposing_ids)
    try:
        return await build_balanced_answer(body.question, supporting, opposing)
    except Exception as exc:  # noqa: BLE001
        logger.exception("build_balanced_answer failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class CounterEchoBody(BaseModel):
    fact_ids: list[str]


@router.post(
    "/counter/echo-chamber",
    summary="에코 챔버 감지",
    description="주된 사실들이 실제로 독립 출처에 기반하는지 검사 (originalFactId 기반).",
)
async def api_counter_echo(body: CounterEchoBody) -> dict:
    if not body.fact_ids:
        raise HTTPException(status_code=400, detail="fact_ids empty")
    facts = await _load_facts_pydantic(body.fact_ids)
    try:
        return await detect_echo_chamber(facts)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/counter/stance-diverse",
    summary="stance 다양성 버킷",
    description="entity 에 대한 factual/interpretation/opinion/contested 버킷 샘플.",
)
async def api_counter_stance_diverse(
    entity: str = Query(..., min_length=1),
) -> dict:
    try:
        return await find_stance_diverse_facts(entity)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/counter/summarize-perspectives",
    summary="엔티티에 대한 입장 요약",
    description="진보/보수 등 서로 다른 입장을 LLM 으로 중립 요약.",
)
async def api_counter_summarize_perspectives(
    entity: str = Query(..., min_length=1),
) -> dict:
    try:
        summary = await summarize_perspectives(entity)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"entity": entity, "summary": summary}


@router.get(
    "/counter/warn-minority/{fact_id}",
    summary="소수 입장 경고 생성",
    description="해당 사실이 주변 기록 대비 소수 입장인지 판정 후 경고 메시지 반환.",
)
async def api_counter_warn_minority(fact_id: str) -> dict:
    fact = await _load_fact_pydantic(fact_id)
    try:
        result = await warn_if_minority_view(fact)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if result is None:
        return {"fact_id": fact_id, "minority": False, "warning": None}
    return {"fact_id": fact_id, **result}


# ---------------------------------------------------------------------------
# ⑨ Arbitrator — 진실 중재
# ---------------------------------------------------------------------------
@router.post(
    "/arbitrator/compute/{fact_id}",
    summary="단일 사실의 중재 신뢰도 계산",
    description="tier × reputation × independence × stance × falsifiability × retracted 결합.",
)
async def api_arbitrator_compute(fact_id: str) -> dict:
    fact = await _load_fact_pydantic(fact_id)
    try:
        result = await arbitrated_confidence(fact)
    except Exception as exc:  # noqa: BLE001
        logger.exception("arbitrated_confidence failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"fact_id": fact_id, **result}


class ArbitratorBatchBody(BaseModel):
    domain: str | None = None
    limit: int = 500


@router.post(
    "/arbitrator/batch",
    summary="CONFIRMED 사실 arbitrated_score 일괄 재계산",
    description="도메인 필터 지원. 결과에 처리/실패/평균점수 포함.",
)
async def api_arbitrator_batch(
    body: ArbitratorBatchBody, _: str = Depends(require_admin)
) -> dict:
    if body.limit < 1 or body.limit > 10000:
        raise HTTPException(status_code=400, detail="limit must be 1..10000")
    try:
        return await batch_arbitrate(domain=body.domain, limit=body.limit)
    except Exception as exc:  # noqa: BLE001
        logger.exception("batch_arbitrate failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class ArbitratorAnswerBody(BaseModel):
    question: str
    fact_ids: list[str]


@router.post(
    "/arbitrator/answer",
    summary="질의 종합 중재",
    description="검색 결과 사실들을 재랭킹 + 반대 증거 + echo-chamber + verdict 를 포함한 답변.",
)
async def api_arbitrator_answer(body: ArbitratorAnswerBody) -> dict:
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question empty")
    if not body.fact_ids:
        raise HTTPException(status_code=400, detail="fact_ids empty")
    facts = await _load_facts_pydantic(body.fact_ids)
    try:
        return await arbitrate_answer(body.question, facts)
    except Exception as exc:  # noqa: BLE001
        logger.exception("arbitrate_answer failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/arbitrator/explain/{fact_id}",
    summary="중재 계산 설명 (마크다운)",
    description="arbitrated_confidence 내부 계산을 한국어 마크다운으로 리포트.",
)
async def api_arbitrator_explain(fact_id: str) -> dict:
    try:
        md = await explain_arbitration(fact_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("explain_arbitration failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"fact_id": fact_id, "markdown": md}


@router.get(
    "/arbitrator/audit/{fact_id}",
    summary="TAL 전체 감사 리포트",
    description="hierarchy / provenance / reputation / stance / falsifiability / retraction / "
                "claims / counter-evidence / breakdown / verdict / recommendations 를 한 번에 반환.",
)
async def api_arbitrator_audit(fact_id: str) -> dict:
    try:
        result = await full_trust_audit(fact_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("full_trust_audit failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="fact not found")
    return result


# v3 lint keepalive
_ = (
    _detect_provenance,
    count_independent_sources,
    find_original_of,
    list_copies_of,
)


# ===========================================================================
# v3.1 TAL 확장 — 외부 정정 DB / 언론사 정정 스크래퍼 / 편향 / 멀티모달 / 교차언어
# ===========================================================================
# 모든 import 는 이 섹션 상단에서만 이루어지며, 위의 v1/v2/v3 섹션은 수정하지 않는다.
from hwarang_api.knowledge.external_retraction import (  # noqa: E402
    seed_providers as _er_seed_providers,
    query_retraction_watch as _er_query_retraction_watch,
    query_snopes as _er_query_snopes,
    query_factcheck_snu as _er_query_factcheck_snu,
    query_all_providers as _er_query_all_providers,
    sync_provider as _er_sync_provider,
    sync_all_providers as _er_sync_all_providers,
    list_providers as _er_list_providers,
    update_provider as _er_update_provider,
    deactivate_provider as _er_deactivate_provider,
)
from hwarang_api.knowledge.press_correction_scraper import (  # noqa: E402
    scrape_correction_page as _ps_scrape_correction_page,
    scrape_press_arbitration as _ps_scrape_press_arbitration,
    scrape_kpcc_official as _ps_scrape_kpcc_official,
    run_full_press_scan as _ps_run_full_press_scan,
)
from hwarang_api.knowledge.bias_detection import (  # noqa: E402
    seed_media_bias_profiles as _bd_seed_media_bias_profiles,
    detect_bias as _bd_detect_bias,
    batch_detect_bias as _bd_batch_detect_bias,
    find_balanced_perspective as _bd_find_balanced_perspective,
    warn_echo_chamber_by_bias as _bd_warn_echo_chamber_by_bias,
    get_bias_profile as _bd_get_bias_profile,
    list_media_bias_profiles as _bd_list_media_bias_profiles,
    update_media_bias_profile as _bd_update_media_bias_profile,
)
from hwarang_api.knowledge.multimodal import (  # noqa: E402
    register_media_fact as _mm_register_media_fact,
    process_media as _mm_process_media,
    find_similar_media as _mm_find_similar_media,
    detect_deepfake_heuristic as _mm_detect_deepfake_heuristic,
    media_fact_summary as _mm_media_fact_summary,
    list_suspect_media as _mm_list_suspect_media,
    scan_media_for_copies as _mm_scan_media_for_copies,
)
from hwarang_api.knowledge.cross_lingual import (  # noqa: E402
    detect_language as _xl_detect_language,
    detect_translation_pair as _xl_detect_translation_pair,
    register_translation as _xl_register_translation,
    find_original_across_languages as _xl_find_original_across_languages,
    find_translations_of as _xl_find_translations_of,
    scan_new_fact_for_translation as _xl_scan_new_fact_for_translation,
    trace_translation_chain as _xl_trace_translation_chain,
    detect_back_translation as _xl_detect_back_translation,
    unified_entity_across_languages as _xl_unified_entity_across_languages,
    detect_foreign_wire_origin as _xl_detect_foreign_wire_origin,
    translation_stats as _xl_translation_stats,
    list_potential_back_translations as _xl_list_potential_back_translations,
)


# ---------------------------------------------------------------------------
# ① 외부 정정 DB 연동 — Retraction Watch / Snopes / FactCheck SNU / ...
# ---------------------------------------------------------------------------
@router.post(
    "/external-retraction/providers/seed",
    summary="기본 외부 정정 제공자 시드",
    description="DEFAULT_PROVIDERS 목록(RetractionWatch/Snopes/SNU FactCheck 등)을 DB 에 upsert.",
)
async def api_er_seed_providers(_: str = Depends(require_admin)) -> dict:
    try:
        inserted = await _er_seed_providers()
    except Exception as exc:  # noqa: BLE001
        logger.exception("seed_providers failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"inserted": inserted}


@router.get(
    "/external-retraction/providers",
    summary="외부 정정 제공자 목록",
    description="등록된 ExternalRetractionSource 목록을 반환 (active_only 필터 지원).",
)
async def api_er_list_providers(
    active_only: bool = Query(True),
) -> dict:
    try:
        rows = await _er_list_providers(active_only=active_only)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"count": len(rows), "providers": rows}


class ExternalRetractionUpdateBody(BaseModel):
    baseUrl: str | None = None
    apiKey: str | None = None
    syncIntervalHours: int | None = None
    active: bool | None = None
    domain: str | None = None


@router.post(
    "/external-retraction/providers/{name}/update",
    summary="외부 정정 제공자 업데이트",
    description="지정한 provider 의 baseUrl/apiKey/syncIntervalHours/active/domain 부분 업데이트.",
)
async def api_er_update_provider(
    name: str,
    body: ExternalRetractionUpdateBody,
    _: str = Depends(require_admin),
) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="no fields to update")
    try:
        await _er_update_provider(name, **updates)
    except Exception as exc:  # noqa: BLE001
        logger.exception("update_provider failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"provider": name, "updated": list(updates.keys())}


@router.post(
    "/external-retraction/providers/{name}/deactivate",
    summary="외부 정정 제공자 비활성화",
    description="active=false 로 전환. 이후 sync/query 루프에서 제외된다.",
)
async def api_er_deactivate_provider(
    name: str, _: str = Depends(require_admin)
) -> dict:
    try:
        await _er_deactivate_provider(name)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"provider": name, "active": False}


class ExternalRetractionQueryBody(BaseModel):
    fact_id: str


@router.post(
    "/external-retraction/query",
    summary="단일 사실 외부 정정 질의",
    description="주어진 fact 에 대해 활성 제공자 전체를 병렬 질의 (Retraction Watch DOI 매칭 등).",
)
async def api_er_query(body: ExternalRetractionQueryBody) -> dict:
    if not body.fact_id.strip():
        raise HTTPException(status_code=400, detail="fact_id empty")
    fact = await _load_fact_pydantic(body.fact_id)
    try:
        hits = await _er_query_all_providers(fact)
    except Exception as exc:  # noqa: BLE001
        logger.exception("query_all_providers failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"fact_id": body.fact_id, "count": len(hits), "hits": hits}


@router.post(
    "/external-retraction/sync/{provider_name}",
    summary="단일 제공자 동기화",
    description="해당 제공자의 배치 동기화 실행. 후보 사실과 매칭해 retraction 기록을 자동 삽입.",
)
async def api_er_sync_provider(
    provider_name: str,
    batch_size: int = Query(50, ge=1, le=500),
    _: str = Depends(require_admin),
) -> dict:
    try:
        return await _er_sync_provider(provider_name, batch_size=batch_size)
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_provider failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/external-retraction/sync-all",
    summary="전체 제공자 동기화",
    description="활성 제공자 전체를 순차 동기화. 각 제공자별 결과를 취합해 반환.",
)
async def api_er_sync_all(_: str = Depends(require_admin)) -> dict:
    try:
        return await _er_sync_all_providers()
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_all_providers failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# ② 언론사 정정 스크래퍼 — Korean Press Correction Scraper
# ---------------------------------------------------------------------------
@router.post(
    "/press-scraper/scan/{outlet}",
    summary="특정 언론사 정정 페이지 스크래핑",
    description="KOREAN_PRESS_CORRECTION_PAGES 의 outlet 키 (예: chosun, donga, press_arbitration 등).",
)
async def api_ps_scan_outlet(
    outlet: str, _: str = Depends(require_admin)
) -> dict:
    try:
        if outlet == "press_arbitration":
            items = await _ps_scrape_press_arbitration()
        elif outlet == "kpcc":
            items = await _ps_scrape_kpcc_official()
        else:
            items = await _ps_scrape_correction_page(outlet)
    except Exception as exc:  # noqa: BLE001
        logger.exception("press scraper scan failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"outlet": outlet, "count": len(items), "items": items}


@router.post(
    "/press-scraper/scan-arbitration",
    summary="언론중재위원회 시정권고/반론보도 스크래핑",
    description="PAC 공지사항 리스트 기반. 키워드: 시정권고/반론보도/정정보도/직권조정/심의결정.",
)
async def api_ps_scan_arbitration(_: str = Depends(require_admin)) -> dict:
    try:
        items = await _ps_scrape_press_arbitration()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"count": len(items), "items": items}


@router.post(
    "/press-scraper/scan-all",
    summary="전체 언론사 정정 스캔 + 자동 반영",
    description="모든 outlet 병렬 스크래핑 → fact 매칭 → retraction 기록. 결과 통계 반환.",
)
async def api_ps_scan_all(
    similarity_threshold: float = Query(0.7, ge=0.0, le=1.0),
    _: str = Depends(require_admin),
) -> dict:
    try:
        return await _ps_run_full_press_scan(similarity_threshold=similarity_threshold)
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_full_press_scan failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# ③ 정치 편향 감지 — Bias Detection
# ---------------------------------------------------------------------------
@router.post(
    "/bias/seed-profiles",
    summary="기본 언론사 편향 프로필 시드",
    description="SEED_MEDIA_BIAS_PROFILES 를 MediaBiasProfile 테이블에 upsert.",
)
async def api_bd_seed_profiles(_: str = Depends(require_admin)) -> dict:
    try:
        inserted = await _bd_seed_media_bias_profiles()
    except Exception as exc:  # noqa: BLE001
        logger.exception("seed_media_bias_profiles failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"inserted": inserted}


@router.get(
    "/bias/profiles",
    summary="언론사 편향 프로필 목록",
    description="등록된 MediaBiasProfile 전체 조회 (biasScore/biasLabel/factualityRating 포함).",
)
async def api_bd_list_profiles() -> dict:
    try:
        rows = await _bd_list_media_bias_profiles()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"count": len(rows), "profiles": rows}


@router.get(
    "/bias/profiles/{outlet}",
    summary="특정 언론사 편향 프로필",
    description="정확한 outlet 이름 또는 URL 일부로 매칭 (extract_outlet_from_source 내부 사용).",
)
async def api_bd_get_profile(outlet: str) -> dict:
    try:
        row = await _bd_get_bias_profile(outlet)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="profile not found")
    return row


class BiasProfileUpdateBody(BaseModel):
    biasScore: float | None = None
    biasLabel: str | None = None
    factualityRating: str | None = None
    biasSource: str | None = None
    notes: str | None = None


@router.post(
    "/bias/profiles/{outlet}/update",
    summary="언론사 편향 프로필 수동 업데이트",
    description="AllSides/MBFC 외 자체 검증 결과를 반영. 비어 있는 필드는 무시.",
)
async def api_bd_update_profile(
    outlet: str,
    body: BiasProfileUpdateBody,
    _: str = Depends(require_admin),
) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="no fields to update")
    try:
        await _bd_update_media_bias_profile(outlet, **updates)
    except Exception as exc:  # noqa: BLE001
        logger.exception("update_media_bias_profile failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"outlet": outlet, "updated": list(updates.keys())}


@router.post(
    "/bias/detect/{fact_id}",
    summary="단일 사실 편향 감지",
    description="출처 → 어휘 → LLM 순으로 단계별 감지. 결과를 BiasDetection + KnowledgeFact 에 반영.",
)
async def api_bd_detect(fact_id: str) -> dict:
    fact = await _load_fact_pydantic(fact_id)
    try:
        return await _bd_detect_bias(fact)
    except Exception as exc:  # noqa: BLE001
        logger.exception("detect_bias failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class BiasBatchBody(BaseModel):
    domain: str | None = "politics"
    limit: int = 200


@router.post(
    "/bias/batch",
    summary="편향 라벨 일괄 감지",
    description="biasLabel 이 비어있는 정치 도메인 사실을 일괄 분류. limit 1~2000.",
)
async def api_bd_batch(
    body: BiasBatchBody, _: str = Depends(require_admin)
) -> dict:
    if body.limit < 1 or body.limit > 2000:
        raise HTTPException(status_code=400, detail="limit must be 1..2000")
    try:
        return await _bd_batch_detect_bias(
            domain=body.domain or "politics", limit=body.limit
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("batch_detect_bias failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/bias/balanced-perspective",
    summary="편향 스펙트럼 별 관점 정리",
    description="같은 entity 에 대해 progressive/centrist/conservative/mixed 버킷(최대 5건씩) 반환.",
)
async def api_bd_balanced(
    entity: str = Query(..., min_length=1),
) -> dict:
    try:
        return await _bd_find_balanced_perspective(entity)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class BiasEchoBody(BaseModel):
    fact_ids: list[str]


@router.post(
    "/bias/warn-echo-chamber",
    summary="편향 에코 체임버 경고",
    description="여러 근거 fact 의 biasLabel 이 한쪽으로 80% 이상 쏠렸는지 검사.",
)
async def api_bd_warn_echo(body: BiasEchoBody) -> dict:
    if not body.fact_ids:
        raise HTTPException(status_code=400, detail="fact_ids empty")
    try:
        res = await _bd_warn_echo_chamber_by_bias(body.fact_ids)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if res is None:
        return {"echo_chamber": False, "warning": None}
    return {"echo_chamber": True, **res}


# ---------------------------------------------------------------------------
# ④ 멀티모달 사실 — Multimodal (image/video/audio/document)
# ---------------------------------------------------------------------------
class MediaRegisterBody(BaseModel):
    fact_id: str
    media_url: str
    media_type: str  # IMAGE | VIDEO | AUDIO | DOCUMENT


@router.post(
    "/media/register",
    summary="미디어 사실 등록",
    description="MediaFact 레코드 생성 후 백그라운드에서 perceptual hash/OCR/딥페이크 점수 계산을 큐잉.",
)
async def api_mm_register(body: MediaRegisterBody) -> dict:
    if not body.fact_id.strip() or not body.media_url.strip():
        raise HTTPException(status_code=400, detail="fact_id/media_url required")
    try:
        return await _mm_register_media_fact(
            body.fact_id, body.media_url, body.media_type
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("register_media_fact failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/media/process/{media_fact_id}",
    summary="미디어 수동 분석",
    description="해당 MediaFact 를 동기 분석 (다운로드 → pHash/dHash/OCR/딥페이크 점수 → DB 업데이트).",
)
async def api_mm_process(
    media_fact_id: str, _: str = Depends(require_admin)
) -> dict:
    try:
        return await _mm_process_media(media_fact_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("process_media failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/media/similar/{phash}",
    summary="pHash 유사 미디어 검색",
    description="해밍 거리 ≤ max_distance 인 MediaFact 를 반환. 기본 10.",
)
async def api_mm_similar(
    phash: str,
    max_distance: int = Query(10, ge=0, le=64),
) -> dict:
    try:
        rows = await _mm_find_similar_media(phash, max_distance=max_distance)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"phash": phash, "count": len(rows), "similar": rows}


@router.get(
    "/media/suspect",
    summary="딥페이크 의심 미디어 목록",
    description="deepfakeScore 가 임계값 이상인 MediaFact 를 점수 내림차순으로 반환.",
)
async def api_mm_suspect(
    min_deepfake_score: float = Query(0.6, ge=0.0, le=1.0),
    _: str = Depends(require_admin),
) -> dict:
    try:
        rows = await _mm_list_suspect_media(min_deepfake_score=min_deepfake_score)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"threshold": min_deepfake_score, "count": len(rows), "items": rows}


@router.get(
    "/media/summary/{fact_id}",
    summary="사실 + 미디어 조인 요약",
    description="KnowledgeFact 와 MediaFact 를 조인해 pHash/OCR/전사/manipulationFlags 를 한 번에 반환.",
)
async def api_mm_summary(fact_id: str) -> dict:
    try:
        res = await _mm_media_fact_summary(fact_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if res.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="fact/media not found")
    return res


@router.post(
    "/media/scan-copies/{media_fact_id}",
    summary="미디어 복사본 탐지",
    description="대상 MediaFact 의 pHash 기준으로 유사 미디어를 찾아 provenance(MEDIA_COPY) 로 기록.",
)
async def api_mm_scan_copies(media_fact_id: str) -> dict:
    try:
        rows = await _mm_scan_media_for_copies(media_fact_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("scan_media_for_copies failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"media_fact_id": media_fact_id, "count": len(rows), "copies": rows}


# ---------------------------------------------------------------------------
# ⑤ 교차 언어 원본 추적 — Cross-lingual Provenance
# ---------------------------------------------------------------------------
class XLingualDetectLangBody(BaseModel):
    text: str


@router.post(
    "/xlingual/detect-language",
    summary="텍스트 언어 감지",
    description="한중일 + 영어/유럽어를 문자 분포 기반으로 탐지 (ko/en/ja/zh/mixed 등).",
)
async def api_xl_detect_language(body: XLingualDetectLangBody) -> dict:
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="text empty")
    try:
        lang = _xl_detect_language(body.text)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"language": lang}


class XLingualPairBody(BaseModel):
    fact_a_id: str
    fact_b_id: str


@router.post(
    "/xlingual/detect-translation-pair",
    summary="두 사실의 번역 관계 판정",
    description="언어/임베딩 유사도/시간순/방법을 분석해 is_translation 과 원문/번역본 방향 반환.",
)
async def api_xl_detect_pair(body: XLingualPairBody) -> dict:
    if body.fact_a_id == body.fact_b_id:
        raise HTTPException(status_code=400, detail="fact_a_id and fact_b_id must differ")
    fa = await _load_fact_pydantic(body.fact_a_id)
    fb = await _load_fact_pydantic(body.fact_b_id)
    try:
        res = await _xl_detect_translation_pair(fa, fb)
    except Exception as exc:  # noqa: BLE001
        logger.exception("detect_translation_pair failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    # 번역이면 TranslationLink 기록 (best-effort).
    if res.get("is_translation"):
        try:
            link_id = await _xl_register_translation(
                source_fact_id=res["source_fact"],
                target_fact_id=res["target_fact"],
                source_lang=res["source_lang"],
                target_lang=res["target_lang"],
                method=res.get("method", "unknown"),
                confidence=float(res.get("confidence", 0.0)),
                similarity=float(res.get("similarity", 0.0)),
            )
            res["link_id"] = link_id
        except Exception as exc:  # noqa: BLE001
            logger.debug("register_translation skip: %s", exc)
    return res


@router.post(
    "/xlingual/scan/{fact_id}",
    summary="신규 사실 번역 관계 자동 스캔",
    description="같은 entity + 다른 언어 후보와 비교해 번역 관계를 탐지하고 TranslationLink 기록.",
)
async def api_xl_scan(fact_id: str) -> dict:
    fact = await _load_fact_pydantic(fact_id)
    try:
        res = await _xl_scan_new_fact_for_translation(fact)
    except Exception as exc:  # noqa: BLE001
        logger.exception("scan_new_fact_for_translation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if res is None:
        return {"fact_id": fact_id, "is_translation": False}
    return {"fact_id": fact_id, **res}


@router.get(
    "/xlingual/original-across-langs/{fact_id}",
    summary="교차 언어 원본 추정",
    description="같은 entity, 다른 언어, 더 이른 발행일 후보 중 임베딩 유사도가 가장 높은 원본 반환.",
)
async def api_xl_original_across(
    fact_id: str,
    candidate_langs: str | None = Query(None, description="쉼표 구분 목록. 예: 'ko,en'"),
) -> dict:
    langs = (
        [c.strip() for c in candidate_langs.split(",") if c.strip()]
        if candidate_langs
        else None
    )
    try:
        original = await _xl_find_original_across_languages(fact_id, candidate_langs=langs)
    except Exception as exc:  # noqa: BLE001
        logger.exception("find_original_across_languages failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if original is None:
        return {"fact_id": fact_id, "original": None}
    return {
        "fact_id": fact_id,
        "original": {
            "id": original.id,
            "content": original.content,
            "domain": original.domain,
            "entity": original.entity,
            "language": original.language,
            "source": original.source,
            "source_url": original.source_url,
            "valid_from": original.valid_from.isoformat() if original.valid_from else None,
        },
    }


@router.get(
    "/xlingual/translations-of/{fact_id}",
    summary="원문에 대한 번역본 목록",
    description="해당 fact 를 원문으로 삼는 TranslationLink + 번역본 fact 정보.",
)
async def api_xl_translations_of(fact_id: str) -> dict:
    try:
        rows = await _xl_find_translations_of(fact_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"fact_id": fact_id, "count": len(rows), "translations": rows}


@router.get(
    "/xlingual/chain/{fact_id}",
    summary="번역 체인 추적",
    description="translatedFromFactId 를 따라 최상위 원본 → 현재 → 모든 자손 번역본 시간순 나열.",
)
async def api_xl_chain(fact_id: str) -> dict:
    try:
        rows = await _xl_trace_translation_chain(fact_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("trace_translation_chain failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"fact_id": fact_id, "length": len(rows), "chain": rows}


@router.get(
    "/xlingual/back-translation/{fact_id}",
    summary="역번역(한→영→한 등) 감지",
    description="체인 언어 패턴이 A-B-A 형태이고 의미 왜곡(drift>0.2) 이 크면 warning=True.",
)
async def api_xl_back_translation(fact_id: str) -> dict:
    try:
        res = await _xl_detect_back_translation(fact_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if res is None:
        return {"fact_id": fact_id, "is_back_translation": False}
    return {"fact_id": fact_id, "is_back_translation": True, **res}


@router.get(
    "/xlingual/unified-entity",
    summary="엔티티 다국어 통합 뷰",
    description="동일 entity 의 ko/en/ja/zh 등 언어별 사실을 묶어 primary_lang/original_found 표시.",
)
async def api_xl_unified_entity(
    entity: str = Query(..., min_length=1),
) -> dict:
    try:
        return await _xl_unified_entity_across_languages(entity)
    except Exception as exc:  # noqa: BLE001
        logger.exception("unified_entity_across_languages failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/xlingual/wire-origin/{fact_id}",
    summary="외신 전재 감지",
    description="한국어 기사에서 외신 통신사 패턴을 찾거나, 영어 원문과의 교차 매칭으로 전재 여부 판정.",
)
async def api_xl_wire_origin(fact_id: str) -> dict:
    fact = await _load_fact_pydantic(fact_id)
    try:
        res = await _xl_detect_foreign_wire_origin(fact)
    except Exception as exc:  # noqa: BLE001
        logger.exception("detect_foreign_wire_origin failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if res is None:
        return {"fact_id": fact_id, "is_foreign_wire": False}
    return {"fact_id": fact_id, **res}


@router.get(
    "/xlingual/stats",
    summary="번역 링크 통계",
    description="TranslationLink 전체 혹은 domain 필터 기준으로 언어쌍/방법별 카운트 반환.",
)
async def api_xl_stats(
    domain: str | None = Query(None),
) -> dict:
    try:
        base = await _xl_translation_stats(domain=domain)
        back = await _xl_list_potential_back_translations(limit=50)
    except Exception as exc:  # noqa: BLE001
        logger.exception("translation_stats failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {**base, "potential_back_translations": back}


# v3.1 lint keepalive
_ = (
    _er_query_retraction_watch,
    _er_query_snopes,
    _er_query_factcheck_snu,
    _mm_detect_deepfake_heuristic,
)
