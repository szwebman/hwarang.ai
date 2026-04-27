"""HLKM — 기여자 등급 시스템 (Contributor Tier).

Bronze / Silver / Gold / Diamond / Suspended 5단계 등급.
등급에 따라 기여 가능 도메인, 동료 검토 권한, 분쟁 투표 권한,
일일 기여 한도가 달라진다.

핵심 규칙:
  - EMA 기반 평판(reputation) 업데이트 (alpha=0.15)
  - 승급: TIER_REQUIREMENTS 충족 시 자동 평가
  - 강등: 최근 슬래시 비율 급증 시 자동 강등
  - 권한 체크는 반드시 이 모듈 함수를 통해 중앙화

의존:
  - `hwarang_api.db.prisma`
  - `.types.KnowledgeFact`
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from hwarang_api.db import prisma

from .types import KnowledgeFact  # noqa: F401 (spec 요구: 타입 의존 명시)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
EMA_ALPHA = 0.15                  # 평판 EMA 가중치
MIN_REPUTATION = 0.0
MAX_REPUTATION = 1.0
INITIAL_REPUTATION = 0.5
CORRECT_BOOST = 0.05              # 정답 기여 시 반영할 관측값 상승분
WRONG_PENALTY = 0.2               # 오답 기여 시 반영할 관측값 하락분

# 등급별 승급 조건
TIER_REQUIREMENTS: dict = {
    "SILVER": {
        "min_correct": 5,
        "min_reputation": 0.6,
        "min_kyc": True,
        "max_slash_ratio": 0.3,
    },
    "GOLD": {
        "min_correct": 50,
        "min_reputation": 0.75,
        "min_kyc": True,
        "max_slash_ratio": 0.15,
        "min_months_active": 1,
    },
    "DIAMOND": {
        "min_correct": 500,
        "min_reputation": 0.88,
        "min_kyc": True,
        "max_slash_ratio": 0.05,
        "min_months_active": 6,
        "expert_or_vote_count": 20,
    },
}

# 등급별 권한
TIER_PERMISSIONS: dict = {
    "BRONZE": {
        "domains": ["general", "tech"],
        "peer_review": False,
        "dispute_vote": False,
        "daily_contrib_limit": 5,
    },
    "SILVER": {
        "domains": ["general", "tech", "news", "local_law"],
        "peer_review": True,
        "dispute_vote": False,
        "daily_contrib_limit": 20,
    },
    "GOLD": {
        "domains": "*",
        "peer_review": True,
        "dispute_vote": False,
        "daily_contrib_limit": 50,
    },
    "DIAMOND": {
        "domains": "*",
        "peer_review": True,
        "dispute_vote": True,
        "daily_contrib_limit": 100,
    },
    "SUSPENDED": {
        "domains": [],
        "peer_review": False,
        "dispute_vote": False,
        "daily_contrib_limit": 0,
    },
}

# 한국어 등급명 및 뱃지
_TIER_DISPLAY_KO: dict[str, str] = {
    "BRONZE": "브론즈",
    "SILVER": "실버",
    "GOLD": "골드",
    "DIAMOND": "다이아몬드",
    "SUSPENDED": "정지됨",
}

_TIER_BADGE: dict[str, str] = {
    "BRONZE": "🥉",
    "SILVER": "🥈",
    "GOLD": "🥇",
    "DIAMOND": "💎",
    "SUSPENDED": "⛔",
}


# ─────────────────────────────────────────────
# 프로필 조회/생성
# ─────────────────────────────────────────────
async def get_or_create_profile(user_id: str) -> dict:
    """사용자의 ContributorProfile 을 조회하거나 생성한다.

    Bronze 등급, 평판 0.5 로 초기화한다.
    """
    row = await prisma.contributorprofile.find_unique(where={"userId": user_id})
    if row is not None:
        return _row_to_dict(row)

    created = await prisma.contributorprofile.create(
        data={
            "userId": user_id,
            "tier": "BRONZE",
            "reputation": INITIAL_REPUTATION,
            "stakedBalance": 0,
            "correctContribs": 0,
            "wrongContribs": 0,
            "totalEarned": 0,
            "kycVerified": False,
            "expertTags": [],
        }
    )
    logger.info("contributor profile created: user=%s tier=BRONZE", user_id)
    return _row_to_dict(created)


def _row_to_dict(row) -> dict:
    """Prisma ContributorProfile row → dict."""
    return {
        "user_id": row.userId,
        "tier": row.tier,
        "reputation": float(row.reputation),
        "staked_balance": int(row.stakedBalance),
        "correct_contribs": int(row.correctContribs),
        "wrong_contribs": int(row.wrongContribs),
        "total_earned": int(row.totalEarned),
        "kyc_verified": bool(row.kycVerified),
        "expert_tags": list(row.expertTags or []),
        "suspension_reason": row.suspensionReason,
        "suspended_until": row.suspendedUntil,
    }


# ─────────────────────────────────────────────
# 평판 업데이트
# ─────────────────────────────────────────────
async def update_reputation(user_id: str, delta: float, reason: str) -> float:
    """평판을 EMA 기반으로 업데이트한다.

    new = (1-α)·old + α·observation  where observation = clamp(old+delta, 0, 1)
    [0, 1] 범위로 클램프한다.
    """
    profile = await get_or_create_profile(user_id)
    old = float(profile["reputation"])
    observation = max(MIN_REPUTATION, min(MAX_REPUTATION, old + float(delta)))
    new = (1.0 - EMA_ALPHA) * old + EMA_ALPHA * observation
    new = max(MIN_REPUTATION, min(MAX_REPUTATION, new))

    await prisma.contributorprofile.update(
        where={"userId": user_id},
        data={"reputation": new},
    )
    logger.info(
        "reputation update: user=%s %.3f → %.3f (Δobs=%.3f, reason=%s)",
        user_id, old, new, delta, reason,
    )
    return new


async def record_correct_contribution(
    user_id: str, fact_id: str, reward: int
) -> None:
    """정답 기여 기록: correctContribs++, totalEarned+=reward, 평판 상승."""
    profile = await get_or_create_profile(user_id)
    await prisma.contributorprofile.update(
        where={"userId": user_id},
        data={
            "correctContribs": profile["correct_contribs"] + 1,
            "totalEarned": profile["total_earned"] + int(reward),
        },
    )
    await update_reputation(user_id, CORRECT_BOOST, reason=f"correct:{fact_id}")


async def record_wrong_contribution(
    user_id: str, fact_id: str, slash: int
) -> None:
    """오답 기여 기록: wrongContribs++, 평판 하락."""
    profile = await get_or_create_profile(user_id)
    await prisma.contributorprofile.update(
        where={"userId": user_id},
        data={"wrongContribs": profile["wrong_contribs"] + 1},
    )
    await update_reputation(user_id, -WRONG_PENALTY, reason=f"wrong:{fact_id}")
    logger.info("wrong contrib: user=%s fact=%s slash=%d", user_id, fact_id, slash)


# ─────────────────────────────────────────────
# 등급 평가
# ─────────────────────────────────────────────
async def _months_active(user_id: str) -> float:
    """사용자가 활동한 개월 수 (가장 오래된 KnowledgeFact 기준)."""
    row = await prisma.knowledgefact.find_first(
        where={"contributedBy": user_id},
        order={"createdAt": "asc"},
    )
    if row is None or row.createdAt is None:
        return 0.0
    delta = datetime.now(timezone.utc) - row.createdAt
    return delta.days / 30.0


async def _vote_count(user_id: str) -> int:
    """해당 사용자가 작성한 PeerReview 개수 (DIAMOND 평가용)."""
    try:
        return await prisma.peerreview.count(where={"reviewerId": user_id})
    except Exception:  # pragma: no cover
        return 0


def _slash_ratio(profile: dict) -> float:
    total = profile["correct_contribs"] + profile["wrong_contribs"]
    if total <= 0:
        return 0.0
    return profile["wrong_contribs"] / total


async def evaluate_tier_upgrade(user_id: str) -> str | None:
    """TIER_REQUIREMENTS 체크하여 다음 등급 조건 충족 시 승급시킨다.

    Return: 새 등급 문자열 or None (변동 없음).
    """
    profile = await get_or_create_profile(user_id)
    current_tier = profile["tier"]

    if current_tier == "SUSPENDED":
        return None

    # 승급 우선순위: 현 등급보다 높은 목표 먼저 평가 (DIAMOND → GOLD → SILVER)
    candidate_order = ["DIAMOND", "GOLD", "SILVER"]
    current_rank = _tier_rank(current_tier)

    months_active = await _months_active(user_id)
    votes = await _vote_count(user_id)
    slash_ratio = _slash_ratio(profile)

    for target in candidate_order:
        if _tier_rank(target) <= current_rank:
            continue
        req = TIER_REQUIREMENTS.get(target)
        if not req:
            continue

        if profile["correct_contribs"] < req["min_correct"]:
            continue
        if profile["reputation"] < req["min_reputation"]:
            continue
        if req.get("min_kyc") and not profile["kyc_verified"]:
            continue
        if slash_ratio > req.get("max_slash_ratio", 1.0):
            continue
        if months_active < req.get("min_months_active", 0):
            continue
        if target == "DIAMOND":
            # 전문가 자격 있거나 검토 수 충족
            is_expert = len(profile["expert_tags"]) > 0
            if not is_expert and votes < req.get("expert_or_vote_count", 0):
                continue

        await prisma.contributorprofile.update(
            where={"userId": user_id},
            data={"tier": target},
        )
        logger.info("tier promotion: user=%s %s → %s", user_id, current_tier, target)
        return target

    return None


def _tier_rank(tier: str) -> int:
    return {"SUSPENDED": -1, "BRONZE": 0, "SILVER": 1, "GOLD": 2, "DIAMOND": 3}.get(tier, 0)


async def auto_promote_eligible(batch: int = 100) -> dict:
    """배치로 모든 사용자 승급 검토를 실행한다.

    Return: {"checked": N, "promoted": [(user_id, new_tier), ...]}
    """
    rows = await prisma.contributorprofile.find_many(
        where={"tier": {"not": "SUSPENDED"}},
        take=batch,
    )
    promoted: list[tuple[str, str]] = []
    for r in rows:
        new_tier = await evaluate_tier_upgrade(r.userId)
        if new_tier:
            promoted.append((r.userId, new_tier))
    logger.info("auto_promote: checked=%d promoted=%d", len(rows), len(promoted))
    return {"checked": len(rows), "promoted": promoted}


async def demote_if_degraded(user_id: str) -> str | None:
    """최근 슬래시 비율이 급증한 사용자를 한 등급 강등시킨다.

    Return: 새 등급 or None.
    """
    profile = await get_or_create_profile(user_id)
    current = profile["tier"]
    if current in ("BRONZE", "SUSPENDED"):
        return None

    slash_ratio = _slash_ratio(profile)
    req = TIER_REQUIREMENTS.get(current, {})
    max_allowed = req.get("max_slash_ratio", 0.5)
    # 현재 등급 유지 기준을 초과하면 강등
    if slash_ratio <= max_allowed * 1.5:
        return None

    new_tier = {"SILVER": "BRONZE", "GOLD": "SILVER", "DIAMOND": "GOLD"}.get(current)
    if not new_tier:
        return None

    await prisma.contributorprofile.update(
        where={"userId": user_id},
        data={"tier": new_tier},
    )
    logger.warning(
        "tier demotion: user=%s %s → %s (slash_ratio=%.2f)",
        user_id, current, new_tier, slash_ratio,
    )
    return new_tier


# ─────────────────────────────────────────────
# 권한 체크 (중앙화)
# ─────────────────────────────────────────────
async def can_contribute_to_domain(user_id: str, domain: str) -> bool:
    """해당 tier 의 도메인 권한에 포함되는지 판정한다."""
    profile = await get_or_create_profile(user_id)
    perms = TIER_PERMISSIONS.get(profile["tier"], {})
    domains = perms.get("domains", [])
    if domains == "*":
        return True
    return domain in domains


async def can_peer_review(user_id: str) -> bool:
    """동료 검토 권한 보유 여부."""
    profile = await get_or_create_profile(user_id)
    return bool(TIER_PERMISSIONS.get(profile["tier"], {}).get("peer_review"))


async def can_vote_dispute(user_id: str) -> bool:
    """분쟁 투표 권한 보유 여부."""
    profile = await get_or_create_profile(user_id)
    return bool(TIER_PERMISSIONS.get(profile["tier"], {}).get("dispute_vote"))


# ─────────────────────────────────────────────
# 일일 기여 한도
# ─────────────────────────────────────────────
async def daily_contribution_count(user_id: str) -> int:
    """오늘(UTC 기준) 해당 사용자가 생성한 KnowledgeFact 수."""
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        return await prisma.knowledgefact.count(
            where={"contributedBy": user_id, "createdAt": {"gte": start}},
        )
    except Exception:  # pragma: no cover
        return 0


async def within_daily_limit(user_id: str) -> bool:
    """해당 사용자가 아직 일일 기여 한도 내에 있는지 여부."""
    profile = await get_or_create_profile(user_id)
    perms = TIER_PERMISSIONS.get(profile["tier"], {})
    limit = int(perms.get("daily_contrib_limit", 0))
    if limit <= 0 and profile["tier"] != "SUSPENDED":
        # 명시적으로 0 이면 불허
        return False
    if profile["tier"] == "SUSPENDED":
        return False
    used = await daily_contribution_count(user_id)
    return used < limit


# ─────────────────────────────────────────────
# 통계 / 랭킹
# ─────────────────────────────────────────────
async def tier_distribution() -> dict:
    """현재 등급별 사용자 수 집계."""
    result: dict[str, int] = {t: 0 for t in ("BRONZE", "SILVER", "GOLD", "DIAMOND", "SUSPENDED")}
    rows = await prisma.contributorprofile.find_many(take=100000)
    for r in rows:
        result[r.tier] = result.get(r.tier, 0) + 1
    return result


async def leaderboard(by: str = "reputation", limit: int = 50) -> list[dict]:
    """리더보드 조회.

    by ∈ {"reputation", "correctContribs", "totalEarned"}
    """
    allowed = {"reputation", "correctContribs", "totalEarned"}
    if by not in allowed:
        by = "reputation"

    rows = await prisma.contributorprofile.find_many(
        where={"tier": {"not": "SUSPENDED"}},
        order={by: "desc"},
        take=limit,
    )
    return [_row_to_dict(r) for r in rows]


# ─────────────────────────────────────────────
# 표시용 헬퍼
# ─────────────────────────────────────────────
def tier_display_name(tier: str) -> str:
    """등급 코드를 한국어 표시명으로 변환한다. (예: BRONZE → '브론즈')"""
    return _TIER_DISPLAY_KO.get(tier, tier)


def tier_badge_emoji(tier: str) -> str:
    """등급 뱃지 이모지를 반환한다."""
    return _TIER_BADGE.get(tier, "▫")


__all__ = [
    "TIER_REQUIREMENTS",
    "TIER_PERMISSIONS",
    "EMA_ALPHA",
    "get_or_create_profile",
    "update_reputation",
    "record_correct_contribution",
    "record_wrong_contribution",
    "evaluate_tier_upgrade",
    "auto_promote_eligible",
    "demote_if_degraded",
    "can_contribute_to_domain",
    "can_peer_review",
    "can_vote_dispute",
    "daily_contribution_count",
    "within_daily_limit",
    "tier_distribution",
    "leaderboard",
    "tier_display_name",
    "tier_badge_emoji",
]
