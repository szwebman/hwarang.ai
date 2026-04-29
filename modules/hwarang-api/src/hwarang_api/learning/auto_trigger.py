"""학습 자동 트리거.

조건이 만족되면 HFL 라운드를 시작하거나 LoRA 학습 잡을 큐에 푸시한다.

기본 정책:
- 도메인별 최근 24 시간 ``RLHFFeedback`` 누적 ≥ ``MIN_SAMPLES_PER_ROUND``
- ``isSatisfied`` 가 부정인 비율이 ``MIN_NEGATIVE_RATIO`` 이상 (= 개선 여지)
- 같은 도메인의 활성 라운드가 없을 때

내부적으로는 ``hwarang_api.routers.grid.start_round`` 와 동일한 인메모리 라운드 객체를
직접 만든다 — 별도 HTTP 호출 없이.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)

MIN_SAMPLES_PER_ROUND = int(os.getenv("HSEE_MIN_SAMPLES_PER_ROUND", "1000"))
MIN_NEGATIVE_RATIO = float(os.getenv("HSEE_MIN_NEGATIVE_RATIO", "0.10"))
COOLDOWN_HOURS = int(os.getenv("HSEE_TRIGGER_COOLDOWN_HOURS", "6"))

# 도메인별 마지막 트리거 시각 (인메모리). 실제로는 SystemSetting 으로 영속화 가능.
_last_trigger: dict[str, float] = {}
_lock = asyncio.Lock()


def _prisma_ready() -> bool:
    try:
        return bool(prisma.is_connected())
    except Exception:
        return False


async def maybe_trigger_training(domain: str) -> dict:
    """조건 충족 시 HFL 라운드 시작.

    반환:
    - ``{"triggered": False, "reason": "..."}`` (조건 불만족)
    - ``{"triggered": True, "round_id": "...", ...}``
    """
    domain = (domain or "general").strip().lower()
    now_ts = time.time()

    # 1) 쿨다운 (같은 도메인 너무 자주 안 돌게)
    last = _last_trigger.get(domain)
    if last and (now_ts - last) < COOLDOWN_HOURS * 3600:
        return {
            "triggered": False,
            "reason": "cooldown",
            "domain": domain,
            "next_eligible_in_sec": int(COOLDOWN_HOURS * 3600 - (now_ts - last)),
        }

    if not _prisma_ready():
        return {"triggered": False, "reason": "db_unavailable", "domain": domain}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        total = await prisma.rlhffeedback.count(
            where={"domain": domain, "createdAt": {"gte": cutoff}},
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"RLHFFeedback count 실패: {e}")
        return {"triggered": False, "reason": f"db_error:{e}", "domain": domain}

    if total < MIN_SAMPLES_PER_ROUND:
        return {
            "triggered": False,
            "reason": "insufficient_samples",
            "domain": domain,
            "count": total,
            "needed": MIN_SAMPLES_PER_ROUND,
        }

    # 2) 부정 피드백 비율 — 개선 여지가 있어야 학습 의미
    try:
        neg = await prisma.rlhffeedback.count(
            where={
                "domain": domain,
                "createdAt": {"gte": cutoff},
                "isSatisfied": False,
            },
        )
    except Exception:
        neg = 0

    neg_ratio = neg / total if total else 0.0
    if neg_ratio < MIN_NEGATIVE_RATIO:
        return {
            "triggered": False,
            "reason": "insufficient_negative_signal",
            "domain": domain,
            "count": total,
            "negative_ratio": round(neg_ratio, 3),
            "needed_ratio": MIN_NEGATIVE_RATIO,
        }

    # 3) 라운드 시작
    async with _lock:
        # 동시 진입 보호 — lock 안에서 다시 한 번 쿨다운 체크
        last = _last_trigger.get(domain)
        if last and (time.time() - last) < COOLDOWN_HOURS * 3600:
            return {"triggered": False, "reason": "cooldown_race", "domain": domain}

        try:
            result = await _start_round_internal(domain=domain)
        except Exception as e:  # pragma: no cover
            logger.warning(f"라운드 시작 실패: {e}")
            return {"triggered": False, "reason": f"start_failed:{e}", "domain": domain}

        _last_trigger[domain] = time.time()

    return {
        "triggered": True,
        "domain": domain,
        "samples": total,
        "negative_ratio": round(neg_ratio, 3),
        **result,
    }


async def _start_round_internal(domain: str) -> dict:
    """``routers.grid`` 의 인메모리 라운드를 직접 생성.

    HTTP 콜 없이 동일 프로세스 내에서 트리거. 실제 학습은 grid 모듈이 진행.
    """
    try:
        from hwarang_api.routers import grid as grid_router  # 순환 import 방지
    except Exception as e:  # pragma: no cover
        return {"round_id": None, "error": f"grid_module_unavailable:{e}"}

    if grid_router._current_round and grid_router._current_round.get("status") in (
        "training",
        "collecting",
    ):
        return {
            "round_id": grid_router._current_round.get("round_id"),
            "status": "already_running",
            "domain": grid_router._current_round.get("domain"),
        }

    cutoff = time.time() - 60
    active = [a for a in grid_router._agents.values() if a["last_heartbeat"] > cutoff]
    eligible = [a for a in active if a["tier"] in ("standard", "full")]

    if not eligible:
        return {"round_id": None, "error": "no_eligible_agents", "active": len(active)}

    round_number = len(grid_router._round_history) + 1
    round_id = f"round_{round_number}_{int(time.time())}_{domain}"

    grid_router._current_round = {
        "round_id": round_id,
        "round_number": round_number,
        "status": "training",
        "domain": domain,
        "config": {
            "lora_r": 16,
            "lora_alpha": 32,
            "learning_rate": 2e-4,
            "steps_per_round": 100,
            "auto_triggered": True,
            "trigger_source": "hsee_compounding_loop",
        },
        "participants": [a["agent_id"] for a in eligible],
        "submissions": [],
        "started_at": time.time(),
    }

    logger.info(
        f"[HSEE auto-trigger] domain={domain} round={round_id} "
        f"participants={len(eligible)}"
    )

    return {
        "round_id": round_id,
        "round_number": round_number,
        "participants": len(eligible),
        "participant_ids": [a["agent_id"] for a in eligible],
    }


async def trigger_status() -> dict[str, Any]:
    """현재 도메인별 트리거 상태 (관리자용)."""
    return {
        "min_samples_per_round": MIN_SAMPLES_PER_ROUND,
        "min_negative_ratio": MIN_NEGATIVE_RATIO,
        "cooldown_hours": COOLDOWN_HOURS,
        "last_trigger": {d: ts for d, ts in _last_trigger.items()},
    }


__all__ = ["maybe_trigger_training", "trigger_status"]
