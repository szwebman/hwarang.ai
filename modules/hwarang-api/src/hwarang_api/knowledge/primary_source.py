"""HLKM TAL v3 ④ - Primary / Secondary Source 구분.

검색 결과에서 1차 출처(원문 공문서·논문)를 우선하고, 2차 출처(일반 매체·블로그)는
보조적으로만 표시한다. 도메인별 최소 tier 정책을 부여해 "법률 질문에 블로그만
끌고 오는" 답변을 막는다.

핵심 함수:
  - rank_facts_by_tier : tier × authority × 시간 × (1-retracted) 가중합 정렬
  - promote_primary_in_results : SearchResult dict 를 primary/secondary 로 분리
  - require_primary_source_or_warn : 도메인 정책 미달 시 경고 포함 답변
  - find_better_source / suggest_source_upgrade : 상향 대체안 추천
  - domain_primary_source_coverage : 커버리지 통계
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from hwarang_api.db import prisma

from .types import KnowledgeFact, KnowledgeStatus

# Group 1 제공 유틸 (아직 미구현이라도 import 실패 시 graceful).
try:
    from .hierarchy import lookup_authority  # type: ignore
except Exception:  # noqa: BLE001
    async def lookup_authority(domain: str, source_url: str | None) -> float:  # type: ignore
        """fallback: hierarchy.py 부재 시 기본 권위 0.5."""
        return 0.5

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Tier 우선순위 & 도메인 최소 정책
# ─────────────────────────────────────────────
TIER_PRIORITY: dict[str, int] = {
    "PRIMARY_OFFICIAL": 100,
    "PEER_REVIEWED": 90,
    "SPECIALIZED_MEDIA": 70,
    "GENERAL_MEDIA": 50,
    "USER_GENERATED": 20,
    "UNKNOWN": 10,
}

DOMAIN_MIN_TIER: dict[str, str] = {
    "law": "SPECIALIZED_MEDIA",
    "medical": "PEER_REVIEWED",
    "politics": "GENERAL_MEDIA",
    "tech": "USER_GENERATED",
    "general": "USER_GENERATED",
}

# "1차 출처 있어야 CONFIRMED 답변" 을 강제하는 도메인.
_STRICT_PRIMARY_DOMAINS = {"law", "medical"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fact_tier(fact: KnowledgeFact) -> str:
    """fact 의 tier 필드를 읽어 문자열로 정규화."""
    tier = getattr(fact, "source_tier", None) or getattr(fact, "sourceTier", None)
    if tier is None:
        return "UNKNOWN"
    if hasattr(tier, "value"):
        return str(tier.value)
    return str(tier)


def _fact_authority(fact: KnowledgeFact) -> float:
    """0~1 범위의 출처 권위 (Group 1 지정 또는 기본 0.5)."""
    auth = getattr(fact, "source_authority", None) or getattr(fact, "sourceAuthority", None)
    try:
        return max(0.0, min(1.0, float(auth))) if auth is not None else 0.5
    except (TypeError, ValueError):
        return 0.5


def _is_retracted(fact: KnowledgeFact) -> bool:
    if getattr(fact, "retracted", False):
        return True
    return getattr(fact, "status", None) == KnowledgeStatus.RETRACTED


def _recency_factor(fact: KnowledgeFact, now: datetime | None = None) -> float:
    """valid_from 기준 최근도(0~1). 30일 이내=1.0, 1년=0.5 로 완만히 감쇠."""
    now = now or _utcnow()
    vf = getattr(fact, "valid_from", None)
    if not isinstance(vf, datetime):
        return 0.5
    if vf.tzinfo is None:
        vf = vf.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - vf).total_seconds() / 86400.0)
    # 지수 감쇠 half-life 365일.
    from math import exp
    return float(exp(-age_days / 365.0))


# ─────────────────────────────────────────────
# 정규화된 점수
# ─────────────────────────────────────────────
def fact_tier_rank_score(fact: KnowledgeFact) -> float:
    """팩트 정렬용 0~1 정규화 점수.

    공식:
        score = tier_norm * 0.55 + authority * 0.25 + recency * 0.20
        if retracted: score *= 0.2
    """
    tier = _fact_tier(fact)
    tier_score = TIER_PRIORITY.get(tier, TIER_PRIORITY["UNKNOWN"]) / 100.0
    auth = _fact_authority(fact)
    recency = _recency_factor(fact)

    score = tier_score * 0.55 + auth * 0.25 + recency * 0.20
    if _is_retracted(fact):
        score *= 0.2
    return max(0.0, min(1.0, score))


# ─────────────────────────────────────────────
# 정렬 & 분리
# ─────────────────────────────────────────────
async def rank_facts_by_tier(facts: list[KnowledgeFact]) -> list[KnowledgeFact]:
    """tier × authority × recency × (1 - retracted) 가중합 내림차순.

    동점일 때 원래 입력 순서가 유지되도록 stable sort 를 사용한다.
    """
    if not facts:
        return []
    scored = list(enumerate(facts))
    scored.sort(
        key=lambda ix: (fact_tier_rank_score(ix[1]), -ix[0]),
        reverse=True,
    )
    return [f for _, f in scored]


async def promote_primary_in_results(search_result: dict) -> dict:
    """SearchResult-like dict 를 재정렬 + primary/secondary 로 분리.

    입력: {"facts": [...], ...}
    반환: {
        "primary": [...],      # PRIMARY_OFFICIAL + PEER_REVIEWED
        "secondary": [...],    # 그 외
        "warnings": [...],
    }
    """
    facts: list[KnowledgeFact] = list(search_result.get("facts") or [])
    ranked = await rank_facts_by_tier(facts)

    primary: list[KnowledgeFact] = []
    secondary: list[KnowledgeFact] = []
    for f in ranked:
        tier = _fact_tier(f)
        if tier in ("PRIMARY_OFFICIAL", "PEER_REVIEWED"):
            primary.append(f)
        else:
            secondary.append(f)

    warnings: list[str] = []
    if not primary and secondary:
        warnings.append("1차 출처가 없어 보조 출처로 답변했습니다.")
    if any(_is_retracted(f) for f in ranked):
        warnings.append("철회된 출처가 결과에 포함되어 있습니다.")

    out = dict(search_result)
    out["primary"] = primary
    out["secondary"] = secondary
    out["warnings"] = warnings
    out["facts"] = ranked  # 재정렬 반영
    return out


# ─────────────────────────────────────────────
# 도메인 정책
# ─────────────────────────────────────────────
async def require_primary_source_or_warn(
    question: str, facts: list[KnowledgeFact], domain: str
) -> dict:
    """도메인별 최소 출처 정책 검사.

    - law/medical : 1차 출처 없으면 CONFIRMED 라벨을 제거하고 경고 추가.
    - news/politics : SPECIALIZED_MEDIA 이상 없으면 약한 경고.
    - general : 제한 없음.
    """
    ranked = await rank_facts_by_tier(facts)
    warnings: list[str] = []
    answer_confidence = "CONFIRMED"

    tiers_present = {_fact_tier(f) for f in ranked}
    min_tier = DOMAIN_MIN_TIER.get(domain, "USER_GENERATED")
    min_rank = TIER_PRIORITY.get(min_tier, 0)

    has_primary = bool(tiers_present & {"PRIMARY_OFFICIAL", "PEER_REVIEWED"})

    if domain in _STRICT_PRIMARY_DOMAINS and not has_primary:
        warnings.append(
            f"[{domain}] 1차 출처(법령 원문/논문)가 없습니다. "
            "답변은 참고용이며 공식 확인이 필요합니다."
        )
        answer_confidence = "UNCERTAIN"

    # 최소 tier 미달만 있는 경우 경고
    all_below = all(
        TIER_PRIORITY.get(_fact_tier(f), 0) < min_rank for f in ranked
    )
    if ranked and all_below:
        warnings.append(
            f"[{domain}] 도메인 최소 출처 수준({min_tier}) 미달 자료로 답변되었습니다."
        )
        if answer_confidence == "CONFIRMED":
            answer_confidence = "LOW_CONFIDENCE"

    if not ranked:
        warnings.append("답변 근거가 될 사실이 없습니다.")
        answer_confidence = "UNKNOWN"

    return {
        "question": question,
        "domain": domain,
        "answer_confidence": answer_confidence,
        "has_primary": has_primary,
        "facts": ranked,
        "warnings": warnings,
    }


# ─────────────────────────────────────────────
# 상향 대체 출처 추천
# ─────────────────────────────────────────────
async def find_better_source(fact: KnowledgeFact) -> KnowledgeFact | None:
    """같은 entity/domain 에서 더 상위 tier 의 유사 사실을 찾는다.

    embedding 유사도 검색 대신 entity+domain+contentHash/content 일부 매칭으로
    탐색 (상세 임베딩 매칭은 search 모듈이 담당).
    """
    if not fact.entity and not fact.content:
        return None

    current_rank = TIER_PRIORITY.get(_fact_tier(fact), 0)
    where: dict[str, Any] = {
        "domain": fact.domain,
        "retracted": False,
        "status": KnowledgeStatus.CONFIRMED.value,
    }
    if fact.entity:
        where["entity"] = fact.entity

    try:
        rows = await prisma.knowledgefact.find_many(
            where=where, take=50, order={"createdAt": "desc"}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("find_better_source query failed: %s", exc)
        return None

    best: KnowledgeFact | None = None
    best_score = fact_tier_rank_score(fact)
    snippet = (fact.content or "")[:80]

    for row in rows:
        if row.id == fact.id:
            continue
        row_tier = getattr(row, "sourceTier", None) or "UNKNOWN"
        row_tier = row_tier.value if hasattr(row_tier, "value") else str(row_tier)
        row_rank = TIER_PRIORITY.get(row_tier, 0)
        if row_rank <= current_rank:
            continue
        # 내용 유사 대리 지표: snippet 교집합
        if snippet and snippet not in (row.content or "") and (row.content or "")[:80] not in (fact.content or ""):
            continue

        candidate = KnowledgeFact(
            id=row.id,
            content=row.content,
            content_hash=getattr(row, "contentHash", None),
            domain=row.domain,
            entity=row.entity,
            valid_from=row.validFrom,
            valid_to=row.validTo,
            created_at=row.createdAt,
            confidence_t0=float(getattr(row, "confidenceT0", 1.0)),
            status=KnowledgeStatus(row.status),
            source=row.source,
            source_url=row.sourceUrl,
        )
        score = fact_tier_rank_score(candidate)
        if score > best_score:
            best, best_score = candidate, score

    return best


async def suggest_source_upgrade(fact_id: str) -> dict | None:
    """현 사실보다 상위 tier 의 대체안을 사용자에게 제안할 수 있는지 판단."""
    try:
        row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("suggest_source_upgrade lookup failed: %s", exc)
        return None
    if not row:
        return None

    fact = KnowledgeFact(
        id=row.id,
        content=row.content,
        content_hash=getattr(row, "contentHash", None),
        domain=row.domain,
        entity=row.entity,
        valid_from=row.validFrom,
        valid_to=row.validTo,
        created_at=row.createdAt,
        confidence_t0=float(getattr(row, "confidenceT0", 1.0)),
        status=KnowledgeStatus(row.status),
        source=row.source,
        source_url=row.sourceUrl,
    )

    better = await find_better_source(fact)
    if not better:
        return None

    # 도메인별 친화 메시지
    msg = "더 권위 있는 1차 출처가 존재합니다."
    if fact.domain == "law":
        msg = "블로그/기사에서 온 법률 사실입니다. law.go.kr 원문을 확인해 보세요."
    elif fact.domain == "medical":
        msg = "의학 정보입니다. PubMed/공식 임상 가이드라인 원문을 확인해 보세요."
    elif fact.domain == "politics":
        msg = "정치 관련 정보입니다. 여러 주요 매체의 교차 확인을 권장합니다."

    return {
        "fact_id": fact.id,
        "current_tier": _fact_tier(fact),
        "current_score": fact_tier_rank_score(fact),
        "suggested_fact_id": better.id,
        "suggested_tier": _fact_tier(better),
        "suggested_score": fact_tier_rank_score(better),
        "suggested_url": better.source_url,
        "message": msg,
    }


# ─────────────────────────────────────────────
# 통계
# ─────────────────────────────────────────────
async def domain_primary_source_coverage(domain: str) -> dict:
    """도메인별 PRIMARY_OFFICIAL / PEER_REVIEWED 비율 통계."""
    try:
        total = await prisma.knowledgefact.count(where={"domain": domain})
    except Exception as exc:  # noqa: BLE001
        logger.warning("coverage total failed domain=%s: %s", domain, exc)
        return {"domain": domain, "total": 0, "primary": 0, "ratio": 0.0}

    if total == 0:
        return {
            "domain": domain,
            "total": 0,
            "primary_official": 0,
            "peer_reviewed": 0,
            "primary_total": 0,
            "ratio": 0.0,
            "min_tier": DOMAIN_MIN_TIER.get(domain, "USER_GENERATED"),
        }

    async def _count_tier(tier: str) -> int:
        try:
            return await prisma.knowledgefact.count(
                where={"domain": domain, "sourceTier": tier}
            )
        except Exception:  # noqa: BLE001
            return 0

    primary_official = await _count_tier("PRIMARY_OFFICIAL")
    peer_reviewed = await _count_tier("PEER_REVIEWED")
    primary_total = primary_official + peer_reviewed

    return {
        "domain": domain,
        "total": total,
        "primary_official": primary_official,
        "peer_reviewed": peer_reviewed,
        "primary_total": primary_total,
        "ratio": round(primary_total / total, 4) if total else 0.0,
        "min_tier": DOMAIN_MIN_TIER.get(domain, "USER_GENERATED"),
    }


# ─────────────────────────────────────────────
# 최소 tier 필터
# ─────────────────────────────────────────────
async def filter_by_min_tier(
    facts: list[KnowledgeFact], domain: str
) -> tuple[list[KnowledgeFact], list[KnowledgeFact]]:
    """(accepted, rejected_low_tier) 로 분리.

    거부 목록은 호출측에서 답변에서 제외하거나 별도 경고에 사용.
    """
    min_tier = DOMAIN_MIN_TIER.get(domain, "USER_GENERATED")
    threshold = TIER_PRIORITY.get(min_tier, 0)

    accepted: list[KnowledgeFact] = []
    rejected: list[KnowledgeFact] = []
    for f in facts:
        rank = TIER_PRIORITY.get(_fact_tier(f), TIER_PRIORITY["UNKNOWN"])
        if rank >= threshold:
            accepted.append(f)
        else:
            rejected.append(f)

    # authority 보정: hierarchy 기반 권위가 매우 높으면 tier 미달이어도 수용
    if rejected:
        keep: list[KnowledgeFact] = []
        still_rejected: list[KnowledgeFact] = []
        for f in rejected:
            try:
                authority = await lookup_authority(domain, f.source_url)
            except Exception:  # noqa: BLE001
                authority = _fact_authority(f)
            if authority >= 0.85:
                keep.append(f)
            else:
                still_rejected.append(f)
        accepted.extend(keep)
        rejected = still_rejected

    return accepted, rejected


__all__ = [
    "TIER_PRIORITY",
    "DOMAIN_MIN_TIER",
    "fact_tier_rank_score",
    "rank_facts_by_tier",
    "promote_primary_in_results",
    "require_primary_source_or_warn",
    "find_better_source",
    "suggest_source_upgrade",
    "domain_primary_source_coverage",
    "filter_by_min_tier",
]
