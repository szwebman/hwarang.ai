"""HLKM — 예측 시장 (Prediction Market, Augur-style).

PENDING 상태의 KnowledgeFact 에 대해 "이 사실이 예정 시점에 실제로
CONFIRMED 될 것인가?" 에 대한 YES/NO 베팅 시장을 운영한다.

시장 수학:
  - yesPool, noPool 은 각 측 누적 베팅액
  - 현재 확률  p(YES) = yesPool / (yesPool + noPool)
  - 정산 시 승리 측 베팅자는 비례 배분으로 상금 수령
        payoff_i = total_pool × (1 - fee) × (my_amount / winning_side_pool)
  - 패배 측은 전액 손실 (→ 승자 풀에 포함)

핵심 리스크 대응:
  - `detect_manipulation`: 마감 직전 대량 매수, 단일 유저 극단 베팅 감지
  - `calibration_report`: 시장의 확률 예측이 실제 결과와 얼마나 일치하는지
  - INVALID outcome → 전원 환불 (정당성 불명 시)

의존:
  - `hwarang_api.db.prisma`
  - `.types.KnowledgeFact`
  - `.contributor_tier.get_or_create_profile`, `can_contribute_to_domain`
  - `.staking.deposit_to_stake_balance`, `withdraw_stake_balance`
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from hwarang_api.db import prisma

from .contribution_gate import WriteAction, require_contribution_permission
from .contributor_tier import can_contribute_to_domain, get_or_create_profile  # noqa: F401
from .staking import deposit_to_stake_balance, withdraw_stake_balance
from .types import KnowledgeFact, KnowledgeStatus  # noqa: F401

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
MIN_BET_AMOUNT: int = 10
MIN_MARKET_PARTICIPANTS: int = 3
PLATFORM_FEE_RATIO: float = 0.03

_VALID_SIDES = {"YES", "NO"}
_VALID_OUTCOMES = {"YES", "NO", "INVALID"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _big(x: Any) -> int:
    """Prisma BigInt → Python int 안전 변환."""
    if x is None:
        return 0
    try:
        return int(x)
    except Exception:
        return 0


# ─────────────────────────────────────────────
# 시장 생성
# ─────────────────────────────────────────────
async def create_market(
    pending_fact_id: str, question: str, resolution_date: datetime
) -> str:
    """PENDING fact 에 대한 예측 시장을 생성한다.

    검증:
      - fact.status == PENDING
      - fact.predictedValidFrom 존재 (예측 시점 명시돼 있어야 함)
      - 해당 fact 에 이미 market 존재 시 거부
      - resolution_date 가 현재 이후
    """
    if not question or not question.strip():
        raise ValueError("question 은 비어 있을 수 없습니다.")
    resolution_date = _as_aware(resolution_date)
    if resolution_date is None or resolution_date <= _utcnow():
        raise ValueError("resolution_date 는 현재 이후여야 합니다.")

    fact = await prisma.knowledgefact.find_unique(where={"id": pending_fact_id})
    if fact is None:
        raise ValueError(f"fact not found: {pending_fact_id}")
    if fact.status != KnowledgeStatus.PENDING.value:
        raise ValueError(f"fact 상태가 PENDING 이 아닙니다: {fact.status}")
    if getattr(fact, "predictedValidFrom", None) is None:
        raise ValueError("fact 에 predictedValidFrom 이 설정되어야 합니다.")

    existing = await prisma.predictionmarket.find_unique(
        where={"pendingFactId": pending_fact_id}
    )
    if existing is not None:
        raise ValueError("이미 해당 fact 에 대한 예측 시장이 존재합니다.")

    row = await prisma.predictionmarket.create(
        data={
            "pendingFactId": pending_fact_id,
            "question": question.strip(),
            "yesPool": 0,
            "noPool": 0,
            "bettersCount": 0,
            "resolutionDate": resolution_date,
            "resolved": False,
        }
    )
    logger.info(
        "prediction market created: id=%s fact=%s resolution=%s",
        row.id, pending_fact_id, resolution_date.isoformat(),
    )
    return row.id


# ─────────────────────────────────────────────
# 베팅
# ─────────────────────────────────────────────
async def place_bet(
    market_id: str,
    user_id: str,
    side: str,
    amount: int,
    bypass_gate: bool = False,
) -> str:
    """YES/NO 측에 베팅한다 (에스크로 차감).

    - amount >= MIN_BET_AMOUNT
    - market.resolved=False, now < resolutionDate
    - 새 유저면 bettersCount 증가
    """
    # KYC 게이트
    if not bypass_gate:
        await require_contribution_permission(
            user_id, WriteAction.PREDICTION_BET.value
        )

    side_upper = (side or "").upper()
    if side_upper not in _VALID_SIDES:
        raise ValueError(f"side 는 YES/NO 여야 합니다: {side}")
    amt = int(amount)
    if amt < MIN_BET_AMOUNT:
        raise ValueError(f"amount 는 최소 {MIN_BET_AMOUNT} 이상이어야 합니다.")

    market = await prisma.predictionmarket.find_unique(where={"id": market_id})
    if market is None:
        raise ValueError(f"market not found: {market_id}")
    if market.resolved:
        raise ValueError("이미 정산된 시장입니다.")
    resolution_date = _as_aware(market.resolutionDate)
    if resolution_date is not None and _utcnow() >= resolution_date:
        raise ValueError("정산일이 지나 베팅할 수 없습니다.")

    # 에스크로 차감
    try:
        await deposit_to_stake_balance(
            user_id, amt, reason=f"market_bet:{market_id}:{side_upper}"
        )
    except Exception as exc:
        logger.warning("market bet 에스크로 실패 user=%s amount=%d: %s", user_id, amt, exc)
        raise

    # 새 참여자 여부
    existing_bet = await prisma.marketbet.find_first(
        where={"marketId": market_id, "userId": user_id}
    )
    is_new_user = existing_bet is None

    # MarketBet insert
    bet = await prisma.marketbet.create(
        data={
            "marketId": market_id,
            "userId": user_id,
            "side": side_upper,
            "amount": amt,
            "payoff": 0,
        }
    )

    # 풀 업데이트
    new_yes = _big(market.yesPool) + (amt if side_upper == "YES" else 0)
    new_no = _big(market.noPool) + (amt if side_upper == "NO" else 0)
    new_betters = int(market.bettersCount or 0) + (1 if is_new_user else 0)
    await prisma.predictionmarket.update(
        where={"id": market_id},
        data={
            "yesPool": new_yes,
            "noPool": new_no,
            "bettersCount": new_betters,
        },
    )

    logger.info(
        "market bet: market=%s user=%s side=%s amount=%d new_user=%s",
        market_id, user_id, side_upper, amt, is_new_user,
    )
    return bet.id


# ─────────────────────────────────────────────
# 확률 / 배당 계산
# ─────────────────────────────────────────────
async def current_odds(market_id: str) -> dict:
    """현재 시점의 YES/NO 확률과 총 풀 크기."""
    market = await prisma.predictionmarket.find_unique(where={"id": market_id})
    if market is None:
        raise ValueError(f"market not found: {market_id}")
    yes = _big(market.yesPool)
    no = _big(market.noPool)
    total = yes + no
    if total <= 0:
        return {"yes": 0.5, "no": 0.5, "total_pool": 0, "yes_pool": 0, "no_pool": 0}
    return {
        "yes": round(yes / total, 6),
        "no": round(no / total, 6),
        "total_pool": total,
        "yes_pool": yes,
        "no_pool": no,
    }


async def expected_payoff(market_id: str, side: str, amount: int) -> dict:
    """이 금액으로 베팅해서 맞혔을 때 예상 수령액.

    payoff_approx = (total_pool + amount) × (1 - fee)
                    × (amount / (winning_side_pool + amount))
    """
    side_upper = (side or "").upper()
    if side_upper not in _VALID_SIDES:
        raise ValueError(f"side 는 YES/NO 여야 합니다: {side}")
    amt = int(amount)
    if amt <= 0:
        raise ValueError("amount 는 양수여야 합니다.")

    market = await prisma.predictionmarket.find_unique(where={"id": market_id})
    if market is None:
        raise ValueError(f"market not found: {market_id}")

    yes = _big(market.yesPool)
    no = _big(market.noPool)
    total = yes + no + amt
    winning_pool = (yes if side_upper == "YES" else no) + amt

    if winning_pool <= 0:
        return {"payoff": 0.0, "profit": -amt, "roi": -1.0}

    gross = Decimal(total) * Decimal(1 - PLATFORM_FEE_RATIO) * (
        Decimal(amt) / Decimal(winning_pool)
    )
    gross_int = int(gross)
    profit = gross_int - amt
    roi = (profit / amt) if amt > 0 else 0.0
    return {
        "payoff": gross_int,
        "profit": profit,
        "roi": round(float(roi), 4),
        "implied_probability": round(winning_pool / total, 4) if total > 0 else 0.0,
    }


# ─────────────────────────────────────────────
# 정산
# ─────────────────────────────────────────────
async def resolve_market(market_id: str, outcome: str, resolver_id: str) -> dict:
    """시장 정산. YES/NO/INVALID.

    - YES:     연관 fact.status=CONFIRMED, validFrom 확정, YES 측에 비례 배분
    - NO:      연관 fact.status=EXPIRED, expiredReason 기록, NO 측에 비례 배분
    - INVALID: 전원 환불
    """
    outcome_upper = (outcome or "").upper()
    if outcome_upper not in _VALID_OUTCOMES:
        raise ValueError(f"outcome 값 오류: {outcome}")

    market = await prisma.predictionmarket.find_unique(where={"id": market_id})
    if market is None:
        raise ValueError(f"market not found: {market_id}")
    if market.resolved:
        raise ValueError("이미 정산된 시장입니다.")

    bets = await prisma.marketbet.find_many(where={"marketId": market_id})

    yes_pool = _big(market.yesPool)
    no_pool = _big(market.noPool)
    total = yes_pool + no_pool

    result: dict[str, Any] = {
        "market_id": market_id,
        "outcome": outcome_upper,
        "total_pool": total,
        "payouts": {},
        "platform_fee": 0,
        "resolver_id": resolver_id,
    }

    # INVALID → 전원 환불
    if outcome_upper == "INVALID":
        for b in bets:
            amt = _big(b.amount)
            try:
                await withdraw_stake_balance(
                    b.userId,
                    amt,
                    reason=f"market_refund:{market_id}",
                )
            except Exception as exc:
                logger.warning("refund 실패 user=%s: %s", b.userId, exc)
            await prisma.marketbet.update(
                where={"id": b.id},
                data={"payoff": amt, "settledAt": _utcnow()},
            )
            result["payouts"][b.userId] = result["payouts"].get(b.userId, 0) + amt

        await prisma.predictionmarket.update(
            where={"id": market_id},
            data={
                "resolved": True,
                "outcome": "INVALID",
                "resolvedAt": _utcnow(),
            },
        )
        logger.info("market resolved INVALID (refund all): id=%s bets=%d",
                    market_id, len(bets))
        return result

    # YES / NO 정산
    winning_pool = yes_pool if outcome_upper == "YES" else no_pool
    platform_fee = int(round(total * PLATFORM_FEE_RATIO))
    distributable = max(0, total - platform_fee)
    result["platform_fee"] = platform_fee

    if winning_pool <= 0:
        # 승자가 없음 → 전원 환불 (fail-safe)
        logger.warning("winning side 풀이 0. 환불 처리. market=%s outcome=%s",
                       market_id, outcome_upper)
        for b in bets:
            amt = _big(b.amount)
            try:
                await withdraw_stake_balance(
                    b.userId, amt, reason=f"market_refund_no_winner:{market_id}"
                )
            except Exception as exc:
                logger.warning("refund 실패 user=%s: %s", b.userId, exc)
            await prisma.marketbet.update(
                where={"id": b.id},
                data={"payoff": amt, "settledAt": _utcnow()},
            )
        await prisma.predictionmarket.update(
            where={"id": market_id},
            data={
                "resolved": True,
                "outcome": "INVALID",
                "resolvedAt": _utcnow(),
            },
        )
        result["outcome"] = "INVALID"
        return result

    for b in bets:
        amt = _big(b.amount)
        if b.side == outcome_upper:
            # 비례 배분 (Decimal 로 정밀도 확보 후 int 내림)
            share = Decimal(amt) / Decimal(winning_pool)
            payoff = int(Decimal(distributable) * share)
            if payoff > 0:
                try:
                    await withdraw_stake_balance(
                        b.userId,
                        payoff,
                        reason=f"market_payoff:{market_id}",
                    )
                except Exception as exc:
                    logger.warning("payoff 지급 실패 user=%s: %s", b.userId, exc)
            await prisma.marketbet.update(
                where={"id": b.id},
                data={"payoff": payoff, "settledAt": _utcnow()},
            )
            result["payouts"][b.userId] = result["payouts"].get(b.userId, 0) + payoff
        else:
            # 패배 베팅 — 손실 확정 (payoff=0, 에스크로 해제 없음)
            await prisma.marketbet.update(
                where={"id": b.id},
                data={"payoff": 0, "settledAt": _utcnow()},
            )

    # 연관 fact 상태 전이
    try:
        fact = await prisma.knowledgefact.find_unique(
            where={"id": market.pendingFactId}
        )
        if fact is not None:
            if outcome_upper == "YES":
                await prisma.knowledgefact.update(
                    where={"id": fact.id},
                    data={
                        "status": KnowledgeStatus.CONFIRMED.value,
                        "validFrom": getattr(fact, "predictedValidFrom", None)
                        or fact.validFrom,
                    },
                )
            else:  # NO
                await prisma.knowledgefact.update(
                    where={"id": fact.id},
                    data={
                        "status": KnowledgeStatus.EXPIRED.value,
                        "expiredReason": "market resolution",
                    },
                )
    except Exception as exc:
        logger.warning("fact 상태 전이 실패 market=%s: %s", market_id, exc)

    await prisma.predictionmarket.update(
        where={"id": market_id},
        data={
            "resolved": True,
            "outcome": outcome_upper,
            "resolvedAt": _utcnow(),
        },
    )
    logger.info(
        "market resolved: id=%s outcome=%s distributable=%d fee=%d winners=%d",
        market_id, outcome_upper, distributable, platform_fee,
        sum(1 for v in result["payouts"].values() if v > 0),
    )
    return result


# ─────────────────────────────────────────────
# 자동 정산 / 취소
# ─────────────────────────────────────────────
async def auto_resolve_markets() -> dict:
    """resolutionDate 가 지난 시장을 자동 정산.

    연관 fact 의 status 전이를 먼저 확인:
      - CONFIRMED → outcome=YES
      - EXPIRED  → outcome=NO
      - 그 외    → 스킵 (수동 resolver 필요)
    """
    now = _utcnow()
    rows = await prisma.predictionmarket.find_many(
        where={
            "resolved": False,
            "resolutionDate": {"lt": now},
        },
        take=500,
    )
    resolved = 0
    skipped = 0
    for m in rows:
        try:
            fact = await prisma.knowledgefact.find_unique(
                where={"id": m.pendingFactId}
            )
            if fact is None:
                skipped += 1
                continue
            if fact.status == KnowledgeStatus.CONFIRMED.value:
                await resolve_market(m.id, "YES", resolver_id="system:auto")
                resolved += 1
            elif fact.status == KnowledgeStatus.EXPIRED.value:
                await resolve_market(m.id, "NO", resolver_id="system:auto")
                resolved += 1
            else:
                skipped += 1
        except Exception as exc:
            logger.warning("auto_resolve 실패 market=%s: %s", m.id, exc)
            skipped += 1

    logger.info("auto_resolve_markets: resolved=%d skipped=%d", resolved, skipped)
    return {"resolved": resolved, "skipped": skipped, "checked": len(rows)}


async def cancel_market(market_id: str, admin_id: str, reason: str) -> dict:
    """관리자 권한으로 시장 취소 (전원 환불)."""
    market = await prisma.predictionmarket.find_unique(where={"id": market_id})
    if market is None:
        raise ValueError(f"market not found: {market_id}")
    if market.resolved:
        raise ValueError("이미 정산된 시장은 취소할 수 없습니다.")

    bets = await prisma.marketbet.find_many(where={"marketId": market_id})
    refunded = 0
    for b in bets:
        amt = _big(b.amount)
        try:
            await withdraw_stake_balance(
                b.userId, amt, reason=f"market_cancel:{market_id}:{reason[:60]}"
            )
            refunded += amt
        except Exception as exc:
            logger.warning("cancel refund 실패 user=%s: %s", b.userId, exc)
        await prisma.marketbet.update(
            where={"id": b.id},
            data={"payoff": amt, "settledAt": _utcnow()},
        )

    await prisma.predictionmarket.update(
        where={"id": market_id},
        data={
            "resolved": True,
            "outcome": "INVALID",
            "resolvedAt": _utcnow(),
        },
    )
    logger.info(
        "market cancelled: id=%s admin=%s refunded=%d reason=%s",
        market_id, admin_id, refunded, reason[:80],
    )
    return {"action": "cancelled", "refunded_total": refunded, "bettors": len(bets)}


# ─────────────────────────────────────────────
# 조회
# ─────────────────────────────────────────────
async def list_active_markets(
    domain: str | None = None, sort_by: str = "pool_size"
) -> list[dict]:
    """활성(미정산) 시장 목록.

    sort_by ∈ {"pool_size", "deadline", "participants"}
    """
    rows = await prisma.predictionmarket.find_many(
        where={"resolved": False},
        take=500,
    )
    out: list[dict] = []
    for m in rows:
        fact_domain = None
        if domain:
            try:
                fact = await prisma.knowledgefact.find_unique(
                    where={"id": m.pendingFactId}
                )
                fact_domain = (fact.domain or "general") if fact else None
                if fact_domain != domain.lower():
                    continue
            except Exception:
                continue
        out.append(_market_to_dict(m, include_pool_sum=True))

    if sort_by == "pool_size":
        out.sort(key=lambda x: x["total_pool"], reverse=True)
    elif sort_by == "deadline":
        out.sort(key=lambda x: x.get("resolution_date") or "")
    elif sort_by == "participants":
        out.sort(key=lambda x: x["betters_count"], reverse=True)
    return out


async def list_my_bets(user_id: str, status: str | None = None) -> list[dict]:
    """내 베팅 목록.

    status ∈ {"active", "settled", None}
    """
    rows = await prisma.marketbet.find_many(
        where={"userId": user_id},
        order={"createdAt": "desc"},
        take=500,
    )
    out: list[dict] = []
    for b in rows:
        settled = getattr(b, "settledAt", None) is not None
        if status == "active" and settled:
            continue
        if status == "settled" and not settled:
            continue
        out.append(
            {
                "bet_id": b.id,
                "market_id": b.marketId,
                "side": b.side,
                "amount": _big(b.amount),
                "payoff": _big(b.payoff),
                "settled_at": b.settledAt.isoformat() if settled else None,
            }
        )
    return out


async def market_stats() -> dict:
    """전체 시장 요약."""
    all_rows = await prisma.predictionmarket.find_many(take=5000)
    total = len(all_rows)
    active = sum(1 for m in all_rows if not m.resolved)
    resolved_cnt = sum(1 for m in all_rows if m.resolved)
    total_pool = sum(_big(m.yesPool) + _big(m.noPool) for m in all_rows)

    # 시장 예측 정확도: 마감 직전 확률 중 실제 outcome 과 일치 비율
    correct = 0
    scored = 0
    for m in all_rows:
        if not m.resolved or m.outcome not in ("YES", "NO"):
            continue
        yes = _big(m.yesPool)
        no = _big(m.noPool)
        if yes + no <= 0:
            continue
        predicted_yes = yes / (yes + no)
        actual_yes = 1.0 if m.outcome == "YES" else 0.0
        if (predicted_yes >= 0.5 and actual_yes == 1.0) or (
            predicted_yes < 0.5 and actual_yes == 0.0
        ):
            correct += 1
        scored += 1
    avg_accuracy = round(correct / scored, 4) if scored > 0 else 0.0

    return {
        "total_markets": total,
        "active": active,
        "resolved": resolved_cnt,
        "total_pool": total_pool,
        "avg_accuracy": avg_accuracy,
    }


# ─────────────────────────────────────────────
# Calibration
# ─────────────────────────────────────────────
async def calibration_report(last_days: int = 90) -> dict:
    """시장이 예측한 확률 vs 실제 outcome 보정 리포트.

    확률 구간 10% 단위로 그룹화하여 "80% YES로 가격 형성된 것들 중
    실제 80% 가 YES 였는가?" 를 측정한다.
    """
    since = _utcnow() - timedelta(days=int(last_days))
    rows = await prisma.predictionmarket.find_many(
        where={
            "resolved": True,
            "resolvedAt": {"gte": since},
            "outcome": {"in": ["YES", "NO"]},
        },
        take=5000,
    )

    buckets: dict[int, dict[str, int]] = {
        i: {"count": 0, "yes_actual": 0} for i in range(10)
    }
    brier_sum = 0.0

    for m in rows:
        yes = _big(m.yesPool)
        no = _big(m.noPool)
        if yes + no <= 0:
            continue
        p_yes = yes / (yes + no)
        actual = 1 if m.outcome == "YES" else 0
        # 10% 버킷
        b = min(9, int(p_yes * 10))
        buckets[b]["count"] += 1
        buckets[b]["yes_actual"] += actual
        # Brier score: (predicted - actual)^2
        brier_sum += (p_yes - actual) ** 2

    out_buckets: list[dict] = []
    calibration_error = 0.0
    total_n = 0
    for b, data in buckets.items():
        cnt = data["count"]
        if cnt == 0:
            continue
        bucket_prob_center = (b + 0.5) / 10.0
        empirical = data["yes_actual"] / cnt
        out_buckets.append(
            {
                "predicted_range": f"{b*10}%-{(b+1)*10}%",
                "predicted_midpoint": bucket_prob_center,
                "empirical_yes_ratio": round(empirical, 4),
                "count": cnt,
            }
        )
        calibration_error += abs(bucket_prob_center - empirical) * cnt
        total_n += cnt

    calibration_error = (
        round(calibration_error / total_n, 4) if total_n > 0 else 0.0
    )
    brier = round(brier_sum / len(rows), 4) if rows else 0.0

    return {
        "sample_size": len(rows),
        "buckets": sorted(out_buckets, key=lambda x: x["predicted_midpoint"]),
        "expected_calibration_error": calibration_error,
        "brier_score": brier,
    }


# ─────────────────────────────────────────────
# 조작 감지
# ─────────────────────────────────────────────
async def detect_manipulation(market_id: str) -> list[dict]:
    """시장 조작 의심 패턴 감지.

    검사 항목:
      1. 마감 임박(최근 10%) 시점에 총 풀 대비 >30% 대량 매수
      2. 단일 user 의 풀 집중도 > 50%
      3. 양측 베팅 편차 > 95% 한쪽 쏠림 + 베터 수 < MIN_MARKET_PARTICIPANTS
    """
    market = await prisma.predictionmarket.find_unique(where={"id": market_id})
    if market is None:
        raise ValueError(f"market not found: {market_id}")

    bets = await prisma.marketbet.find_many(where={"marketId": market_id})
    flags: list[dict] = []

    if not bets:
        return flags

    total = sum(_big(b.amount) for b in bets)

    # 1) 마감 임박 대량 매수
    resolution = _as_aware(market.resolutionDate)
    if resolution is not None:
        # 시장 기간 추정 (첫 베팅 ~ resolution) 의 마지막 10% 시점
        sorted_bets = sorted(bets, key=lambda x: getattr(x, "createdAt", _utcnow()))
        first_time = _as_aware(getattr(sorted_bets[0], "createdAt", None)) or resolution
        window_total = (resolution - first_time).total_seconds()
        threshold_time = resolution - timedelta(seconds=window_total * 0.1)
        late_sum = 0
        for b in bets:
            bt = _as_aware(getattr(b, "createdAt", None))
            if bt is not None and bt >= threshold_time:
                late_sum += _big(b.amount)
        if total > 0 and (late_sum / total) > 0.30:
            flags.append(
                {
                    "type": "late_burst",
                    "severity": "high",
                    "detail": f"마감 임박 10% 구간 매수 비중 {late_sum/total:.1%}",
                }
            )

    # 2) 단일 유저 집중
    per_user: dict[str, int] = {}
    for b in bets:
        per_user[b.userId] = per_user.get(b.userId, 0) + _big(b.amount)
    if per_user and total > 0:
        top_user, top_amt = max(per_user.items(), key=lambda x: x[1])
        share = top_amt / total
        if share > 0.50:
            flags.append(
                {
                    "type": "single_user_dominance",
                    "severity": "high" if share > 0.70 else "medium",
                    "user_id": top_user,
                    "share": round(share, 4),
                }
            )

    # 3) 극단 쏠림 + 참여자 부족
    yes_pool = _big(market.yesPool)
    no_pool = _big(market.noPool)
    if yes_pool + no_pool > 0:
        dominant = max(yes_pool, no_pool) / (yes_pool + no_pool)
        betters = int(market.bettersCount or 0)
        if dominant > 0.95 and betters < MIN_MARKET_PARTICIPANTS:
            flags.append(
                {
                    "type": "extreme_skew_low_participants",
                    "severity": "medium",
                    "dominant_ratio": round(dominant, 4),
                    "betters": betters,
                }
            )

    if flags:
        logger.warning(
            "manipulation flags market=%s count=%d types=%s",
            market_id, len(flags), [f["type"] for f in flags],
        )
    return flags


# ─────────────────────────────────────────────
# 심화 조회
# ─────────────────────────────────────────────
async def get_market_depth(market_id: str) -> dict:
    """YES/NO 측 베팅 내역 요약."""
    market = await prisma.predictionmarket.find_unique(where={"id": market_id})
    if market is None:
        raise ValueError(f"market not found: {market_id}")

    bets = await prisma.marketbet.find_many(where={"marketId": market_id})

    yes_bets: list[dict] = []
    no_bets: list[dict] = []
    for b in bets:
        entry = {
            "user_id": b.userId,
            "amount": _big(b.amount),
            "created_at": b.createdAt.isoformat() if getattr(b, "createdAt", None) else None,
        }
        if b.side == "YES":
            yes_bets.append(entry)
        else:
            no_bets.append(entry)

    yes_bets.sort(key=lambda x: x["amount"], reverse=True)
    no_bets.sort(key=lambda x: x["amount"], reverse=True)

    return {
        "market_id": market_id,
        "yes_side": {
            "total": _big(market.yesPool),
            "count": len(yes_bets),
            "top": yes_bets[:10],
        },
        "no_side": {
            "total": _big(market.noPool),
            "count": len(no_bets),
            "top": no_bets[:10],
        },
        "betters_count": int(market.bettersCount or 0),
    }


async def calculate_payoffs_preview(market_id: str) -> dict:
    """정산 전 시뮬레이션: 각 outcome 별 예상 payoff 테이블."""
    market = await prisma.predictionmarket.find_unique(where={"id": market_id})
    if market is None:
        raise ValueError(f"market not found: {market_id}")

    bets = await prisma.marketbet.find_many(where={"marketId": market_id})
    yes_pool = _big(market.yesPool)
    no_pool = _big(market.noPool)
    total = yes_pool + no_pool
    fee = int(round(total * PLATFORM_FEE_RATIO))
    distributable = max(0, total - fee)

    preview: dict[str, list[dict]] = {"YES": [], "NO": []}
    for outcome in ("YES", "NO"):
        winning_pool = yes_pool if outcome == "YES" else no_pool
        if winning_pool <= 0:
            continue
        for b in bets:
            if b.side != outcome:
                continue
            amt = _big(b.amount)
            share = Decimal(amt) / Decimal(winning_pool)
            payoff = int(Decimal(distributable) * share)
            preview[outcome].append(
                {
                    "user_id": b.userId,
                    "bet_amount": amt,
                    "estimated_payoff": payoff,
                    "profit": payoff - amt,
                }
            )

    return {
        "market_id": market_id,
        "total_pool": total,
        "platform_fee_estimate": fee,
        "distributable": distributable,
        "by_outcome": preview,
    }


# ─────────────────────────────────────────────
# 내부: row → dict
# ─────────────────────────────────────────────
def _market_to_dict(m, include_pool_sum: bool = False) -> dict:
    yes = _big(m.yesPool)
    no = _big(m.noPool)
    out = {
        "id": m.id,
        "pending_fact_id": m.pendingFactId,
        "question": m.question,
        "yes_pool": yes,
        "no_pool": no,
        "betters_count": int(m.bettersCount or 0),
        "resolution_date": m.resolutionDate.isoformat()
        if getattr(m, "resolutionDate", None)
        else None,
        "resolved": bool(m.resolved),
        "outcome": m.outcome,
        "resolved_at": m.resolvedAt.isoformat()
        if getattr(m, "resolvedAt", None)
        else None,
    }
    if include_pool_sum:
        out["total_pool"] = yes + no
    return out


__all__ = [
    "MIN_BET_AMOUNT",
    "MIN_MARKET_PARTICIPANTS",
    "PLATFORM_FEE_RATIO",
    "create_market",
    "place_bet",
    "current_odds",
    "expected_payoff",
    "resolve_market",
    "auto_resolve_markets",
    "list_active_markets",
    "list_my_bets",
    "market_stats",
    "calibration_report",
    "detect_manipulation",
    "cancel_market",
    "get_market_depth",
    "calculate_payoffs_preview",
]
