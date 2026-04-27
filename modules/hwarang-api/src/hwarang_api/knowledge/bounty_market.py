"""HLKM — 지식 현상금 시장 (Knowledge Bounty Market).

필요한 지식이 있는 사용자가 HWARANG 토큰으로 현상금을 걸면,
여러 기여자가 그에 대한 답변(KnowledgeFact)을 제출해 경쟁한다.
심사를 통해 최고 답변 1건을 선정하고 상금을 지급하며,
나머지 참가자에게도 소액 격려금을 지급한다.

주요 흐름::

    1. create_bounty  — 사용자가 reward_amount 를 에스크로해 Bounty open
    2. submit_to_bounty — 기여자가 기존/신규 fact 를 제출
    3. score_submissions — 자동/피어/창설자 방식으로 점수 매김
    4. award_bounty   — winner 지급 + 참가자 격려금 + 수수료 차감
    5. expire_bounty  — 마감 후 자동 환불/선정

평가 방법:
  - "arbitrator": arbitrated_confidence() 점수 자동 순위 (기본)
  - "peer_vote":  Diamond 등급 기여자 투표 결과
  - "creator":    Bounty 창설자 수동 선택

의존:
  - `hwarang_api.db.prisma`
  - `.types.KnowledgeFact`
  - `.contributor_tier.get_or_create_profile`, `can_contribute_to_domain`
  - `.staking.deposit_to_stake_balance`, `withdraw_stake_balance`
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma

from .contribution_gate import WriteAction, require_contribution_permission
from .contributor_tier import can_contribute_to_domain, get_or_create_profile
from .staking import deposit_to_stake_balance, withdraw_stake_balance
from .types import KnowledgeFact  # noqa: F401  (spec 요구: 타입 의존 명시)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
MIN_BOUNTY_AMOUNT: int = 50
MAX_BOUNTY_DURATION_DAYS: int = 90
PLATFORM_FEE_RATIO: float = 0.05  # 플랫폼 수수료 5%
PARTICIPATION_POOL_RATIO: float = 0.10  # 남은 reward 중 격려금 풀 10%

_TIER_RANK: dict[str, int] = {
    "SUSPENDED": -1,
    "BRONZE": 0,
    "SILVER": 1,
    "GOLD": 2,
    "DIAMOND": 3,
}

_VALID_TIERS = {"BRONZE", "SILVER", "GOLD", "DIAMOND"}
_VALID_JUDGING = {"arbitrator", "peer_vote", "creator"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ─────────────────────────────────────────────
# Bounty 생성
# ─────────────────────────────────────────────
async def create_bounty(
    creator_id: str,
    topic: str,
    description: str,
    reward_amount: int,
    deadline_days: int = 14,
    domain: str | None = None,
    required_tier: str = "SILVER",
    bypass_gate: bool = False,
) -> str:
    """현상금 지식 요청 생성 (에스크로 차감).

    검증:
      - reward_amount >= MIN_BOUNTY_AMOUNT
      - 0 < deadline_days <= MAX_BOUNTY_DURATION_DAYS
      - required_tier 가 유효한 값인지 확인
      - 생성자 잔액이 reward_amount 이상인지 확인
    반환: 생성된 bounty_id
    """
    # KYC 게이트
    if not bypass_gate:
        await require_contribution_permission(
            creator_id,
            WriteAction.BOUNTY_CREATE.value,
            domain=domain,
        )

    amount = int(reward_amount)
    if amount < MIN_BOUNTY_AMOUNT:
        raise ValueError(f"reward_amount 는 최소 {MIN_BOUNTY_AMOUNT} 이상이어야 합니다.")
    if deadline_days <= 0 or deadline_days > MAX_BOUNTY_DURATION_DAYS:
        raise ValueError(
            f"deadline_days 는 1~{MAX_BOUNTY_DURATION_DAYS} 사이여야 합니다."
        )
    tier = (required_tier or "SILVER").upper()
    if tier not in _VALID_TIERS:
        raise ValueError(f"required_tier 값이 올바르지 않습니다: {required_tier}")
    if not topic or not topic.strip():
        raise ValueError("topic 은 비어 있을 수 없습니다.")

    # 에스크로 — 생성자 staked balance 로 이동 (부족 시 예외 발생)
    try:
        await deposit_to_stake_balance(creator_id, amount, reason=f"bounty_escrow:{topic[:40]}")
    except Exception as exc:
        logger.warning("bounty 에스크로 실패 user=%s amount=%d: %s", creator_id, amount, exc)
        raise

    deadline = _utcnow() + timedelta(days=deadline_days)
    row = await prisma.bounty.create(
        data={
            "creatorId": creator_id,
            "topic": topic.strip(),
            "description": description or "",
            "domain": (domain or "general").lower(),
            "rewardAmount": amount,
            "requiredTier": tier,
            "deadline": deadline,
            "status": "open",
        }
    )

    # 관련 KnowledgeGap 자동 연결 (topic 정확 매칭)
    try:
        gap = await prisma.knowledgegap.find_unique(where={"topic": topic.strip()})
        if gap is not None:
            await prisma.knowledgegap.update(
                where={"id": gap.id},
                data={"bountyId": row.id},
            )
    except Exception as exc:
        logger.debug("knowledge gap 연결 스킵: %s", exc)

    logger.info(
        "bounty created: id=%s creator=%s topic=%s reward=%d deadline_days=%d",
        row.id, creator_id, topic[:30], amount, deadline_days,
    )
    return row.id


# ─────────────────────────────────────────────
# Submission
# ─────────────────────────────────────────────
async def submit_to_bounty(
    bounty_id: str,
    contributor_id: str,
    fact_id: str,
    submission_note: str | None = None,
    bypass_gate: bool = False,
) -> str:
    """기존 KnowledgeFact 를 Bounty 답변으로 제출.

    검증:
      - bounty.status == "open"
      - deadline 이전
      - contributor 등급이 required_tier 이상
      - 해당 도메인에 기여 가능한 권한 (`can_contribute_to_domain`)
      - 본인 bounty 에 제출 불가
      - (bountyId, factId) 중복 제출 불가 (DB 레벨 unique)
    반환: submission_id
    """
    # KYC 게이트
    if not bypass_gate:
        await require_contribution_permission(
            contributor_id, WriteAction.BOUNTY_SUBMIT.value
        )

    bounty = await prisma.bounty.find_unique(where={"id": bounty_id})
    if bounty is None:
        raise ValueError(f"bounty not found: {bounty_id}")
    if bounty.status != "open":
        raise ValueError(f"bounty 상태가 open 이 아닙니다: {bounty.status}")
    deadline = _as_aware(bounty.deadline)
    if deadline is not None and deadline < _utcnow():
        raise ValueError("bounty 마감시간이 지났습니다.")

    if bounty.creatorId == contributor_id:
        raise ValueError("본인이 생성한 bounty 에는 제출할 수 없습니다.")

    # 기여자 등급 체크
    profile = await get_or_create_profile(contributor_id)
    required_rank = _TIER_RANK.get(bounty.requiredTier, 1)
    my_rank = _TIER_RANK.get(profile["tier"], 0)
    if my_rank < required_rank:
        raise ValueError(
            f"등급 부족: {bounty.requiredTier} 이상 필요 (현재 {profile['tier']})"
        )

    # 도메인 권한
    if not await can_contribute_to_domain(contributor_id, bounty.domain or "general"):
        raise ValueError(f"해당 도메인 기여 권한이 없습니다: {bounty.domain}")

    # fact 존재 확인
    fact = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if fact is None:
        raise ValueError(f"fact not found: {fact_id}")

    try:
        row = await prisma.bountysubmission.create(
            data={
                "bountyId": bounty_id,
                "contributorId": contributor_id,
                "factId": fact_id,
                "submissionNote": submission_note,
                "score": 0.0,
                "selected": False,
            }
        )
    except Exception as exc:
        # unique 제약 위반 가능성 (bountyId, factId)
        msg = str(exc)
        if "unique" in msg.lower() or "Unique" in msg:
            raise ValueError("동일 fact 로 이미 제출되었습니다.") from exc
        raise

    logger.info(
        "bounty submission: bounty=%s contributor=%s fact=%s",
        bounty_id, contributor_id, fact_id,
    )
    return row.id


# ─────────────────────────────────────────────
# 점수 매기기
# ─────────────────────────────────────────────
async def score_submissions(
    bounty_id: str, judging_method: str = "arbitrator"
) -> list[dict]:
    """제출물들에 점수를 매겨 순위 리스트를 반환한다.

    - arbitrator: arbitrated_confidence() 호출해 자동 점수
    - peer_vote:  Diamond 등급 투표 수 기반
    - creator:    창설자가 score 를 직접 매긴 결과 사용 (아직 미채점이면 0)
    """
    method = (judging_method or "arbitrator").lower()
    if method not in _VALID_JUDGING:
        raise ValueError(f"judging_method 값 오류: {judging_method}")

    bounty = await prisma.bounty.find_unique(where={"id": bounty_id})
    if bounty is None:
        raise ValueError(f"bounty not found: {bounty_id}")

    submissions = await prisma.bountysubmission.find_many(
        where={"bountyId": bounty_id}
    )
    if not submissions:
        return []

    ranked: list[dict] = []

    if method == "arbitrator":
        # arbitrator 모듈의 arbitrated_confidence 로 자동 점수화
        try:
            from .arbitrator import arbitrated_confidence  # type: ignore
        except Exception:
            arbitrated_confidence = None  # type: ignore

        for s in submissions:
            score = 0.0
            try:
                fact_row = await prisma.knowledgefact.find_unique(
                    where={"id": s.factId}
                )
                if fact_row is not None and arbitrated_confidence is not None:
                    fact_pydantic = KnowledgeFact(
                        id=fact_row.id,
                        content=fact_row.content,
                        domain=fact_row.domain or "general",
                        valid_from=fact_row.validFrom,
                        confidence_t0=float(fact_row.confidenceT0 or 1.0),
                        source=fact_row.source or "",
                    )
                    res = await arbitrated_confidence(fact_pydantic)
                    score = float(res.get("score", 0.0))
            except Exception as exc:
                logger.warning("arbitrator 점수 실패 sub=%s: %s", s.id, exc)
                score = 0.0
            await prisma.bountysubmission.update(
                where={"id": s.id},
                data={"score": score},
            )
            ranked.append(
                {
                    "submission_id": s.id,
                    "contributor_id": s.contributorId,
                    "fact_id": s.factId,
                    "score": score,
                }
            )

    elif method == "peer_vote":
        # Diamond 등급 투표 수 (KnowledgeContribution 의 votesUp 활용)
        for s in submissions:
            votes_up = 0
            try:
                contribs = await prisma.knowledgecontribution.find_many(
                    where={"factId": s.factId}
                )
                for c in contribs:
                    votes_up += int(getattr(c, "votesUp", 0) or 0)
            except Exception:
                votes_up = 0
            score = float(votes_up)
            await prisma.bountysubmission.update(
                where={"id": s.id},
                data={"score": score},
            )
            ranked.append(
                {
                    "submission_id": s.id,
                    "contributor_id": s.contributorId,
                    "fact_id": s.factId,
                    "score": score,
                }
            )

    else:  # creator
        for s in submissions:
            score = float(s.score or 0.0)
            ranked.append(
                {
                    "submission_id": s.id,
                    "contributor_id": s.contributorId,
                    "fact_id": s.factId,
                    "score": score,
                }
            )

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked


# ─────────────────────────────────────────────
# 수상 / 지급
# ─────────────────────────────────────────────
async def award_bounty(
    bounty_id: str,
    winner_submission_id: str | None = None,
    admin_id: str | None = None,
) -> dict:
    """Bounty 종료 및 상금 지급.

    - winner_submission_id 가 없으면 자동 점수(arbitrator) 1등 선택
    - winner: reward × (1 - PLATFORM_FEE_RATIO) 지급
    - 나머지 참가자: (reward × PARTICIPATION_POOL_RATIO) 를 n 등분
      (단, winner 제외한 참가자 수 기준)
    - PLATFORM_FEE 는 시스템 풀(로그)로 기록
    - Bounty.status=awarded, winnerId, winnerFactId, awardedAt 업데이트
    반환: {"winner_id", "reward_paid", "participants_rewards": {...}, "platform_fee"}
    """
    bounty = await prisma.bounty.find_unique(where={"id": bounty_id})
    if bounty is None:
        raise ValueError(f"bounty not found: {bounty_id}")
    if bounty.status != "open":
        raise ValueError(f"bounty 상태가 open 이 아닙니다: {bounty.status}")

    submissions = await prisma.bountysubmission.find_many(
        where={"bountyId": bounty_id}
    )
    if not submissions:
        raise ValueError("제출물이 없어 수상할 수 없습니다. expire_bounty 를 사용하세요.")

    # winner 결정
    winner_sub = None
    if winner_submission_id:
        for s in submissions:
            if s.id == winner_submission_id:
                winner_sub = s
                break
        if winner_sub is None:
            raise ValueError(f"submission not found in bounty: {winner_submission_id}")
    else:
        ranked = await score_submissions(bounty_id, judging_method="arbitrator")
        if not ranked:
            raise ValueError("자동 채점 결과가 비어있습니다.")
        top = ranked[0]
        for s in submissions:
            if s.id == top["submission_id"]:
                winner_sub = s
                break
        if winner_sub is None:
            raise ValueError("winner 를 확정할 수 없습니다.")

    reward = int(bounty.rewardAmount or 0)
    platform_fee = int(round(reward * PLATFORM_FEE_RATIO))
    remaining = reward - platform_fee  # 기여자 풀 총합

    # 격려금 풀 계산
    losers = [s for s in submissions if s.id != winner_sub.id]
    participation_pool = 0
    per_participant = 0
    if losers:
        participation_pool = int(round(reward * PARTICIPATION_POOL_RATIO))
        if participation_pool > remaining:
            participation_pool = max(0, remaining - 1)  # winner 최소 1 보장
        per_participant = participation_pool // max(1, len(losers))

    winner_reward = remaining - (per_participant * len(losers))
    if winner_reward < 1:
        winner_reward = max(1, remaining)
        per_participant = 0
        losers = []

    # 에스크로에서 상금 지급
    try:
        await withdraw_stake_balance(
            bounty.creatorId,
            winner_reward,
            reason=f"bounty_award:{bounty_id}:winner",
            beneficiary_id=winner_sub.contributorId,
        )
    except TypeError:
        # beneficiary 인자 미지원 시 fallback: 에스크로 해제 후 수령자에게 deposit
        await withdraw_stake_balance(
            bounty.creatorId, winner_reward, reason=f"bounty_award:{bounty_id}:winner"
        )
        try:
            await deposit_to_stake_balance(
                winner_sub.contributorId,
                winner_reward,
                reason=f"bounty_award:{bounty_id}:winner",
            )
        except Exception as exc:
            logger.warning("winner deposit 실패: %s", exc)

    participants_rewards: dict[str, int] = {}
    for l in losers:
        if per_participant <= 0:
            break
        try:
            await withdraw_stake_balance(
                bounty.creatorId,
                per_participant,
                reason=f"bounty_award:{bounty_id}:participant",
                beneficiary_id=l.contributorId,
            )
        except TypeError:
            await withdraw_stake_balance(
                bounty.creatorId,
                per_participant,
                reason=f"bounty_award:{bounty_id}:participant",
            )
            try:
                await deposit_to_stake_balance(
                    l.contributorId,
                    per_participant,
                    reason=f"bounty_award:{bounty_id}:participant",
                )
            except Exception as exc:
                logger.warning("participant deposit 실패: %s", exc)
        participants_rewards[l.contributorId] = (
            participants_rewards.get(l.contributorId, 0) + per_participant
        )

    # PLATFORM_FEE 는 에스크로에서 withdraw (시스템 풀 기록용)
    if platform_fee > 0:
        try:
            await withdraw_stake_balance(
                bounty.creatorId,
                platform_fee,
                reason=f"bounty_platform_fee:{bounty_id}",
            )
        except Exception as exc:
            logger.warning("platform fee withdraw 실패: %s", exc)

    # 상태 업데이트
    await prisma.bounty.update(
        where={"id": bounty_id},
        data={
            "status": "awarded",
            "winnerId": winner_sub.contributorId,
            "winnerFactId": winner_sub.factId,
            "awardedAt": _utcnow(),
        },
    )
    await prisma.bountysubmission.update(
        where={"id": winner_sub.id},
        data={"selected": True},
    )

    logger.info(
        "bounty awarded: id=%s winner=%s reward=%d fee=%d participants=%d admin=%s",
        bounty_id, winner_sub.contributorId, winner_reward, platform_fee,
        len(losers), admin_id,
    )
    return {
        "winner_id": winner_sub.contributorId,
        "winner_fact_id": winner_sub.factId,
        "reward_paid": winner_reward,
        "participants_rewards": participants_rewards,
        "platform_fee": platform_fee,
    }


# ─────────────────────────────────────────────
# 만료 처리
# ─────────────────────────────────────────────
async def expire_bounty(bounty_id: str) -> dict:
    """마감 시점이 지난 bounty 정리.

    - 제출 없음:     생성자에게 전액 환불, status=expired
    - 제출 있음:     자동 award 시도 (score_submissions + 1등 지급)
    반환: {"action", "refunded"?, "winner_id"?, ...}
    """
    bounty = await prisma.bounty.find_unique(where={"id": bounty_id})
    if bounty is None:
        raise ValueError(f"bounty not found: {bounty_id}")
    if bounty.status != "open":
        return {"action": "noop", "status": bounty.status}

    deadline = _as_aware(bounty.deadline)
    if deadline is not None and deadline > _utcnow():
        return {"action": "noop", "reason": "not yet deadline"}

    subs = await prisma.bountysubmission.find_many(where={"bountyId": bounty_id})
    if not subs:
        # 환불
        try:
            await withdraw_stake_balance(
                bounty.creatorId,
                int(bounty.rewardAmount or 0),
                reason=f"bounty_refund:{bounty_id}",
                beneficiary_id=bounty.creatorId,
            )
        except TypeError:
            await withdraw_stake_balance(
                bounty.creatorId,
                int(bounty.rewardAmount or 0),
                reason=f"bounty_refund:{bounty_id}",
            )
        await prisma.bounty.update(
            where={"id": bounty_id},
            data={"status": "expired"},
        )
        logger.info("bounty expired (refunded): id=%s amount=%d",
                    bounty_id, int(bounty.rewardAmount or 0))
        return {
            "action": "refunded",
            "refunded": int(bounty.rewardAmount or 0),
        }

    # 제출 있음 → 자동 award
    try:
        result = await award_bounty(bounty_id)
        return {"action": "auto_awarded", **result}
    except Exception as exc:
        logger.warning("auto award 실패 → 환불 처리: %s", exc)
        try:
            await withdraw_stake_balance(
                bounty.creatorId,
                int(bounty.rewardAmount or 0),
                reason=f"bounty_refund_fallback:{bounty_id}",
            )
        except Exception:
            pass
        await prisma.bounty.update(
            where={"id": bounty_id},
            data={"status": "expired"},
        )
        return {"action": "refunded_fallback", "refunded": int(bounty.rewardAmount or 0)}


# ─────────────────────────────────────────────
# 조회
# ─────────────────────────────────────────────
async def list_open_bounties(
    domain: str | None = None,
    min_reward: int | None = None,
    sort_by: str = "reward",
) -> list[dict]:
    """열린 bounty 목록 조회.

    sort_by ∈ {"reward", "deadline", "recent"}
    """
    where: dict[str, Any] = {"status": "open"}
    if domain:
        where["domain"] = domain.lower()
    if min_reward is not None:
        where["rewardAmount"] = {"gte": int(min_reward)}

    order_map = {
        "reward": {"rewardAmount": "desc"},
        "deadline": {"deadline": "asc"},
        "recent": {"createdAt": "desc"},
    }
    order = order_map.get(sort_by, order_map["reward"])

    rows = await prisma.bounty.find_many(where=where, order=order, take=100)
    return [_bounty_to_dict(r) for r in rows]


async def list_my_bounties(creator_id: str) -> list[dict]:
    """내가 생성한 bounty 목록 (최신순)."""
    rows = await prisma.bounty.find_many(
        where={"creatorId": creator_id},
        order={"createdAt": "desc"},
        take=200,
    )
    return [_bounty_to_dict(r) for r in rows]


async def list_my_submissions(contributor_id: str) -> list[dict]:
    """내가 제출한 답변 목록 (최신순)."""
    rows = await prisma.bountysubmission.find_many(
        where={"contributorId": contributor_id},
        order={"createdAt": "desc"},
        take=200,
    )
    return [
        {
            "submission_id": r.id,
            "bounty_id": r.bountyId,
            "fact_id": r.factId,
            "score": float(r.score or 0.0),
            "selected": bool(r.selected),
            "submission_note": r.submissionNote,
        }
        for r in rows
    ]


# ─────────────────────────────────────────────
# 취소
# ─────────────────────────────────────────────
async def cancel_bounty(bounty_id: str, creator_id: str) -> dict:
    """창설자가 bounty 를 취소(환불) 한다.

    - 제출자가 1명이라도 있으면 취소 불가.
    - status=open 이어야 함.
    """
    bounty = await prisma.bounty.find_unique(where={"id": bounty_id})
    if bounty is None:
        raise ValueError(f"bounty not found: {bounty_id}")
    if bounty.creatorId != creator_id:
        raise ValueError("본인이 생성한 bounty 만 취소할 수 있습니다.")
    if bounty.status != "open":
        raise ValueError(f"bounty 상태가 open 이 아닙니다: {bounty.status}")

    sub_count = await prisma.bountysubmission.count(where={"bountyId": bounty_id})
    if sub_count > 0:
        raise ValueError(f"이미 {sub_count} 건 제출된 bounty 는 취소할 수 없습니다.")

    refund = int(bounty.rewardAmount or 0)
    try:
        await withdraw_stake_balance(
            creator_id,
            refund,
            reason=f"bounty_cancel:{bounty_id}",
        )
    except Exception as exc:
        logger.warning("bounty cancel 환불 실패: %s", exc)
        raise

    await prisma.bounty.update(
        where={"id": bounty_id},
        data={"status": "cancelled"},
    )
    logger.info("bounty cancelled: id=%s refund=%d", bounty_id, refund)
    return {"action": "cancelled", "refunded": refund}


# ─────────────────────────────────────────────
# 통계 / 제안 / 자동 만료
# ─────────────────────────────────────────────
async def bounty_stats(last_days: int = 30) -> dict:
    """최근 N 일 bounty 통계."""
    since = _utcnow() - timedelta(days=int(last_days))
    rows = await prisma.bounty.find_many(
        where={"createdAt": {"gte": since}},
        take=5000,
    )
    total = len(rows)
    awarded = sum(1 for r in rows if r.status == "awarded")
    expired = sum(1 for r in rows if r.status == "expired")
    active = sum(1 for r in rows if r.status == "open")
    cancelled = sum(1 for r in rows if r.status == "cancelled")
    total_reward_paid = sum(
        int(r.rewardAmount or 0) for r in rows if r.status == "awarded"
    )
    return {
        "total_bounties": total,
        "awarded": awarded,
        "expired": expired,
        "active": active,
        "cancelled": cancelled,
        "total_reward_paid": total_reward_paid,
    }


async def suggest_bounty_from_gap(
    gap_id: str, reward_amount: int, creator_id: str
) -> str:
    """KnowledgeGap 을 Bounty 로 자동 전환한다.

    gap.topic / failureCount 기반으로 deadline/domain 결정.
    """
    gap = await prisma.knowledgegap.find_unique(where={"id": gap_id})
    if gap is None:
        raise ValueError(f"gap not found: {gap_id}")

    desc = (
        f"[자동 전환] KnowledgeGap 기반 요청 — 최근 실패 {gap.failureCount or 0}회. "
        f"주제: {gap.topic}"
    )
    bounty_id = await create_bounty(
        creator_id=creator_id,
        topic=gap.topic,
        description=desc,
        reward_amount=int(reward_amount),
        deadline_days=21,
        domain=getattr(gap, "domain", None) or "general",
        required_tier="SILVER",
    )
    try:
        await prisma.knowledgegap.update(
            where={"id": gap_id},
            data={"bountyId": bounty_id, "status": "bounty"},
        )
    except Exception as exc:
        logger.debug("gap 상태 업데이트 스킵: %s", exc)
    return bounty_id


async def top_earners(last_days: int = 30, limit: int = 20) -> list[dict]:
    """Bounty 수상으로 많이 번 기여자 집계."""
    since = _utcnow() - timedelta(days=int(last_days))
    rows = await prisma.bounty.find_many(
        where={
            "status": "awarded",
            "awardedAt": {"gte": since},
        },
        take=5000,
    )
    tally: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not r.winnerId:
            continue
        bucket = tally.setdefault(
            r.winnerId, {"user_id": r.winnerId, "earned": 0, "wins": 0}
        )
        # 승자가 가져간 몫 근사치 (platform fee + 참가자 몫 제외)
        reward = int(r.rewardAmount or 0)
        approx_winner = reward - int(round(reward * PLATFORM_FEE_RATIO))
        bucket["earned"] += approx_winner
        bucket["wins"] += 1

    out = list(tally.values())
    out.sort(key=lambda x: x["earned"], reverse=True)
    return out[: int(limit)]


async def auto_expire_overdue(batch: int = 100) -> int:
    """deadline 지났는데 아직 open 인 bounty 를 일괄 처리."""
    now = _utcnow()
    rows = await prisma.bounty.find_many(
        where={"status": "open", "deadline": {"lt": now}},
        take=int(batch),
    )
    processed = 0
    for r in rows:
        try:
            await expire_bounty(r.id)
            processed += 1
        except Exception as exc:
            logger.warning("auto_expire 실패 id=%s: %s", r.id, exc)
    logger.info("auto_expire_overdue: processed=%d", processed)
    return processed


# ─────────────────────────────────────────────
# 내부: row → dict 변환
# ─────────────────────────────────────────────
def _bounty_to_dict(r) -> dict:
    return {
        "id": r.id,
        "creator_id": r.creatorId,
        "topic": r.topic,
        "description": getattr(r, "description", "") or "",
        "domain": r.domain or "general",
        "reward_amount": int(r.rewardAmount or 0),
        "required_tier": r.requiredTier,
        "deadline": r.deadline.isoformat() if r.deadline else None,
        "status": r.status,
        "winner_id": r.winnerId,
        "winner_fact_id": r.winnerFactId,
        "awarded_at": r.awardedAt.isoformat() if getattr(r, "awardedAt", None) else None,
    }


__all__ = [
    "MIN_BOUNTY_AMOUNT",
    "MAX_BOUNTY_DURATION_DAYS",
    "PLATFORM_FEE_RATIO",
    "create_bounty",
    "submit_to_bounty",
    "score_submissions",
    "award_bounty",
    "expire_bounty",
    "list_open_bounties",
    "list_my_bounties",
    "list_my_submissions",
    "cancel_bounty",
    "bounty_stats",
    "suggest_bounty_from_gap",
    "top_earners",
    "auto_expire_overdue",
]
