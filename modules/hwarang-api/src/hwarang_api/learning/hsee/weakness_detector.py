"""HSEE Phase 4 — Weakness Detector (통합 모듈).

기존 3 개 신호 소스를 묶어서 도메인별 약점 점수를 산출:

  1. ``gap_detector.get_priority_gaps`` — KnowledgeGap 우선순위
  2. ``self_questioner`` — confidence 낮은 자기 질문 (KnowledgeGap 안에 누적된 것 사용)
  3. ``RLHFFeedback`` 의 negative pattern (rating=-1, isSatisfied=False, followupMsg negative)

**중요 — 암묵 신호만**:
    명시 피드백 (👍/👎) 은 사용하지 않는다.
    rating=-1 / isSatisfied=False / followupMsg 의 부정 어휘만 활용한다.

출력 포맷::

    [
      {
        "domain": "coding",
        "query_pattern": "비동기 락 데드락 디버깅",
        "confidence_drop": 0.42,    # 0~1, 클수록 약점
        "sample_count": 7,
        "evidence_ids": ["gap:abc", "rlhf:def", ...],
        "last_seen": "2026-05-06T10:00:00Z"
      },
      ...
    ]

다음 단계 (synthetic_generator) 가 이 출력을 입력으로 받는다.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


# 도메인 매핑 — gap_detector 와 동일한 휴리스틱 + 코딩/모바일 추가
_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "legal": ("법", "조항", "판례", "민법", "형법", "헌법", "소송", "재판"),
    "tax": ("세금", "세무", "신고", "공제", "부가세", "원천세", "연말정산"),
    "medical": ("병", "약", "진단", "증상", "치료", "처방", "병원"),
    "finance": ("금리", "주식", "부동산", "대출", "투자", "환율"),
    "coding": (
        "코드", "프로그래밍", "개발", "라이브러리", "framework",
        "버그", "디버그", "함수", "class", "async", "타입",
    ),
    "mobile": ("안드로이드", "iOS", "swift", "kotlin", "flutter", "RN", "react native"),
    "design": ("디자인", "UI", "UX", "color", "typography", "레이아웃"),
}

# 명시 피드백 토큰은 사용 X — 암묵 신호 negative 어휘만
_NEGATIVE_TOKENS: tuple[str, ...] = (
    "틀렸", "잘못", "엉뚱", "이상해", "틀려", "다시", "이해 못", "모르겠",
    "오답", "오류", "에러나", "막혀",
)


@dataclass
class WeaknessSignal:
    """단일 약점 신호 — 약한 도메인/패턴/근거."""

    domain: str
    query_pattern: str
    confidence_drop: float  # 0~1, 클수록 약점
    sample_count: int
    evidence_ids: list[str] = field(default_factory=list)
    last_seen: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "query_pattern": self.query_pattern,
            "confidence_drop": round(float(self.confidence_drop), 3),
            "sample_count": int(self.sample_count),
            "evidence_ids": list(self.evidence_ids),
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _prisma_ready() -> bool:
    try:
        return bool(prisma.is_connected())
    except Exception:  # noqa: BLE001
        return False


def _infer_domain(text: str) -> str:
    if not text:
        return "general"
    for dom, words in _DOMAIN_KEYWORDS.items():
        if any(w in text for w in words):
            return dom
    return "general"


def _looks_negative(text: str | None) -> bool:
    """followupMsg 등에서 암묵 부정 신호 검출.

    명시 피드백 (👍/👎) 은 일부러 검사하지 않는다 (정책).
    """
    if not text:
        return False
    return any(tok in text for tok in _NEGATIVE_TOKENS)


def _normalize_pattern(text: str, max_len: int = 120) -> str:
    """질문/주제 → 패턴 키. 공백/구두점 정규화."""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = cleaned.replace("\n", " ")
    return cleaned[:max_len]


# ───────────────────────────────────────────────────────────────
# 신호 1 : KnowledgeGap (gap_detector + self_questioner 누적분)
# ───────────────────────────────────────────────────────────────
async def _from_knowledge_gaps(limit: int = 50) -> list[WeaknessSignal]:
    if not _prisma_ready():
        return []
    try:
        gaps = await prisma.knowledgegap.find_many(
            where={"status": "open"},
            order=[
                {"failureCount": "desc"},
                {"lastSeenAt": "desc"},
            ],
            take=limit,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("weakness/gap query failed: %s", exc)
        return []

    out: list[WeaknessSignal] = []
    for g in gaps:
        topic = _normalize_pattern(getattr(g, "topic", "") or "")
        if not topic:
            continue
        # failureCount → confidence_drop. 5+ 회 실패 → 1.0 포화.
        fcount = int(getattr(g, "failureCount", 1) or 1)
        drop = min(1.0, fcount / 5.0)
        out.append(
            WeaknessSignal(
                domain=_infer_domain(topic),
                query_pattern=topic,
                confidence_drop=drop,
                sample_count=fcount,
                evidence_ids=[f"gap:{getattr(g, 'id', '?')}"],
                last_seen=getattr(g, "lastSeenAt", None),
            )
        )
    return out


# ───────────────────────────────────────────────────────────────
# 신호 2 : RLHFFeedback (암묵 부정 신호)
# ───────────────────────────────────────────────────────────────
async def _from_rlhf_negative(window_hours: int = 168) -> list[WeaknessSignal]:
    """최근 ``window_hours`` 시간의 부정 RLHF 신호.

    명시 thumbs 가 아니라 — 사용자가 followup 으로 불만/재질문한 패턴만.
    """
    if not _prisma_ready():
        return []
    cutoff = _utcnow() - timedelta(hours=window_hours)
    try:
        rows = await prisma.rlhffeedback.find_many(
            where={
                "createdAt": {"gte": cutoff},
                "OR": [
                    {"rating": -1},
                    {"isSatisfied": False},
                ],
            },
            take=300,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("weakness/rlhf query failed: %s", exc)
        return []

    out: list[WeaknessSignal] = []
    for r in rows:
        # 우선 followupMsg 에서 부정 신호가 있는지 확인
        followup = getattr(r, "followupMsg", None) or ""
        if not (
            getattr(r, "rating", 0) == -1
            or getattr(r, "isSatisfied", True) is False
            or _looks_negative(followup)
        ):
            continue
        question = (
            getattr(r, "userMsg", None)
            or getattr(r, "prompt", None)
            or followup
            or ""
        )
        pattern = _normalize_pattern(question)
        if not pattern:
            continue
        domain = (getattr(r, "domain", None) or _infer_domain(pattern))
        out.append(
            WeaknessSignal(
                domain=domain or "general",
                query_pattern=pattern,
                confidence_drop=0.6,  # 단일 부정 — 중간 가중
                sample_count=1,
                evidence_ids=[f"rlhf:{getattr(r, 'id', '?')}"],
                last_seen=getattr(r, "createdAt", None),
            )
        )
    return out


# ───────────────────────────────────────────────────────────────
# 결합 + Top-N
# ───────────────────────────────────────────────────────────────
def _merge_by_pattern(signals: list[WeaknessSignal]) -> list[WeaknessSignal]:
    """동일 (domain, query_pattern) 신호를 하나로 합산."""
    bucket: dict[tuple[str, str], WeaknessSignal] = {}
    for s in signals:
        key = (s.domain, s.query_pattern)
        if key in bucket:
            cur = bucket[key]
            cur.sample_count += s.sample_count
            cur.confidence_drop = min(
                1.0, max(cur.confidence_drop, s.confidence_drop)
            )
            cur.evidence_ids.extend(s.evidence_ids)
            if s.last_seen and (not cur.last_seen or s.last_seen > cur.last_seen):
                cur.last_seen = s.last_seen
        else:
            bucket[key] = WeaknessSignal(
                domain=s.domain,
                query_pattern=s.query_pattern,
                confidence_drop=s.confidence_drop,
                sample_count=s.sample_count,
                evidence_ids=list(s.evidence_ids),
                last_seen=s.last_seen,
            )
    return list(bucket.values())


def _score(s: WeaknessSignal) -> float:
    """Top-N 정렬 키 — drop * sqrt(sample_count)."""
    sample = max(1, s.sample_count)
    return s.confidence_drop * (sample ** 0.5)


# ───────────────────────────────────────────────────────────────
# 진입점
# ───────────────────────────────────────────────────────────────
async def detect_weaknesses(
    top_n: int = 30,
    rlhf_window_hours: int = 168,
    gap_limit: int = 50,
) -> list[WeaknessSignal]:
    """약점 Top-N 추출.

    Args:
        top_n: 최종 반환 개수.
        rlhf_window_hours: RLHF 윈도우 (기본 7 일).
        gap_limit: KnowledgeGap pull 개수.

    Returns:
        ``WeaknessSignal`` 리스트, ``_score`` 내림차순.
    """
    gap_sigs = await _from_knowledge_gaps(limit=gap_limit)
    rlhf_sigs = await _from_rlhf_negative(window_hours=rlhf_window_hours)
    merged = _merge_by_pattern(gap_sigs + rlhf_sigs)
    merged.sort(key=_score, reverse=True)
    return merged[:top_n]


async def detect_weaknesses_dict(top_n: int = 30) -> list[dict[str, Any]]:
    """``detect_weaknesses`` 의 dict 직렬화 버전 (JSON 출력용)."""
    sigs = await detect_weaknesses(top_n=top_n)
    return [s.to_dict() for s in sigs]


__all__ = [
    "WeaknessSignal",
    "detect_weaknesses",
    "detect_weaknesses_dict",
]
