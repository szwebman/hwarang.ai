"""Cognitive Layer 엔드포인트 (Phase 6).

엔드포인트
----------
* ``POST /api/cognitive/cycle``           — 즉시 1 사이클 실행 (관리자/디버그)
* ``GET  /api/cognitive/health``          — 헬스/비용 메트릭
* ``POST /api/cognitive/disable``         — 수동 비상 비활성
* ``POST /api/cognitive/enable``          — 수동 재활성
* ``POST /api/cognitive/debate``          — 다도메인 다회차 토론 트리거
* ``POST /api/cognitive/consult-agents``  — 라운드 시작 전 에이전트 의향 조사

권한
----
``cycle`` / ``disable`` / ``enable`` / ``debate`` / ``consult-agents`` 는
``HWARANG_INTERNAL_KEY`` 보호 (``learning._check_internal_key``).
``health`` 는 누구나 (운영 모니터링용).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from hwarang_api.routers.learning import _check_internal_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cognitive", tags=["Cognitive"])


def _require_internal(authorization: Optional[str] = Header(None)) -> None:
    """Depends 래퍼 — 내부 키 검사. 실패 시 ``_check_internal_key`` 가 401."""
    _check_internal_key(authorization)


# ────────────────────────────────────────────────────────────
# 1. 사이클 트리거
# ────────────────────────────────────────────────────────────
@router.post("/cycle")
async def trigger_cycle(_: None = Depends(_require_internal)) -> dict:
    """즉시 1 사이클 트리거 (관리자/디버그용)."""
    from hwarang_api.cognitive import cognitive_cycle

    return await cognitive_cycle()


# ────────────────────────────────────────────────────────────
# 2. 헬스 메트릭
# ────────────────────────────────────────────────────────────
@router.get("/health")
async def health(actor: str = "master") -> dict:
    from hwarang_api.cognitive.guardrails_advanced import (
        check_cost_budget,
        check_health,
        is_cognitive_enabled,
    )

    return {
        "actor": actor,
        "enabled": await is_cognitive_enabled(actor),
        "health": await check_health(actor),
        "cost": await check_cost_budget(actor),
    }


# ────────────────────────────────────────────────────────────
# 3. 비활성/재활성
# ────────────────────────────────────────────────────────────
@router.post("/disable")
async def disable(
    actor: str = "master",
    reason: str = "manual",
    _: None = Depends(_require_internal),
) -> dict:
    from hwarang_api.cognitive.guardrails_advanced import emergency_disable

    await emergency_disable(actor, [f"manual: {reason}"])
    return {"disabled": True, "actor": actor, "reason": reason}


@router.post("/enable")
async def enable(
    actor: str = "master",
    _: None = Depends(_require_internal),
) -> dict:
    """수동 재활성 — DB flag 삭제."""
    from hwarang_api.cognitive.guardrails_advanced import clear_disable_flag

    cleared = await clear_disable_flag(actor)
    return {"enabled": True, "actor": actor, "flag_cleared": cleared}


# ────────────────────────────────────────────────────────────
# 4. 다회차 토론 트리거
# ────────────────────────────────────────────────────────────
class DebatePayload(BaseModel):
    question: str
    expert_answers: list[dict] = Field(default_factory=list)
    max_rounds: int = 3


@router.post("/debate")
async def trigger_debate(
    payload: DebatePayload,
    _: None = Depends(_require_internal),
) -> dict:
    """다도메인 토론 트리거.

    ``expert_answers`` 형식: ``[{agent_id, domain, answer, confidence, reasoning}]``
    """
    from hwarang_api.cognitive.inter_agent import multi_round_debate

    state = await multi_round_debate(
        question=payload.question,
        expert_answers=payload.expert_answers,
        max_rounds=payload.max_rounds,
    )

    return {
        "consensus_reached": state.consensus_reached,
        "rounds": len(state.rounds),
        "domains_involved": state.domains_involved,
        "final_answer": state.final_answer,
        "summary": state.debate_summary,
        "history": [
            [
                {
                    "agent_id": op.agent_id,
                    "domain": op.domain,
                    "round_num": op.round_num,
                    "confidence": op.confidence,
                    "changed_from": op.changed_from,
                }
                for op in round_ops
            ]
            for round_ops in state.rounds
        ],
    }


# ────────────────────────────────────────────────────────────
# 5. 라운드 의향 조사
# ────────────────────────────────────────────────────────────
class ConsultPayload(BaseModel):
    domain: str
    estimated_minutes: int = 30
    estimated_hwr: float = 100
    min_vram_gb: float = 8


@router.post("/consult-agents")
async def consult(
    payload: ConsultPayload,
    _: None = Depends(_require_internal),
) -> dict:
    """라운드 시작 전 에이전트 의향 조사."""
    from hwarang_api.cognitive.orchestrator import consult_agents_for_round

    return await consult_agents_for_round(
        domain=payload.domain,
        estimated_minutes=payload.estimated_minutes,
        estimated_hwr=payload.estimated_hwr,
        min_vram_gb=payload.min_vram_gb,
    )


# ────────────────────────────────────────────────────────────
# 6. 메모리 목록 (관리자 UI 용)
# ────────────────────────────────────────────────────────────
@router.get("/memories")
async def list_memories(
    actor: str = "master",
    hours: int = 24,
    limit: int = 50,
) -> dict:
    """관리자 UI 용 — 최근 사고 메모리 목록.

    Args:
        actor: "master" / "inter_agent_debate" / "agent_<id>"
        hours: 조회 시간 범위 (기본 24h)
        limit: 최대 개수 (기본 50, 최대 500)
    """
    from datetime import datetime, timezone, timedelta

    from hwarang_api.db import prisma

    take = max(1, min(int(limit), 500))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours)))

    try:
        records = await prisma.cognitivememory.find_many(
            where={
                "actor": actor,
                "timestamp": {"gte": cutoff},
            },
            order={"timestamp": "desc"},
            take=take,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_memories 실패: %s", exc)
        return {"memories": [], "error": str(exc)}

    memories = [
        {
            "id": r.id,
            "actor": r.actor,
            "timestamp": r.timestamp.isoformat() if getattr(r, "timestamp", None) else None,
            "observed": getattr(r, "observed", None),
            "reasoning": getattr(r, "reasoning", "") or "",
            "decision": getattr(r, "decision", "") or "",
            "actionTaken": getattr(r, "actionTaken", None),
            "outcome": getattr(r, "outcome", None),
            "outcomeScore": getattr(r, "outcomeScore", None),
            "lesson": getattr(r, "lesson", None),
        }
        for r in records
    ]

    return {
        "actor": actor,
        "hours": hours,
        "count": len(memories),
        "memories": memories,
    }


# ────────────────────────────────────────────────────────────
# 7. Phase 7 — Free Will / 창의적 목표 / 호기심 / 의도
# ────────────────────────────────────────────────────────────
@router.post("/free-will/start")
async def start_free_will(_: None = Depends(_require_internal)) -> dict:
    """Free Will 무한 루프 수동 시작.

    이미 돌고 있으면 ``{"already_running": True}``.
    HWARANG_FREEWILL_ENABLED 환경변수 무시 — 명시 시작 시.
    """
    import asyncio

    from hwarang_api.cognitive.free_will import free_will_loop, is_running

    if is_running():
        return {"started": False, "already_running": True}

    asyncio.create_task(free_will_loop(), name="hlkm.free_will_manual")
    return {"started": True}


@router.post("/free-will/stop")
async def stop_free_will_endpoint(_: None = Depends(_require_internal)) -> dict:
    """Free Will 루프 정지 (다음 인터럽트 시 종료)."""
    from hwarang_api.cognitive.free_will import stop_free_will

    stop_free_will()
    return {"stopped": True}


@router.post("/free-will/trigger")
async def trigger_free_will(
    reason: str = "manual",
    _: None = Depends(_require_internal),
) -> dict:
    """외부 자극 — 즉시 다음 사이클 깨움."""
    from hwarang_api.cognitive.free_will import trigger_immediate_cycle

    trigger_immediate_cycle(reason)
    return {"triggered": True, "reason": reason}


@router.get("/free-will/status")
async def free_will_status() -> dict:
    """Free Will 루프 상태 (운영 모니터링)."""
    from hwarang_api.cognitive.free_will import current_interval, is_running

    return {
        "running": is_running(),
        "current_interval_sec": current_interval(),
    }


@router.post("/goals/generate")
async def trigger_goal_generation(_: None = Depends(_require_internal)) -> dict:
    """창의적 목표 즉시 생성 (관리자/디버그)."""
    from hwarang_api.cognitive.free_will import free_will_goal_cycle

    return await free_will_goal_cycle()


@router.post("/curiosity")
async def trigger_curiosity(_: None = Depends(_require_internal)) -> dict:
    """자발적 호기심 사이클 즉시 트리거."""
    from hwarang_api.cognitive.spontaneous import spontaneous_curiosity_cycle

    return await spontaneous_curiosity_cycle()


@router.post("/intent/declare")
async def declare_intent_endpoint(_: None = Depends(_require_internal)) -> dict:
    """이번 주 의도 즉시 선언 (관리자/디버그)."""
    from hwarang_api.cognitive.intent import declare_weekly_intent

    return await declare_weekly_intent()


@router.get("/intent/current")
async def current_intent_endpoint() -> dict:
    """현재 주 의도 조회 (사이클들이 참조하는 값)."""
    from hwarang_api.cognitive.intent import get_current_intent

    return await get_current_intent() or {}


# ────────────────────────────────────────────────────────────
# 8. 환각 검증 / 감사 (Hallucination + Audit)
# ────────────────────────────────────────────────────────────
@router.get("/audit/summary")
async def audit_summary(days: int = 7) -> dict:
    """최근 N 일 cognitive 감사 요약 (관리자 UI 용).

    응답: ``{days, total, blocked_count, halluc_count, schema_violations,
    avg_consistency, avg_hallucination, approval_required}``
    """
    from hwarang_api.cognitive.audit import get_audit_summary

    return await get_audit_summary(days)


class HallucinationCheckPayload(BaseModel):
    prompt: str = ""
    decision: dict = Field(default_factory=dict)
    n_repeats: int = 3


@router.post("/check-hallucination")
async def check_halluc(
    payload: HallucinationCheckPayload,
    _: None = Depends(_require_internal),
) -> dict:
    """수동 환각 체크 — 디버그/검증용."""
    from hwarang_api.cognitive.hallucination_check import check_hallucination

    report = await check_hallucination(
        prompt=payload.prompt,
        decision=payload.decision,
        n_repeats=payload.n_repeats,
    )
    return {
        "is_hallucination": report.is_hallucination,
        "confidence": report.confidence,
        "consistency_score": report.consistency_score,
        "factual_score": report.factual_score,
        "schema_valid": report.schema_valid,
        "risky_keywords": report.risky_keywords,
        "reasoning": report.reasoning,
    }


# ────────────────────────────────────────────────────────────
# 9. Constitutional AI — 헌법 / 자기비판 / 가치충돌 / 도덕추론
# ────────────────────────────────────────────────────────────
class ConstitutionCritiquePayload(BaseModel):
    question: str
    response: str


@router.post("/constitution/critique")
async def constitution_critique(
    payload: ConstitutionCritiquePayload,
    _: None = Depends(_require_internal),
) -> dict:
    """응답 자기 비판 + 위반 시 자동 수정안.

    응답: ``{revised, original_response, revised_response?, violations, had_critical}``
    """
    from hwarang_api.cognitive.constitution.self_critique import auto_revise_if_violation

    return await auto_revise_if_violation(
        user_question=payload.question,
        ai_response=payload.response,
    )


class ConstitutionConflictPayload(BaseModel):
    request: str
    principle_ids: list[str] = Field(default_factory=list)


@router.post("/constitution/conflict")
async def constitution_conflict(
    payload: ConstitutionConflictPayload,
    _: None = Depends(_require_internal),
) -> dict:
    """가치 충돌 해결 — priority + LLM 회색 영역."""
    from hwarang_api.cognitive.constitution.value_conflict import resolve_conflict

    result = await resolve_conflict(
        user_request=payload.request,
        candidate_principle_ids=payload.principle_ids,
    )
    return {
        "winning": result.winning_principle,
        "losing": result.losing_principles,
        "reasoning": result.reasoning,
        "suggested_response": result.suggested_response,
    }


class MoralJudgePayload(BaseModel):
    request: str


@router.post("/constitution/moral-judge")
async def constitution_moral_judge(
    payload: MoralJudgePayload,
    _: None = Depends(_require_internal),
) -> dict:
    """회색 영역 도덕 추론."""
    from hwarang_api.cognitive.constitution.moral_reasoning import judge_moral_gray_area

    judgment = await judge_moral_gray_area(payload.request)
    return {
        "is_acceptable": judgment.is_acceptable,
        "confidence": judgment.confidence,
        "suggested_style": judgment.suggested_response_style,
        "reasoning": judgment.reasoning,
        "cultural_context": judgment.cultural_context,
    }


@router.get("/constitution")
async def get_constitution_endpoint() -> dict:
    """화랑 헌법 전체 조회 (관리자 UI / 투명성)."""
    from hwarang_api.cognitive.constitution.constitution import CONSTITUTION

    return {
        "principles": [
            {
                "id": p.id,
                "title": p.title,
                "description": p.description,
                "priority": p.priority,
                "category": p.category,
            }
            for p in CONSTITUTION
        ],
        "total": len(CONSTITUTION),
    }


# ────────────────────────────────────────────────────────────
# 10. Phase 8 — World Model (시나리오 시뮬레이터)
# ────────────────────────────────────────────────────────────
class WorldModelSimulatePayload(BaseModel):
    scenario_name: str
    action: str
    steps: int = 5


class WorldModelComparePayload(BaseModel):
    scenario_name: str
    actions: list[str] = Field(default_factory=list)
    criteria: str = "안정성"
    steps: int = 3


@router.get("/world-model/scenarios")
async def world_model_scenarios() -> dict:
    """사전 정의 시나리오 목록 (UI 드롭다운용)."""
    from hwarang_api.cognitive.world_model import list_scenarios

    items = list_scenarios()
    return {"scenarios": items, "count": len(items)}


@router.post("/world-model/simulate")
async def world_model_simulate(
    payload: WorldModelSimulatePayload,
    _: None = Depends(_require_internal),
) -> dict:
    """단일 액션을 다단계 시뮬레이션."""
    from hwarang_api.cognitive.world_model import WorldSimulator, get_scenario

    scenario = get_scenario(payload.scenario_name)
    if scenario is None:
        return {"error": f"unknown scenario: {payload.scenario_name}"}

    sim = WorldSimulator()
    result = await sim.simulate(scenario, action=payload.action, steps=payload.steps)
    return result.to_dict()


@router.post("/world-model/compare")
async def world_model_compare(
    payload: WorldModelComparePayload,
    _: None = Depends(_require_internal),
) -> dict:
    """여러 액션 비교 + 기준에 따른 최선안 추천."""
    from hwarang_api.cognitive.world_model import (
        compare_actions,
        get_scenario,
        recommend_best,
    )

    scenario = get_scenario(payload.scenario_name)
    if scenario is None:
        return {"error": f"unknown scenario: {payload.scenario_name}"}

    if not payload.actions:
        return {"error": "actions list is empty"}

    results = await compare_actions(scenario, payload.actions, steps=payload.steps)
    best = await recommend_best(
        scenario,
        payload.actions,
        criteria=payload.criteria,
        steps=payload.steps,
    )

    return {
        "scenario": scenario.name,
        "criteria": payload.criteria,
        "results": {a: r.to_dict() for a, r in results.items()},
        "recommended": best,
    }


# ────────────────────────────────────────────────────────────
# 11. Phase 9.ζ — Meta-cognition + Theory of Mind
# ────────────────────────────────────────────────────────────
class MetaReflectPayload(BaseModel):
    question: str
    answer: str
    sources: Optional[list[str]] = None


@router.post("/metacog/reflect")
async def metacog_reflect(
    payload: MetaReflectPayload,
    _: None = Depends(_require_internal),
) -> dict:
    """답변 자기 비판 — 논리 공백/미입증/누락관점/품질."""
    from hwarang_api.cognitive.metacog import SelfReflection

    sr = SelfReflection()
    result = await sr.reflect_on_answer(
        question=payload.question,
        answer=payload.answer,
        sources=payload.sources or [],
    )
    return {
        **result.to_dict(),
        "should_revise": SelfReflection.should_revise(result),
    }


class MetaCalibratePayload(BaseModel):
    question: str
    answer: str
    domain: str = ""


@router.post("/metacog/calibrate")
async def metacog_calibrate(
    payload: MetaCalibratePayload,
    _: None = Depends(_require_internal),
) -> dict:
    """답변 신뢰도 재보정 — raw × historical → calibrated + suggestion."""
    from hwarang_api.cognitive.metacog import ConfidenceCalibrator

    cc = ConfidenceCalibrator()
    return await cc.calibrated_confidence(
        question=payload.question,
        answer=payload.answer,
        domain=payload.domain,
    )


class ToMUpdatePayload(BaseModel):
    user_id: str
    question: str
    answer: str
    feedback: Optional[str] = None


@router.post("/metacog/theory-of-mind/update")
async def metacog_tom_update(
    payload: ToMUpdatePayload,
    _: None = Depends(_require_internal),
) -> dict:
    """사용자 멘탈 모델 업데이트 (LLM 추출 후 점진적 머지)."""
    from hwarang_api.cognitive.metacog import TheoryOfMind

    tom = TheoryOfMind()
    model = await tom.update_from_interaction(
        user_id=payload.user_id,
        question=payload.question,
        answer=payload.answer,
        feedback=payload.feedback,
    )
    return {"user_id": payload.user_id, "model": model}


@router.get("/metacog/theory-of-mind/{user_id}")
async def metacog_tom_get(user_id: str) -> dict:
    """사용자 멘탈 모델 조회 — 폴백 포함, 항상 200."""
    from hwarang_api.cognitive.metacog import TheoryOfMind

    tom = TheoryOfMind()
    model = await tom.get_model(user_id)
    return {"user_id": user_id, "model": model}


class PredictNeedPayload(BaseModel):
    user_id: str
    current_question: str


@router.post("/metacog/predict-need")
async def metacog_predict_need(
    payload: PredictNeedPayload,
    _: None = Depends(_require_internal),
) -> dict:
    """사용자 기대 깊이/형식/후속질문 예측."""
    from hwarang_api.cognitive.metacog import TheoryOfMind

    tom = TheoryOfMind()
    return await tom.predict_user_need(
        user_id=payload.user_id,
        current_question=payload.current_question,
    )


class DetectGapsPayload(BaseModel):
    question: str
    answer: str


@router.post("/metacog/detect-gaps")
async def metacog_detect_gaps(
    payload: DetectGapsPayload,
    _: None = Depends(_require_internal),
) -> dict:
    """답변 자기진단 — 모르는/불확실 부분 식별 + 외부탐색 힌트."""
    from hwarang_api.cognitive.metacog import KnowledgeGapDetector

    kgd = KnowledgeGapDetector()
    gaps = await kgd.detect_gaps(payload.question, payload.answer)
    return {
        "gaps": [g.to_dict() for g in gaps],
        "should_search_external": KnowledgeGapDetector.should_search_external(gaps),
        "count": len(gaps),
    }


__all__ = ["router"]
