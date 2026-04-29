"""Master Cognitive Loop — 매 15분 자율 사고 사이클 (Phase 6).

사이클 단계
-----------
1. ``reflect_on_recent()`` — 1시간 이전 actionTaken 있고 outcome 비어있는
   기록을 평가해 outcome / score / lesson 채움.
2. ``observe()`` — KnowledgeFact / Gap / RLHF / Round / GrowthDecision /
   CrawlJob / 활성 에이전트 등 메트릭 수집.
3. ``get_recent_lessons()`` — 추론 컨텍스트로 사용할 최근 lesson 10 개.
4. 일일 액션 한도 체크 (``HWARANG_COGNITIVE_MAX_ACTIONS_DAY``, 기본 20).
5. ``reason_about_state()`` — LLM 으로 분석 + 결정 JSON 생성.
6. ``record_decision()`` — observed/reasoning/decision 을 CognitiveMemory 에 기록.
7. ``check_and_execute()`` — guardrails 통해 자유 액션은 즉시 실행, 승인
   필요 액션은 GrowthDecision 으로 큐잉, 미지원 액션은 blocked.
8. 각 결정의 status 를 ``actionTaken`` 컬럼에 요약 저장.

사람 승인이 필요한 액션은 ``REQUIRES_APPROVAL`` 카탈로그 참조.
``HWARANG_COGNITIVE_ENABLED=false`` 이면 사이클 자체가 ``{"skipped": True}``.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from hwarang_api.cognitive.memory import (
    get_recent_lessons,
    record_decision,
    update_outcome,
)
from hwarang_api.cognitive.reasoning import reason_about_state
from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 환경 / 카탈로그
# ---------------------------------------------------------------------------
def _env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


COGNITIVE_ENABLED = _env_bool("HWARANG_COGNITIVE_ENABLED", True)
MAX_ACTIONS_PER_DAY = _env_int("HWARANG_COGNITIVE_MAX_ACTIONS_DAY", 20)


# 마스터가 자율로 호출 가능한 액션 목록 (LLM 프롬프트로 전달)
AVAILABLE_ACTIONS: list[str] = [
    "trigger_curious_crawl",        # 표적 크롤
    "trigger_arxiv_summarize",       # 논문 요약 가속
    "propose_new_trusted_source",    # 출처 추가 (사람 승인)
    "adjust_quality_threshold",      # 품질 임계 조정
    "trigger_code_round",            # 코드 라운드 시작 (사람 승인)
    "trigger_design_round",          # 디자인 라운드 (사람 승인)
    "rebuild_eval_set",              # 평가셋 재구성
    "increase_lora_rank",            # LoRA rank 확장 (사람 승인)
    "trigger_self_question_eager",   # 적극 자기질문
    "trigger_sleep_cycle",           # 수동 sleep 사이클
    "no_action",                     # 정상 상태 — 아무것도 안 함
]


# 사람 승인이 필요한 액션 패턴 (suffix * 와일드카드 지원)
REQUIRES_APPROVAL: list[str] = [
    "scale_base_model",
    "delete_*",
    "spawn_lora",
    "add_trusted_source",
    "propose_new_trusted_source",
    "increase_lora_rank",
    "trigger_code_round",
    "trigger_design_round",
]


# ---------------------------------------------------------------------------
# 메인 사이클
# ---------------------------------------------------------------------------
async def cognitive_cycle(actor: str = "master") -> dict:
    """매 15분 cron — 1 사이클 실행.

    Phase 6 보강: ``guardrails_advanced`` 의 런타임 비활성 / 자가종료 검사 선행.
    """
    if not COGNITIVE_ENABLED:
        return {"skipped": True, "reason": "disabled"}

    # 런타임 비활성 체크 (env + DB flag)
    try:
        from hwarang_api.cognitive.guardrails_advanced import (
            emergency_disable,
            is_cognitive_enabled,
            should_self_disable,
        )

        if not await is_cognitive_enabled(actor):
            return {"skipped": True, "reason": "cognitive_disabled"}

        disable_check = await should_self_disable(actor)
        if disable_check.get("should_disable"):
            await emergency_disable(actor, disable_check["reasons"])
            return {
                "skipped": True,
                "reason": "emergency_disabled",
                "details": {
                    "reasons": disable_check["reasons"],
                    "recent_failed_2h": disable_check.get("recent_failed_2h"),
                },
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("advanced guardrail 검사 실패(계속 진행): %s", exc)

    started = datetime.now(timezone.utc)

    # 1. 이전 사이클 결과 반성 (있으면)
    try:
        await reflect_on_recent(actor)
    except Exception as exc:  # noqa: BLE001
        logger.warning("reflect_on_recent 실패: %s", exc)

    # 2. 현재 상태 관찰
    observation = await observe()

    # 3. 과거 교훈 가져오기
    past_lessons = await get_recent_lessons(actor, limit=10)

    # 4. 일일 액션 한도 체크
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    try:
        today_decisions = await prisma.cognitivememory.count(
            where={
                "actor": actor,
                "timestamp": {"gte": today_start},
                "actionTaken": {"not": None},
            },
        )
    except Exception:  # noqa: BLE001
        today_decisions = 0
    max_remaining = max(0, MAX_ACTIONS_PER_DAY - today_decisions)

    if max_remaining == 0:
        logger.info("일일 자율 액션 한도 도달 (%d) — skip", MAX_ACTIONS_PER_DAY)
        return {
            "skipped": True,
            "reason": "daily_limit",
            "actions_today": today_decisions,
        }

    # 5. LLM 추론
    plan = await reason_about_state(
        observation=observation,
        past_lessons=past_lessons,
        available_actions=AVAILABLE_ACTIONS,
        requires_approval=REQUIRES_APPROVAL,
        max_actions_remaining=max_remaining,
    )

    # 5.5. 환각 검증 (Multi-Source Verification)
    halluc_report: dict | None = None
    try:
        from hwarang_api.cognitive.hallucination_check import (
            HALLUC_CHECK_ENABLED,
            HALLUC_REPEATS,
            check_hallucination,
        )

        if HALLUC_CHECK_ENABLED and plan.get("decisions"):
            halluc = await check_hallucination(
                prompt="(internal_reasoning)",
                decision=plan,
                n_repeats=HALLUC_REPEATS,
            )
            halluc_report = {
                "is_hallucination": halluc.is_hallucination,
                "confidence": halluc.confidence,
                "consistency_score": halluc.consistency_score,
                "factual_score": halluc.factual_score,
                "schema_valid": halluc.schema_valid,
                "risky_keywords": halluc.risky_keywords,
                "reasoning": halluc.reasoning,
            }

            if halluc.is_hallucination:
                logger.warning(
                    "환각 의심 — 실행 차단: %s", halluc.reasoning
                )

                # 사이클 기록만 하고 실행 안 함
                blocked_reasoning = (
                    plan.get("reasoning", "")
                    + f"\n[환각 차단] {halluc.reasoning}"
                )[:3000]
                memory_id = await record_decision(
                    actor=actor,
                    observed=observation,
                    reasoning=blocked_reasoning,
                    decision="BLOCKED_HALLUCINATION",
                    action_taken="blocked_by_safety",
                )

                # 감사 로그
                try:
                    from hwarang_api.cognitive.audit import log_audit

                    blocked_actions = [
                        d.get("action", "?")
                        for d in plan.get("decisions", [])
                        if isinstance(d, dict)
                    ]
                    await log_audit(
                        memory_id=memory_id,
                        cycle_type="scheduled",
                        hallucination_report=halluc_report,
                        risky_actions_blocked=blocked_actions,
                        user_approval_required=False,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("audit 기록 실패: %s", exc)

                # 관리자 알림
                try:
                    from hwarang_api.knowledge.notifier import notify_admin

                    await notify_admin(
                        f"[Cognitive] 환각 차단\n"
                        f"이유: {halluc.reasoning}\n"
                        f"일관성: {halluc.consistency_score:.2f}\n"
                        f"메모리 ID: {memory_id}",
                        severity="warn",
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("notify_admin 실패: %s", exc)

                return {
                    "cycle_id": memory_id,
                    "blocked": True,
                    "reason": halluc.reasoning,
                    "halluc_report": halluc_report,
                }
    except Exception as exc:  # noqa: BLE001
        logger.warning("환각 검증 자체 실패 (계속 진행): %s", exc)

    # 6. 결정 기록
    decisions_text = json.dumps(plan.get("decisions", []), ensure_ascii=False)[
        :2000
    ]
    memory_id = await record_decision(
        actor=actor,
        observed=observation,
        reasoning=plan.get("reasoning", "")[:3000],
        decision=decisions_text,
    )

    # 7. 실행 (guardrails 가 승인/실행 분기)
    from hwarang_api.cognitive.guardrails import check_and_execute

    executed = []
    for d in plan.get("decisions", [])[:max_remaining]:
        result = await check_and_execute(d, memory_id, actor)
        executed.append(result)

    # actionTaken 업데이트
    if executed and memory_id:
        actions_summary = "; ".join(
            f"{e.get('action', '?')}={e.get('status', '?')}" for e in executed
        )
        try:
            await prisma.cognitivememory.update(
                where={"id": memory_id},
                data={"actionTaken": actions_summary[:500]},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("actionTaken 업데이트 실패: %s", exc)

    # 7.5. 감사 로그 (정상 경로)
    if memory_id:
        try:
            from hwarang_api.cognitive.audit import log_audit

            approval_required = any(
                e.get("status") == "pending_approval" for e in executed
            )
            await log_audit(
                memory_id=memory_id,
                cycle_type="scheduled",
                hallucination_report=halluc_report,
                risky_actions_blocked=[],
                user_approval_required=approval_required,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("audit 기록 실패: %s", exc)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    return {
        "cycle_id": memory_id,
        "elapsed_seconds": elapsed,
        "decisions_made": len(plan.get("decisions", [])),
        "actions_executed": len(
            [e for e in executed if e.get("status") == "executed"]
        ),
        "actions_pending_approval": len(
            [e for e in executed if e.get("status") == "pending_approval"]
        ),
        "actions_blocked": len(
            [e for e in executed if e.get("status") == "blocked"]
        ),
        "executed": executed,
    }


# ---------------------------------------------------------------------------
# Observe — 시스템 상태 수집
# ---------------------------------------------------------------------------
async def observe() -> dict:
    """현재 시스템 상태 관찰 (LLM 프롬프트로 들어감)."""
    obs: dict = {}
    now = datetime.now(timezone.utc)

    try:
        # KnowledgeFact 도메인별 통계
        for domain in (
            "code",
            "design",
            "legal",
            "tax",
            "medical",
            "research",
            "general",
        ):
            try:
                obs[f"facts_{domain}"] = await prisma.knowledgefact.count(
                    where={"domain": domain}
                )
            except Exception:  # noqa: BLE001
                obs[f"facts_{domain}"] = None

        # 최근 24h 신규 사실
        try:
            obs["new_facts_24h"] = await prisma.knowledgefact.count(
                where={"createdAt": {"gte": now - timedelta(days=1)}},
            )
        except Exception:  # noqa: BLE001
            obs["new_facts_24h"] = None

        # KnowledgeGap (open)
        try:
            obs["open_gaps"] = await prisma.knowledgegap.count(
                where={"status": "open"}
            )
        except Exception:  # noqa: BLE001
            obs["open_gaps"] = None

        # 최근 RLHF 만족도 (7일)
        try:
            recent_rlhf = await prisma.rlhffeedback.find_many(
                where={"createdAt": {"gte": now - timedelta(days=7)}},
                take=200,
            )
        except Exception:  # noqa: BLE001
            recent_rlhf = []
        if recent_rlhf:
            satisfied = sum(1 for r in recent_rlhf if getattr(r, "isSatisfied", False))
            obs["rlhf_satisfaction_7d"] = round(satisfied / len(recent_rlhf), 2)
            obs["rlhf_count_7d"] = len(recent_rlhf)
            for domain in ("code", "legal", "tax", "medical"):
                domain_rlhf = [
                    r for r in recent_rlhf if getattr(r, "domain", None) == domain
                ]
                if domain_rlhf:
                    obs[f"rlhf_{domain}_pct"] = round(
                        sum(1 for r in domain_rlhf if getattr(r, "isSatisfied", False))
                        / len(domain_rlhf),
                        2,
                    )

        # 최근 라운드 결과 (7일)
        try:
            recent_rounds = await prisma.round.find_many(
                where={"completedAt": {"gte": now - timedelta(days=7)}},
                order={"completedAt": "desc"},
                take=10,
            )
        except Exception:  # noqa: BLE001
            recent_rounds = []
        obs["rounds_7d"] = len(recent_rounds)
        if recent_rounds:
            obs["rounds_accepted_7d"] = sum(
                1 for r in recent_rounds if getattr(r, "accepted", False)
            )

        # 검토 대기 GrowthDecision
        try:
            obs["pending_decisions"] = await prisma.growthdecision.count(
                where={"status": "proposed"},
            )
        except Exception:  # noqa: BLE001
            obs["pending_decisions"] = None

        # CrawlJob 큐
        try:
            obs["crawl_queue_pending"] = await prisma.crawljob.count(
                where={"status": "pending"}
            )
            obs["crawl_queue_failed"] = await prisma.crawljob.count(
                where={"status": "failed"}
            )
        except Exception:  # noqa: BLE001
            obs["crawl_queue_pending"] = None
            obs["crawl_queue_failed"] = None

        # 활성 에이전트 (in-memory grid)
        try:
            from hwarang_api.routers.grid import _agents

            obs["active_agents"] = len(_agents)
        except Exception:  # noqa: BLE001
            obs["active_agents"] = None

    except Exception as exc:  # noqa: BLE001
        logger.warning("observe 실패: %s", exc)

    return obs


# ---------------------------------------------------------------------------
# Reflect — 이전 결정 평가
# ---------------------------------------------------------------------------
async def reflect_on_recent(actor: str) -> int:
    """이전 사이클 결과 평가 — outcome_score 와 lesson 을 채움.

    1시간 이전, ``actionTaken`` 있고 ``outcome`` 없는 메모리들을 5개씩 처리.

    Returns:
        평가한 메모리 수
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    try:
        pending = await prisma.cognitivememory.find_many(
            where={
                "actor": actor,
                "outcome": None,
                "actionTaken": {"not": None},
                "timestamp": {"lt": cutoff},
            },
            take=5,
            order={"timestamp": "asc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("reflect_on_recent 조회 실패: %s", exc)
        return 0

    count = 0
    for m in pending:
        score, lesson = await _evaluate_outcome(m)
        await update_outcome(m.id, str(score), score, lesson)
        count += 1
    return count


async def _evaluate_outcome(memory) -> tuple[float, str | None]:
    """결정의 결과 평가 — 간단 휴리스틱.

    더 정교한 평가 (액션 전후 메트릭 비교, GrowthDecision 추적) 는 후속 작업.
    현재 룰:
      * actionTaken 안에 ``executed`` 가 있으면 +0.7
      * 모두 ``blocked`` 이면 -0.3
      * ``no_action`` 만 있으면 0.5 (정상 휴식)
      * ``pending_approval`` 만 있으면 0.4
    """
    action_taken = (getattr(memory, "actionTaken", "") or "").lower()

    if not action_taken:
        return 0.0, None

    if "executed" in action_taken:
        return 0.7, "결정 실행됨, 추후 메트릭 비교 필요"
    if "no_action" in action_taken:
        return 0.5, None
    if "pending_approval" in action_taken:
        return 0.4, "사람 승인 대기 — GrowthDecision 추적 필요"
    if "blocked" in action_taken:
        return -0.3, "결정이 가드레일에 막힘 — 액션 카탈로그 점검 필요"

    return 0.0, None


__all__ = [
    "cognitive_cycle",
    "observe",
    "reflect_on_recent",
    "AVAILABLE_ACTIONS",
    "REQUIRES_APPROVAL",
    "COGNITIVE_ENABLED",
    "MAX_ACTIONS_PER_DAY",
]
