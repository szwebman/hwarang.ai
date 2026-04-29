"""고급 가드레일 — 무한루프 / 비용 / 자가 종료 (Phase 6 보강).

기존 ``guardrails.py`` 가 단일 결정의 액션 카탈로그/승인 디스패치를 담당하면,
``guardrails_advanced.py`` 는 사이클 전체의 "메타 안전" 을 본다:

* ``detect_infinite_loop``  — 같은 액션이 일일 한도 초과면 차단
* ``check_cost_budget``     — 누적 LLM 토큰 (reasoning+decision 길이 기반 추정) 한도
* ``check_health``          — 실패율 / 평균 outcome / 액션 다양성 종합
* ``should_self_disable``   — 위 3 신호 + 연속 실패로 자가 종료 판정
* ``emergency_disable``     — 비상 비활성 (DB flag + 관리자 알림)
* ``is_cognitive_enabled``  — 런타임 비활성 체크 (env + DB flag)

DB flag 는 ``SystemSetting(key="cognitive_<actor>_disabled", value=<JSON>)`` 으로
관리한다. 스키마에 ``metadata`` 컬럼이 없어 reasons/disabled_at 은 ``value`` JSON
안에 인라인으로 저장한다.
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 한도 (env 로 오버라이드 가능)
# ---------------------------------------------------------------------------
MAX_SAME_ACTION_PER_DAY = int(os.getenv("HWARANG_COGNITIVE_MAX_SAME_ACTION", "5"))
MAX_LLM_TOKENS_PER_DAY = int(
    os.getenv("HWARANG_COGNITIVE_MAX_LLM_TOKENS_DAY", "1000000")
)
MAX_FAILED_CYCLES_BEFORE_DISABLE = int(
    os.getenv("HWARANG_COGNITIVE_MAX_FAILED_CYCLES", "5")
)


def _today_start_utc() -> datetime:
    return datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


# ---------------------------------------------------------------------------
# 무한루프 감지
# ---------------------------------------------------------------------------
async def detect_infinite_loop(actor: str, planned_action: str) -> bool:
    """같은 액션이 오늘 ``MAX_SAME_ACTION_PER_DAY`` 회 이상이면 True."""
    if not planned_action:
        return False
    try:
        same_action_count = await prisma.cognitivememory.count(
            where={
                "actor": actor,
                "actionTaken": {"contains": planned_action},
                "timestamp": {"gte": _today_start_utc()},
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("detect_infinite_loop 조회 실패: %s", exc)
        return False

    if same_action_count >= MAX_SAME_ACTION_PER_DAY:
        logger.warning(
            "무한루프 감지: %s 가 '%s' 을 %d회 시도",
            actor,
            planned_action,
            same_action_count,
        )
        return True
    return False


# ---------------------------------------------------------------------------
# 비용 추적
# ---------------------------------------------------------------------------
async def check_cost_budget(actor: str) -> dict:
    """LLM 비용 누적 체크 — reasoning+decision 길이로 토큰 추정 (≈ chars/4)."""
    try:
        today_memories = await prisma.cognitivememory.find_many(
            where={"actor": actor, "timestamp": {"gte": _today_start_utc()}},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("check_cost_budget 조회 실패: %s", exc)
        today_memories = []

    estimated_tokens = sum(
        (len(getattr(m, "reasoning", "") or "")
         + len(getattr(m, "decision", "") or "")) // 4
        for m in today_memories
    )

    return {
        "estimated_tokens_today": estimated_tokens,
        "limit": MAX_LLM_TOKENS_PER_DAY,
        "usage_pct": (
            estimated_tokens / MAX_LLM_TOKENS_PER_DAY
            if MAX_LLM_TOKENS_PER_DAY
            else 0
        ),
        "exceeded": estimated_tokens >= MAX_LLM_TOKENS_PER_DAY,
        "memories_counted": len(today_memories),
    }


# ---------------------------------------------------------------------------
# 건강 상태
# ---------------------------------------------------------------------------
async def check_health(actor: str) -> dict:
    """전체 건강 상태 — 사이클이 잘 동작하는지 (24시간)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        recent = await prisma.cognitivememory.find_many(
            where={"actor": actor, "timestamp": {"gte": cutoff}},
            order={"timestamp": "desc"},
            take=50,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("check_health 조회 실패: %s", exc)
        recent = []

    if not recent:
        return {
            "healthy": True,
            "reason": "no_recent_activity",
            "cycles_24h": 0,
        }

    # 실패율
    failed = sum(
        1
        for m in recent
        if getattr(m, "outcomeScore", None) is not None
        and m.outcomeScore < 0.3
    )
    failure_rate = failed / len(recent)

    # 평균 outcome
    scored = [m for m in recent if getattr(m, "outcomeScore", None) is not None]
    avg_score = (
        sum(m.outcomeScore for m in scored) / len(scored) if scored else 0.5
    )

    # 액션 다양성 — 한 액션 점유율이 70% 넘으면 단조
    actions = Counter(
        getattr(m, "actionTaken", None) or "no_action" for m in recent
    )
    most_common_action, most_common_count = actions.most_common(1)[0]
    diversity = 1 - (most_common_count / len(recent))

    healthy = (
        failure_rate < 0.5
        and avg_score > 0.4
        and diversity > 0.3
    )

    return {
        "healthy": healthy,
        "failure_rate": round(failure_rate, 3),
        "avg_outcome_score": round(avg_score, 3),
        "action_diversity": round(diversity, 3),
        "most_common_action": most_common_action,
        "most_common_action_count": most_common_count,
        "cycles_24h": len(recent),
        "scored_cycles": len(scored),
    }


# ---------------------------------------------------------------------------
# 자가 종료 판정
# ---------------------------------------------------------------------------
async def should_self_disable(actor: str) -> dict:
    """자가 종료 판단 — 3 신호 (건강 / 비용 / 연속실패) 중 하나라도 ON 이면 종료."""
    health = await check_health(actor)
    cost = await check_cost_budget(actor)

    reasons: list[str] = []
    if not health.get("healthy", True) and health.get("cycles_24h", 0) > 0:
        reasons.append(
            f"건강도 낮음 (avg={health.get('avg_outcome_score')}, "
            f"diversity={health.get('action_diversity')}, "
            f"failure_rate={health.get('failure_rate')})"
        )
    if cost.get("exceeded"):
        reasons.append(
            f"비용 한도 초과 ({cost['estimated_tokens_today']}/{cost['limit']} 토큰)"
        )

    # 연속 실패 — 최근 2시간 outcomeScore < 0.3
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    try:
        recent_failed = await prisma.cognitivememory.count(
            where={
                "actor": actor,
                "timestamp": {"gte": cutoff},
                "outcomeScore": {"lt": 0.3},
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("연속실패 조회 실패: %s", exc)
        recent_failed = 0

    if recent_failed >= MAX_FAILED_CYCLES_BEFORE_DISABLE:
        reasons.append(f"연속 실패 {recent_failed}회 (최근 2h)")

    return {
        "should_disable": bool(reasons),
        "reasons": reasons,
        "health": health,
        "cost": cost,
        "recent_failed_2h": recent_failed,
    }


# ---------------------------------------------------------------------------
# 비상 비활성 + 알림
# ---------------------------------------------------------------------------
async def emergency_disable(actor: str, reasons: list[str]) -> None:
    """비상 비활성 — DB flag 표시 + 관리자 알림."""
    logger.error("Cognitive 비상 비활성: %s — %s", actor, reasons)

    payload = {
        "disabled": True,
        "reasons": reasons,
        "disabled_at": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
    }
    value_str = json.dumps(payload, ensure_ascii=False)[:1000]

    # 관리자 알림 (notifier)
    try:
        from hwarang_api.knowledge.notifier import notify_admin

        await notify_admin(
            f"[Cognitive Layer 자가 비활성]\n"
            f"Actor: {actor}\n"
            f"이유: {', '.join(reasons)}\n\n"
            f"관리자 검토 후 ``/api/cognitive/enable`` 또는 환경변수로 재활성 필요.",
            severity="critical",
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("notify_admin 실패: %s", exc)

    # DB flag 저장 — SystemSetting 에 metadata 가 없으므로 value 안에 JSON 인라인.
    key = f"cognitive_{actor}_disabled"
    try:
        await prisma.systemsetting.upsert(
            where={"key": key},
            data={
                "create": {"key": key, "value": value_str},
                "update": {"value": value_str},
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("SystemSetting 저장 실패: %s", exc)


# ---------------------------------------------------------------------------
# 활성화 체크
# ---------------------------------------------------------------------------
async def is_cognitive_enabled(actor: str = "master") -> bool:
    """런타임 비활성 체크 — env + DB flag.

    1. ``HWARANG_COGNITIVE_ENABLED=false`` 면 즉시 False
    2. ``SystemSetting(cognitive_<actor>_disabled).value`` 가 비어있지 않고
       JSON 의 ``disabled=True`` 또는 단순 "true" 면 False
    """
    if os.getenv("HWARANG_COGNITIVE_ENABLED", "true").lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False

    try:
        setting = await prisma.systemsetting.find_unique(
            where={"key": f"cognitive_{actor}_disabled"},
        )
    except Exception:  # noqa: BLE001
        setting = None

    if not setting:
        return True

    value = (getattr(setting, "value", "") or "").strip()
    if not value:
        return True
    if value.lower() in ("true", "1", "yes", "on"):
        return False
    try:
        data = json.loads(value)
        if isinstance(data, dict) and data.get("disabled"):
            return False
    except Exception:  # noqa: BLE001
        # 미파싱 — 안전하게 활성으로 간주
        return True
    return True


async def clear_disable_flag(actor: str = "master") -> bool:
    """수동 재활성 — DB flag 삭제."""
    try:
        await prisma.systemsetting.delete(
            where={"key": f"cognitive_{actor}_disabled"},
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("clear_disable_flag: %s", exc)
        return False


__all__ = [
    "MAX_SAME_ACTION_PER_DAY",
    "MAX_LLM_TOKENS_PER_DAY",
    "MAX_FAILED_CYCLES_BEFORE_DISABLE",
    "detect_infinite_loop",
    "check_cost_budget",
    "check_health",
    "should_self_disable",
    "emergency_disable",
    "is_cognitive_enabled",
    "clear_disable_flag",
]
