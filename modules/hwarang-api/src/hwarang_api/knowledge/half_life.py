"""HLKM B2: 반감기 ML 학습 모듈.

도메인/태그별 지식 반감기를 관리한다.
  1. DEFAULT_HALF_LIFE 로 기본값 제공 (수학=영속, 법=5년, 뉴스=7일 등).
  2. current_confidence() 로 시간 감쇠된 현재 신뢰도 계산.
  3. next_check_time() 로 다음 재검증 시점 산출 (반감기의 절반).
  4. HalfLifeModel 은 KnowledgeVerification 실측 데이터로부터
     도메인별 실제 업데이트 주기를 학습해 DEFAULT 값을 보정한다.

의존:
  - hwarang_api.db.prisma : Prisma 클라이언트
  - .types.KnowledgeFact  : 사실 모델
"""

from __future__ import annotations

import json
import logging
import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from hwarang_api.db import prisma

from .types import KnowledgeFact, KnowledgeStatus

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 기본 반감기 테이블 (days)
# ─────────────────────────────────────────────
DEFAULT_HALF_LIFE: dict[str, int | None] = {
    "math": None,                # 수학 정리는 영속
    "theorem": None,
    "physics_constant": None,
    "law": 1825,                 # 5년 (법률 개정 주기)
    "medical_guideline": 730,    # 2년
    "technology": 180,           # 6개월
    "news": 7,
    "market_price": 1,
    "weather": 0,                # 0 = 즉시 만료, 매번 재확인
    "general": 365,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime) -> datetime:
    """Naive datetime 을 UTC 로 가정해 aware 로 변환."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ─────────────────────────────────────────────
# 신뢰도 감쇠 / 다음 체크 시점
# ─────────────────────────────────────────────
def current_confidence(fact: KnowledgeFact, now: datetime | None = None) -> float:
    """시간 경과에 따른 현재 신뢰도를 반환한다.

    공식: confidence(t) = confidence_t0 * 0.5 ** (age_days / half_life_days)
    half_life_days 가 None 이면 감쇠 없음.
    """
    now = _as_aware(now or _utcnow())
    base = max(0.0, min(1.0, fact.confidence_t0))

    # 반감기가 지정되지 않았거나 영속 지식 → 감쇠 없음
    if fact.half_life_days is None:
        return base

    # 반감기가 0 이면 즉시 0 으로 수렴 (단, 방금 검증했다면 1)
    anchor = fact.last_verified_at or fact.valid_from
    anchor = _as_aware(anchor)
    age_seconds = max(0.0, (now - anchor).total_seconds())
    age_days = age_seconds / 86_400.0

    if fact.half_life_days == 0:
        # 0 반감기: 1시간(=1/24일)마다 반감
        effective_half = 1.0 / 24.0
    else:
        effective_half = float(fact.half_life_days)

    decay = 0.5 ** (age_days / effective_half)
    return max(0.0, min(1.0, base * decay))


def next_check_time(fact: KnowledgeFact, now: datetime | None = None) -> datetime | None:
    """다음 자동 재검증 시점을 반환한다.

    기준: last_verified_at + half_life_days * 0.5
    half_life_days 가 None 이면 None (자동 재검증 안 함).
    """
    if fact.half_life_days is None:
        return None

    anchor = fact.last_verified_at or fact.valid_from or (now or _utcnow())
    anchor = _as_aware(anchor)

    if fact.half_life_days == 0:
        return anchor + timedelta(hours=1)

    return anchor + timedelta(days=fact.half_life_days * 0.5)


# ─────────────────────────────────────────────
# 학습형 반감기 모델
# ─────────────────────────────────────────────
class HalfLifeModel:
    """KnowledgeVerification 이력으로부터 도메인/태그별 실제 반감기를 학습.

    학습 방식:
      - result='updated' 인 Verification 레코드를 모은다.
      - 해당 사실의 (이전 last_verified_at ~ verifiedAt) 간격을 구한다.
      - 도메인 + 주요 태그별로 중앙값을 저장한다.
    """

    def __init__(self) -> None:
        self._domain_median: dict[str, int] = {}
        self._tag_median: dict[str, int] = {}
        self._trained_at: datetime | None = None

    async def train(self) -> None:
        """Prisma 에서 검증 이력을 조회해 중앙값을 계산."""
        verifications = await prisma.knowledgeverification.find_many(
            where={"result": "updated"},
            take=5000,
            order={"verifiedAt": "desc"},
        )

        by_domain: dict[str, list[float]] = defaultdict(list)
        by_tag: dict[str, list[float]] = defaultdict(list)

        for v in verifications:
            fact = await prisma.knowledgefact.find_unique(where={"id": v.factId})
            if fact is None:
                continue
            prev = _as_aware(fact.lastVerifiedAt or fact.createdAt)
            verified_at = _as_aware(v.verifiedAt)
            days = max(0.0, (verified_at - prev).total_seconds() / 86_400.0)
            if days <= 0:
                continue

            by_domain[fact.domain].append(days)
            for tag in (fact.tags or []):
                by_tag[tag].append(days)

        self._domain_median = {
            d: int(statistics.median(vals))
            for d, vals in by_domain.items()
            if len(vals) >= 3
        }
        self._tag_median = {
            t: int(statistics.median(vals))
            for t, vals in by_tag.items()
            if len(vals) >= 5
        }
        self._trained_at = _utcnow()
        logger.info(
            "HalfLifeModel trained: %d domains, %d tags",
            len(self._domain_median),
            len(self._tag_median),
        )

    def predict(self, domain: str, tags: list[str]) -> int | None:
        """학습값 > 태그 평균 > DEFAULT 순으로 반감기 추정."""
        if domain in self._domain_median:
            return self._domain_median[domain]

        tag_hits = [self._tag_median[t] for t in tags if t in self._tag_median]
        if tag_hits:
            return int(statistics.median(tag_hits))

        if domain in DEFAULT_HALF_LIFE:
            return DEFAULT_HALF_LIFE[domain]
        return DEFAULT_HALF_LIFE["general"]

    async def save(self, path: str) -> None:
        payload: dict[str, Any] = {
            "domain_median": self._domain_median,
            "tag_median": self._tag_median,
            "trained_at": self._trained_at.isoformat() if self._trained_at else None,
        }
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    async def load(cls, path: str) -> HalfLifeModel:
        model = cls()
        p = Path(path)
        if not p.exists():
            return model
        data = json.loads(p.read_text(encoding="utf-8"))
        model._domain_median = {k: int(v) for k, v in data.get("domain_median", {}).items()}
        model._tag_median = {k: int(v) for k, v in data.get("tag_median", {}).items()}
        ts = data.get("trained_at")
        model._trained_at = datetime.fromisoformat(ts) if ts else None
        return model


# ─────────────────────────────────────────────
# 배치 갱신
# ─────────────────────────────────────────────
async def update_all_next_check_times() -> int:
    """모든 CONFIRMED 사실의 next_check_at 을 재계산해 DB 에 반영.

    반환: 갱신된 레코드 수.
    """
    updated = 0
    offset = 0
    page = 500

    while True:
        rows = await prisma.knowledgefact.find_many(
            where={"status": KnowledgeStatus.CONFIRMED.value},
            take=page,
            skip=offset,
            order={"lastVerifiedAt": "asc"},
        )
        if not rows:
            break

        for row in rows:
            if row.halfLifeDays is None:
                continue
            anchor = _as_aware(row.lastVerifiedAt or row.createdAt)
            if row.halfLifeDays == 0:
                nxt = anchor + timedelta(hours=1)
            else:
                nxt = anchor + timedelta(days=row.halfLifeDays * 0.5)
            await prisma.knowledgefact.update(
                where={"id": row.id},
                data={"nextCheckAt": nxt},
            )
            updated += 1

        if len(rows) < page:
            break
        offset += page

    logger.info("update_all_next_check_times: %d facts updated", updated)
    return updated


__all__ = [
    "DEFAULT_HALF_LIFE",
    "HalfLifeModel",
    "current_confidence",
    "next_check_time",
    "update_all_next_check_times",
]
