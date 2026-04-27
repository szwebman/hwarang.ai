"""평판 스테이킹 (Reputation Staking).

토큰뿐만 아니라 **평판 자체를 담보로** 사실에 베팅하는 메커니즘.
High risk, high reward — 맞으면 평판 가속 상승, 틀리면 평판 급락.

핵심 원리:
    - 평판은 0~1 범위 float 값 (ContributorProfile.reputation)
    - 한 번에 걸 수 있는 최대치는 0.3 (디레버리지 방지)
    - 복수의 베팅을 동시 보유 가능하나, 합계도 0.3 을 넘지 못함
    - 실제로는 ``ContributionStake.metadata`` 에 ``{"reputation_stake": float}``
      를 저장 (별도 컬럼을 추가하지 않기 위함)
    - 군중의 평판 베팅 총합은 사실의 crowd confidence 신호로 활용

경제적 안전장치:
    - 한 번 베팅 cap = 0.3
    - 동시 보유 cap = 0.3 (available_reputation_to_stake 로 계산)
    - 과잉 risk 경고 (warn_excessive_risk)
    - 정산 시 평판은 절대 음수가 되지 않음 (max 0.0 으로 floor)
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma

from .types import KnowledgeFact

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

MAX_SINGLE_BET: float = 0.3
MAX_TOTAL_ACTIVE: float = 0.3
MIN_BET: float = 0.01

DEFAULT_BOOST_MULTIPLIER: float = 1.5
DEFAULT_PENALTY_MULTIPLIER: float = 2.0

EXCESSIVE_RISK_RATIO: float = 0.5  # 최근 1주 베팅 합 / 총 평판 >= 0.5 → 경고
RECENT_WINDOW_DAYS: int = 7

AUTO_SETTLE_DEFAULT_DAYS: int = 14

# ---------------------------------------------------------------------------
# 내부 유틸
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clip_reputation(value: float) -> float:
    """평판 0~1 범위 유지."""
    return max(0.0, min(1.0, float(value)))


def _extract_rep_stake(stake_row: Any) -> float:
    """ContributionStake.metadata 에서 reputation_stake 값을 추출."""
    meta = getattr(stake_row, "metadata", None) or {}
    if isinstance(meta, dict):
        return float(meta.get("reputation_stake", 0.0) or 0.0)
    return 0.0


# ---------------------------------------------------------------------------
# 1. 베팅 / 조회
# ---------------------------------------------------------------------------


async def stake_reputation(
    user_id: str,
    fact_id: str,
    reputation_stake: float,
    reason: str | None = None,
) -> str:
    """평판 스테이킹.

    Args:
        user_id: 기여자 ID.
        fact_id: 베팅 대상 사실.
        reputation_stake: 거는 평판 (0.01 ~ 0.3).
        reason: 베팅 근거 (선택).

    Returns:
        생성된 ``stake_id``.

    Raises:
        ValueError: 범위 위반 / 잔여 한도 초과.
    """
    rep = float(reputation_stake)
    if rep < MIN_BET or rep > MAX_SINGLE_BET:
        raise ValueError(
            f"reputation_stake 는 [{MIN_BET}, {MAX_SINGLE_BET}] 범위여야 합니다"
        )

    available = await available_reputation_to_stake(user_id)
    if rep > available:
        raise ValueError(
            f"걸 수 있는 평판 잔여 한도({available:.3f})를 초과했습니다"
        )

    profile = await prisma.contributorprofile.find_unique(where={"userId": user_id})
    if profile is None:
        raise ValueError("ContributorProfile 이 없습니다")
    current_rep = float(getattr(profile, "reputation", 0.0) or 0.0)

    # 평판 일시 동결 (원본 값에서 차감하여 저장)
    new_rep = _clip_reputation(current_rep - rep)
    await prisma.contributorprofile.update(
        where={"userId": user_id},
        data={"reputation": new_rep},
    )

    # ContributionStake 에 메타로 저장
    stake = await prisma.contributionstake.create(
        data={
            "userId": user_id,
            "factId": fact_id,
            "amount": 0,  # 토큰 stake 는 없음
            "status": "active",
            "context": "reputation_stake",
            "metadata": {
                "reputation_stake": rep,
                "reason": reason,
                "frozen_at": _now().isoformat(),
            },
        }
    )
    logger.info(
        "평판 스테이킹: user=%s fact=%s rep=%.3f stake_id=%s",
        user_id,
        fact_id,
        rep,
        stake.id,
    )
    return stake.id


async def available_reputation_to_stake(user_id: str) -> float:
    """현재 걸 수 있는 평판 잔여 한도.

    ``min(MAX_TOTAL_ACTIVE - active_stake_sum, current_reputation)``.
    """
    profile = await prisma.contributorprofile.find_unique(where={"userId": user_id})
    current_rep = float(getattr(profile, "reputation", 0.0) or 0.0) if profile else 0.0

    active = await prisma.contributionstake.find_many(
        where={"userId": user_id, "status": "active", "context": "reputation_stake"}
    )
    active_sum = sum(_extract_rep_stake(s) for s in (active or []))
    cap_remaining = max(0.0, MAX_TOTAL_ACTIVE - active_sum)
    return round(min(cap_remaining, current_rep), 4)


async def list_active_reputation_stakes(user_id: str) -> list[dict[str, Any]]:
    """활성 평판 스테이킹 목록."""
    rows = await prisma.contributionstake.find_many(
        where={
            "userId": user_id,
            "status": "active",
            "context": "reputation_stake",
        },
        order={"id": "desc"},
    )
    return [
        {
            "stake_id": r.id,
            "fact_id": r.factId,
            "reputation_stake": _extract_rep_stake(r),
            "frozen_at": (r.metadata or {}).get("frozen_at")
            if isinstance(r.metadata, dict)
            else None,
            "reason": (r.metadata or {}).get("reason")
            if isinstance(r.metadata, dict)
            else None,
        }
        for r in (rows or [])
    ]


# ---------------------------------------------------------------------------
# 2. 정산
# ---------------------------------------------------------------------------


async def settle_reputation_correct(
    stake_id: str, boost_multiplier: float = DEFAULT_BOOST_MULTIPLIER
) -> float:
    """정답 정산: 동결 평판 원상복구 + boost.

    보상 = reputation_stake * boost_multiplier (원금 + 추가 보상 모두 포함한 총합).

    Returns:
        정산 후 새 평판 값.
    """
    stake = await prisma.contributionstake.find_unique(where={"id": stake_id})
    if stake is None:
        raise ValueError("stake 를 찾을 수 없습니다")
    if stake.status != "active":
        raise ValueError(f"이미 정산됨 (status={stake.status})")

    rep = _extract_rep_stake(stake)
    reward = rep * float(boost_multiplier)

    profile = await prisma.contributorprofile.find_unique(
        where={"userId": stake.userId}
    )
    current = float(getattr(profile, "reputation", 0.0) or 0.0) if profile else 0.0
    new_rep = _clip_reputation(current + reward)

    await prisma.contributorprofile.update(
        where={"userId": stake.userId}, data={"reputation": new_rep}
    )
    await prisma.contributionstake.update(
        where={"id": stake_id},
        data={
            "status": "settled_correct",
            "metadata": {
                **(stake.metadata or {}),
                "settled_at": _now().isoformat(),
                "reward": reward,
                "boost_multiplier": boost_multiplier,
            },
        },
    )
    logger.info(
        "평판 정산(정답): user=%s rep=%.3f → %.3f (+%.3f)",
        stake.userId,
        current,
        new_rep,
        reward,
    )
    return new_rep


async def settle_reputation_wrong(
    stake_id: str, penalty_multiplier: float = DEFAULT_PENALTY_MULTIPLIER
) -> float:
    """오답 정산: 걸었던 평판 × penalty 만큼 차감.

    원금은 이미 동결 차감되어 있으므로, **추가로** penalty 비례 차감.
    총 손실 = reputation_stake * penalty_multiplier (단, floor 0.0).

    Returns:
        정산 후 새 평판 값.
    """
    stake = await prisma.contributionstake.find_unique(where={"id": stake_id})
    if stake is None:
        raise ValueError("stake 를 찾을 수 없습니다")
    if stake.status != "active":
        raise ValueError(f"이미 정산됨 (status={stake.status})")

    rep = _extract_rep_stake(stake)
    extra_penalty = rep * max(0.0, float(penalty_multiplier) - 1.0)

    profile = await prisma.contributorprofile.find_unique(
        where={"userId": stake.userId}
    )
    current = float(getattr(profile, "reputation", 0.0) or 0.0) if profile else 0.0
    new_rep = _clip_reputation(current - extra_penalty)

    await prisma.contributorprofile.update(
        where={"userId": stake.userId}, data={"reputation": new_rep}
    )
    await prisma.contributionstake.update(
        where={"id": stake_id},
        data={
            "status": "settled_wrong",
            "metadata": {
                **(stake.metadata or {}),
                "settled_at": _now().isoformat(),
                "total_loss": rep * float(penalty_multiplier),
                "penalty_multiplier": penalty_multiplier,
            },
        },
    )
    logger.warning(
        "평판 정산(오답): user=%s rep=%.3f → %.3f (-%.3f)",
        stake.userId,
        current,
        new_rep,
        rep + extra_penalty,
    )
    return new_rep


async def auto_settle_reputation_stakes(
    older_than_days: int = AUTO_SETTLE_DEFAULT_DAYS,
) -> dict[str, Any]:
    """오래 미정산된 평판 스테이킹 자동 처리.

    대응 규칙: 같은 ``factId`` 의 최종 fact.status 를 보고
        - CONFIRMED → correct
        - RETRACTED / EXPIRED → wrong
        - 그 외 → skip
    """
    cutoff = _now() - timedelta(days=older_than_days)
    rows = await prisma.contributionstake.find_many(
        where={
            "status": "active",
            "context": "reputation_stake",
            "createdAt": {"lt": cutoff},
        }
    )
    correct = wrong = skipped = 0
    for r in rows or []:
        fact = await prisma.knowledgefact.find_unique(where={"id": r.factId})
        if fact is None:
            skipped += 1
            continue
        if fact.status == "CONFIRMED":
            try:
                await settle_reputation_correct(r.id)
                correct += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("auto settle correct 실패 %s: %s", r.id, e)
                skipped += 1
        elif fact.status in ("RETRACTED", "EXPIRED"):
            try:
                await settle_reputation_wrong(r.id)
                wrong += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("auto settle wrong 실패 %s: %s", r.id, e)
                skipped += 1
        else:
            skipped += 1
    return {
        "scanned": len(rows or []),
        "settled_correct": correct,
        "settled_wrong": wrong,
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# 3. 히스토리 / 랭킹
# ---------------------------------------------------------------------------


async def reputation_bet_history(
    user_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    """사용자의 평판 베팅 히스토리."""
    rows = await prisma.contributionstake.find_many(
        where={"userId": user_id, "context": "reputation_stake"},
        take=limit,
        order={"id": "desc"},
    )
    out: list[dict[str, Any]] = []
    for r in rows or []:
        rep = _extract_rep_stake(r)
        meta = r.metadata if isinstance(r.metadata, dict) else {}
        reward = float(meta.get("reward") or 0.0)
        loss = float(meta.get("total_loss") or 0.0)
        pnl = reward - loss - rep if r.status == "settled_wrong" else reward - rep
        if r.status == "active":
            pnl = 0.0
        out.append(
            {
                "stake_id": r.id,
                "fact_id": r.factId,
                "reputation_stake": rep,
                "status": r.status,
                "pnl": round(pnl, 4),
                "reason": meta.get("reason"),
                "settled_at": meta.get("settled_at"),
            }
        )
    return out


async def reputation_bet_leaderboard(limit: int = 20) -> list[dict[str, Any]]:
    """평판 베팅 누적 수익 랭킹."""
    rows = await prisma.contributionstake.find_many(
        where={"context": "reputation_stake"},
    )
    agg: dict[str, dict[str, float]] = {}
    for r in rows or []:
        rep = _extract_rep_stake(r)
        meta = r.metadata if isinstance(r.metadata, dict) else {}
        reward = float(meta.get("reward") or 0.0)
        loss = float(meta.get("total_loss") or 0.0)
        d = agg.setdefault(
            r.userId, {"net": 0.0, "wins": 0, "losses": 0, "total_bets": 0}
        )
        d["total_bets"] += 1
        if r.status == "settled_correct":
            d["net"] += reward - rep
            d["wins"] += 1
        elif r.status == "settled_wrong":
            d["net"] += -(loss - rep)  # 순손실
            d["losses"] += 1
    ranked = sorted(agg.items(), key=lambda kv: kv[1]["net"], reverse=True)[:limit]
    return [
        {
            "user_id": uid,
            "net_gain": round(d["net"], 4),
            "wins": int(d["wins"]),
            "losses": int(d["losses"]),
            "total_bets": int(d["total_bets"]),
        }
        for uid, d in ranked
    ]


# ---------------------------------------------------------------------------
# 4. 리스크 관리 / 군중 신호
# ---------------------------------------------------------------------------


async def warn_excessive_risk(user_id: str) -> dict[str, Any] | None:
    """최근 1주일 베팅 합이 총 평판의 50% 이상이면 경고 반환."""
    since = _now() - timedelta(days=RECENT_WINDOW_DAYS)
    rows = await prisma.contributionstake.find_many(
        where={
            "userId": user_id,
            "context": "reputation_stake",
            "createdAt": {"gte": since},
        }
    )
    recent_sum = sum(_extract_rep_stake(r) for r in (rows or []))

    profile = await prisma.contributorprofile.find_unique(where={"userId": user_id})
    current_rep = float(getattr(profile, "reputation", 0.0) or 0.0) if profile else 0.0
    # 위험 비율 계산 시 분모가 0 이면 비율을 1.0 으로 (최대 경고)
    total_base = current_rep + recent_sum
    ratio = (recent_sum / total_base) if total_base > 0 else 0.0

    if ratio >= EXCESSIVE_RISK_RATIO:
        return {
            "user_id": user_id,
            "recent_bet_sum": round(recent_sum, 4),
            "current_reputation": round(current_rep, 4),
            "risk_ratio": round(ratio, 4),
            "message": (
                "최근 1주일 평판 베팅이 과도합니다. "
                "분산 투자와 휴식을 권장합니다."
            ),
        }
    return None


def _reputation_weighted_confidence(
    fact: KnowledgeFact, reputation_stake: float
) -> float:
    """평판 스테이킹이 추가될 때의 신뢰도 가중치.

    기본 confidence 에 최대 ``+reputation_stake * 0.5`` 의 boost 를 더해
    0~1 로 clip. 평판은 군중 신호로 작동.
    """
    base = float(fact.confidence_t0 or 0.0)
    boost = float(reputation_stake) * 0.5
    return _clip_reputation(base + boost)


async def fact_reputation_backing(fact_id: str) -> dict[str, Any]:
    """특정 사실에 평판을 건 사람들의 집계."""
    rows = await prisma.contributionstake.find_many(
        where={
            "factId": fact_id,
            "context": "reputation_stake",
            "status": "active",
        }
    )
    rows = list(rows or [])
    backers: list[dict[str, Any]] = []
    total = 0.0
    for r in rows:
        rep = _extract_rep_stake(r)
        total += rep
        backers.append({"user_id": r.userId, "reputation_stake": rep})
    avg = (total / len(rows)) if rows else 0.0
    return {
        "fact_id": fact_id,
        "total_reputation_staked": round(total, 4),
        "backer_count": len(rows),
        "avg_stake": round(avg, 4),
        "backers": backers,
    }


async def compute_fact_crowd_confidence(fact_id: str) -> float:
    """사실의 군중 신뢰도 = (사실에 걸린 평판 합) / (활성 기여자 평균 평판).

    값이 클수록 군중이 강한 확신으로 베팅한 사실. 0~1 로 clip.
    """
    backing = await fact_reputation_backing(fact_id)
    total = float(backing["total_reputation_staked"])
    if total <= 0:
        return 0.0

    profiles = await prisma.contributorprofile.find_many(
        where={"tier": {"not": "SUSPENDED"}}, take=500
    )
    reps = [float(getattr(p, "reputation", 0.0) or 0.0) for p in (profiles or [])]
    if not reps:
        return 0.0
    avg_rep = float(statistics.mean(reps))
    if avg_rep <= 0:
        return 0.0
    raw = total / (avg_rep * max(1, backing["backer_count"]))
    return round(_clip_reputation(raw), 4)
