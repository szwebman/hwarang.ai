"""HSEE Phase 3 — 종합 성장 계획 (Daily Growth Cycle).

매일 (예: 자정 cron) 호출되어 다음 사이클을 일괄 실행:

1. **능력 측정** — :func:`capability_monitor.measure_all_domains`
2. **새 도메인 발견** — :func:`domain_clustering.discover_emergent_domains`
3. **Growth 제안** — :func:`auto_spawn.evaluate_and_propose`
4. **베이스 확장 필요 판단** — :func:`scale_decision.propose_scale_decision_if_needed`
5. **자동 승인 + 실행** — 낮은 위험 결정만 (``spawn_lora`` 한정).
   ``split_domain``, ``scale_base``, ``expand_lora_rank`` 는 사람 승인 필수.

자동 승인 정책:
- ``spawn_lora`` 중 ``trigger_metric=emergent_domain`` 또는 ``low_factual_accuracy`` 만 자동.
- ``split_domain`` / ``scale_base`` / ``expand_lora_rank`` 는 위험도가 높아 사람 승인 필수.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from hwarang_api.db import prisma
from hwarang_api.learning import auto_spawn, capability_monitor, scale_decision
from hwarang_api.learning import domain_clustering

logger = logging.getLogger(__name__)


# 자동 승인 정책 — 결정 타입 + 트리거 메트릭 화이트리스트
AUTO_APPROVE_RULES: set[tuple[str, str]] = {
    ("spawn_lora", "emergent_domain"),
    ("spawn_lora", "low_factual_accuracy"),
}


def _prisma_ready() -> bool:
    try:
        return bool(prisma.is_connected())
    except Exception:
        return False


# ────────────────────────────────────────────────────────────
# 일일 사이클
# ────────────────────────────────────────────────────────────
async def daily_growth_cycle(
    window_days: int = 7,
    auto_execute: bool = True,
) -> dict[str, Any]:
    """전체 사이클: 측정 → 클러스터링 → 제안 → 자동승인+실행.

    Parameters
    ----------
    window_days
        능력 측정 윈도우 (일).
    auto_execute
        화이트리스트 결정 자동 승인+실행 여부.
    """
    started = datetime.now(timezone.utc)
    summary: dict[str, Any] = {"startedAt": started.isoformat()}

    # 1) 능력 측정
    try:
        metrics = await capability_monitor.measure_all_domains(
            window_days=window_days
        )
        summary["metrics_domains"] = list(metrics.keys())
    except Exception as e:  # pragma: no cover
        logger.warning(f"measure_all_domains 실패: {e}")
        summary["metrics_error"] = str(e)
        metrics = {}

    # 2) 새 도메인 발견
    try:
        emergent = await domain_clustering.discover_emergent_domains()
        summary["emergent_count"] = len(emergent)
    except Exception as e:  # pragma: no cover
        logger.warning(f"discover_emergent_domains 실패: {e}")
        summary["emergent_error"] = str(e)
        emergent = []

    # 3) Growth 제안
    try:
        proposals = await auto_spawn.evaluate_and_propose(
            window_days=window_days
        )
        summary["new_proposals"] = len(proposals)
    except Exception as e:  # pragma: no cover
        logger.warning(f"evaluate_and_propose 실패: {e}")
        summary["proposals_error"] = str(e)
        proposals = []

    # 4) 베이스 확장 필요 판단
    try:
        scale = await scale_decision.propose_scale_decision_if_needed()
        summary["scale_check"] = scale
    except Exception as e:  # pragma: no cover
        logger.warning(f"propose_scale_decision 실패: {e}")
        summary["scale_error"] = str(e)

    # 5) 자동 승인 + 실행
    if auto_execute:
        executed = await _auto_approve_and_execute()
        summary["auto_executed"] = executed
    else:
        summary["auto_executed"] = []

    summary["finishedAt"] = datetime.now(timezone.utc).isoformat()
    return summary


async def _auto_approve_and_execute() -> list[dict[str, Any]]:
    """화이트리스트 규칙에 맞는 ``proposed`` 결정을 자동 승인 후 실행."""
    if not _prisma_ready():
        return []

    try:
        candidates = await prisma.growthdecision.find_many(
            where={"status": "proposed"},
            order={"createdAt": "asc"},
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"GrowthDecision 조회 실패: {e}")
        return []

    out: list[dict[str, Any]] = []
    for d in candidates:
        key = (d.decisionType, d.triggerMetric or "")
        if key not in AUTO_APPROVE_RULES:
            continue

        approve = await auto_spawn.approve_decision(
            d.id, reviewed_by="auto:growth_planner"
        )
        if not approve.get("approved"):
            out.append({"id": d.id, "result": approve})
            continue

        result = await auto_spawn.execute_decision(d.id)
        out.append({"id": d.id, "type": d.decisionType, "result": result})

    return out


__all__ = [
    "daily_growth_cycle",
    "AUTO_APPROVE_RULES",
]
