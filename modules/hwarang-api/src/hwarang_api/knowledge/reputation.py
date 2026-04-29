"""출처 평판 — 지식 출처의 사실 정확도 신뢰.

주의: 에이전트 작업 평판은 ``hwarang_api.grid.social.reputation`` 에 별도 시스템.
통합 조회는 ``hwarang_api.cognitive.trust.unified_trust.UnifiedTrust`` 사용.

HLKM ④ Source Reputation — 출처 평판 관리.

KnowledgeFact 의 출처(source)별 평판 점수를 계산/유지한다.
평판은 재검증 결과(unchanged/updated/invalidated/source_gone)의
누적 이력으로부터 산출되며, 가중 신뢰도 계산에 반영된다.

핵심 규칙:
  - 초기값: 출처 분류(official/peer_reviewed/community/unknown)에 따라 0.5~0.9
  - 업데이트: EMA(alpha=0.3) 로 기존 평판과 새 관측을 부드럽게 섞는다.
  - 가중 신뢰도: fact.confidence_t0 × half_life 감쇠 × 출처 평판

의존:
  - `hwarang_api.db.prisma` (Prisma 클라이언트)
  - `.half_life.current_confidence`
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from hwarang_api.db import prisma

from .half_life import current_confidence
from .types import KnowledgeFact, KnowledgeStatus

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
DEFAULT_REPUTATION = 0.7
EMA_ALPHA = 0.3                  # 새 관측 가중치 (0~1, 클수록 빠르게 반응)
MIN_CHANGE_THRESHOLD = 0.05      # "significant" 변화로 보는 최소 폭

# 결과별 기여 가중치 (0~1)
_RESULT_WEIGHT: dict[str, float] = {
    "unchanged": 1.0,
    "updated": 0.6,
    "invalidated": 0.0,
    "source_gone": 0.2,
}

# 공식 도메인 화이트리스트
_OFFICIAL_SUFFIXES: tuple[str, ...] = (
    ".go.kr",
    ".gov.kr",
    ".gov",
    "law.go.kr",
    "moleg.go.kr",
)
_PEER_REVIEWED_DOMAINS: tuple[str, ...] = (
    "nature.com",
    "science.org",
    "pubmed.ncbi.nlm.nih.gov",
    "nejm.org",
    "thelancet.com",
    "cell.com",
    "ieee.org",
    "acm.org",
    "arxiv.org",
    "biorxiv.org",
)


# ─────────────────────────────────────────────
# 소스 분류
# ─────────────────────────────────────────────
def classify_source_type(url: str | None, source_name: str) -> str:
    """URL 과 출처명으로 소스 유형을 분류한다.

    반환값: "official" | "peer_reviewed" | "community" | "unknown"
    """
    target = (url or "").lower()
    name = (source_name or "").lower()

    # 공식
    for suffix in _OFFICIAL_SUFFIXES:
        if suffix in target or suffix in name:
            return "official"

    # 심사 저널 / 학술
    for dom in _PEER_REVIEWED_DOMAINS:
        if dom in target or dom in name:
            return "peer_reviewed"

    # 커뮤니티/사용자 기여
    if any(tok in name for tok in ("user:", "community", "커뮤니티", "사용자")):
        return "community"
    if any(tok in target for tok in ("reddit.com", "blog.", "medium.com", "tistory.com")):
        return "community"

    return "unknown"


def _initial_reputation_for(source_type: str) -> float:
    return {
        "official": 0.9,
        "peer_reviewed": 0.85,
        "community": 0.6,
        "unknown": 0.5,
    }.get(source_type, DEFAULT_REPUTATION)


# ─────────────────────────────────────────────
# 조회 / 초기화
# ─────────────────────────────────────────────
async def get_reputation(source: str) -> float:
    """출처 평판을 조회한다. 없으면 기본값 0.7."""
    if not source:
        return DEFAULT_REPUTATION
    row = await prisma.sourcereputation.find_unique(where={"source": source})
    if row is None:
        return DEFAULT_REPUTATION
    return float(row.reputation)


async def initialize_reputation_for_new_source(
    source: str, source_url: str | None = None
) -> float:
    """새 출처 등장 시 SourceReputation 행을 생성한다.

    이미 존재하면 현재 reputation 만 반환한다.
    """
    existing = await prisma.sourcereputation.find_unique(where={"source": source})
    if existing is not None:
        return float(existing.reputation)

    stype = classify_source_type(source_url, source)
    initial = _initial_reputation_for(stype)
    await prisma.sourcereputation.create(
        data={
            "source": source,
            "sourceType": stype,
            "reputation": initial,
            "totalFacts": 0,
            "confirmedUnchanged": 0,
            "invalidated": 0,
            "updatedCount": 0,
            "lastUpdated": datetime.now(timezone.utc),
            "notes": f"initialized as {stype}",
        }
    )
    logger.info("init reputation: %s (%s) → %.2f", source, stype, initial)
    return initial


# ─────────────────────────────────────────────
# 평판 계산
# ─────────────────────────────────────────────
def _compute_base_reputation(
    unchanged: int, updated: int, invalidated: int, source_gone: int
) -> float:
    """카운터 기반 기본 평판 공식.

    reputation = Σ(count_i × weight_i) / total  (0~1)
    """
    total = unchanged + updated + invalidated + source_gone
    if total <= 0:
        return DEFAULT_REPUTATION
    weighted = (
        unchanged * _RESULT_WEIGHT["unchanged"]
        + updated * _RESULT_WEIGHT["updated"]
        + invalidated * _RESULT_WEIGHT["invalidated"]
        + source_gone * _RESULT_WEIGHT["source_gone"]
    )
    return max(0.0, min(1.0, weighted / total))


def _apply_ema(old: float, new: float, alpha: float = EMA_ALPHA) -> float:
    """EMA 로 부드럽게 섞는다: rep ← (1-α)·old + α·new."""
    return max(0.0, min(1.0, (1.0 - alpha) * old + alpha * new))


async def update_reputation_from_verification(source: str, result: str) -> float:
    """단일 검증 결과를 반영해 평판을 갱신한다.

    result ∈ {unchanged, updated, invalidated, source_gone}
    """
    if result not in _RESULT_WEIGHT:
        raise ValueError(f"unknown verification result: {result}")

    row = await prisma.sourcereputation.find_unique(where={"source": source})
    if row is None:
        await initialize_reputation_for_new_source(source)
        row = await prisma.sourcereputation.find_unique(where={"source": source})
        if row is None:
            return DEFAULT_REPUTATION

    unchanged = row.confirmedUnchanged + (1 if result == "unchanged" else 0)
    updated = row.updatedCount + (1 if result == "updated" else 0)
    invalidated = row.invalidated + (1 if result == "invalidated" else 0)
    # source_gone 은 별도 카운터가 없으므로 invalidated 약가중으로 처리
    source_gone_count = 1 if result == "source_gone" else 0

    base = _compute_base_reputation(
        unchanged, updated, invalidated, source_gone_count
    )
    new_rep = _apply_ema(float(row.reputation), base, EMA_ALPHA)

    await prisma.sourcereputation.update(
        where={"source": source},
        data={
            "confirmedUnchanged": unchanged,
            "updatedCount": updated,
            "invalidated": invalidated,
            "reputation": new_rep,
            "lastUpdated": datetime.now(timezone.utc),
        },
    )
    return new_rep


async def bulk_update_reputations_from_history(days: int = 30) -> dict:
    """최근 N 일 검증 이력을 전부 재집계하여 평판을 재계산한다.

    반환:
        {"updated": N, "changed_significantly": [(source, old, new), ...]}
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    verifications = await prisma.knowledgeverification.find_many(
        where={"verifiedAt": {"gte": cutoff}},
        take=20000,
        order={"verifiedAt": "desc"},
    )

    # source 단위 집계: factId → fact 를 가져와 source 를 찾는다.
    buckets: dict[str, dict[str, int]] = {}
    fact_cache: dict[str, str] = {}

    for v in verifications:
        fid = v.factId
        if fid not in fact_cache:
            fact = await prisma.knowledgefact.find_unique(where={"id": fid})
            if fact is None:
                continue
            fact_cache[fid] = fact.source
        source = fact_cache[fid]
        b = buckets.setdefault(
            source,
            {"unchanged": 0, "updated": 0, "invalidated": 0, "source_gone": 0},
        )
        if v.result in b:
            b[v.result] += 1

    updated_count = 0
    changed_significantly: list[tuple[str, float, float]] = []

    for source, counts in buckets.items():
        row = await prisma.sourcereputation.find_unique(where={"source": source})
        old_rep = float(row.reputation) if row else DEFAULT_REPUTATION
        base = _compute_base_reputation(
            counts["unchanged"],
            counts["updated"],
            counts["invalidated"],
            counts["source_gone"],
        )
        new_rep = _apply_ema(old_rep, base, EMA_ALPHA)

        if row is None:
            stype = classify_source_type(None, source)
            await prisma.sourcereputation.create(
                data={
                    "source": source,
                    "sourceType": stype,
                    "confirmedUnchanged": counts["unchanged"],
                    "updatedCount": counts["updated"],
                    "invalidated": counts["invalidated"],
                    "reputation": new_rep,
                    "lastUpdated": datetime.now(timezone.utc),
                    "notes": f"bulk init from {days}d history",
                }
            )
        else:
            await prisma.sourcereputation.update(
                where={"source": source},
                data={
                    "confirmedUnchanged": counts["unchanged"],
                    "updatedCount": counts["updated"],
                    "invalidated": counts["invalidated"],
                    "reputation": new_rep,
                    "lastUpdated": datetime.now(timezone.utc),
                },
            )
        updated_count += 1
        if abs(new_rep - old_rep) >= MIN_CHANGE_THRESHOLD:
            changed_significantly.append((source, old_rep, new_rep))

    logger.info(
        "bulk_update_reputations: %d sources refreshed, %d changed ≥%.2f",
        updated_count,
        len(changed_significantly),
        MIN_CHANGE_THRESHOLD,
    )
    return {
        "updated": updated_count,
        "changed_significantly": changed_significantly,
    }


async def penalize_source(
    source: str, reason: str, magnitude: float = 0.1
) -> float:
    """출처에 패널티를 가한다 (reputation -= magnitude).

    magnitude 는 [0, 1]. 0 이하/1 초과는 클램프.
    """
    mag = max(0.0, min(1.0, magnitude))
    row = await prisma.sourcereputation.find_unique(where={"source": source})
    if row is None:
        await initialize_reputation_for_new_source(source)
        row = await prisma.sourcereputation.find_unique(where={"source": source})
        if row is None:
            return DEFAULT_REPUTATION

    new_rep = max(0.0, float(row.reputation) - mag)
    note_line = f"[{datetime.now(timezone.utc).isoformat()}] -{mag:.2f} ({reason})"
    merged_notes = (row.notes or "") + "\n" + note_line

    await prisma.sourcereputation.update(
        where={"source": source},
        data={
            "reputation": new_rep,
            "notes": merged_notes[-4000:],  # 필드 크기 방어
            "lastUpdated": datetime.now(timezone.utc),
        },
    )
    logger.warning("penalize %s: -%.2f → %.2f (%s)", source, mag, new_rep, reason)
    return new_rep


# ─────────────────────────────────────────────
# 조회 (관리자 UI 용)
# ─────────────────────────────────────────────
async def list_reputations(
    min_facts: int = 5, order_by: str = "reputation"
) -> list[dict]:
    """최소 min_facts 개 이상 팩트를 가진 소스의 랭킹을 반환한다.

    order_by ∈ {"reputation", "totalFacts", "lastUpdated"}.
    """
    rows = await prisma.sourcereputation.find_many(take=500)
    items: list[dict] = []
    for r in rows:
        total_observed = (
            r.confirmedUnchanged + r.updatedCount + r.invalidated
        )
        if total_observed + r.totalFacts < min_facts:
            continue
        items.append(
            {
                "source": r.source,
                "source_type": r.sourceType,
                "reputation": float(r.reputation),
                "total_facts": r.totalFacts,
                "confirmed_unchanged": r.confirmedUnchanged,
                "updated_count": r.updatedCount,
                "invalidated": r.invalidated,
                "last_updated": r.lastUpdated,
                "notes": (r.notes or "")[:200],
            }
        )

    key = order_by if order_by in {"reputation", "totalFacts", "lastUpdated"} else "reputation"
    reverse = key in {"reputation", "totalFacts", "lastUpdated"}
    sort_key = {
        "reputation": lambda d: d["reputation"],
        "totalFacts": lambda d: d["total_facts"],
        "lastUpdated": lambda d: d["last_updated"],
    }[key]
    items.sort(key=sort_key, reverse=reverse)
    return items


# ─────────────────────────────────────────────
# 가중 신뢰도
# ─────────────────────────────────────────────
async def weighted_confidence(fact_id: str) -> float:
    """평판 가중 신뢰도를 계산한다.

    공식: clamp( confidence_t0 × current_confidence(fact) × reputation )
    """
    row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if row is None:
        return 0.0

    fact = KnowledgeFact(
        id=row.id,
        content=row.content,
        content_hash=row.contentHash,
        domain=row.domain,
        entity=row.entity,
        tags=list(row.tags or []),
        language=row.language,
        valid_from=row.validFrom,
        valid_to=row.validTo,
        created_at=row.createdAt,
        last_verified_at=row.lastVerifiedAt,
        next_check_at=row.nextCheckAt,
        confidence_t0=float(row.confidenceT0),
        half_life_days=row.halfLifeDays,
        status=KnowledgeStatus(row.status),
        source=row.source,
        source_url=row.sourceUrl,
    )

    decayed = current_confidence(fact)
    rep = await get_reputation(fact.source)
    combined = float(fact.confidence_t0) * float(decayed) * float(rep)
    # confidence_t0 는 이미 decayed 계산의 베이스지만, 공식 사양이
    # "t0 × current × rep" 이므로 그대로 적용 후 [0,1] 클램프.
    return max(0.0, min(1.0, combined))


__all__ = [
    "DEFAULT_REPUTATION",
    "EMA_ALPHA",
    "MIN_CHANGE_THRESHOLD",
    "classify_source_type",
    "get_reputation",
    "initialize_reputation_for_new_source",
    "update_reputation_from_verification",
    "bulk_update_reputations_from_history",
    "penalize_source",
    "list_reputations",
    "weighted_confidence",
]
