"""Research Engine 엔드포인트.

Group A (수집/파싱) + Group B (요약/트렌드) + Group C (적용/검토) 결과를
관리자 UI 와 내부 트리거에 노출.

엔드포인트:
  - GET  /api/research/papers                      : Paper 목록 (status/score 필터)
  - GET  /api/research/papers/{paper_id}           : Paper 단건 + applications
  - POST /api/research/summarize                   : parsed → summarized 즉시 처리 (internal)
  - POST /api/research/trends/analyze              : 주간 트렌드 즉시 계산 (internal)
  - GET  /api/research/trends                      : 최근 N주 트렌드 조회

Group C — 자동 적용 제안 + 관리자 검토:
  - GET  /api/research/applications                : application 목록 (status 필터)
  - POST /api/research/applications/analyze        : summarized → application 즉시 분석 (internal)
  - POST /api/research/applications/{id}/approve   : 관리자 승인 (GrowthDecision 동기)
  - POST /api/research/applications/{id}/reject    : 관리자 거절 (reason 기록)

Code Engine — 코딩 출처 통합 크롤 + 패턴 추출:
  - POST /api/research/dev/crawl                   : 즉시 코딩 출처 4종 크롤 (internal)
  - POST /api/research/dev/patterns                : 즉시 패턴 추출 LLM 사이클 (internal)
  - GET  /api/research/patterns                    : CodePattern 목록 (language/category 필터)
  - GET  /api/research/patterns/{id}               : CodePattern 단건

Design Engine — 디자인 출처 통합 크롤 + 시각 패턴 추출:
  - POST /api/research/design/crawl                : 즉시 디자인 출처 5종 크롤 (internal)
  - POST /api/research/design/patterns             : 즉시 디자인 패턴 추출 (internal)
  - GET  /api/research/design/patterns             : DesignPattern 목록 (layout/trend 필터)
  - GET  /api/research/design/trends               : 최근 트렌드 키워드 빈도
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from hwarang_api.db import prisma
from hwarang_api.routers.learning import _check_internal_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["Research"])


# Depends 래퍼 — _check_internal_key 는 (Optional[str]) 시그니처라 직접 호출.
def _require_internal_key(authorization: Optional[str] = Header(None)) -> bool:
    _check_internal_key(authorization)
    return True


@router.get("/papers")
async def list_papers(
    status: Optional[str] = Query(None, description="pending|parsed|summarized|applied|rejected"),
    domain: Optional[str] = Query(None, description="(미사용 — 향후 도메인 분류용 예약)"),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=500),
):
    """Paper 목록 조회. 관리자 UI 가 사용."""
    where: dict = {}
    if status:
        where["status"] = status
    if min_score > 0:
        where["applicabilityScore"] = {"gte": min_score}

    try:
        papers = await prisma.paper.find_many(
            where=where,
            order={"publishedAt": "desc"},
            take=limit,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_papers DB 실패: %s", exc)
        return {"papers": [], "error": "db_error"}

    return {"papers": papers, "count": len(papers)}


@router.get("/papers/{paper_id}")
async def get_paper(paper_id: str):
    """Paper 단건 + 연결된 PaperApplication 들."""
    try:
        paper = await prisma.paper.find_unique(where={"id": paper_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_paper DB 실패: %s", exc)
        return JSONResponse({"error": "db_error"}, status_code=500)

    if not paper:
        return JSONResponse({"error": "not_found"}, status_code=404)

    try:
        apps = await prisma.paperapplication.find_many(where={"paperId": paper_id})
    except Exception as exc:  # noqa: BLE001
        logger.debug("paperapplication.find_many 실패: %s", exc)
        apps = []

    return {"paper": paper, "applications": apps}


@router.post("/summarize")
async def trigger_summarize(_: bool = Depends(_require_internal_key)):
    """parsed → summarized 즉시 처리 (cron 안 기다리고 수동 트리거)."""
    from hwarang_api.research.auto_summarizer import summarize_pending_papers

    return await summarize_pending_papers(batch_size=20)


@router.post("/trends/analyze")
async def trigger_trend_analysis(_: bool = Depends(_require_internal_key)):
    """주간 트렌드 즉시 계산 (cron 외 수동 트리거)."""
    from hwarang_api.research.trend_tracker import weekly_trend_analysis

    return await weekly_trend_analysis()


@router.get("/trends")
async def list_trends(
    weeks: int = Query(4, ge=1, le=52),
    only_emerging: bool = Query(False),
):
    """최근 N주 트렌드 조회. 관리자 UI 의 트렌드 보드가 호출."""
    from hwarang_api.research.trend_tracker import get_recent_trends

    trends = await get_recent_trends(weeks, only_emerging)
    return {"trends": trends, "count": len(trends), "weeks": weeks}


# ---------------------------------------------------------------------------
# Group C — Application Engine (논문 → 화랑 적용 자동 제안)
# ---------------------------------------------------------------------------
@router.get("/applications")
async def list_applications(
    status: str = Query("proposed", description="proposed|approved|rejected|implementing|done"),
    limit: int = Query(50, ge=1, le=500),
):
    """PaperApplication 목록 — 관리자 UI 의 검토 보드가 호출."""
    from hwarang_api.research.application_engine import (
        list_pending_applications,
    )

    if status == "proposed":
        apps = await list_pending_applications(limit)
    else:
        try:
            apps = await prisma.paperapplication.find_many(
                where={"status": status},
                take=limit,
                include={"paper": True},
                order={"createdAt": "desc"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("list_applications DB 실패: %s", exc)
            return {"applications": [], "count": 0, "error": "db_error"}
    return {"applications": apps, "count": len(apps), "status": status}


@router.post("/applications/analyze")
async def trigger_application_analyze(
    _: bool = Depends(_require_internal_key),
):
    """summarized → application 즉시 분석 (cron 외 수동 트리거)."""
    from hwarang_api.research.application_engine import (
        analyze_summarized_papers,
    )

    return await analyze_summarized_papers(batch_size=20)


@router.post("/applications/{app_id}/approve")
async def approve_app(
    app_id: str,
    payload: dict,
    _: bool = Depends(_require_internal_key),
):
    """관리자 승인 — 연결된 GrowthDecision 도 approved 로 동기."""
    from hwarang_api.research.application_engine import approve_application

    reviewer = str(payload.get("reviewer") or "admin")
    return await approve_application(app_id, reviewer)


@router.post("/applications/{app_id}/reject")
async def reject_app(
    app_id: str,
    payload: dict,
    _: bool = Depends(_require_internal_key),
):
    """관리자 거절 — reason 을 GrowthDecision.rejectReason 으로 저장."""
    from hwarang_api.research.application_engine import reject_application

    reason = str(payload.get("reason") or "")
    reviewer = str(payload.get("reviewer") or "admin")
    return await reject_application(app_id, reason, reviewer)


# ---------------------------------------------------------------------------
# Code Engine — 코딩 출처 통합 크롤 + 패턴 추출
# ---------------------------------------------------------------------------
@router.post("/dev/crawl")
async def trigger_dev_crawl(_: bool = Depends(_require_internal_key)):
    """즉시 코딩 출처 4종 (GitHub/HN/SO/한국 RSS) 통합 크롤 + HLKM ingest."""
    from hwarang_api.research.dev_source_crawler import daily_dev_crawl

    return await daily_dev_crawl()


@router.post("/dev/patterns")
async def trigger_pattern_extract(
    window_hours: int = Query(6, ge=1, le=72),
    _: bool = Depends(_require_internal_key),
):
    """즉시 최근 ingest 된 code fact 들에서 LLM 패턴 추출."""
    from hwarang_api.research.code_pattern_extractor import (
        extract_patterns_from_recent_facts,
    )

    return await extract_patterns_from_recent_facts(window_hours=window_hours)


@router.get("/patterns")
async def list_code_patterns(
    language: Optional[str] = Query(None, description="javascript|python|rust|..."),
    category: Optional[str] = Query(
        None,
        description="hook|utility|architecture|antipattern|optimization|design_pattern",
    ),
    framework: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """CodePattern 목록. 관리자 UI 의 코드 라이브러리 보드가 호출."""
    where: dict = {}
    if language:
        where["language"] = language
    if category:
        where["category"] = category
    if framework:
        where["framework"] = framework

    try:
        patterns = await prisma.codepattern.find_many(
            where=where,
            order=[{"popularity": "desc"}, {"createdAt": "desc"}],
            take=limit,
        )
    except Exception as exc:  # noqa: BLE001
        # codepattern 모델 prisma generate 안 됐으면 빈 응답
        logger.warning("list_code_patterns DB 실패: %s", exc)
        return {"patterns": [], "count": 0, "error": "db_or_model_missing"}

    return {"patterns": patterns, "count": len(patterns)}


@router.get("/patterns/{pattern_id}")
async def get_code_pattern(pattern_id: str):
    """CodePattern 단건."""
    try:
        pattern = await prisma.codepattern.find_unique(where={"id": pattern_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("get_code_pattern DB 실패: %s", exc)
        return JSONResponse({"error": "db_error"}, status_code=500)

    if not pattern:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return {"pattern": pattern}


# ---------------------------------------------------------------------------
# Design Engine — 디자인 출처 통합 크롤 + 패턴 추출
# ---------------------------------------------------------------------------
@router.post("/design/crawl")
async def trigger_design_crawl(_: bool = Depends(_require_internal_key)):
    """즉시 디자인 출처 5종 (Awwwards/Smashing/CSS-Tricks/한국/shadcn) 크롤."""
    from hwarang_api.research.design_source_crawler import (
        daily_design_crawl,
    )

    return await daily_design_crawl()


@router.post("/design/patterns")
async def trigger_design_pattern_extract(
    window_hours: int = Query(24, ge=1, le=168),
    _: bool = Depends(_require_internal_key),
):
    """즉시 최근 ingest 된 design fact 들에서 LLM 시각 패턴 추출."""
    from hwarang_api.research.design_pattern_extractor import (
        extract_design_patterns,
    )

    return await extract_design_patterns(window_hours=window_hours)


@router.get("/design/patterns")
async def list_design_patterns(
    layout: Optional[str] = Query(
        None, description="hero|grid|split|asymmetric|magazine|fullscreen"
    ),
    trend: Optional[str] = Query(
        None, description="trendKeywords 배열에 포함된 단일 키워드"
    ),
    applicable: Optional[str] = Query(
        None, description="applicableTo 배열의 단일 카테고리 (landing 등)"
    ),
    limit: int = Query(50, ge=1, le=500),
):
    """DesignPattern 목록. 관리자 UI 의 디자인 라이브러리 보드가 호출."""
    where: dict = {}
    if layout:
        where["layoutCategory"] = layout
    if trend:
        where["trendKeywords"] = {"has": trend}
    if applicable:
        where["applicableTo"] = {"has": applicable}

    try:
        patterns = await prisma.designpattern.find_many(
            where=where,
            order=[{"popularity": "desc"}, {"createdAt": "desc"}],
            take=limit,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_design_patterns DB 실패: %s", exc)
        return {
            "patterns": [],
            "count": 0,
            "error": "db_or_model_missing",
        }

    return {"patterns": patterns, "count": len(patterns)}


@router.get("/design/trends")
async def list_design_trends(
    window_hours: int = Query(168, ge=1, le=720),
    limit: int = Query(30, ge=1, le=200),
):
    """최근 N시간 동안 추출된 DesignPattern 의 trendKeywords 빈도 집계."""
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    try:
        patterns = await prisma.designpattern.find_many(
            where={"createdAt": {"gte": cutoff}},
            take=2000,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_design_trends DB 실패: %s", exc)
        return {"trends": [], "error": "db_or_model_missing"}

    counts: dict[str, int] = {}
    for p in patterns:
        for kw in (getattr(p, "trendKeywords", None) or []):
            k = (kw or "").strip().lower()
            if not k:
                continue
            counts[k] = counts.get(k, 0) + 1

    sorted_trends = sorted(counts.items(), key=lambda x: x[1], reverse=True)[
        :limit
    ]
    return {
        "trends": [{"keyword": k, "count": c} for k, c in sorted_trends],
        "window_hours": window_hours,
        "patterns_analyzed": len(patterns),
    }


# ---------------------------------------------------------------------------
# Group C — Tech Trends (코드 + 디자인 주간 트렌드 통합)
# ---------------------------------------------------------------------------
@router.post("/tech-trends/analyze")
async def trigger_tech_trend_analysis(
    _: bool = Depends(_require_internal_key),
):
    """주간 코드/디자인 트렌드 즉시 계산 + LoRA 재학습 제안 자동 생성."""
    from hwarang_api.research.tech_trend_tracker import (
        weekly_tech_trends_full_cycle,
    )

    return await weekly_tech_trends_full_cycle()


@router.get("/tech-trends")
async def list_tech_trends(
    domain: Optional[str] = Query(
        None, description="code | design (없으면 전체)"
    ),
    weeks: int = Query(4, ge=1, le=52),
    only_emerging: bool = Query(False),
):
    """최근 N주 ``TechTrend`` 조회. 관리자 UI 의 코드/디자인 보드가 호출."""
    from hwarang_api.research.tech_trend_tracker import (
        get_recent_tech_trends,
    )

    trends = await get_recent_tech_trends(
        domain=domain, weeks=weeks, only_emerging=only_emerging
    )
    return {
        "trends": trends,
        "count": len(trends),
        "weeks": weeks,
        "domain": domain,
    }


@router.get("/code/patterns/popular")
async def list_popular_code(
    language: Optional[str] = Query(None),
    top: int = Query(20, ge=1, le=200),
):
    """인기 코드 패턴 (popularity desc + 최신순)."""
    from hwarang_api.research.tech_trend_tracker import (
        list_popular_code_patterns,
    )

    patterns = await list_popular_code_patterns(language=language, top=top)
    return {"patterns": patterns, "count": len(patterns)}


@router.get("/design/patterns/popular")
async def list_popular_design(
    layout: Optional[str] = Query(
        None, description="hero|grid|split|asymmetric|magazine|fullscreen"
    ),
    top: int = Query(20, ge=1, le=200),
):
    """인기 디자인 패턴 (popularity desc + 최신순)."""
    from hwarang_api.research.tech_trend_tracker import (
        list_popular_design_patterns,
    )

    patterns = await list_popular_design_patterns(layout=layout, top=top)
    return {"patterns": patterns, "count": len(patterns)}


# ---------------------------------------------------------------------------
# Code Quality Pipeline — 품질/페어/실행 검증
# ---------------------------------------------------------------------------
@router.post("/code/quality/evaluate")
async def trigger_quality_evaluate(
    window_hours: int = Query(24, ge=1, le=168),
    _: bool = Depends(_require_internal_key),
):
    """즉시 최근 code fact 들 품질 평가 (cron 외 수동 트리거)."""
    from hwarang_api.research.quality.code_quality_filter import (
        filter_recent_facts,
    )

    return await filter_recent_facts(window_hours=window_hours)


@router.post("/code/pairs/build")
async def trigger_pair_build(
    limit: int = Query(50, ge=1, le=500),
    _: bool = Depends(_require_internal_key),
):
    """즉시 high_quality fact → CodePair 생성 (LLM)."""
    from hwarang_api.research.quality.code_pair_builder import (
        build_pairs_from_high_quality,
    )

    return await build_pairs_from_high_quality(limit=limit)


@router.post("/code/pairs/execute")
async def trigger_pair_execute(
    batch_size: int = Query(50, ge=1, le=500),
    _: bool = Depends(_require_internal_key),
):
    """즉시 untested CodePair 들 샌드박스 실행 검증."""
    from hwarang_api.research.quality.code_executor import (
        execute_pending_pairs,
    )

    return await execute_pending_pairs(batch_size=batch_size)


@router.post("/code/feedback", include_in_schema=False)
async def code_feedback_alias(payload: dict):
    """``/api/research/code/feedback`` 별칭 — 본 엔드포인트는
    아래 모듈 단위에서 ``/api/code-feedback`` 으로도 노출됨.
    """
    return await _handle_code_feedback(payload)


async def _handle_code_feedback(payload: dict) -> dict:
    """코드 응답 피드백 4 유형 처리 — chat 측에서 호출."""
    from hwarang_api.research.quality.code_rlhf_collector import (
        record_code_feedback,
    )

    user_id = (payload.get("userId") or payload.get("user_id") or "").strip()
    conversation_id = (
        payload.get("conversationId") or payload.get("conversation_id") or ""
    ).strip()
    message_id = (
        payload.get("messageId") or payload.get("message_id") or ""
    ).strip()
    feedback_type = (
        payload.get("feedbackType") or payload.get("feedback_type") or ""
    ).strip()

    missing = [
        k
        for k, v in {
            "userId": user_id,
            "conversationId": conversation_id,
            "messageId": message_id,
            "feedbackType": feedback_type,
        }.items()
        if not v
    ]
    if missing:
        raise HTTPException(400, f"missing fields: {missing}")

    return await record_code_feedback(
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=message_id,
        feedback_type=feedback_type,
        edited_code=payload.get("editedCode") or payload.get("edited_code"),
        error_message=payload.get("errorMessage") or payload.get("error_message"),
    )


@router.get("/code/pairs")
async def list_code_pairs(
    language: Optional[str] = Query(None),
    framework: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(
        None,
        description="untested|passed|failed|timeout|syntax_only|no_code|error",
    ),
    is_used_in_lora: Optional[bool] = Query(None),
    min_quality: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(100, ge=1, le=2000),
):
    """학습용 CodePair export — language/status 등으로 필터.

    LoRA 데이터 빌더가 ``status=passed`` + ``is_used_in_lora=false`` 로 호출.
    """
    where: dict = {}
    if language:
        where["language"] = language
    if framework:
        where["framework"] = framework
    if category:
        where["category"] = category
    if status:
        where["executionStatus"] = status
    if is_used_in_lora is not None:
        where["isUsedInLora"] = is_used_in_lora
    if min_quality > 0:
        where["qualityScore"] = {"gte": min_quality}

    try:
        pairs = await prisma.codepair.find_many(
            where=where,
            order={"createdAt": "desc"},
            take=limit,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_code_pairs DB 실패: %s", exc)
        return {"pairs": [], "count": 0, "error": "db_or_model_missing"}

    return {"pairs": pairs, "count": len(pairs), "filter": where}


# ---------------------------------------------------------------------------
# 사용자 코드 피드백 — chat UI 가 호출하는 별도 prefix 라우터
# ---------------------------------------------------------------------------
feedback_router = APIRouter(prefix="/api", tags=["CodeFeedback"])


@feedback_router.post("/code-feedback")
async def code_feedback(payload: dict):
    """사용자 코드 응답 피드백 (chat UI 가 호출).

    Body::

        {
          "userId": "...",
          "conversationId": "...",
          "messageId": "...",
          "feedbackType": "executed|broken|edited|accepted",
          "editedCode": "(선택) 사용자가 직접 고친 코드",
          "errorMessage": "(선택) 에러 본문"
        }
    """
    return await _handle_code_feedback(payload)


__all__ = ["router", "feedback_router"]
