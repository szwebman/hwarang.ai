"""HLKM C4 - 코인 기여 보상.

KnowledgeContribution 레코드 관리 + HWARANG 토큰 민팅 연동.

보상 공식:
    reward = base[domain] * quality * uniqueness * tier_bonus
  - base:    {"law":100, "medical":150, "tech":50, "general":20}
  - tier:    basic=1.0, verified=1.3, expert=1.8
  - 최소 1 토큰 보장.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma
from hwarang_api.knowledge.embeddings import cosine
from hwarang_api.knowledge.types import KnowledgeStatus

logger = logging.getLogger(__name__)


_BASE_REWARD: dict[str, int] = {
    "law": 100,
    "medical": 150,
    "tech": 50,
    "general": 20,
}
_TIER_BONUS: dict[str, float] = {"basic": 1.0, "verified": 1.3, "expert": 1.8}

_DOWNVOTE_THRESHOLD = 5
_UP_DOWN_RATIO_THRESHOLD = 0.3


def calculate_reward(
    quality_score: float,
    uniqueness_score: float,
    domain: str,
    contributor_tier: str = "basic",
) -> int:
    """보상량(정수 토큰) 계산.

    q, u 는 [0, 1] 로 클램프. domain 미등록 시 general 규격.
    tier 미등록 시 basic.
    """
    q = max(0.0, min(1.0, float(quality_score)))
    u = max(0.0, min(1.0, float(uniqueness_score)))
    base = _BASE_REWARD.get(domain.lower(), _BASE_REWARD["general"])
    tier = _TIER_BONUS.get(contributor_tier.lower(), 1.0)
    amount = int(round(base * q * u * tier))
    return max(1, amount)


async def pay_contribution(
    fact_id: str,
    contributor_user_id: str,
    quality_score: float,
    uniqueness_score: float,
) -> int:
    """기여 보상 지급 + 코인 민팅.

    - KnowledgeContribution row 생성.
    - KnowledgeFact.rewardPaid / contributedBy 업데이트.
    - coin.mint_for_user() 호출 (실패해도 DB 기록은 유지).
    반환: 실제 지급된 토큰 수.
    """
    fact = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if fact is None:
        raise ValueError(f"fact not found: {fact_id}")

    tier = await _lookup_tier(contributor_user_id)
    reward = calculate_reward(quality_score, uniqueness_score, fact.domain, tier)

    await prisma.knowledgecontribution.create(
        data={
            "factId": fact_id,
            "contributorId": contributor_user_id,
            "qualityScore": float(quality_score),
            "uniquenessScore": float(uniqueness_score),
            "reward": reward,
        }
    )
    await prisma.knowledgefact.update(
        where={"id": fact_id},
        data={
            "rewardPaid": (fact.rewardPaid or 0) + reward,
            "contributedBy": contributor_user_id,
        },
    )

    try:
        from hwarang_api.knowledge.coin import mint_for_user  # type: ignore

        await mint_for_user(
            contributor_user_id, reward, reason=f"HLKM contribution:{fact_id}"
        )
    except Exception as exc:
        logger.warning("coin mint_for_user failed (will retry offline): %s", exc)

    return reward


async def vote_on_contribution(
    fact_id: str, voter_user_id: str, up: bool
) -> None:
    """기여 레코드에 찬/반 투표.

    여러 기여 row 가 있어도 최근(acceptedAt DESC) 1건 기준으로 갱신.
    반대표가 임계치를 초과하면 KnowledgeFact.status = DISPUTED.
    """
    contrib = await prisma.knowledgecontribution.find_first(
        where={"factId": fact_id}, order={"acceptedAt": "desc"}
    )
    if contrib is None:
        logger.debug("no contribution row for fact %s", fact_id)
        return

    update: dict[str, Any] = (
        {"votesUp": (contrib.votesUp or 0) + 1}
        if up
        else {"votesDown": (contrib.votesDown or 0) + 1}
    )
    await prisma.knowledgecontribution.update(
        where={"id": contrib.id}, data=update
    )

    ups = (contrib.votesUp or 0) + (1 if up else 0)
    downs = (contrib.votesDown or 0) + (0 if up else 1)
    total = ups + downs
    ratio = (ups / total) if total else 1.0
    if downs > _DOWNVOTE_THRESHOLD and ratio < _UP_DOWN_RATIO_THRESHOLD:
        await prisma.knowledgefact.update(
            where={"id": fact_id},
            data={"status": KnowledgeStatus.DISPUTED.value},
        )
        logger.info("fact %s marked DISPUTED (up=%d down=%d)", fact_id, ups, downs)


async def calculate_uniqueness(new_fact_content: str, embedding: list[float]) -> float:
    """기존 팩트들과의 의미 중복도를 0~1 유니크도로 환산.

    - 후보: 최근 500개 팩트 중 임베딩이 있는 것.
    - 상위 5개 유사도를 보고, max sim 을 기준으로:
        max < 0.5 → 1.0 (매우 독창)
        max > 0.9 → 0.0 (거의 중복)
        중간 구간은 선형 보간.
    """
    if not embedding:
        return 0.5

    candidates = await prisma.knowledgefact.find_many(
        where={"embeddingHex": {"not": None}},
        take=500,
        order={"createdAt": "desc"},
    )
    if not candidates:
        return 1.0

    from hwarang_api.knowledge.search import _hex_to_floats  # 재사용

    sims: list[float] = []
    for row in candidates:
        emb = _hex_to_floats(getattr(row, "embeddingHex", None))
        if emb is None:
            continue
        s = cosine(embedding, emb)
        sims.append(s)

    if not sims:
        return 1.0
    sims.sort(reverse=True)
    top = sims[:5]
    max_sim = top[0]

    if max_sim < 0.5:
        return 1.0
    if max_sim > 0.9:
        return 0.0
    # 선형 보간: 0.5→1.0, 0.9→0.0
    return 1.0 - (max_sim - 0.5) / (0.9 - 0.5)


async def get_top_contributors(days: int = 30, limit: int = 20) -> list[dict]:
    """최근 N 일 상위 기여자 집계.

    반환: [{"user_id","total_reward","fact_count","avg_quality"}, ...] (reward 내림차순).
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await prisma.knowledgecontribution.find_many(
        where={"acceptedAt": {"gte": since}}
    )
    if not rows:
        return []

    agg: dict[str, dict[str, float]] = defaultdict(
        lambda: {"total_reward": 0.0, "fact_count": 0.0, "quality_sum": 0.0}
    )
    for r in rows:
        bucket = agg[r.contributorId]
        bucket["total_reward"] += float(r.reward or 0)
        bucket["fact_count"] += 1
        bucket["quality_sum"] += float(r.qualityScore or 0)

    out: list[dict] = []
    for uid, b in agg.items():
        cnt = b["fact_count"] or 1
        out.append(
            {
                "user_id": uid,
                "total_reward": int(b["total_reward"]),
                "fact_count": int(b["fact_count"]),
                "avg_quality": round(b["quality_sum"] / cnt, 4),
            }
        )
    out.sort(key=lambda x: x["total_reward"], reverse=True)
    return out[:limit]


async def slash_reward(fact_id: str, reason: str) -> int:
    """사실이 무효화됐을 때 이미 지급한 보상을 회수.

    - 해당 fact 관련 KnowledgeContribution 총합만큼 user 에게 차감 호출.
    - coin.slash_from_user() placeholder 가 없으면 mint_for_user(음수) 로 보정.
    반환: 회수한 총 토큰 수.
    """
    contribs = await prisma.knowledgecontribution.find_many(
        where={"factId": fact_id}
    )
    if not contribs:
        return 0

    total = 0
    per_user: dict[str, int] = defaultdict(int)
    for c in contribs:
        amt = int(c.reward or 0)
        per_user[c.contributorId] += amt
        total += amt

    try:
        from hwarang_api.knowledge.coin import slash_from_user  # type: ignore

        for uid, amt in per_user.items():
            await slash_from_user(uid, amt, reason=f"HLKM slash:{fact_id}:{reason}")
    except Exception:
        # fallback: mint with negative amount
        try:
            from hwarang_api.knowledge.coin import mint_for_user  # type: ignore

            for uid, amt in per_user.items():
                await mint_for_user(uid, -amt, reason=f"HLKM slash:{fact_id}:{reason}")
        except Exception as exc:
            logger.warning("coin slash fallback failed: %s", exc)

    # DB 상 rewardPaid 초기화 + fact 상태 변경
    await prisma.knowledgefact.update(
        where={"id": fact_id},
        data={
            "rewardPaid": 0,
            "status": KnowledgeStatus.RETRACTED.value,
            "expiredReason": reason[:480],
        },
    )
    return total


async def _lookup_tier(user_id: str) -> str:
    """사용자의 티어 조회 placeholder.

    User 모델에 tier 가 있다면 그걸, 없으면 'basic'.
    """
    try:
        row = await prisma.user.find_unique(where={"id": user_id})
        if row is None:
            return "basic"
        tier = getattr(row, "tier", None) or getattr(row, "role", None)
        if isinstance(tier, str) and tier.lower() in _TIER_BONUS:
            return tier.lower()
    except Exception:
        pass
    return "basic"


__all__ = [
    "calculate_reward",
    "pay_contribution",
    "vote_on_contribution",
    "calculate_uniqueness",
    "get_top_contributors",
    "slash_reward",
]
