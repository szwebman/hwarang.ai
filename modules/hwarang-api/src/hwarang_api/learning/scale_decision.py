"""HSEE Phase 3 — 베이스 모델 확장 결정.

LoRA 추가만으로 더는 품질 개선이 안 될 때 베이스 모델 자체를 키울지 판단한다.

조건 (모두 만족 시 ``scale_base`` 권장):
- 30 일 평균 ``satisfactionAvg`` < 0.7
- 30 일 평균 ``factualAccuracy`` < 0.7
- 활성 LoRA 가 5 개 이상인데도 위 두 메트릭이 개선되지 않음

권장 액션:
- ``depth_up_scaling`` — Solar 식 깊이 확장 (mergekit passthrough)
- ``moe_conversion`` — Mixture-of-Experts 변환
- ``base_replace``    — 더 큰 사전학습 베이스로 교체

실제 실행은 외부 mergekit / 학습 파이프라인이 담당. 여기서는 ``GrowthDecision``
형태로 권장만 기록.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


# 임계치 — 모두 30 일 평균 기준
SAT_THRESHOLD = 0.7
FACTUAL_THRESHOLD = 0.7
LORA_COUNT_THRESHOLD = 5


def _prisma_ready() -> bool:
    try:
        return bool(prisma.is_connected())
    except Exception:
        return False


def _days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


# ────────────────────────────────────────────────────────────
# 메인 판단
# ────────────────────────────────────────────────────────────
async def should_scale_base(window_days: int = 30) -> dict[str, Any]:
    """베이스 모델 확장이 필요한지 종합 판단.

    Returns
    -------
    dict
        ``{should_scale, avg_satisfaction, avg_factual, lora_count, recommendation, ...}``.
    """
    if not _prisma_ready():
        return {
            "should_scale": False,
            "reason": "db_unavailable",
        }

    cutoff = _days_ago(window_days)

    try:
        metrics = await prisma.capabilitymetric.find_many(
            where={"measuredAt": {"gte": cutoff}},
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"CapabilityMetric 조회 실패: {e}")
        return {"should_scale": False, "reason": f"db_error:{e}"}

    sat_vals = [m.satisfactionAvg for m in metrics if m.satisfactionAvg is not None]
    fact_vals = [m.factualAccuracy for m in metrics if m.factualAccuracy is not None]
    avg_sat = sum(sat_vals) / len(sat_vals) if sat_vals else None
    avg_fact = sum(fact_vals) / len(fact_vals) if fact_vals else None

    # 활성 LoRA 개수
    try:
        lora_count = await prisma.aimodel.count(
            where={"loraName": {"not": None}, "isActive": True}
        )
    except Exception:  # pragma: no cover
        lora_count = 0

    # 최근 LoRA 학습 잡 효과 — 최근 done 잡들의 qualityScore 가 정체됐는지
    plateau = await _is_lora_plateaued(window_days=window_days)

    # 종합 판단
    needs_scale = (
        avg_sat is not None
        and avg_fact is not None
        and avg_sat < SAT_THRESHOLD
        and avg_fact < FACTUAL_THRESHOLD
        and lora_count >= LORA_COUNT_THRESHOLD
        and plateau
    )

    recommendation = _recommend_strategy(
        avg_sat=avg_sat, avg_fact=avg_fact, lora_count=lora_count
    )

    return {
        "should_scale": bool(needs_scale),
        "avg_satisfaction": avg_sat,
        "avg_factual": avg_fact,
        "lora_count": lora_count,
        "lora_plateaued": plateau,
        "thresholds": {
            "sat": SAT_THRESHOLD,
            "factual": FACTUAL_THRESHOLD,
            "lora_count": LORA_COUNT_THRESHOLD,
        },
        "recommendation": recommendation if needs_scale else "stay",
        "window_days": window_days,
    }


async def _is_lora_plateaued(window_days: int) -> bool:
    """최근 LoRA 학습 잡들의 qualityScore 가 정체/하락했는지.

    최근 5 개 done 잡의 qualityScore 평균 vs 이전 5 개 비교.
    개선 < 5%p 이면 plateau 로 간주.
    """
    try:
        recent = await prisma.trainingjob.find_many(
            where={"status": "done", "qualityScore": {"not": None}},
            order={"completedAt": "desc"},
            take=10,
        )
    except Exception:  # pragma: no cover
        return False

    if len(recent) < 6:
        return False

    half = len(recent) // 2
    new_avg = sum(j.qualityScore for j in recent[:half]) / half
    old_avg = sum(j.qualityScore for j in recent[half:]) / (len(recent) - half)
    return (new_avg - old_avg) < 0.05


def _recommend_strategy(
    avg_sat: Optional[float],
    avg_fact: Optional[float],
    lora_count: int,
) -> str:
    """간단한 룰 — 만족도가 더 낮으면 depth, 사실성이 더 낮으면 MoE."""
    if avg_sat is None or avg_fact is None:
        return "stay"
    if avg_sat < avg_fact - 0.1:
        return "depth_up_scaling"
    if lora_count >= 8:
        return "moe_conversion"
    return "depth_up_scaling"


# ────────────────────────────────────────────────────────────
# GrowthDecision 으로 등록
# ────────────────────────────────────────────────────────────
async def propose_scale_decision_if_needed() -> Optional[dict[str, Any]]:
    """``should_scale=True`` 면 ``GrowthDecision(scale_base, status=proposed)`` 생성.

    이미 동일한 미처리 결정이 있으면 skip.
    사람 승인 필수 — 자동 실행 안 함.
    """
    if not _prisma_ready():
        return None

    check = await should_scale_base()
    if not check.get("should_scale"):
        return {"proposed": False, **check}

    # 중복 회피
    try:
        existing = await prisma.growthdecision.find_first(
            where={
                "decisionType": "scale_base",
                "status": {"in": ["proposed", "approved", "executing"]},
            },
        )
    except Exception:  # pragma: no cover
        existing = None
    if existing:
        return {"proposed": False, "reason": "already_pending", "id": existing.id}

    try:
        row = await prisma.growthdecision.create(
            data={
                "decisionType": "scale_base",
                "triggerDomain": None,
                "triggerMetric": "global_quality_low",
                "triggerValue": float(check["avg_satisfaction"] or 0.0),
                "proposalJson": check,
                "status": "proposed",
            }
        )
        return {"proposed": True, "id": row.id, **check}
    except Exception as e:  # pragma: no cover
        logger.warning(f"propose_scale_decision 실패: {e}")
        return {"proposed": False, "error": str(e)}


__all__ = [
    "should_scale_base",
    "propose_scale_decision_if_needed",
    "SAT_THRESHOLD",
    "FACTUAL_THRESHOLD",
    "LORA_COUNT_THRESHOLD",
]
