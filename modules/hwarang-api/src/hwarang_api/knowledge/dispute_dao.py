"""분쟁 DAO (Dispute DAO).

HLKM 지식 그래프에서 모순이 발생하거나 복수의 사실이 충돌할 때,
고신뢰 기여자(Diamond 등급)들이 스테이킹 기반 투표로 해결하는
탈중앙 판결 메커니즘.

경제적 공격 방지를 위한 보호 장치:
    - 분쟁 제기 비용 (MIN_STAKE_TO_INITIATE) → 악의적 남발 방지
    - 투표 stake 상한 (고래 독점 방지)
    - 최소 투표수 요구 (소수에 의한 조작 방지)
    - 패배 측 일부 슬래시 (무책임 투표 억제)
    - 공모 탐지 (detect_vote_collusion)

테이블:
    Dispute (id, relatedFactIds[], topic, description, initiatorId, status,
             votingEndsAt, winningSide, totalStaked, resolvedAt, resolutionNote)
    DisputeVote (id, disputeId, voterId, side, stakedAmount, rationale,
                 settledAmount) — unique (disputeId, voterId)
"""

from __future__ import annotations

import logging
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma

from .contribution_gate import WriteAction, require_contribution_permission
from .contributor_tier import can_vote_dispute, update_reputation
from .staking import place_stake, settle_correct, settle_slashed
from .types import KnowledgeFact

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

DEFAULT_VOTING_PERIOD_HOURS: int = 96  # 4일
MIN_VOTES_REQUIRED: int = 5
MIN_TIER_TO_VOTE: str = "DIAMOND"  # GOLD 로 완화 가능
MIN_STAKE_TO_INITIATE: int = 100

MIN_VOTE_STAKE: int = 10
MAX_VOTE_STAKE_ABS: int = 1000
MAX_VOTE_STAKE_RATIO: float = 0.2  # 보유 stake의 20%가 한도

VALID_SIDES: set[str] = {"A", "B", "both_invalid", "coexist"}

LOSER_SLASH_RATIO: float = 0.5  # 패배자 stake의 50% 슬래시
INITIATOR_SLASH_ON_INVALID: float = 0.3  # 최소 투표수 미달 시 제기자 30% 슬래시
REPUTATION_DELTA_WINNER: float = 0.02
REPUTATION_DELTA_LOSER: float = -0.03

COLLUSION_TIME_WINDOW_MIN: int = 10
COLLUSION_STAKE_DIFF_RATIO: float = 0.05


# ---------------------------------------------------------------------------
# 내부 유틸
# ---------------------------------------------------------------------------


def _now() -> datetime:
    """UTC 현재시각."""
    return datetime.now(timezone.utc)


def _clamp_vote_stake(stake: int, voter_balance: int) -> int:
    """투표 stake 상한/하한 적용.

    고래 독점을 막기 위해 보유 stake의 ``MAX_VOTE_STAKE_RATIO`` 와
    절대 상한 ``MAX_VOTE_STAKE_ABS`` 중 작은 값을 최댓값으로 사용.
    """
    hard_cap = min(MAX_VOTE_STAKE_ABS, int(voter_balance * MAX_VOTE_STAKE_RATIO))
    hard_cap = max(hard_cap, MIN_VOTE_STAKE)
    return max(MIN_VOTE_STAKE, min(stake, hard_cap))


def _winning_side_from_stakes(stakes_by_side: dict[str, int]) -> str | None:
    """stake 합계가 가장 큰 side 반환. 동점이면 None."""
    if not stakes_by_side:
        return None
    ordered = sorted(stakes_by_side.items(), key=lambda kv: kv[1], reverse=True)
    if len(ordered) >= 2 and ordered[0][1] == ordered[1][1]:
        return None
    return ordered[0][0]


# ---------------------------------------------------------------------------
# 1. 분쟁 제기
# ---------------------------------------------------------------------------


async def initiate_dispute(
    initiator_id: str,
    related_fact_ids: list[str],
    topic: str,
    description: str,
    voting_period_hours: int = DEFAULT_VOTING_PERIOD_HOURS,
    bypass_gate: bool = False,
) -> str:
    """분쟁을 제기한다.

    Args:
        initiator_id: 제기자 사용자 ID.
        related_fact_ids: 충돌하는 사실 ID 리스트 (최소 1개).
        topic: 분쟁 주제 (한 줄 요약).
        description: 상세 설명 (근거/맥락 포함).
        voting_period_hours: 투표 기간 (시간).

    Returns:
        생성된 ``dispute_id``.

    Raises:
        ValueError: 관련 사실이 비어있거나 제기자 스테이킹 실패.
    """
    # KYC 게이트
    if not bypass_gate:
        await require_contribution_permission(
            initiator_id, WriteAction.DISPUTE_INITIATE.value
        )

    if not related_fact_ids:
        raise ValueError("related_fact_ids 는 최소 1개 이상이어야 합니다")
    if voting_period_hours <= 0:
        raise ValueError("voting_period_hours 는 양수여야 합니다")

    # 제기자 stake (악의적 분쟁 남발 방지)
    stake_id = await place_stake(
        user_id=initiator_id,
        amount=MIN_STAKE_TO_INITIATE,
        context="dispute_initiation",
        metadata={"topic": topic[:120]},
    )
    if not stake_id:
        raise ValueError("제기자 스테이킹에 실패했습니다 (잔액 부족 가능)")

    voting_ends_at = _now() + timedelta(hours=voting_period_hours)

    dispute = await prisma.dispute.create(
        data={
            "relatedFactIds": related_fact_ids,
            "topic": topic,
            "description": description,
            "initiatorId": initiator_id,
            "status": "open",
            "votingEndsAt": voting_ends_at,
            "totalStaked": MIN_STAKE_TO_INITIATE,
        }
    )

    # 관련 사실들을 DISPUTED 로 표시
    await prisma.knowledgefact.update_many(
        where={"id": {"in": related_fact_ids}},
        data={"status": "DISPUTED"},
    )

    # 투표권자 알림 (placeholder — 실제 구현은 notify 모듈)
    logger.info(
        "분쟁 제기 완료: dispute_id=%s initiator=%s facts=%s",
        dispute.id,
        initiator_id,
        related_fact_ids,
    )
    return dispute.id


# ---------------------------------------------------------------------------
# 2. 투표
# ---------------------------------------------------------------------------


async def vote(
    dispute_id: str,
    voter_id: str,
    side: str,
    staked_amount: int,
    rationale: str | None = None,
    bypass_gate: bool = False,
) -> str:
    """분쟁에 투표한다.

    Args:
        dispute_id: 대상 분쟁.
        voter_id: 투표자 ID.
        side: ``"A"``, ``"B"``, ``"both_invalid"``, ``"coexist"`` 중 하나.
        staked_amount: 거는 stake 양 (자동으로 min/max 로 clamp).
        rationale: 투표 근거 (선택).

    Returns:
        생성된 ``dispute_vote_id``.

    Raises:
        ValueError: 권한 부족/중복 투표/잘못된 side 값 등.
    """
    # KYC 게이트
    if not bypass_gate:
        await require_contribution_permission(
            voter_id, WriteAction.DISPUTE_VOTE.value
        )

    if side not in VALID_SIDES:
        raise ValueError(f"side 는 {VALID_SIDES} 중 하나여야 합니다")

    # 권한 체크
    allowed = await can_vote_dispute(voter_id, min_tier=MIN_TIER_TO_VOTE)
    if not allowed:
        raise ValueError(f"투표 권한이 없습니다 (최소 {MIN_TIER_TO_VOTE} 등급 필요)")

    dispute = await prisma.dispute.find_unique(where={"id": dispute_id})
    if dispute is None:
        raise ValueError("분쟁을 찾을 수 없습니다")
    if dispute.status != "open":
        raise ValueError(f"이미 종료된 분쟁입니다 (status={dispute.status})")
    if dispute.votingEndsAt and dispute.votingEndsAt < _now():
        raise ValueError("투표 기간이 종료되었습니다")

    # 중복 투표 차단 (unique constraint 백업 가드)
    existing = await prisma.disputevote.find_first(
        where={"disputeId": dispute_id, "voterId": voter_id}
    )
    if existing is not None:
        raise ValueError("이미 투표하셨습니다")

    # 투표자 잔액 조회 후 stake clamp
    profile = await prisma.contributorprofile.find_unique(where={"userId": voter_id})
    voter_balance = int(getattr(profile, "stakedBalance", 0) or 0)
    clamped = _clamp_vote_stake(int(staked_amount), voter_balance)

    # 실제 토큰 stake 등록
    stake_id = await place_stake(
        user_id=voter_id,
        amount=clamped,
        context="dispute_vote",
        metadata={"dispute_id": dispute_id, "side": side},
    )
    if not stake_id:
        raise ValueError("stake 실패 (잔액 부족 가능)")

    dv = await prisma.disputevote.create(
        data={
            "disputeId": dispute_id,
            "voterId": voter_id,
            "side": side,
            "stakedAmount": clamped,
            "rationale": rationale,
        }
    )

    await prisma.dispute.update(
        where={"id": dispute_id},
        data={"totalStaked": (dispute.totalStaked or 0) + clamped},
    )

    logger.info(
        "투표 등록: dispute=%s voter=%s side=%s stake=%s",
        dispute_id,
        voter_id,
        side,
        clamped,
    )
    return dv.id


async def withdraw_vote(dispute_id: str, voter_id: str) -> bool:
    """투표 철회.

    투표 기간 내에만 가능. 철회 시 stake 는 반환되며 DisputeVote 는 삭제.
    """
    dispute = await prisma.dispute.find_unique(where={"id": dispute_id})
    if dispute is None or dispute.status != "open":
        return False
    if dispute.votingEndsAt and dispute.votingEndsAt < _now():
        return False

    dv = await prisma.disputevote.find_first(
        where={"disputeId": dispute_id, "voterId": voter_id}
    )
    if dv is None:
        return False

    # stake 반환 (정답 정산 경로 재사용: 원금만 돌려주는 형태)
    await settle_correct(
        user_id=voter_id,
        amount=int(dv.stakedAmount),
        context="dispute_vote_withdraw",
        metadata={"dispute_id": dispute_id},
    )
    await prisma.disputevote.delete(where={"id": dv.id})
    await prisma.dispute.update(
        where={"id": dispute_id},
        data={
            "totalStaked": max(
                0, int(dispute.totalStaked or 0) - int(dv.stakedAmount)
            )
        },
    )
    return True


# ---------------------------------------------------------------------------
# 3. 확정 (finalize)
# ---------------------------------------------------------------------------


async def finalize_dispute(dispute_id: str, force: bool = False) -> dict[str, Any]:
    """분쟁 확정: 승리 side 계산 → 상벌 집행 → 사실 상태 갱신.

    Args:
        dispute_id: 대상 분쟁.
        force: True 면 투표 기간 종료 전이라도 강제 확정 (관리자용).

    Returns:
        ``{"winning_side", "votes_by_side", "stakes_by_side", "facts_action"}``.
    """
    dispute = await prisma.dispute.find_unique(where={"id": dispute_id})
    if dispute is None:
        raise ValueError("분쟁을 찾을 수 없습니다")
    if dispute.status != "open":
        raise ValueError(f"이미 확정된 분쟁입니다 (status={dispute.status})")

    now = _now()
    if not force and dispute.votingEndsAt and dispute.votingEndsAt > now:
        raise ValueError("투표 기간이 아직 끝나지 않았습니다 (force=True 로 강제 가능)")

    votes = await prisma.disputevote.find_many(where={"disputeId": dispute_id})
    votes_list = list(votes or [])

    votes_by_side: dict[str, int] = Counter()
    stakes_by_side: dict[str, int] = defaultdict(int)
    for v in votes_list:
        votes_by_side[v.side] += 1
        stakes_by_side[v.side] += int(v.stakedAmount)

    # 최소 투표수 미달 → invalid
    if len(votes_list) < MIN_VOTES_REQUIRED:
        await _handle_invalid_dispute(dispute, votes_list)
        return {
            "winning_side": "invalid",
            "votes_by_side": dict(votes_by_side),
            "stakes_by_side": dict(stakes_by_side),
            "facts_action": "status_restored",
            "reason": f"투표수 부족 ({len(votes_list)} < {MIN_VOTES_REQUIRED})",
        }

    winning_side = _winning_side_from_stakes(dict(stakes_by_side))
    if winning_side is None:
        # 동점 → invalid 처리
        await _handle_invalid_dispute(dispute, votes_list)
        return {
            "winning_side": "tie",
            "votes_by_side": dict(votes_by_side),
            "stakes_by_side": dict(stakes_by_side),
            "facts_action": "status_restored",
            "reason": "stake 동점",
        }

    # 승/패 분리 및 정산
    winner_votes = [v for v in votes_list if v.side == winning_side]
    loser_votes = [v for v in votes_list if v.side != winning_side]

    total_loser_stake = sum(int(v.stakedAmount) for v in loser_votes)
    total_winner_stake = sum(int(v.stakedAmount) for v in winner_votes) or 1
    slashed_pool = int(total_loser_stake * LOSER_SLASH_RATIO)

    # 패배자: 절반 슬래시 + 절반 보존
    for lv in loser_votes:
        preserved = int(lv.stakedAmount) - int(int(lv.stakedAmount) * LOSER_SLASH_RATIO)
        slashed = int(lv.stakedAmount) - preserved
        if preserved > 0:
            await settle_correct(
                user_id=lv.voterId,
                amount=preserved,
                context="dispute_loser_preserved",
                metadata={"dispute_id": dispute_id},
            )
        if slashed > 0:
            await settle_slashed(
                user_id=lv.voterId,
                amount=slashed,
                context="dispute_loser_slashed",
                metadata={"dispute_id": dispute_id},
            )
        await prisma.disputevote.update(
            where={"id": lv.id},
            data={"settledAmount": preserved},
        )
        await update_reputation(lv.voterId, REPUTATION_DELTA_LOSER)

    # 승리자: 원금 + 슬래시된 pool 을 stake 비례로 배분
    for wv in winner_votes:
        share = int(slashed_pool * (int(wv.stakedAmount) / total_winner_stake))
        payout = int(wv.stakedAmount) + share
        await settle_correct(
            user_id=wv.voterId,
            amount=payout,
            context="dispute_winner",
            metadata={"dispute_id": dispute_id, "bonus": share},
        )
        await prisma.disputevote.update(
            where={"id": wv.id},
            data={"settledAmount": payout},
        )
        await update_reputation(wv.voterId, REPUTATION_DELTA_WINNER)

    # 제기자 stake 반환 (유효한 분쟁이었으므로)
    await settle_correct(
        user_id=dispute.initiatorId,
        amount=MIN_STAKE_TO_INITIATE,
        context="dispute_initiator_refund",
        metadata={"dispute_id": dispute_id},
    )

    facts_action = await _apply_fact_actions(
        list(dispute.relatedFactIds or []), winning_side
    )

    await prisma.dispute.update(
        where={"id": dispute_id},
        data={
            "status": "resolved",
            "winningSide": winning_side,
            "resolvedAt": now,
            "resolutionNote": f"stake_based: {winning_side}",
        },
    )

    logger.info(
        "분쟁 확정: dispute=%s winning=%s voters=%d",
        dispute_id,
        winning_side,
        len(votes_list),
    )
    return {
        "winning_side": winning_side,
        "votes_by_side": dict(votes_by_side),
        "stakes_by_side": dict(stakes_by_side),
        "facts_action": facts_action,
    }


async def _handle_invalid_dispute(dispute: Any, votes_list: list[Any]) -> None:
    """무효 분쟁 처리: 투표자 stake 는 전액 반환, 제기자 일부 슬래시."""
    for v in votes_list:
        await settle_correct(
            user_id=v.voterId,
            amount=int(v.stakedAmount),
            context="dispute_invalid_refund",
            metadata={"dispute_id": dispute.id},
        )
        await prisma.disputevote.update(
            where={"id": v.id},
            data={"settledAmount": int(v.stakedAmount)},
        )

    # 제기자 30% 슬래시 (남발 억제)
    slash = int(MIN_STAKE_TO_INITIATE * INITIATOR_SLASH_ON_INVALID)
    preserve = MIN_STAKE_TO_INITIATE - slash
    if preserve > 0:
        await settle_correct(
            user_id=dispute.initiatorId,
            amount=preserve,
            context="dispute_initiator_partial_refund",
            metadata={"dispute_id": dispute.id},
        )
    if slash > 0:
        await settle_slashed(
            user_id=dispute.initiatorId,
            amount=slash,
            context="dispute_initiator_slash",
            metadata={"dispute_id": dispute.id},
        )

    # 사실 상태 복원
    await prisma.knowledgefact.update_many(
        where={"id": {"in": list(dispute.relatedFactIds or [])}},
        data={"status": "CONFIRMED"},
    )
    await prisma.dispute.update(
        where={"id": dispute.id},
        data={
            "status": "invalid",
            "winningSide": "invalid",
            "resolvedAt": _now(),
            "resolutionNote": "최소 투표수 미달 또는 동점",
        },
    )


async def _apply_fact_actions(fact_ids: list[str], winning_side: str) -> str:
    """승리 side 에 따라 관련 사실들의 status 업데이트."""
    if not fact_ids:
        return "noop"

    if winning_side == "A":
        # A 측 승리 → 첫 사실 유지, 나머지 RETRACTED
        head = fact_ids[0]
        await prisma.knowledgefact.update(
            where={"id": head}, data={"status": "CONFIRMED"}
        )
        if len(fact_ids) > 1:
            await prisma.knowledgefact.update_many(
                where={"id": {"in": fact_ids[1:]}}, data={"status": "RETRACTED"}
            )
        return "A_wins_others_retracted"

    if winning_side == "B":
        # B 측 승리 → 두 번째 사실 유지, 나머지 RETRACTED
        if len(fact_ids) >= 2:
            keep = fact_ids[1]
            await prisma.knowledgefact.update(
                where={"id": keep}, data={"status": "CONFIRMED"}
            )
            others = [f for f in fact_ids if f != keep]
            await prisma.knowledgefact.update_many(
                where={"id": {"in": others}}, data={"status": "RETRACTED"}
            )
        return "B_wins_others_retracted"

    if winning_side == "both_invalid":
        await prisma.knowledgefact.update_many(
            where={"id": {"in": fact_ids}}, data={"status": "RETRACTED"}
        )
        return "all_retracted"

    if winning_side == "coexist":
        # CONTRADICTS 관계는 유지하되 모두 CONFIRMED 복원
        await prisma.knowledgefact.update_many(
            where={"id": {"in": fact_ids}}, data={"status": "CONFIRMED"}
        )
        return "coexist_confirmed"

    return "noop"


# ---------------------------------------------------------------------------
# 4. 조회
# ---------------------------------------------------------------------------


async def list_open_disputes(
    my_tier_can_vote: bool = False, user_id: str | None = None
) -> list[dict[str, Any]]:
    """열려있는 분쟁 목록.

    Args:
        my_tier_can_vote: True 이고 user_id 가 주어지면, 해당 사용자가
            투표권이 있는 분쟁만 필터링.
    """
    rows = await prisma.dispute.find_many(
        where={"status": "open"},
        order={"votingEndsAt": "asc"},
    )
    out: list[dict[str, Any]] = []
    for d in rows or []:
        if my_tier_can_vote and user_id:
            allowed = await can_vote_dispute(user_id, min_tier=MIN_TIER_TO_VOTE)
            if not allowed:
                continue
        out.append(
            {
                "id": d.id,
                "topic": d.topic,
                "initiator_id": d.initiatorId,
                "related_fact_ids": list(d.relatedFactIds or []),
                "voting_ends_at": d.votingEndsAt,
                "total_staked": int(d.totalStaked or 0),
            }
        )
    return out


async def get_dispute(dispute_id: str) -> dict[str, Any]:
    """분쟁 상세 (투표 내역 포함)."""
    d = await prisma.dispute.find_unique(where={"id": dispute_id})
    if d is None:
        raise ValueError("분쟁을 찾을 수 없습니다")
    votes = await prisma.disputevote.find_many(
        where={"disputeId": dispute_id},
        order={"stakedAmount": "desc"},
    )
    return {
        "id": d.id,
        "topic": d.topic,
        "description": d.description,
        "initiator_id": d.initiatorId,
        "status": d.status,
        "winning_side": d.winningSide,
        "voting_ends_at": d.votingEndsAt,
        "resolved_at": d.resolvedAt,
        "resolution_note": d.resolutionNote,
        "related_fact_ids": list(d.relatedFactIds or []),
        "total_staked": int(d.totalStaked or 0),
        "votes": [
            {
                "voter_id": v.voterId,
                "side": v.side,
                "staked_amount": int(v.stakedAmount),
                "rationale": v.rationale,
                "settled_amount": int(v.settledAmount or 0),
            }
            for v in (votes or [])
        ],
    }


async def list_my_votes(voter_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """내 투표 이력."""
    rows = await prisma.disputevote.find_many(
        where={"voterId": voter_id},
        take=limit,
        order={"id": "desc"},
    )
    return [
        {
            "id": v.id,
            "dispute_id": v.disputeId,
            "side": v.side,
            "staked_amount": int(v.stakedAmount),
            "settled_amount": int(v.settledAmount or 0),
            "rationale": v.rationale,
        }
        for v in (rows or [])
    ]


# ---------------------------------------------------------------------------
# 5. 자동화 / 통계
# ---------------------------------------------------------------------------


async def auto_finalize_expired(batch: int = 50) -> dict[str, Any]:
    """투표 기간이 지난 분쟁들을 자동 확정 (cron 호출용)."""
    now = _now()
    rows = await prisma.dispute.find_many(
        where={"status": "open", "votingEndsAt": {"lt": now}},
        take=batch,
    )
    processed, failed = 0, 0
    for d in rows or []:
        try:
            await finalize_dispute(d.id, force=False)
            processed += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("auto_finalize 실패 dispute=%s: %s", d.id, e)
            failed += 1
    return {"processed": processed, "failed": failed, "scanned": len(rows or [])}


async def dispute_stats(last_days: int = 30) -> dict[str, Any]:
    """최근 N일 분쟁 통계."""
    since = _now() - timedelta(days=last_days)
    rows = await prisma.dispute.find_many(where={"votingEndsAt": {"gte": since}})
    rows = rows or []
    total = len(rows)
    resolved = sum(1 for r in rows if r.status == "resolved")
    pending = sum(1 for r in rows if r.status == "open")
    winning_dist: Counter = Counter(
        r.winningSide for r in rows if r.winningSide is not None
    )
    participation: list[int] = []
    for r in rows:
        cnt = await prisma.disputevote.count(where={"disputeId": r.id})
        participation.append(int(cnt or 0))
    avg = float(statistics.mean(participation)) if participation else 0.0
    return {
        "total_disputes": total,
        "resolved": resolved,
        "pending": pending,
        "winning_side_distribution": dict(winning_dist),
        "avg_participation": round(avg, 2),
    }


async def voter_accuracy(voter_id: str) -> float:
    """투표자가 과거 다수 승리 측에 선 비율 (0~1)."""
    votes = await prisma.disputevote.find_many(where={"voterId": voter_id})
    votes = votes or []
    if not votes:
        return 0.0
    hits, total = 0, 0
    for v in votes:
        d = await prisma.dispute.find_unique(where={"id": v.disputeId})
        if d is None or d.status != "resolved":
            continue
        total += 1
        if d.winningSide and v.side == d.winningSide:
            hits += 1
    return round(hits / total, 4) if total else 0.0


async def detect_vote_collusion(dispute_id: str) -> list[dict[str, Any]]:
    """공모 의심 패턴 탐지.

    같은 side, 비슷한 시각 (10분 이내), 비슷한 stake 금액 (5% 이내) 군집을 반환.
    """
    votes = await prisma.disputevote.find_many(where={"disputeId": dispute_id})
    votes = list(votes or [])
    # 동일 side 별로 묶기
    by_side: dict[str, list[Any]] = defaultdict(list)
    for v in votes:
        by_side[v.side].append(v)

    suspects: list[dict[str, Any]] = []
    for side, group in by_side.items():
        # 생성 시각 순 정렬 (createdAt 없으면 id 기준 fallback)
        group_sorted = sorted(group, key=lambda x: getattr(x, "createdAt", x.id))
        for i in range(len(group_sorted)):
            cluster = [group_sorted[i]]
            for j in range(i + 1, len(group_sorted)):
                a = group_sorted[i]
                b = group_sorted[j]
                ta = getattr(a, "createdAt", None)
                tb = getattr(b, "createdAt", None)
                if ta and tb:
                    diff_min = abs((tb - ta).total_seconds()) / 60.0
                    if diff_min > COLLUSION_TIME_WINDOW_MIN:
                        continue
                sa, sb = int(a.stakedAmount), int(b.stakedAmount)
                if sa == 0:
                    continue
                if abs(sa - sb) / sa <= COLLUSION_STAKE_DIFF_RATIO:
                    cluster.append(b)
            if len(cluster) >= 3:
                suspects.append(
                    {
                        "side": side,
                        "voter_ids": [c.voterId for c in cluster],
                        "stake_amounts": [int(c.stakedAmount) for c in cluster],
                        "size": len(cluster),
                    }
                )
    return suspects


async def dispute_markdown_summary(dispute_id: str) -> str:
    """관리자/공개용 마크다운 리포트."""
    d = await get_dispute(dispute_id)
    lines: list[str] = []
    lines.append(f"# 분쟁 {d['id']}: {d['topic']}")
    lines.append("")
    lines.append(f"- 상태: **{d['status']}**")
    lines.append(f"- 제기자: `{d['initiator_id']}`")
    if d.get("voting_ends_at"):
        lines.append(f"- 투표 종료: {d['voting_ends_at']}")
    if d.get("winning_side"):
        lines.append(f"- 승리 측: **{d['winning_side']}**")
    if d.get("resolution_note"):
        lines.append(f"- 결정 사유: {d['resolution_note']}")
    lines.append(f"- 총 stake: {d['total_staked']}")
    lines.append("")
    lines.append("## 설명")
    lines.append(d.get("description") or "(없음)")
    lines.append("")
    lines.append("## 관련 사실")
    for fid in d.get("related_fact_ids", []):
        lines.append(f"- `{fid}`")
    lines.append("")
    lines.append("## 투표 내역")
    lines.append("| 투표자 | Side | Stake | 정산 | 근거 |")
    lines.append("|---|---|---:|---:|---|")
    for v in d.get("votes", []):
        rationale = (v.get("rationale") or "").replace("|", "\\|")[:80]
        lines.append(
            f"| `{v['voter_id']}` | {v['side']} | {v['staked_amount']} "
            f"| {v['settled_amount']} | {rationale} |"
        )
    return "\n".join(lines)
