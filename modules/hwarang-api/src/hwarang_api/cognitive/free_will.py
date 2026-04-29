"""Free Will Mode — 자율적 연속 사고 (Phase 7).

기존 ``cognitive_cycle`` 은 cron 기반 (매 15 분 강제).
자유의사 모드는 다음 차이점을 가진다:

* 사이클 종료 시 다음 간격을 자기가 결정 (1 분 ~ 30 분)
* 새 자극 (사용자 행동, 외부 이벤트) 감지 시 즉시 사고
* 한가할 때 (모든 메트릭 안정) 길게 쉼
* 위기 상황 (실패율 ↑, 사용자 불만족) 시 빠르게 사고

기본은 OFF (``HWARANG_FREEWILL_ENABLED=false``). 검증 후 활성.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone

from hwarang_api.cognitive.master_loop import cognitive_cycle, observe
from hwarang_api.cognitive.memory import get_recent_lessons, record_decision
from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 환경 변수 — 적응적 간격 한도
# ---------------------------------------------------------------------------
def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


MIN_INTERVAL_SEC = _env_int("HWARANG_FREEWILL_MIN_SEC", 60)        # 1 분
MAX_INTERVAL_SEC = _env_int("HWARANG_FREEWILL_MAX_SEC", 1800)       # 30 분
DEFAULT_INTERVAL_SEC = 900                                          # 15 분 (Phase 6 폴백)


# ---------------------------------------------------------------------------
# 루프 상태
# ---------------------------------------------------------------------------
_running: bool = False
_current_interval: int = DEFAULT_INTERVAL_SEC
_interrupt_event: asyncio.Event = asyncio.Event()


# ---------------------------------------------------------------------------
# 메인 루프
# ---------------------------------------------------------------------------
async def free_will_loop() -> None:
    """무한 루프 — 자기가 다음 사이클 간격 결정.

    종료 조건:
        * ``stop_free_will()`` 호출
        * ``HWARANG_FREEWILL_ENABLED`` 가 ``true`` 가 아닐 때 (시작 시점 체크)

    동작:
        1. 비활성화 체크 (cognitive 자체가 disabled 면 5 분 후 재체크)
        2. 사이클 1 회 실행
        3. 결과로 다음 간격 결정 (위기 = 짧게, 안정 = 길게)
        4. 외부 자극 인터럽트 가능한 sleep
    """
    global _running, _current_interval

    if _running:
        logger.info("Free Will loop already running")
        return

    _running = True
    logger.info("Free Will 모드 시작 (min=%ds, max=%ds)", MIN_INTERVAL_SEC, MAX_INTERVAL_SEC)

    while _running:
        # 1. cognitive 자체가 비활성이면 5분 대기
        try:
            from hwarang_api.cognitive.guardrails_advanced import is_cognitive_enabled

            if not await is_cognitive_enabled("master"):
                logger.info("Cognitive disabled — Free Will 5분 일시정지")
                try:
                    await asyncio.wait_for(_interrupt_event.wait(), timeout=300)
                    _interrupt_event.clear()
                except asyncio.TimeoutError:
                    pass
                continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("guardrail 체크 실패 (계속 진행): %s", exc)

        # 2. 사이클 실행
        next_interval = DEFAULT_INTERVAL_SEC
        try:
            result = await cognitive_cycle(actor="master")

            # 3. 다음 간격 결정 — observation 기반 적응적
            next_interval = await decide_next_interval(result)
            _current_interval = next_interval

            logger.info(
                "Free Will 사이클 완료 — 다음 사이클: %ds 후 (결정 %d, 실행 %d)",
                next_interval,
                result.get("decisions_made", 0),
                result.get("actions_executed", 0),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Free Will 사이클 실패: %s", exc)
            next_interval = MIN_INTERVAL_SEC * 5  # 5 분 wait on error

        # 4. 외부 자극 감지 시 즉시 깨움
        await wait_or_interrupt(next_interval)


# ---------------------------------------------------------------------------
# 적응적 간격 결정
# ---------------------------------------------------------------------------
async def decide_next_interval(last_cycle_result: dict) -> int:
    """다음 사이클 간격 — 적응적.

    규칙 (위기 → 짧게, 안정 → 길게):
        1. RLHF 만족도 < 0.5         → 1 분 (사용자 불만족 ↑)
        2. open_gaps > 50             → 3 분 (gap 폭주)
        3. crawl_failed > 100         → 2 분 (크롤 위기)
        4. actions_executed >= 3      → 5 분 (사고 활발)
        5. decisions >= 2 OR pending >= 1 → 7.5 분 (보통 활동)
        6. 모두 안정                   → 30 분 (휴식)

    기본은 ``DEFAULT_INTERVAL_SEC`` (15 분).
    """
    decisions = last_cycle_result.get("decisions_made", 0) or 0
    executed = last_cycle_result.get("actions_executed", 0) or 0
    pending_approval = last_cycle_result.get("actions_pending_approval", 0) or 0

    # 외부 메트릭
    try:
        obs = await observe()
    except Exception as exc:  # noqa: BLE001
        logger.warning("observe 실패 (default interval): %s", exc)
        return DEFAULT_INTERVAL_SEC

    rlhf_satisfaction = obs.get("rlhf_satisfaction_7d", 0.7) or 0.7
    open_gaps = obs.get("open_gaps", 0) or 0
    crawl_failed = obs.get("crawl_queue_failed", 0) or 0
    new_facts_24h = obs.get("new_facts_24h", 0) or 0

    # ── 위기 신호 — 빠르게 사고 ────────────────────────────────
    if rlhf_satisfaction < 0.5:
        return MIN_INTERVAL_SEC                # 1 분
    if open_gaps > 50:
        return MIN_INTERVAL_SEC * 3            # 3 분
    if crawl_failed > 100:
        return MIN_INTERVAL_SEC * 2            # 2 분

    # ── 활발 신호 — 짧게 ─────────────────────────────────────
    if executed >= 3:
        return MIN_INTERVAL_SEC * 5            # 5 분
    if decisions >= 2 or pending_approval >= 1:
        return DEFAULT_INTERVAL_SEC // 2       # 7.5 분

    # ── 안정 — 길게 (휴식) ──────────────────────────────────
    if rlhf_satisfaction > 0.85 and open_gaps < 10 and new_facts_24h < 50:
        return MAX_INTERVAL_SEC                # 30 분

    return DEFAULT_INTERVAL_SEC                # 15 분 기본


# ---------------------------------------------------------------------------
# 외부 자극 인터럽트
# ---------------------------------------------------------------------------
async def wait_or_interrupt(seconds: int) -> None:
    """sleep 하다가 인터럽트 시 즉시 깨움."""
    try:
        await asyncio.wait_for(_interrupt_event.wait(), timeout=max(1, seconds))
        _interrupt_event.clear()
        logger.info("외부 자극 감지 — 즉시 사고")
    except asyncio.TimeoutError:
        pass


def trigger_immediate_cycle(reason: str = "external_stimulus") -> None:
    """외부에서 호출 — 다음 사이클 즉시 시작."""
    logger.info("Free Will 즉시 트리거: %s", reason)
    _interrupt_event.set()


def stop_free_will() -> None:
    """루프 종료 (다음 인터럽트 시점에 종료)."""
    global _running
    _running = False
    _interrupt_event.set()


def is_running() -> bool:
    return _running


def current_interval() -> int:
    return _current_interval


# ---------------------------------------------------------------------------
# Free Will Goal Cycle — 매일 1번 LLM 으로 새 목표 자유 생성
# ---------------------------------------------------------------------------
async def free_will_goal_cycle() -> dict:
    """매일 1 번 (예: 새벽 1 시) — 창의적 목표 생성.

    실제 생성 로직은 ``goal_generator.py`` 에 있고, 이 함수는 thin wrapper.
    스케줄러가 직접 호출하기 좋게 cognitive 패키지 표면에 노출.
    """
    from hwarang_api.cognitive.goal_generator import (
        generate_creative_goals,
        queue_goal_as_decision,
    )

    obs = await observe()
    goals = await generate_creative_goals(obs)

    if not goals:
        return {"goals_generated": 0, "queued_for_approval": 0}

    memory_id = await record_decision(
        actor="master",
        observed=obs,
        reasoning=f"자유의사 모드 — 창의적 목표 {len(goals)}개 생성",
        decision=json.dumps([g.get("title", "") for g in goals], ensure_ascii=False),
        action_taken="generate_creative_goals",
    )

    decision_ids: list[str] = []
    for g in goals[:2]:  # 최대 2 개
        try:
            did = await queue_goal_as_decision(g, memory_id)
            decision_ids.append(did)
        except Exception as exc:  # noqa: BLE001
            logger.warning("queue_goal_as_decision 실패: %s", exc)

    return {
        "goals_generated": len(goals),
        "queued_for_approval": len(decision_ids),
        "decision_ids": decision_ids,
        "memory_id": memory_id,
    }


__all__ = [
    "free_will_loop",
    "decide_next_interval",
    "wait_or_interrupt",
    "trigger_immediate_cycle",
    "stop_free_will",
    "is_running",
    "current_interval",
    "free_will_goal_cycle",
    "MIN_INTERVAL_SEC",
    "MAX_INTERVAL_SEC",
    "DEFAULT_INTERVAL_SEC",
]
