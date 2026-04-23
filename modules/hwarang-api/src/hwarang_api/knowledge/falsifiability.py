"""HLKM ⑧ - Falsifiability Classification (반증 가능성 분류).

사실이 "반증 가능한가"를 판정해 자동 재검증 주기·영속성을 결정한다.
수학 정리처럼 반증 불가능한 지식은 재검증 스케줄에서 제외하고,
미래 예측(time-dependent)은 예측 시점 도래 후에만 평가한다.

분류 레이블 (Falsifiability enum):
    - UNFALSIFIABLE    : 수학/논리 진리, 정의 (예: "2+2=4")
    - FALSIFIABLE      : 관측/측정 가능 (예: 온도, 인구, 법령 내용)
    - TIME_DEPENDENT   : 미래 시점 의존 (예: "2027년 금리 2%")
    - VALUE_JUDGMENT   : 가치 판단 (예: "이 정책은 좋다")
    - UNCLEAR          : 분류 불가 — 안전하게 재검증 대상에 포함

의존:
    - hwarang_api.db.prisma
    - .types.KnowledgeFact
    - .llm._chat
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from hwarang_api.db import prisma

from .types import KnowledgeFact

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 휴리스틱 패턴
# ─────────────────────────────────────────────
FALSIFIABILITY_HEURISTICS: dict[str, list[str]] = {
    "MATH_LOGIC": [r"정리|증명|공리|함수|미분|적분", r"theorem|proof|axiom"],
    "OBSERVABLE": [r"현재\s*\d+", r"측정|관측|집계|통계"],
    "FUTURE": [r"\d{4}년\s*(?:예정|예상|전망)", r"will be|predicted to"],
    "VALUE": [r"좋다|나쁘다|옳다|그르다|바람직"],
}

_VALID_FALS = {
    "UNFALSIFIABLE",
    "FALSIFIABLE",
    "TIME_DEPENDENT",
    "VALUE_JUDGMENT",
    "UNCLEAR",
}

# 도메인별 기본 half_life (일 단위)
_DEFAULT_HL_BY_DOMAIN: dict[str, int | None] = {
    "math": None,
    "theorem": None,
    "physics_constant": None,
    "law": 1825,      # 5년
    "medical_guideline": 730,
    "technology": 180,
    "news": 7,
    "market_price": 1,
    "weather": 0,
    "general": 365,
}


def _utcnow() -> datetime:
    """UTC 현재 시각."""
    return datetime.now(timezone.utc)


def _matches_any(patterns: list[str], text: str) -> bool:
    """패턴 리스트 중 하나라도 매칭되면 True."""
    return any(re.search(p, text) for p in patterns)


# ─────────────────────────────────────────────
# 휴리스틱 분류
# ─────────────────────────────────────────────
def _heuristic_falsifiability(content: str, domain: str) -> str | None:
    """정규식/도메인으로 빠르게 분류 가능한 경우 레이블 반환. 애매하면 None."""
    # 수학/논리 도메인 힌트
    if domain in {"math", "theorem", "physics_constant"}:
        return "UNFALSIFIABLE"
    if _matches_any(FALSIFIABILITY_HEURISTICS["MATH_LOGIC"], content):
        return "UNFALSIFIABLE"
    if _matches_any(FALSIFIABILITY_HEURISTICS["FUTURE"], content):
        return "TIME_DEPENDENT"
    if _matches_any(FALSIFIABILITY_HEURISTICS["VALUE"], content):
        return "VALUE_JUDGMENT"
    if _matches_any(FALSIFIABILITY_HEURISTICS["OBSERVABLE"], content):
        return "FALSIFIABLE"
    return None


# ─────────────────────────────────────────────
# LLM 보조 분류
# ─────────────────────────────────────────────
async def _llm_classify_falsifiability(content: str, domain: str) -> str:
    """LLM 으로 반증 가능성 판정. 실패/불명확 시 UNCLEAR."""
    try:
        from .llm import _chat  # type: ignore
    except Exception:
        return "UNCLEAR"

    system = (
        "Classify the given statement's falsifiability. "
        "Reply with EXACTLY one label from: "
        "UNFALSIFIABLE, FALSIFIABLE, TIME_DEPENDENT, VALUE_JUDGMENT, UNCLEAR. "
        "No extra words.\n"
        "- UNFALSIFIABLE: mathematical/logical truths, definitions\n"
        "- FALSIFIABLE: observable facts that can be checked against reality\n"
        "- TIME_DEPENDENT: predictions about future events\n"
        "- VALUE_JUDGMENT: opinions, value-based claims\n"
        "- UNCLEAR: cannot be determined"
    )
    prompt = f"[domain={domain}]\n{content}"
    try:
        resp = await _chat(prompt, system=system, max_tokens=10)
    except Exception as exc:  # noqa: BLE001
        logger.debug("_llm_classify_falsifiability failed: %s", exc)
        return "UNCLEAR"
    if not resp:
        return "UNCLEAR"

    label = resp.strip().upper().split()[0] if resp.strip() else "UNCLEAR"
    if label not in _VALID_FALS:
        for cand in _VALID_FALS:
            if cand in resp.upper():
                return cand
        return "UNCLEAR"
    return label


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────
async def classify_falsifiability(fact: KnowledgeFact) -> str:
    """KnowledgeFact 의 반증 가능성 레이블을 반환.

    휴리스틱이 우선, 애매하면 LLM 호출.
    """
    quick = _heuristic_falsifiability(fact.content, fact.domain)
    if quick is not None:
        return quick
    return await _llm_classify_falsifiability(fact.content, fact.domain)


async def apply_falsifiability(fact_id: str) -> dict:
    """fact 의 반증 가능성을 판정해 DB 에 기록.

    반증 불가능(UNFALSIFIABLE)한 것은 next_check_at=NULL 로 세팅해
    자동 재검증 큐에서 제외시킨다.
    """
    try:
        row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("apply_falsifiability fetch failed: %s", exc)
        return {"fact_id": fact_id, "falsifiability": None}
    if not row:
        return {"fact_id": fact_id, "falsifiability": None}

    fact = KnowledgeFact(
        id=row.id,
        content=getattr(row, "content", ""),
        domain=getattr(row, "domain", "general"),
        valid_from=getattr(row, "validFrom"),
        source=getattr(row, "source", ""),
        half_life_days=getattr(row, "halfLifeDays", None),
    )
    label = await classify_falsifiability(fact)

    update_data: dict[str, Any] = {"falsifiability": label}
    if label in {"UNFALSIFIABLE", "VALUE_JUDGMENT"}:
        update_data["nextCheckAt"] = None

    # 권장 half_life 로 조정
    rec_hl = recommended_half_life(label, fact.domain, fact.half_life_days)
    if rec_hl != fact.half_life_days:
        update_data["halfLifeDays"] = rec_hl

    try:
        await prisma.knowledgefact.update(where={"id": fact_id}, data=update_data)
    except Exception as exc:  # noqa: BLE001
        logger.warning("apply_falsifiability update failed: %s", exc)

    return {"fact_id": fact_id, "falsifiability": label, "half_life_days": rec_hl}


async def batch_apply_falsifiability(limit: int = 200) -> dict:
    """falsifiability 미지정 사실들을 일괄 분류."""
    try:
        rows = await prisma.knowledgefact.find_many(
            where={"falsifiability": None}, take=limit
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("batch_apply_falsifiability find failed: %s", exc)
        return {"total": 0, "labeled": 0, "by_label": {}}

    by_label: dict[str, int] = {k: 0 for k in _VALID_FALS}
    labeled = 0
    for row in rows:
        res = await apply_falsifiability(row.id)
        lbl = res.get("falsifiability")
        if lbl and lbl in by_label:
            by_label[lbl] += 1
            labeled += 1
    return {"total": len(rows), "labeled": labeled, "by_label": by_label}


def should_auto_reverify(fact: KnowledgeFact) -> bool:
    """fact 를 자동 재검증 스케줄에 포함할지 판정.

    규칙:
      - UNFALSIFIABLE → False (수학 정리 재검증 X)
      - FALSIFIABLE → True
      - TIME_DEPENDENT → 예측 시점이 이미 지났으면 True, 아니면 False
      - VALUE_JUDGMENT → False
      - UNCLEAR → True (안전 우선)
    """
    fals = getattr(fact, "falsifiability", None)
    if fals is None:
        return True

    if fals == "UNFALSIFIABLE":
        return False
    if fals == "VALUE_JUDGMENT":
        return False
    if fals == "FALSIFIABLE":
        return True
    if fals == "TIME_DEPENDENT":
        pred = fact.predicted_valid_from
        if pred is None:
            return False
        if pred.tzinfo is None:
            pred = pred.replace(tzinfo=timezone.utc)
        return pred <= _utcnow()
    # UNCLEAR 또는 기타
    return True


def recommended_half_life(
    falsifiability: str, domain: str, current_hl: int | None
) -> int | None:
    """반증성 × 도메인을 근거로 권장 half_life(days) 를 반환.

    규칙 요약:
      - UNFALSIFIABLE + math 계열 → None (영속)
      - FALSIFIABLE + law → 1825 (5년)
      - TIME_DEPENDENT → 현재 값을 유지 (예측 시점까지)
      - VALUE_JUDGMENT → None (감쇠시키지 않음)
      - UNCLEAR → 도메인 기본값
    """
    if falsifiability == "UNFALSIFIABLE":
        return None
    if falsifiability == "VALUE_JUDGMENT":
        return None
    if falsifiability == "FALSIFIABLE":
        if domain == "law":
            return 1825
        return _DEFAULT_HL_BY_DOMAIN.get(domain, current_hl or 365)
    if falsifiability == "TIME_DEPENDENT":
        # 예측 시점까지는 원래 값 유지
        return current_hl
    # UNCLEAR
    return _DEFAULT_HL_BY_DOMAIN.get(domain, current_hl or 365)


async def list_unfalsifiable(domain: str | None = None) -> list[dict]:
    """UNFALSIFIABLE 로 분류된 사실 목록 (수학 정리/영속 지식)."""
    where: dict[str, Any] = {"falsifiability": "UNFALSIFIABLE"}
    if domain:
        where["domain"] = domain
    try:
        rows = await prisma.knowledgefact.find_many(where=where, take=500)
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_unfalsifiable failed: %s", exc)
        return []
    return [
        {
            "fact_id": r.id,
            "content": getattr(r, "content", "")[:200],
            "domain": getattr(r, "domain", ""),
            "source": getattr(r, "source", ""),
        }
        for r in rows
    ]


async def list_time_dependent_upcoming(within_days: int = 90) -> list[dict]:
    """앞으로 ``within_days`` 일 이내에 예측 시점이 도래하는
    TIME_DEPENDENT 사실을 모아 반환한다. 자동 재평가 대기열로 사용.
    """
    now = _utcnow()
    try:
        from datetime import timedelta

        upper = now + timedelta(days=within_days)
        rows = await prisma.knowledgefact.find_many(
            where={
                "falsifiability": "TIME_DEPENDENT",
                "predictedValidFrom": {"gte": now, "lte": upper},
            },
            take=500,
            order={"predictedValidFrom": "asc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_time_dependent_upcoming failed: %s", exc)
        return []

    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "fact_id": r.id,
                "content": getattr(r, "content", "")[:200],
                "domain": getattr(r, "domain", ""),
                "predicted_valid_from": getattr(r, "predictedValidFrom", None),
                "prediction_confidence": getattr(r, "predictionConfidence", None),
            }
        )
    return out


__all__ = [
    "classify_falsifiability",
    "apply_falsifiability",
    "batch_apply_falsifiability",
    "should_auto_reverify",
    "recommended_half_life",
    "list_unfalsifiable",
    "list_time_dependent_upcoming",
    "FALSIFIABILITY_HEURISTICS",
]
