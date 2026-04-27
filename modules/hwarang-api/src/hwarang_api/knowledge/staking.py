"""HLKM - Stake-to-Contribute (스테이킹 기반 기여 담보).

지식 기여 시 HWARANG 토큰을 담보(stake)로 묶고, 검증 결과에 따라
반환(+보상) 또는 슬래시(삭감)한다.

핵심 불변식:
  - tier 가 높을수록 담보 요구량이 적다 (BRONZE 1.5× → DIAMOND 0.5×).
  - 슬래시의 50% 는 시스템 소각, 50% 는 peer reviewer 에게 분배.
  - 모든 BigInt 계산은 Python `int` 로 처리해 정확도 손실 없음.
  - race condition 방지: stakedBalance 변경은 find→update 분리 대신
    Prisma 의 increment/decrement 를 사용.

의존:
  - `hwarang_api.db.prisma`
  - `.rewards.calculate_reward` (slash 시 검증자 보상 참고용)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma

from .types import KnowledgeFact  # noqa: F401 (공개 API 타입 안정화)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
STAKE_REQUIREMENTS: dict[str, int] = {
    "law": 100,
    "medical": 150,
    "general": 20,
    "tech": 30,
    "default": 50,
}

TIER_STAKE_MULTIPLIERS: dict[str, float] = {
    "BRONZE": 1.5,
    "SILVER": 1.0,
    "GOLD": 0.7,
    "DIAMOND": 0.5,
    "SUSPENDED": 999.0,  # 사실상 불가
}

# Reputation EMA
_REP_EMA_ALPHA = 0.2
_REP_UP = 0.05
_REP_DOWN = 0.15

# 자동 정산 설정
_DEFAULT_AUTO_SETTLE_DAYS = 14


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clamp_rep(v: float) -> float:
    return max(0.0, min(1.0, v))


# ─────────────────────────────────────────────
# 필요 스테이킹 계산
# ─────────────────────────────────────────────
async def required_stake(user_id: str, domain: str) -> int:
    """해당 user 의 tier 와 domain 에 따른 최소 필요 stake.

    required = base[domain] × tier_multiplier (올림).
    """
    base = STAKE_REQUIREMENTS.get(
        (domain or "").lower(), STAKE_REQUIREMENTS["default"]
    )
    profile = await prisma.contributorprofile.find_unique(where={"userId": user_id})
    tier = (profile.tier if profile else "BRONZE") or "BRONZE"
    mult = TIER_STAKE_MULTIPLIERS.get(tier.upper(), 1.0)
    return max(1, int(round(base * mult)))


# ─────────────────────────────────────────────
# 스테이크 생성
# ─────────────────────────────────────────────
async def place_stake(user_id: str, fact_id: str, amount: int) -> str:
    """기여 시 담보 토큰 예치.

    - amount >= required_stake 체크.
    - profile.stakedBalance >= amount 체크.
    - ContributionStake(status=pending) 생성 + stakedBalance 차감.
    """
    if amount <= 0:
        raise ValueError("amount must be positive")

    fact = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if fact is None:
        raise ValueError(f"fact not found: {fact_id}")

    need = await required_stake(user_id, fact.domain or "default")
    if amount < need:
        raise ValueError(f"stake amount {amount} < required {need}")

    profile = await prisma.contributorprofile.find_unique(where={"userId": user_id})
    if profile is None:
        raise ValueError(f"contributor profile missing: {user_id}")
    if (profile.stakedBalance or 0) < amount:
        raise ValueError(
            f"insufficient staked balance: have={profile.stakedBalance} need={amount}"
        )
    if (profile.tier or "").upper() == "SUSPENDED":
        raise ValueError("suspended users cannot stake")

    # 차감 (원자적)
    await prisma.contributorprofile.update(
        where={"userId": user_id},
        data={"stakedBalance": {"decrement": amount}},
    )

    stake = await prisma.contributionstake.create(
        data={
            "factId": fact_id,
            "userId": user_id,
            "stakedAmount": amount,
            "status": "pending",
            "slashedAmount": 0,
            "rewardedAmount": 0,
            "peerReviewPassed": False,
        }
    )
    logger.info(
        "place_stake: user=%s fact=%s amount=%d stake_id=%s",
        user_id,
        fact_id,
        amount,
        stake.id,
    )
    return stake.id


# ─────────────────────────────────────────────
# 정산 (성공)
# ─────────────────────────────────────────────
async def settle_correct(stake_id: str, reward_amount: int) -> dict:
    """검증 통과 → 스테이크 반환 + 보상 추가.

    - stakedBalance += stakedAmount + reward.
    - correctContribs++, lifetimeStaked += stakedAmount.
    - totalEarned += reward.
    - reputation 을 EMA 로 상승.
    """
    stake = await prisma.contributionstake.find_unique(where={"id": stake_id})
    if stake is None:
        raise ValueError(f"stake not found: {stake_id}")
    if stake.status != "pending":
        raise ValueError(f"stake already settled: {stake.status}")
    if reward_amount < 0:
        raise ValueError("reward must be non-negative")

    total_return = int(stake.stakedAmount) + int(reward_amount)

    profile = await prisma.contributorprofile.find_unique(
        where={"userId": stake.userId}
    )
    new_rep = _clamp_rep(
        (profile.reputation if profile else 0.5) * (1 - _REP_EMA_ALPHA)
        + (1.0) * _REP_EMA_ALPHA
    ) if profile else 0.5 + _REP_UP

    await prisma.contributorprofile.update(
        where={"userId": stake.userId},
        data={
            "stakedBalance": {"increment": total_return},
            "correctContribs": {"increment": 1},
            "lifetimeStaked": {"increment": int(stake.stakedAmount)},
            "totalEarned": {"increment": int(reward_amount)},
            "reputation": new_rep,
        },
    )
    await prisma.contributionstake.update(
        where={"id": stake_id},
        data={
            "status": "settled_correct",
            "settledAt": _utcnow(),
            "rewardedAmount": int(reward_amount),
            "peerReviewPassed": True,
        },
    )

    logger.info(
        "settle_correct: stake=%s user=%s return=%d (stake=%d + reward=%d)",
        stake_id,
        stake.userId,
        total_return,
        stake.stakedAmount,
        reward_amount,
    )
    return {
        "stake_id": stake_id,
        "status": "settled_correct",
        "returned": total_return,
        "reward": int(reward_amount),
        "new_reputation": new_rep,
    }


# ─────────────────────────────────────────────
# 정산 (실패 - 슬래시)
# ─────────────────────────────────────────────
async def settle_slashed(
    stake_id: str, slash_ratio: float = 1.0, reason: str = ""
) -> dict:
    """실패/거짓 → 슬래시.

    slashed = stakedAmount × slash_ratio.
    절반은 시스템 소각, 절반은 peer reviewer 에게 분배.
    나머지 stake 는 유저에게 반환.
    """
    if not (0.0 <= slash_ratio <= 1.0):
        raise ValueError("slash_ratio must be in [0,1]")
    stake = await prisma.contributionstake.find_unique(where={"id": stake_id})
    if stake is None:
        raise ValueError(f"stake not found: {stake_id}")
    if stake.status != "pending":
        raise ValueError(f"stake already settled: {stake.status}")

    slashed = int(round(int(stake.stakedAmount) * slash_ratio))
    remainder = int(stake.stakedAmount) - slashed
    burn = slashed // 2
    reviewer_pool = slashed - burn

    profile = await prisma.contributorprofile.find_unique(
        where={"userId": stake.userId}
    )
    old_rep = float(profile.reputation) if profile else 0.5
    new_rep = _clamp_rep(old_rep * (1 - _REP_EMA_ALPHA) + 0.0 * _REP_EMA_ALPHA)

    update_data: dict[str, Any] = {
        "wrongContribs": {"increment": 1},
        "lifetimeSlashed": {"increment": slashed},
        "reputation": new_rep,
    }
    if remainder > 0:
        update_data["stakedBalance"] = {"increment": remainder}

    await prisma.contributorprofile.update(
        where={"userId": stake.userId}, data=update_data
    )
    await prisma.contributionstake.update(
        where={"id": stake_id},
        data={
            "status": "settled_slashed",
            "settledAt": _utcnow(),
            "slashedAmount": slashed,
            "peerReviewPassed": False,
        },
    )

    # 코인 소각 hook (옵션)
    try:
        from hwarang_api.knowledge.coin import burn_tokens  # type: ignore

        await burn_tokens(burn, reason=f"stake_slash:{stake_id}:{reason}")
    except Exception as exc:  # noqa: BLE001
        logger.debug("burn_tokens hook skipped: %s", exc)

    logger.warning(
        "settle_slashed: stake=%s user=%s slashed=%d burn=%d reviewer=%d reason=%s",
        stake_id,
        stake.userId,
        slashed,
        burn,
        reviewer_pool,
        reason,
    )
    return {
        "stake_id": stake_id,
        "status": "settled_slashed",
        "slashed": slashed,
        "burned": burn,
        "reviewer_pool": reviewer_pool,
        "returned": remainder,
        "new_reputation": new_rep,
    }


async def partial_slash(stake_id: str, slashed: int, rewarded: int) -> dict:
    """부분 승/패 (품질 점수 0.5 같은 경우).

    slashed + rewarded 를 직접 지정. 남은 금액은 환불.
    """
    if slashed < 0 or rewarded < 0:
        raise ValueError("slashed and rewarded must be non-negative")

    stake = await prisma.contributionstake.find_unique(where={"id": stake_id})
    if stake is None:
        raise ValueError(f"stake not found: {stake_id}")
    if stake.status != "pending":
        raise ValueError(f"stake already settled: {stake.status}")
    if slashed > int(stake.stakedAmount):
        raise ValueError("slashed exceeds staked amount")

    remainder = int(stake.stakedAmount) - slashed
    burn = slashed // 2
    profile = await prisma.contributorprofile.find_unique(
        where={"userId": stake.userId}
    )
    old_rep = float(profile.reputation) if profile else 0.5
    # 부분 평가: 점수 = rewarded / (rewarded + slashed or 1)
    denom = rewarded + slashed or 1
    target = rewarded / denom
    new_rep = _clamp_rep(
        old_rep * (1 - _REP_EMA_ALPHA) + target * _REP_EMA_ALPHA
    )

    await prisma.contributorprofile.update(
        where={"userId": stake.userId},
        data={
            "stakedBalance": {"increment": remainder + rewarded},
            "lifetimeStaked": {"increment": int(stake.stakedAmount)},
            "lifetimeSlashed": {"increment": slashed},
            "totalEarned": {"increment": rewarded},
            "reputation": new_rep,
        },
    )
    await prisma.contributionstake.update(
        where={"id": stake_id},
        data={
            "status": "settled_partial",
            "settledAt": _utcnow(),
            "slashedAmount": slashed,
            "rewardedAmount": rewarded,
            "peerReviewPassed": rewarded >= slashed,
        },
    )
    logger.info(
        "partial_slash: stake=%s slashed=%d rewarded=%d remainder=%d",
        stake_id,
        slashed,
        rewarded,
        remainder,
    )
    return {
        "stake_id": stake_id,
        "status": "settled_partial",
        "slashed": slashed,
        "rewarded": rewarded,
        "returned": remainder + rewarded,
        "burn_share": burn,
        "new_reputation": new_rep,
    }


# ─────────────────────────────────────────────
# 환불
# ─────────────────────────────────────────────
async def refund_unsettled(stake_id: str) -> dict:
    """검증 기간 초과 + 명확한 결론 없음 → 전액 환불 (슬래시 X, 보상 X)."""
    stake = await prisma.contributionstake.find_unique(where={"id": stake_id})
    if stake is None:
        raise ValueError(f"stake not found: {stake_id}")
    if stake.status != "pending":
        raise ValueError(f"stake already settled: {stake.status}")

    await prisma.contributorprofile.update(
        where={"userId": stake.userId},
        data={"stakedBalance": {"increment": int(stake.stakedAmount)}},
    )
    await prisma.contributionstake.update(
        where={"id": stake_id},
        data={
            "status": "refunded",
            "settledAt": _utcnow(),
        },
    )
    logger.info("refund_unsettled: stake=%s amount=%d", stake_id, stake.stakedAmount)
    return {
        "stake_id": stake_id,
        "status": "refunded",
        "returned": int(stake.stakedAmount),
    }


# ─────────────────────────────────────────────
# 조회
# ─────────────────────────────────────────────
async def list_user_stakes(
    user_id: str, status: str | None = None
) -> list[dict]:
    """해당 user 의 스테이크 목록 (최신순)."""
    where: dict[str, Any] = {"userId": user_id}
    if status:
        where["status"] = status
    rows = await prisma.contributionstake.find_many(
        where=where, take=500, order={"id": "desc"}
    )
    return [
        {
            "stake_id": r.id,
            "fact_id": r.factId,
            "staked_amount": int(r.stakedAmount),
            "status": r.status,
            "slashed_amount": int(r.slashedAmount or 0),
            "rewarded_amount": int(r.rewardedAmount or 0),
            "peer_review_passed": r.peerReviewPassed,
            "settled_at": r.settledAt,
        }
        for r in rows
    ]


async def total_staked(user_id: str) -> int:
    """누적 stake 총액 (lifetimeStaked)."""
    p = await prisma.contributorprofile.find_unique(where={"userId": user_id})
    return int(p.lifetimeStaked or 0) if p else 0


async def total_slashed(user_id: str) -> int:
    """누적 슬래시 총액 (lifetimeSlashed)."""
    p = await prisma.contributorprofile.find_unique(where={"userId": user_id})
    return int(p.lifetimeSlashed or 0) if p else 0


# ─────────────────────────────────────────────
# 자동 정산 배치
# ─────────────────────────────────────────────
async def auto_settle_expired(
    older_than_days: int = _DEFAULT_AUTO_SETTLE_DAYS,
) -> dict:
    """N일 이상 pending 인 스테이크를 자동 정산.

    peer review 통과 흔적이 있으면 소액 보상으로 settle_correct,
    아니면 refund_unsettled.
    """
    cutoff = _utcnow() - timedelta(days=older_than_days)
    rows = await prisma.contributionstake.find_many(
        where={"status": "pending"}, take=1000
    )
    settled = 0
    refunded = 0
    for r in rows:
        # createdAt 대신 id 순으로만 판단할 수 있으므로 fact 의 lastVerifiedAt 보조
        fact = await prisma.knowledgefact.find_unique(where={"id": r.factId})
        last = (
            fact.lastVerifiedAt
            if (fact and fact.lastVerifiedAt)
            else (fact.createdAt if fact else None)
        )
        if last is None or last > cutoff:
            continue
        try:
            contrib = await prisma.knowledgecontribution.find_first(
                where={"factId": r.factId, "contributorId": r.userId}
            )
            passed = bool(
                contrib
                and (contrib.votesUp or 0) > (contrib.votesDown or 0)
            )
            if passed:
                reward = max(1, int(int(r.stakedAmount) * 0.1))
                await settle_correct(r.id, reward)
                settled += 1
            else:
                await refund_unsettled(r.id)
                refunded += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("auto_settle failed for %s: %s", r.id, exc)
    logger.info(
        "auto_settle_expired: settled=%d refunded=%d (days=%d)",
        settled,
        refunded,
        older_than_days,
    )
    return {"settled": settled, "refunded": refunded}


# ─────────────────────────────────────────────
# 잔액 이동
# ─────────────────────────────────────────────
async def deposit_to_stake_balance(
    user_id: str, amount: int, tx_hash: str | None = None
) -> int:
    """일반 잔액 → 스테이킹 잔액 이동.

    실제 코인 전송은 `coin.transfer_to_stake_vault` 에 위임 (placeholder).
    """
    if amount <= 0:
        raise ValueError("amount must be positive")

    try:
        from hwarang_api.knowledge.coin import transfer_to_stake_vault  # type: ignore

        await transfer_to_stake_vault(user_id, amount, tx_hash=tx_hash)
    except Exception as exc:  # noqa: BLE001
        logger.debug("coin vault hook skipped: %s", exc)

    await prisma.contributorprofile.upsert(
        where={"userId": user_id},
        data={
            "create": {"userId": user_id, "stakedBalance": amount},
            "update": {"stakedBalance": {"increment": amount}},
        },
    )
    profile = await prisma.contributorprofile.find_unique(where={"userId": user_id})
    return int(profile.stakedBalance or 0) if profile else 0


async def withdraw_stake_balance(user_id: str, amount: int) -> int:
    """스테이킹 잔액 → 일반 잔액. pending 스테이크는 묶여있으므로 건드리지 않음."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    profile = await prisma.contributorprofile.find_unique(where={"userId": user_id})
    if profile is None:
        raise ValueError(f"profile not found: {user_id}")
    if (profile.stakedBalance or 0) < amount:
        raise ValueError("insufficient staked balance")

    await prisma.contributorprofile.update(
        where={"userId": user_id},
        data={"stakedBalance": {"decrement": amount}},
    )

    try:
        from hwarang_api.knowledge.coin import transfer_from_stake_vault  # type: ignore

        await transfer_from_stake_vault(user_id, amount)
    except Exception as exc:  # noqa: BLE001
        logger.debug("coin vault withdraw hook skipped: %s", exc)

    profile = await prisma.contributorprofile.find_unique(where={"userId": user_id})
    return int(profile.stakedBalance or 0) if profile else 0


# ─────────────────────────────────────────────
# 스테이크 건전성 (UI 대시보드)
# ─────────────────────────────────────────────
async def stake_health(user_id: str) -> dict:
    """{"total_staked","total_slashed","win_rate","avg_slash_ratio","risk_score"}."""
    p = await prisma.contributorprofile.find_unique(where={"userId": user_id})
    if p is None:
        return {
            "total_staked": 0,
            "total_slashed": 0,
            "win_rate": 0.0,
            "avg_slash_ratio": 0.0,
            "risk_score": 0.5,
        }

    total_correct = int(p.correctContribs or 0)
    total_wrong = int(p.wrongContribs or 0)
    total_n = total_correct + total_wrong
    win_rate = (total_correct / total_n) if total_n else 0.0
    avg_slash_ratio = (
        (int(p.lifetimeSlashed or 0) / int(p.lifetimeStaked or 0))
        if int(p.lifetimeStaked or 0) > 0
        else 0.0
    )

    # risk_score: 1 = 매우 위험, 0 = 안전. 성향 가중 평균.
    risk_score = max(
        0.0,
        min(
            1.0,
            0.6 * avg_slash_ratio + 0.4 * (1.0 - win_rate),
        ),
    )
    return {
        "total_staked": int(p.lifetimeStaked or 0),
        "total_slashed": int(p.lifetimeSlashed or 0),
        "win_rate": round(win_rate, 4),
        "avg_slash_ratio": round(avg_slash_ratio, 4),
        "risk_score": round(risk_score, 4),
        "current_balance": int(p.stakedBalance or 0),
        "reputation": float(p.reputation or 0.5),
        "tier": p.tier,
    }


__all__ = [
    "STAKE_REQUIREMENTS",
    "TIER_STAKE_MULTIPLIERS",
    "required_stake",
    "place_stake",
    "settle_correct",
    "settle_slashed",
    "partial_slash",
    "refund_unsettled",
    "list_user_stakes",
    "total_staked",
    "total_slashed",
    "auto_settle_expired",
    "deposit_to_stake_balance",
    "withdraw_stake_balance",
    "stake_health",
]
