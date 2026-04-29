"""HSEE Phase 1 라우터.

엔드포인트:
- ``POST /api/learning/on-chat``  : 채팅 응답 직후 4 루프 트리거 (Next.js 가 호출)
- ``POST /api/learning/feedback`` : 사용자 명시 피드백 (👍/👎)
- ``GET  /api/learning/stats``    : 도메인/라우팅 통계 (관리자/디버그)
- ``GET  /api/learning/triggers`` : 자동 트리거 상태
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from hwarang_api.learning import (
    ChatContext,
    extract_and_ingest_facts,
    get_domain_quality,
    on_chat_response,
    record_explicit_feedback,
)
from hwarang_api.learning.auto_trigger import trigger_status
from hwarang_api.learning.routing_stats import list_all_domain_quality

# Phase 2 — Online Continual Learning
from hwarang_api.learning.auto_trainer import (
    maybe_enqueue_training,
    process_queue,
    training_jobs_status,
)
from hwarang_api.learning.replay_buffer import replay_buffer_stats
from hwarang_api.learning.training_state import (
    cancel_job,
    get_job,
    list_jobs,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/learning", tags=["Learning/HSEE"])

INTERNAL_KEY_ENV = "HWARANG_INTERNAL_KEY"

# create_task 가 GC 되지 않도록 강한 레퍼런스 유지
_pending_tasks: set[asyncio.Task] = set()


def _check_internal_key(authorization: Optional[str]) -> None:
    """``/learning/on-chat`` 처럼 내부 호출 전용 엔드포인트 보호.

    환경변수 ``HWARANG_INTERNAL_KEY`` 가 비어 있으면 검사 생략(개발 편의).
    """
    expected = os.getenv(INTERNAL_KEY_ENV, "").strip()
    if not expected:
        return  # 미설정 시 모두 허용 (개발 모드)

    if not authorization:
        raise HTTPException(401, "Missing internal key")
    token = authorization.strip()
    if token.startswith("Bearer "):
        token = token[7:].strip()
    if token != expected:
        raise HTTPException(401, "Invalid internal key")


# ────────────────────────────────────────────────────────────
# /on-chat — Next.js 가 응답 직후 fire-and-forget 호출
# ────────────────────────────────────────────────────────────
class OnChatPayload(BaseModel):
    user_id: str
    user_message: str
    response: str
    domain: str = "general"
    model_name: str = "unknown"

    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    lora_name: Optional[str] = None
    latency_ms: int = 0
    quality_score: Optional[float] = None
    is_kyc_verified: bool = False

    # 클라이언트가 가진 즉시 신호 (있다면)
    followup_msg: Optional[str] = None
    rating: Optional[int] = Field(None, ge=-1, le=1)
    edit_distance: Optional[float] = None

    # 동기 vs 비동기 — true 면 4 루프 결과까지 기다림 (테스트용)
    wait: bool = False


@router.post("/on-chat")
async def on_chat(
    payload: OnChatPayload,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """채팅 응답 직후 4 루프 트리거.

    기본은 fire-and-forget: 즉시 ``{"queued": True}`` 반환.
    ``wait=true`` 면 4 루프 모두 완료까지 기다린 결과를 반환 (테스트/디버그).
    """
    _check_internal_key(authorization)

    ctx = ChatContext(
        user_id=payload.user_id,
        user_message=payload.user_message,
        response=payload.response,
        domain=payload.domain,
        model_name=payload.model_name,
        conversation_id=payload.conversation_id,
        message_id=payload.message_id,
        lora_name=payload.lora_name,
        latency_ms=payload.latency_ms,
        quality_score=payload.quality_score,
        is_kyc_verified=payload.is_kyc_verified,
        followup_msg=payload.followup_msg,
        rating=payload.rating,
        edit_distance=payload.edit_distance,
    )

    if payload.wait:
        result = await on_chat_response(ctx)
        return {"queued": False, "result": result}

    task = asyncio.create_task(_safe_run(ctx))
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)
    return {"queued": True, "domain": ctx.domain, "model": ctx.model_name}


async def _safe_run(ctx: ChatContext) -> None:
    try:
        await on_chat_response(ctx)
    except Exception as e:  # pragma: no cover
        logger.warning(f"on_chat_response 백그라운드 실패: {e}")


# ────────────────────────────────────────────────────────────
# /feedback — 사용자 명시 피드백
# ────────────────────────────────────────────────────────────
class FeedbackPayload(BaseModel):
    message_id: str
    user_id: str
    rating: int = Field(..., ge=-1, le=1)
    comment: Optional[str] = None


@router.post("/feedback")
async def submit_feedback(payload: FeedbackPayload) -> dict[str, Any]:
    """사용자 명시 피드백 (👍/👎) — KYC 무관, 로그인된 누구나."""
    return await record_explicit_feedback(
        user_id=payload.user_id,
        message_id=payload.message_id,
        rating=payload.rating,
        comment=payload.comment,
    )


# ────────────────────────────────────────────────────────────
# /stats — 라우팅 통계 조회
# ────────────────────────────────────────────────────────────
@router.get("/stats")
async def routing_stats(
    domain: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=24 * 14),
) -> dict[str, Any]:
    """도메인 만족도/라우팅 통계.

    ``domain`` 지정 시 모델별 breakdown, 미지정 시 모든 도메인 요약.
    """
    if domain:
        return await get_domain_quality(domain, hours=hours)
    return {"hours": hours, "domains": await list_all_domain_quality(hours=hours)}


# ────────────────────────────────────────────────────────────
# /triggers — 자동 트리거 상태
# ────────────────────────────────────────────────────────────
@router.get("/triggers")
async def triggers() -> dict[str, Any]:
    """현재 트리거 임계치 + 도메인별 마지막 발화 시각."""
    return await trigger_status()


# ────────────────────────────────────────────────────────────
# /extract — 단발 사실 추출 (디버그/관리자)
# ────────────────────────────────────────────────────────────
class ExtractPayload(BaseModel):
    response: str
    domain: str = "general"


@router.post("/extract")
async def extract_only(payload: ExtractPayload) -> dict[str, Any]:
    """응답에서 사실 추출만 시험. ingest 까지 진행."""
    return await extract_and_ingest_facts(payload.response, domain=payload.domain)


# ────────────────────────────────────────────────────────────
# Phase 2 — Online Continual Learning 엔드포인트
# ────────────────────────────────────────────────────────────
class EnqueueTrainingPayload(BaseModel):
    domain: str
    triggered_by: Optional[str] = "manual"


@router.post("/training/enqueue")
async def training_enqueue(
    payload: EnqueueTrainingPayload,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """RLHFFeedback 누적이 임계치를 넘으면 TrainingJob 을 큐에 push.

    auto_trainer.maybe_enqueue_training 의 HTTP 래퍼.
    내부 키 보호 (관리자/스케줄러 호출).
    """
    _check_internal_key(authorization)
    return await maybe_enqueue_training(
        domain=payload.domain,
        triggered_by=payload.triggered_by or "manual",
    )


@router.post("/training/process")
async def training_process(
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """워커가 호출 — queued 잡 1 개를 골라서 학습 실행.

    응답 시간이 매우 길 수 있으므로 (몇 분~수 시간), 호출자는
    워커 컨테이너 또는 cron 작업이어야 한다.
    """
    _check_internal_key(authorization)
    return await process_queue()


@router.get("/training/jobs")
async def training_jobs(
    status: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    """잡 목록. status / domain 필터."""
    items = await list_jobs(status=status, domain=domain, limit=limit)
    return {"count": len(items), "items": items}


@router.get("/training/jobs/{job_id}")
async def training_job_detail(job_id: str) -> dict[str, Any]:
    """잡 상세."""
    job = await get_job(job_id)
    if not job:
        raise HTTPException(404, f"job not found: {job_id}")
    return job


@router.post("/training/cancel/{job_id}")
async def training_cancel(
    job_id: str,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """잡 취소 — queued 만 안전, running 은 cancel flag 만 표시."""
    _check_internal_key(authorization)
    return await cancel_job(job_id)


@router.get("/training/status")
async def training_status() -> dict[str, Any]:
    """전체 학습 큐 + 임계치 요약 (관리자 대시보드용)."""
    return await training_jobs_status()


@router.get("/training/replay/stats")
async def training_replay_stats(
    domain: Optional[str] = Query(None),
) -> dict[str, Any]:
    """ReplaySample 버퍼 크기 등."""
    return await replay_buffer_stats(domain=domain)


# ────────────────────────────────────────────────────────────
# Phase 3 — Self-Growing Architecture
# ────────────────────────────────────────────────────────────
from hwarang_api.learning import (
    auto_spawn as _auto_spawn,
    capability_monitor as _cap,
    domain_clustering as _cluster,
    growth_planner as _planner,
    scale_decision as _scale,
)


class GrowthMeasurePayload(BaseModel):
    window_days: int = Field(7, ge=1, le=90)


@router.post("/growth/measure")
async def growth_measure(
    payload: Optional[GrowthMeasurePayload] = None,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """능력 측정 트리거 — 매일 cron 또는 관리자 수동."""
    _check_internal_key(authorization)
    days = payload.window_days if payload else 7
    return {"measured": await _cap.measure_all_domains(window_days=days)}


@router.get("/growth/metrics")
async def growth_metrics(
    domain: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(200, ge=1, le=1000),
) -> dict[str, Any]:
    """CapabilityMetric 조회 — 도메인 필터 + 윈도우."""
    return {
        "domain": domain,
        "days": days,
        "items": await _cap.list_recent_metrics(
            domain=domain, days=days, limit=limit
        ),
    }


@router.get("/growth/metrics/latest")
async def growth_metrics_latest(
    days: int = Query(7, ge=1, le=90),
) -> dict[str, Any]:
    """도메인별 최신 메트릭 1 건씩 — 대시보드용."""
    return await _cap.latest_per_domain(days=days)


@router.get("/growth/proposals")
async def growth_proposals(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    """GrowthDecision 목록."""
    items = await _auto_spawn.list_decisions(status=status, limit=limit)
    return {"count": len(items), "items": items}


@router.get("/growth/proposals/{decision_id}")
async def growth_proposal_detail(decision_id: str) -> dict[str, Any]:
    d = await _auto_spawn.get_decision(decision_id)
    if not d:
        raise HTTPException(404, f"decision not found: {decision_id}")
    return d


class ApproveDecisionPayload(BaseModel):
    reviewed_by: Optional[str] = None


@router.post("/growth/decisions/{decision_id}/approve")
async def growth_decision_approve(
    decision_id: str,
    payload: Optional[ApproveDecisionPayload] = None,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """관리자 승인."""
    _check_internal_key(authorization)
    reviewer = payload.reviewed_by if payload else None
    return await _auto_spawn.approve_decision(
        decision_id, reviewed_by=reviewer
    )


class RejectDecisionPayload(BaseModel):
    reason: str
    reviewed_by: Optional[str] = None


@router.post("/growth/decisions/{decision_id}/reject")
async def growth_decision_reject(
    decision_id: str,
    payload: RejectDecisionPayload,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """관리자 거절."""
    _check_internal_key(authorization)
    return await _auto_spawn.reject_decision(
        decision_id,
        reason=payload.reason,
        reviewed_by=payload.reviewed_by,
    )


@router.post("/growth/decisions/{decision_id}/execute")
async def growth_decision_execute(
    decision_id: str,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """승인된 결정 실행 — 결정 타입별 핸들러 분기."""
    _check_internal_key(authorization)
    return await _auto_spawn.execute_decision(decision_id)


@router.get("/growth/emergent")
async def growth_emergent(
    promoted: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    """새 도메인 후보 목록."""
    items = await _cluster.list_emergent(promoted=promoted, limit=limit)
    return {"count": len(items), "items": items}


@router.post("/growth/emergent/discover")
async def growth_emergent_discover(
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """미분류 질문 재클러스터링 — 관리자 트리거."""
    _check_internal_key(authorization)
    candidates = await _cluster.discover_emergent_domains()
    return {"count": len(candidates), "items": candidates}


@router.post("/growth/emergent/{emergent_id}/promote")
async def growth_emergent_promote(
    emergent_id: str,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """EmergentDomain → 정식 도메인 승격."""
    _check_internal_key(authorization)
    return await _cluster.promote_emergent(emergent_id)


@router.get("/growth/scale-check")
async def growth_scale_check(
    days: int = Query(30, ge=7, le=90),
) -> dict[str, Any]:
    """베이스 모델 확장 필요성 판단 — 판단만, 결정 생성 안 함."""
    return await _scale.should_scale_base(window_days=days)


@router.post("/growth/cycle")
async def growth_cycle(
    auto_execute: bool = Query(True),
    window_days: int = Query(7, ge=1, le=90),
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """일일 성장 사이클 — cron 호출 / 관리자 수동.

    측정 → 클러스터링 → 제안 → 자동승인+실행.
    """
    _check_internal_key(authorization)
    return await _planner.daily_growth_cycle(
        window_days=window_days, auto_execute=auto_execute
    )


# ────────────────────────────────────────────────────────────
# Phase 5 — Curiosity Cycle (Gap detection / Curious crawl / Sleep)
# ────────────────────────────────────────────────────────────
class DetectGapsPayload(BaseModel):
    window_hours: int = Field(24, ge=1, le=24 * 7)


@router.post("/gaps/detect")
async def gaps_detect(
    payload: Optional[DetectGapsPayload] = None,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """KnowledgeGap 감지 즉시 트리거 (관리자/cron)."""
    _check_internal_key(authorization)
    from hwarang_api.learning.gap_detector import detect_gaps

    hours = payload.window_hours if payload else 24
    return await detect_gaps(window_hours=hours)


@router.get("/gaps")
async def gaps_list(
    status: Optional[str] = Query(None, description="open/searching/crawling/filled/abandoned"),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    """KnowledgeGap 목록 — 관리자 대시보드/디버그용."""
    from hwarang_api.db import prisma

    where: dict[str, Any] = {}
    if status:
        where["status"] = status
    try:
        rows = await prisma.knowledgegap.find_many(
            where=where or None,
            order=[{"failureCount": "desc"}, {"lastSeenAt": "desc"}],
            take=limit,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"db error: {exc}") from exc

    items = [
        {
            "id": getattr(g, "id", None),
            "topic": g.topic,
            "status": g.status,
            "failure_count": getattr(g, "failureCount", 0),
            "search_attempts": getattr(g, "searchAttempts", 0),
            "first_seen_at": (
                g.firstSeenAt.isoformat() if getattr(g, "firstSeenAt", None) else None
            ),
            "last_seen_at": (
                g.lastSeenAt.isoformat() if getattr(g, "lastSeenAt", None) else None
            ),
        }
        for g in rows
    ]
    return {"count": len(items), "items": items}


@router.post("/gaps/curious-crawl")
async def gaps_curious_crawl(
    gap_limit: int = Query(10, ge=1, le=50),
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """우선순위 gap 에 대해 표적 크롤 즉시 실행."""
    _check_internal_key(authorization)
    from hwarang_api.learning.curious_crawler import proactive_crawl_cycle

    return await proactive_crawl_cycle(gap_limit=gap_limit)


@router.post("/sleep")
async def trigger_sleep(
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """Sleep consolidation 사이클 즉시 실행 (관리자/디버그)."""
    _check_internal_key(authorization)
    from hwarang_api.learning.sleep_consolidator import sleep_cycle

    return await sleep_cycle()


# ────────────────────────────────────────────────────────────
# Phase 5 — Self-Adversarial Tester
# ────────────────────────────────────────────────────────────
@router.post("/adversarial/run")
async def adversarial_run(
    samples: int = Query(20, ge=1, le=200),
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """Self-Adversarial 즉시 트리거 — 어제 답변 N개 공격 + 약점 수집."""
    _check_internal_key(authorization)
    from hwarang_api.learning.adversarial_tester import (
        run_adversarial_self_play,
    )

    return await run_adversarial_self_play(samples=samples)


@router.get("/adversarial/findings")
async def adversarial_findings(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    """발견된 약점 목록 — followupMsg 가 ``[adversarial]`` 로 시작하는 RLHFFeedback."""
    from hwarang_api.learning.adversarial_tester import (
        list_adversarial_findings,
    )

    return await list_adversarial_findings(days=days, limit=limit)


# ────────────────────────────────────────────────────────────
# Phase 5 — Multi-Agent Synthesis (Federated Inference)
# ────────────────────────────────────────────────────────────
class FederatedPayload(BaseModel):
    question: str = Field(..., min_length=1)
    max_rounds: int = Field(2, ge=0, le=5)


@router.post("/federated")
async def federated(
    payload: FederatedPayload,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """다도메인 질문 합성 추론.

    내부 키 보호 (Next.js /api/chat 가 호출). 단일 도메인이면 ``skip=True``
    로 빠르게 우회한다.
    """
    _check_internal_key(authorization)
    from hwarang_api.learning.federated_inference import federated_inference

    return await federated_inference(
        question=payload.question,
        max_rounds=payload.max_rounds,
    )


# ────────────────────────────────────────────────────────────
# Phase 5.5 — Self-Questioning Engine
# ────────────────────────────────────────────────────────────
class SelfQuestionTopicPayload(BaseModel):
    topic: str = Field(..., min_length=1)
    domain: str = "general"


class SelfQuestionSocraticPayload(BaseModel):
    question: str = Field(..., min_length=1)
    domain: str = "general"
    max_depth: int = Field(5, ge=1, le=10)


@router.post("/self-question/cycle")
async def self_question_cycle(
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """즉시 self-question 사이클 트리거 (관리자/cron)."""
    _check_internal_key(authorization)
    from hwarang_api.learning.self_questioner import child_questioning_cycle

    return await child_questioning_cycle()


@router.post("/self-question/topic")
async def self_question_topic(
    payload: SelfQuestionTopicPayload,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """특정 토픽에 대해 5 질문을 던지고 답을 시도. 관리자 디버깅용."""
    _check_internal_key(authorization)
    from hwarang_api.learning.self_questioner import manual_question_about

    return await manual_question_about(payload.topic, payload.domain)


@router.post("/self-question/socratic")
async def self_question_socratic(
    payload: SelfQuestionSocraticPayload,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """주어진 질문에서 N층 Socratic dive (depth + confidence 종료)."""
    _check_internal_key(authorization)
    from hwarang_api.learning.self_questioner import socratic_dive

    chain = await socratic_dive(
        payload.question, payload.domain, max_depth=payload.max_depth
    )
    return {"question": payload.question, "depth": len(chain), "chain": chain}


# ────────────────────────────────────────────────────────────
# Phase 5.5 Eager — 1차 출처 API 직접 호출 모드
# ────────────────────────────────────────────────────────────
class EagerCyclePayload(BaseModel):
    topic_count: int = Field(10, ge=1, le=50)
    questions_per_topic: int = Field(5, ge=1, le=10)
    enable_socratic: bool = True


class EagerAnswerPayload(BaseModel):
    question: str = Field(..., min_length=1)
    domain: str = "general"
    confidence_threshold: float = Field(0.5, ge=0.0, le=1.0)


@router.post("/self-question/eager-cycle")
async def self_question_eager_cycle(
    payload: Optional[EagerCyclePayload] = None,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """Eager 사이클 즉시 트리거 — 매일 02:00 KST cron 의 즉시 호출판."""
    _check_internal_key(authorization)
    from hwarang_api.learning.self_questioner import eager_questioning_cycle

    p = payload or EagerCyclePayload()
    return await eager_questioning_cycle(
        topic_count=p.topic_count,
        questions_per_topic=p.questions_per_topic,
        enable_socratic=p.enable_socratic,
    )


@router.post("/self-question/eager-answer")
async def self_question_eager_answer(
    payload: EagerAnswerPayload,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """단일 질문에 eager 답변 — 부족 시 1차 출처 API 직접 호출 + HLKM 저장."""
    _check_internal_key(authorization)
    from hwarang_api.learning.self_questioner import self_answer_eager

    result = await self_answer_eager(
        payload.question,
        payload.domain,
        confidence_threshold=payload.confidence_threshold,
    )
    return {
        "question": result.question,
        "answer": result.answer,
        "confidence": round(result.confidence, 3),
        "missing_info": result.missing_info,
        "used_fact_ids": result.used_fact_ids,
    }


# ────────────────────────────────────────────────────────────
# Online RLHF — 즉시 1 step gradient + LoRA hot-swap
# ────────────────────────────────────────────────────────────
class OnlineFeedbackPayload(BaseModel):
    feedback_id: str
    prompt: str
    response: str
    rating: int = Field(..., ge=-1, le=1)
    domain: str = "general"
    correction: Optional[str] = None
    user_id: Optional[str] = None


@router.post("/online/feedback")
async def submit_online_feedback(
    payload: OnlineFeedbackPayload,
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """RLHF 피드백 → online learning 큐.

    - rating=+1: response 가 정답 → 그대로 학습
    - rating=-1 + correction: correction 이 정답 → 가중치 2배
    - rating=-1, correction 없음: skip
    """
    _check_internal_key(authorization)
    from hwarang_api.learning.online.continuous_lora import submit_feedback

    return await submit_feedback(
        feedback_id=payload.feedback_id,
        domain=payload.domain,
        prompt=payload.prompt,
        response=payload.response,
        rating=payload.rating,
        correction=payload.correction,
        user_id=payload.user_id,
    )


@router.get("/online/status")
async def online_status(
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    _check_internal_key(authorization)
    from hwarang_api.learning.online.continuous_lora import queue_status

    return queue_status()


@router.get("/primary-sources/health")
async def primary_sources_health() -> dict[str, Any]:
    """6개 1차 출처 API 어댑터 상태 — 키 등록 여부 + 단순 호출 결과."""
    from hwarang_api.knowledge.primary_source_apis import (
        primary_sources_health as _health,
    )

    items = await _health()
    return {
        "count": len(items),
        "configured": sum(1 for x in items if x.get("configured")),
        "healthy": sum(1 for x in items if x.get("ok")),
        "items": items,
    }


__all__ = ["router"]
