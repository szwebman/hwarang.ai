"""HLKM — 동료 검토 (Peer Review) 시스템.

기여자 본인 외 3명 이상의 peer 가 Fact 에 대해 accept/reject/abstain
투표를 하고, 스테이킹을 건다. 다수결로 최종 결정되면:
  - 다수 측은 stake 반환 + 소액 보상 + 평판 상승
  - 소수 측은 stake 슬래시 + 평판 하락
  - abstain 은 원금만 반환

이해관계 충돌 방지:
  - 기여자 본인은 자신의 Fact 검토 불가
  - 동일 IP 클러스터 (Sybil 그룹) 은 동시 배정 제외

의존:
  - `hwarang_api.db.prisma`
  - `.types.KnowledgeFact`
  - `.staking.place_stake, settle_correct, settle_slashed, required_stake`
  - `.contributor_tier.can_peer_review, update_reputation`
"""

from __future__ import annotations

import logging
import random
from collections import Counter
from datetime import datetime, timedelta, timezone

from hwarang_api.db import prisma

from . import contributor_tier
from .contribution_gate import WriteAction, require_contribution_permission
from .notifier import notify_admin
from .staking import (  # type: ignore  # Group 1
    place_stake,
    required_stake,
    settle_correct,
    settle_slashed,
)
from .types import KnowledgeFact  # noqa: F401 (spec 요구)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
MIN_REVIEWS_DEFAULT: int = 3
APPROVAL_THRESHOLD_DEFAULT: float = 2 / 3
REVIEW_WINDOW_HOURS: int = 72
REVIEW_STAKE_AMOUNT: int = 10

_VOTE_ACCEPT = "accept"
_VOTE_REJECT = "reject"
_VOTE_ABSTAIN = "abstain"
_VALID_VOTES = {_VOTE_ACCEPT, _VOTE_REJECT, _VOTE_ABSTAIN}

_DECISION_ACCEPTED = "accepted"
_DECISION_REJECTED = "rejected"
_DECISION_INSUFFICIENT = "insufficient"

REVIEW_REWARD_BONUS = 3      # 다수 측 리뷰어 보너스 코인
REPUTATION_AGREE = 0.03      # 다수와 일치 시 평판 관측 상승
REPUTATION_DISAGREE = -0.05  # 다수와 불일치 시 평판 관측 하락


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────
def _row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "fact_id": row.factId,
        "reviewer_id": row.reviewerId,
        "vote": row.vote,
        "staked_amount": int(row.stakedAmount or 0),
        "rationale": row.rationale,
        "confidence": float(row.confidence or 0.0),
        "finalized_at": row.finalizedAt,
        "rewarded_amount": int(row.rewardedAmount or 0),
        "slashed_amount": int(row.slashedAmount or 0),
    }


def _agreement_ratio(reviews: list) -> float:
    """accept / (accept+reject) 비율을 계산한다. abstain 은 분모 제외."""
    accept = sum(1 for r in reviews if r.vote == _VOTE_ACCEPT)
    reject = sum(1 for r in reviews if r.vote == _VOTE_REJECT)
    total = accept + reject
    if total == 0:
        return 0.0
    return accept / total


# ─────────────────────────────────────────────
# 리뷰 제출
# ─────────────────────────────────────────────
async def submit_review(
    fact_id: str,
    reviewer_id: str,
    vote: str,
    rationale: str | None = None,
    confidence: float = 0.7,
    stake: int | None = None,
    bypass_gate: bool = False,
) -> str:
    """동료 검토 투표를 제출한다.

    - 권한 체크: contributor_tier.can_peer_review
    - 자기 Fact 검토 불가
    - (factId, reviewerId) 유일성 충돌 시 업데이트
    - 스테이킹 차감

    Return: review_id
    """
    # KYC 게이트 — 미인증자는 쓰기 불가
    if not bypass_gate:
        await require_contribution_permission(
            reviewer_id, WriteAction.PEER_REVIEW.value
        )

    if vote not in _VALID_VOTES:
        raise ValueError(f"invalid vote: {vote}")

    if not await contributor_tier.can_peer_review(reviewer_id):
        raise PermissionError(f"user {reviewer_id} lacks peer_review permission")

    fact = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if fact is None:
        raise ValueError(f"fact not found: {fact_id}")
    if fact.contributedBy == reviewer_id:
        raise PermissionError("self-review is not allowed")

    stake_amount = int(stake if stake is not None else REVIEW_STAKE_AMOUNT)
    # abstain 은 소액/무 스테이킹 허용
    if vote == _VOTE_ABSTAIN:
        stake_amount = max(0, stake_amount // 2)

    # 최소 요구 스테이킹 검사
    try:
        min_required = int(required_stake(fact.domain))
        if stake_amount < min_required and vote != _VOTE_ABSTAIN:
            raise ValueError(
                f"stake {stake_amount} < required {min_required} for domain {fact.domain}"
            )
    except Exception as e:  # pragma: no cover
        logger.debug("required_stake lookup failed: %s", e)

    # 스테이킹 차감
    if stake_amount > 0:
        await place_stake(reviewer_id, stake_amount, reason=f"peer_review:{fact_id}")

    existing = await prisma.peerreview.find_unique(
        where={"factId_reviewerId": {"factId": fact_id, "reviewerId": reviewer_id}}
    )
    if existing is not None:
        updated = await prisma.peerreview.update(
            where={"id": existing.id},
            data={
                "vote": vote,
                "stakedAmount": stake_amount,
                "rationale": rationale,
                "confidence": float(confidence),
            },
        )
        logger.info("peer review updated: %s user=%s vote=%s", fact_id, reviewer_id, vote)
        return updated.id

    created = await prisma.peerreview.create(
        data={
            "factId": fact_id,
            "reviewerId": reviewer_id,
            "vote": vote,
            "stakedAmount": stake_amount,
            "rationale": rationale,
            "confidence": float(confidence),
        }
    )
    logger.info("peer review submitted: %s user=%s vote=%s", fact_id, reviewer_id, vote)
    return created.id


# ─────────────────────────────────────────────
# 리뷰 집계 / 확정
# ─────────────────────────────────────────────
async def finalize_reviews(
    fact_id: str,
    min_reviews: int = MIN_REVIEWS_DEFAULT,
    approval_threshold: float = APPROVAL_THRESHOLD_DEFAULT,
) -> dict:
    """Fact 에 달린 모든 리뷰를 집계하여 최종 결정을 내린다.

    - 최소 수 미달 → insufficient
    - accept/(accept+reject) ≥ threshold → accepted
    - 아니면 rejected

    결과에 따라 각 리뷰어의 보상/슬래시/평판을 반영한다.
    """
    reviews = await prisma.peerreview.find_many(where={"factId": fact_id}, take=1000)
    counter = Counter(r.vote for r in reviews)
    accept_count = counter.get(_VOTE_ACCEPT, 0)
    reject_count = counter.get(_VOTE_REJECT, 0)
    abstain_count = counter.get(_VOTE_ABSTAIN, 0)

    non_abstain = accept_count + reject_count
    if non_abstain < min_reviews:
        return {
            "decision": _DECISION_INSUFFICIENT,
            "accept_count": accept_count,
            "reject_count": reject_count,
            "abstain_count": abstain_count,
        }

    ratio = accept_count / non_abstain if non_abstain > 0 else 0.0
    decision = _DECISION_ACCEPTED if ratio >= approval_threshold else _DECISION_REJECTED

    await _settle_review_stakes(fact_id, decision)

    logger.info(
        "finalize_reviews: fact=%s decision=%s A=%d R=%d Ab=%d",
        fact_id, decision, accept_count, reject_count, abstain_count,
    )

    # 관리자 알림 (Slack + email) — accepted/rejected 모두 통보
    severity = "info" if decision == _DECISION_ACCEPTED else "warn"
    try:
        await notify_admin(
            (
                f"Peer review for fact `{fact_id}`: *{decision}* "
                f"(accept={accept_count} reject={reject_count} abstain={abstain_count})"
            ),
            severity=severity,
            subject=f"[HLKM peer-review] {decision}: {fact_id}",
        )
    except Exception as e:  # 알림 실패가 본 로직을 막으면 안 됨
        logger.warning("finalize_reviews: notify_admin failed: %s", e)

    return {
        "decision": decision,
        "accept_count": accept_count,
        "reject_count": reject_count,
        "abstain_count": abstain_count,
    }


async def _settle_review_stakes(fact_id: str, decision: str) -> None:
    """리뷰어들의 스테이킹 결제.

    - 다수 측 (decision 과 일치하는 vote): stake 반환 + REVIEW_REWARD_BONUS 보상
    - 소수 측: stake 슬래시
    - abstain: stake 반환 (보상 없음)
    """
    reviews = await prisma.peerreview.find_many(where={"factId": fact_id}, take=1000)
    majority_vote = _VOTE_ACCEPT if decision == _DECISION_ACCEPTED else _VOTE_REJECT
    now = datetime.now(timezone.utc)

    for r in reviews:
        if r.finalizedAt is not None:
            continue
        stake = int(r.stakedAmount or 0)
        rewarded = 0
        slashed = 0

        if r.vote == _VOTE_ABSTAIN:
            if stake > 0:
                await settle_correct(r.reviewerId, stake, reason=f"review_abstain:{fact_id}")
        elif r.vote == majority_vote:
            rewarded = stake + REVIEW_REWARD_BONUS
            if stake > 0:
                await settle_correct(r.reviewerId, stake, reason=f"review_correct:{fact_id}")
            # 보너스 보상
            await settle_correct(
                r.reviewerId, REVIEW_REWARD_BONUS,
                reason=f"review_bonus:{fact_id}",
            )
            await contributor_tier.update_reputation(
                r.reviewerId, REPUTATION_AGREE, reason=f"review_agree:{fact_id}"
            )
        else:
            slashed = stake
            if stake > 0:
                await settle_slashed(r.reviewerId, stake, reason=f"review_wrong:{fact_id}")
            await contributor_tier.update_reputation(
                r.reviewerId, REPUTATION_DISAGREE, reason=f"review_disagree:{fact_id}"
            )

        await prisma.peerreview.update(
            where={"id": r.id},
            data={
                "finalizedAt": now,
                "rewardedAmount": int(rewarded),
                "slashedAmount": int(slashed),
            },
        )


# ─────────────────────────────────────────────
# 조회
# ─────────────────────────────────────────────
async def list_pending_reviews_for_user(
    user_id: str, limit: int = 20
) -> list[dict]:
    """이 사용자가 아직 리뷰하지 않은 대기 Fact 목록.

    - tier 의 도메인 권한과 매칭되는 Fact 만
    - 기여자 본인이 아닌 Fact 만
    - 아직 finalize 되지 않은 리뷰 세션 대상
    """
    profile = await contributor_tier.get_or_create_profile(user_id)
    perms = contributor_tier.TIER_PERMISSIONS.get(profile["tier"], {})
    allowed_domains = perms.get("domains", [])

    # 후보 Fact 조회 (최근 7일 PENDING)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    where: dict = {
        "status": "PENDING",
        "createdAt": {"gte": cutoff},
        "contributedBy": {"not": user_id},
    }
    if allowed_domains != "*" and isinstance(allowed_domains, list):
        if not allowed_domains:
            return []
        where["domain"] = {"in": allowed_domains}

    facts = await prisma.knowledgefact.find_many(
        where=where,
        take=limit * 3,
        order={"createdAt": "desc"},
    )

    # 이미 본인이 리뷰한 fact 제외
    my_reviews = await prisma.peerreview.find_many(
        where={"reviewerId": user_id, "factId": {"in": [f.id for f in facts]}},
        take=limit * 3,
    )
    reviewed_ids = {r.factId for r in my_reviews}

    out: list[dict] = []
    for f in facts:
        if f.id in reviewed_ids:
            continue
        out.append({
            "fact_id": f.id,
            "content": f.content[:200],
            "domain": f.domain,
            "contributed_by": f.contributedBy,
            "created_at": f.createdAt,
        })
        if len(out) >= limit:
            break
    return out


async def list_reviews_of_fact(fact_id: str) -> list[dict]:
    """특정 Fact 의 모든 리뷰 조회."""
    rows = await prisma.peerreview.find_many(
        where={"factId": fact_id}, take=500,
    )
    return [_row_to_dict(r) for r in rows]


async def review_stats_for_user(user_id: str, days: int = 30) -> dict:
    """해당 사용자의 최근 N 일 리뷰 성과."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await prisma.peerreview.find_many(
        where={"reviewerId": user_id, "finalizedAt": {"gte": cutoff}},
        take=5000,
    )
    total = len(rows)
    rewards = sum(int(r.rewardedAmount or 0) for r in rows)
    slashes = sum(int(r.slashedAmount or 0) for r in rows)
    agree_count = sum(
        1 for r in rows
        if int(r.rewardedAmount or 0) > 0 and r.vote != _VOTE_ABSTAIN
    )
    non_abstain = sum(1 for r in rows if r.vote != _VOTE_ABSTAIN)
    agreement_rate = (agree_count / non_abstain) if non_abstain > 0 else 0.0

    return {
        "total_reviews": total,
        "agreement_rate": agreement_rate,
        "rewards_earned": rewards,
        "slashes": slashes,
    }


# ─────────────────────────────────────────────
# 리뷰어 자동 배정
# ─────────────────────────────────────────────
async def auto_assign_reviewers(fact_id: str, count: int = 3) -> list[str]:
    """해당 도메인의 활성 기여자 중 리뷰어를 자동 배정한다.

    - tier Silver 이상
    - 기여자 본인 제외
    - 이미 리뷰한 사람 제외
    - Sybil 그룹 (동일 IP 클러스터) 은 중복 배정 제외
    """
    fact = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if fact is None:
        return []

    candidates = await prisma.contributorprofile.find_many(
        where={"tier": {"in": ["SILVER", "GOLD", "DIAMOND"]}},
        take=500,
    )

    # 이미 리뷰한 사람 제외
    existing = await prisma.peerreview.find_many(
        where={"factId": fact_id}, take=500,
    )
    existing_ids = {r.reviewerId for r in existing}

    eligible: list = []
    for c in candidates:
        if c.userId == fact.contributedBy:
            continue
        if c.userId in existing_ids:
            continue
        if await reviewer_blacklist_check(c.userId):
            continue
        # 도메인 권한 체크
        if not await contributor_tier.can_contribute_to_domain(c.userId, fact.domain):
            continue
        eligible.append(c.userId)

    # Sybil 방지: 동일 IP 클러스터 중복 제거 (placeholder; 실제로는 세션/IP 테이블 join)
    eligible = await _dedupe_by_ip_cluster(eligible)

    if len(eligible) <= count:
        selected = eligible
    else:
        selected = random.sample(eligible, count)

    logger.info(
        "auto_assign_reviewers: fact=%s selected=%d / eligible=%d",
        fact_id, len(selected), len(eligible),
    )
    return selected


async def _dedupe_by_ip_cluster(user_ids: list[str]) -> list[str]:
    """동일 IP 클러스터 사용자 중 대표 1명만 남긴다 (Sybil 방지).

    실제 운영에서는 세션/접속로그 테이블 join 필요.
    placeholder: 입력을 그대로 반환하되 집합 중복만 제거.
    """
    seen: set[str] = set()
    out: list[str] = []
    for uid in user_ids:
        if uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
    return out


async def notify_reviewers(fact_id: str, reviewer_ids: list[str]) -> int:
    """배정된 리뷰어에게 알림을 전송한다.

    채널:
      - logger.info (감사용)
      - Slack 채널 (HWARANG_SLACK_WEBHOOK_URL 설정 시) — 단체 통지
      - 향후 in-app 알림은 별도 모듈에서 enqueue
    """
    for uid in reviewer_ids:
        logger.info("notify_reviewer: fact=%s reviewer=%s", fact_id, uid)
    if reviewer_ids:
        try:
            await notify_admin(
                f"New peer review assignment: fact=`{fact_id}` reviewers={len(reviewer_ids)}",
                severity="info",
                subject=f"[HLKM review-assigned] {fact_id}",
            )
        except Exception as e:
            logger.warning("notify_reviewers: notify_admin failed: %s", e)
    return len(reviewer_ids)


# ─────────────────────────────────────────────
# 기한 초과 / 블랙리스트
# ─────────────────────────────────────────────
async def close_stale_reviews(older_than_hours: int = REVIEW_WINDOW_HOURS) -> int:
    """기한이 초과된 Fact 들의 리뷰 세션을 자동 finalize 한다.

    - PeerReview 가 달렸지만 finalizedAt=null 인 Fact 에 대해
    - 생성된 지 older_than_hours 시간이 지났다면 finalize 호출

    Return: finalize 처리된 Fact 수.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
    pending = await prisma.peerreview.find_many(
        where={"finalizedAt": None},
        take=1000,
    )
    fact_ids = {r.factId for r in pending}

    finalized = 0
    for fid in fact_ids:
        fact = await prisma.knowledgefact.find_unique(where={"id": fid})
        if fact is None or fact.createdAt is None:
            continue
        if fact.createdAt > cutoff:
            continue
        await finalize_reviews(fid)
        finalized += 1
    logger.info("close_stale_reviews: finalized %d facts", finalized)
    return finalized


async def reviewer_blacklist_check(reviewer_id: str) -> bool:
    """허위 검토/공모 의심자를 차단한다.

    판정 기준 (placeholder):
      - tier == SUSPENDED
      - 최근 슬래시 비율이 60% 이상
    """
    profile = await contributor_tier.get_or_create_profile(reviewer_id)
    if profile["tier"] == "SUSPENDED":
        return True

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    recent = await prisma.peerreview.find_many(
        where={"reviewerId": reviewer_id, "finalizedAt": {"gte": cutoff}},
        take=500,
    )
    if not recent:
        return False
    slashed = sum(1 for r in recent if int(r.slashedAmount or 0) > 0)
    if slashed / len(recent) >= 0.6:
        logger.warning("reviewer blacklisted (high slash ratio): %s", reviewer_id)
        return True
    return False


# ─────────────────────────────────────────────
# 대시보드 / 히트맵
# ─────────────────────────────────────────────
async def review_heatmap(last_days: int = 7) -> dict:
    """일별 리뷰 활동 집계 (관리자 대시보드용).

    Return: {"YYYY-MM-DD": {"accept": n, "reject": n, "abstain": n, "total": n}}
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=last_days)
    rows = await prisma.peerreview.find_many(
        where={"finalizedAt": {"gte": cutoff}},
        take=20000,
    )
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        if r.finalizedAt is None:
            continue
        key = r.finalizedAt.strftime("%Y-%m-%d")
        bucket = out.setdefault(
            key, {"accept": 0, "reject": 0, "abstain": 0, "total": 0}
        )
        if r.vote in bucket:
            bucket[r.vote] += 1
        bucket["total"] += 1
    return out


__all__ = [
    "MIN_REVIEWS_DEFAULT",
    "APPROVAL_THRESHOLD_DEFAULT",
    "REVIEW_WINDOW_HOURS",
    "REVIEW_STAKE_AMOUNT",
    "submit_review",
    "finalize_reviews",
    "list_pending_reviews_for_user",
    "list_reviews_of_fact",
    "review_stats_for_user",
    "auto_assign_reviewers",
    "notify_reviewers",
    "close_stale_reviews",
    "reviewer_blacklist_check",
    "review_heatmap",
]
