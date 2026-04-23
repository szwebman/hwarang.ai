"""HLKM B4: 예측적 사실 + 베이지안 확률.

아직 확정되지 않은 사건(발의된 법안, 예정된 기술 출시 등)을
PENDING 상태로 저장하고, 과거 유사 사건들의 결과를 기반으로
베이지안 추론을 통해 확정 확률 및 예상 발효일을 예측한다.

사용 시나리오:
  - 국회 법안 발의 → PENDING, predicted_valid_from = 예상 시행일
  - 신약 임상 3상 → PENDING, prediction_confidence = 승인 확률
  - 실제 확정 시 transition_pending_to_confirmed() 호출.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma

from .types import KnowledgeFact, KnowledgeStatus, PredictionOutcome

logger = logging.getLogger(__name__)

_EPS = 1e-9
_DEFAULT_PRIOR = 0.5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ─────────────────────────────────────────────
# 베이지안 업데이트
# ─────────────────────────────────────────────
def bayesian_update(prior: float, likelihoods: list[tuple[float, float]]) -> float:
    """순차적 베이지안 갱신.

    Args:
        prior: P(H) - 사건 발생 사전확률.
        likelihoods: (P(E|H), P(E|¬H)) 튜플 리스트.

    Returns:
        posterior P(H|E₁,…,Eₙ).
    """
    posterior = min(max(prior, _EPS), 1.0 - _EPS)

    for p_e_given_h, p_e_given_not_h in likelihoods:
        p_e_given_h = min(max(p_e_given_h, _EPS), 1.0 - _EPS)
        p_e_given_not_h = min(max(p_e_given_not_h, _EPS), 1.0 - _EPS)

        numerator = p_e_given_h * posterior
        denominator = numerator + p_e_given_not_h * (1.0 - posterior)
        if denominator <= 0:
            continue
        posterior = numerator / denominator

    return max(0.0, min(1.0, posterior))


# ─────────────────────────────────────────────
# 과거 기저 확률
# ─────────────────────────────────────────────
async def historical_base_rate(domain: str, event_type: str) -> float:
    """과거 동일 도메인/event_type 의 PENDING 사실이
    CONFIRMED 로 전이된 비율을 반환.

    샘플이 부족하면 _DEFAULT_PRIOR 로 폴백.
    """
    past = await prisma.knowledgefact.find_many(
        where={
            "domain": domain,
            "tags": {"has": event_type},
            "status": {"in": [KnowledgeStatus.CONFIRMED.value, KnowledgeStatus.EXPIRED.value]},
        },
        take=500,
    )
    if len(past) < 5:
        return _DEFAULT_PRIOR

    confirmed = sum(1 for p in past if p.status == KnowledgeStatus.CONFIRMED.value)
    total = len(past)
    # Laplace smoothing
    rate = (confirmed + 1) / (total + 2)
    return max(0.01, min(0.99, rate))


# ─────────────────────────────────────────────
# 개별 예측
# ─────────────────────────────────────────────
async def predict_fact_outcome(fact_id: str) -> PredictionOutcome:
    """PENDING 사실의 확정 확률과 예상 발효일을 계산."""
    from .graph import find_related  # 순환 import 방지

    row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if row is None:
        raise ValueError(f"fact not found: {fact_id}")

    event_type = (row.tags[0] if row.tags else "generic")
    prior = await historical_base_rate(row.domain, event_type)

    # 관련 사실(동일 domain/entity) 조회
    related: list[Any] = []
    try:
        related = (await find_related(fact_id, min_strength=0.3))[:20]
    except Exception as exc:  # noqa: BLE001
        logger.debug("find_related fallback: %s", exc)

    likelihoods: list[tuple[float, float]] = []
    signals: list[str] = []

    for r in related:
        # r 은 dict 또는 object 일 수 있음
        rel_type = (r.get("relation_type") if isinstance(r, dict) else getattr(r, "relation_type", None)) or "RELATED_TO"
        strength = float((r.get("strength") if isinstance(r, dict) else getattr(r, "strength", 0.5)) or 0.5)
        rel_status = (r.get("status") if isinstance(r, dict) else getattr(r, "status", None)) or "CONFIRMED"

        if rel_type == "SUPPORTS" and rel_status == "CONFIRMED":
            likelihoods.append((0.7 + 0.2 * strength, 0.3))
            signals.append(f"지지 증거(strength={strength:.2f})")
        elif rel_type == "CONTRADICTS":
            likelihoods.append((0.3, 0.7 + 0.2 * strength))
            signals.append(f"반증(strength={strength:.2f})")
        elif rel_type == "DERIVED_FROM":
            likelihoods.append((0.6 + 0.1 * strength, 0.4))
            signals.append("선례 기반")
        elif rel_type in {"TEMPORAL_AFTER", "CAUSES", "ENABLES"}:
            likelihoods.append((0.6, 0.4))
            signals.append(f"인과 신호({rel_type})")

    posterior = bayesian_update(prior, likelihoods)

    # 예상 발효일 = 지금 + 도메인별 기본 지연
    default_days = {
        "law": 90,
        "regulation": 60,
        "technology": 30,
        "medical_guideline": 180,
        "general": 30,
    }
    delay = default_days.get(row.domain, 30)

    # 강한 지지 증거가 많으면 지연을 단축
    if posterior > 0.8:
        delay = int(delay * 0.6)
    elif posterior < 0.3:
        delay = int(delay * 1.5)

    predicted = _as_aware(row.predictedValidFrom or _utcnow()) + timedelta(days=delay)

    rationale = (
        f"prior={prior:.2f}, posterior={posterior:.2f}, "
        f"evidences={len(likelihoods)}, domain={row.domain}"
    )

    return PredictionOutcome(
        predicted_valid_from=predicted,
        confidence=posterior,
        rationale=rationale,
        contributing_signals=signals,
    )


# ─────────────────────────────────────────────
# 배치 갱신
# ─────────────────────────────────────────────
async def update_pending_predictions() -> int:
    """모든 PENDING 사실을 재예측해 DB 갱신."""
    rows = await prisma.knowledgefact.find_many(
        where={"status": KnowledgeStatus.PENDING.value},
        take=1000,
    )
    updated = 0
    for row in rows:
        try:
            out = await predict_fact_outcome(row.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("predict failed for %s: %s", row.id, exc)
            continue

        await prisma.knowledgefact.update(
            where={"id": row.id},
            data={
                "predictionConfidence": out.confidence,
                "predictedValidFrom": out.predicted_valid_from,
            },
        )
        updated += 1

    logger.info("update_pending_predictions: %d facts", updated)
    return updated


# ─────────────────────────────────────────────
# 상태 전이
# ─────────────────────────────────────────────
async def transition_pending_to_confirmed(fact_id: str, actual_valid_from: datetime) -> None:
    """PENDING → CONFIRMED 전환. valid_from 실제값 설정, 예측 필드 초기화."""
    row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if row is None:
        raise ValueError(f"fact not found: {fact_id}")
    if row.status != KnowledgeStatus.PENDING.value:
        logger.warning("transition_pending_to_confirmed: fact %s not PENDING (got %s)", fact_id, row.status)
        return

    await prisma.knowledgefact.update(
        where={"id": fact_id},
        data={
            "status": KnowledgeStatus.CONFIRMED.value,
            "validFrom": _as_aware(actual_valid_from),
            "lastVerifiedAt": _utcnow(),
            "predictedValidFrom": None,
            "predictionConfidence": None,
            "expiredReason": None,
        },
    )

    # 예측 정확도 로깅 (나중에 base_rate 학습에 반영 가능)
    if row.predictedValidFrom:
        gap_days = abs((_as_aware(row.predictedValidFrom) - _as_aware(actual_valid_from)).days)
        logger.info("prediction gap for %s: %d days", fact_id, gap_days)


async def transition_pending_to_expired(fact_id: str, reason: str) -> None:
    """PENDING 사실이 끝내 확정되지 않고 폐기될 때 호출."""
    row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if row is None:
        raise ValueError(f"fact not found: {fact_id}")

    await prisma.knowledgefact.update(
        where={"id": fact_id},
        data={
            "status": KnowledgeStatus.EXPIRED.value,
            "expiredReason": reason,
            "validTo": _utcnow(),
            "predictionConfidence": None,
        },
    )
    logger.info("transition_pending_to_expired: %s - %s", fact_id, reason)


__all__ = [
    "predict_fact_outcome",
    "bayesian_update",
    "historical_base_rate",
    "update_pending_predictions",
    "transition_pending_to_confirmed",
    "transition_pending_to_expired",
]
