"""HLKM ⑥ - Stance Labeling (입장 분류).

한 사실(KnowledgeFact)이 "객관적 사실"인지 "해석"인지 "의견"인지
"선전성 서술"인지 자동 분류한다. 답변 시 사용자에게 가중치와 라벨을
함께 표시해 편향된 정보에 현혹되지 않도록 한다.

분류 레이블 (FactStance enum):
    - FACTUAL         : 관측 가능한 객관 사실 (인구, 법령, 측정값)
    - INTERPRETATION  : 사실 해석 (원인 분석, 의미 부여)
    - OPINION         : 의견/주장 (가치 판단)
    - CONTESTED       : 논쟁 중 — 같은 주제에 상반된 사실 존재
    - PROPAGANDA      : 선전성 수사 (감정 유발, 미화/비하)

의존:
    - hwarang_api.db.prisma
    - .types.KnowledgeFact
    - .llm._chat
"""

from __future__ import annotations

import logging
import re
from typing import Any

from hwarang_api.db import prisma

from .types import KnowledgeFact

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 휴리스틱 패턴
# ─────────────────────────────────────────────
STANCE_HEURISTICS: dict[str, list[str]] = {
    "OPINION_MARKERS": [r"생각한다", r"의견", r"주장", r"believe", r"think"],
    "OPINION_ADJECTIVES": [r"좋다", r"나쁘다", r"훌륭하다", r"끔찍하다"],
    "FACTUAL_MARKERS": [r"\d{4}-\d{2}-\d{2}", r"\d+원", r"에\s*따르면"],
    "PROPAGANDA_MARKERS": [r"당당히", r"역사적인", r"위대한", r"치욕적"],
    "INTERPRETATION_MARKERS": [r"해석상", r"뜻하는", r"의미하는"],
}

# stance → 한글 표시 라벨
_DISPLAY_LABELS: dict[str, str] = {
    "FACTUAL": "사실",
    "INTERPRETATION": "해석",
    "OPINION": "의견",
    "CONTESTED": "논쟁 중",
    "PROPAGANDA": "선전성",
}

# stance → 신뢰도 가중치 배수
_WEIGHT_MULTIPLIERS: dict[str, float] = {
    "FACTUAL": 1.0,
    "INTERPRETATION": 0.7,
    "OPINION": 0.3,
    "CONTESTED": 0.5,
    "PROPAGANDA": 0.1,
}

_VALID_STANCES = set(_DISPLAY_LABELS.keys())


def _count_hits(patterns: list[str], text: str) -> int:
    """패턴 중 몇 개가 텍스트에 매칭되는지 카운트."""
    return sum(1 for p in patterns if re.search(p, text))


# ─────────────────────────────────────────────
# 휴리스틱 기반 빠른 분류
# ─────────────────────────────────────────────
def _heuristic_stance(content: str) -> tuple[str | None, float]:
    """정규식만으로 명확히 분류 가능한 경우 (stance, confidence) 반환.

    애매하면 ``(None, 0.0)`` 을 돌려 LLM 호출을 유도한다.
    """
    propaganda_hits = _count_hits(STANCE_HEURISTICS["PROPAGANDA_MARKERS"], content)
    if propaganda_hits >= 2:
        return ("PROPAGANDA", 0.8)

    opinion_hits = _count_hits(
        STANCE_HEURISTICS["OPINION_MARKERS"], content
    ) + _count_hits(STANCE_HEURISTICS["OPINION_ADJECTIVES"], content)
    factual_hits = _count_hits(STANCE_HEURISTICS["FACTUAL_MARKERS"], content)
    interp_hits = _count_hits(STANCE_HEURISTICS["INTERPRETATION_MARKERS"], content)

    # 강한 사실 신호 + 의견/선전 신호 없음 → FACTUAL
    if factual_hits >= 1 and opinion_hits == 0 and propaganda_hits == 0:
        return ("FACTUAL", 0.75)

    # 의견 신호 강함 + 사실 신호 없음 → OPINION
    if opinion_hits >= 2 and factual_hits == 0:
        return ("OPINION", 0.7)

    # 해석 신호 강함 → INTERPRETATION
    if interp_hits >= 1 and opinion_hits == 0:
        return ("INTERPRETATION", 0.6)

    return (None, 0.0)


# ─────────────────────────────────────────────
# LLM 분류
# ─────────────────────────────────────────────
async def _llm_classify_stance(content: str, domain: str) -> tuple[str, float]:
    """LLM 으로 stance 판정.

    응답 형식: ``LABEL 0.87`` (5개 라벨 중 하나 + confidence 0~1).
    실패 시 ``("CONTESTED", 0.3)`` 를 반환해 회색 영역 처리.
    """
    try:
        from .llm import _chat  # type: ignore
    except Exception:
        return ("CONTESTED", 0.3)

    system = (
        "Classify the given statement's epistemic stance. "
        "Reply with EXACTLY: '<LABEL> <confidence>' where LABEL is one of "
        "FACTUAL, INTERPRETATION, OPINION, CONTESTED, PROPAGANDA "
        "and confidence is a float 0.0-1.0. No extra words.\n"
        "Guide:\n"
        "- FACTUAL: observable/measurable (numbers, laws, events)\n"
        "- INTERPRETATION: inference about meaning or cause\n"
        "- OPINION: value judgment, personal belief\n"
        "- CONTESTED: disputed claim with multiple sides\n"
        "- PROPAGANDA: emotionally loaded rhetoric, glorification/vilification"
    )
    prompt = f"[domain={domain}]\n{content}"
    try:
        resp = await _chat(prompt, system=system, max_tokens=20)
    except Exception as exc:  # noqa: BLE001
        logger.debug("_llm_classify_stance failed: %s", exc)
        return ("CONTESTED", 0.3)
    if not resp:
        return ("CONTESTED", 0.3)

    m = re.match(r"^\s*([A-Z_]+)\s+([0-9.]+)", resp.strip().upper())
    if not m:
        for lbl in _VALID_STANCES:
            if resp.strip().upper().startswith(lbl):
                return (lbl, 0.5)
        return ("CONTESTED", 0.3)
    label = m.group(1)
    if label not in _VALID_STANCES:
        label = "CONTESTED"
    try:
        conf = max(0.0, min(1.0, float(m.group(2))))
    except ValueError:
        conf = 0.5
    return (label, conf)


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────
async def classify_stance(fact: KnowledgeFact) -> tuple[str, float]:
    """fact 의 stance 를 판정 후 (label, confidence) 반환.

    1) 휴리스틱 빠른 분류
    2) 불확실하면 LLM 호출
    """
    stance, conf = _heuristic_stance(fact.content)
    if stance is not None and conf >= 0.7:
        return (stance, conf)

    # 휴리스틱으로 명확히 안 잡히면 LLM 에 위임
    llm_label, llm_conf = await _llm_classify_stance(fact.content, fact.domain)
    return (llm_label, llm_conf)


async def apply_stance(fact_id: str) -> dict:
    """fact_id 의 stance 를 판정해 DB 업데이트."""
    try:
        row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("apply_stance fetch failed: %s", exc)
        return {"fact_id": fact_id, "stance": None, "confidence": 0.0}
    if not row:
        return {"fact_id": fact_id, "stance": None, "confidence": 0.0}

    fact = KnowledgeFact(
        id=row.id,
        content=getattr(row, "content", ""),
        domain=getattr(row, "domain", "general"),
        valid_from=getattr(row, "validFrom"),
        source=getattr(row, "source", ""),
    )
    stance, conf = await classify_stance(fact)
    try:
        await prisma.knowledgefact.update(
            where={"id": fact_id},
            data={"stance": stance, "stanceConfidence": conf},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("apply_stance update failed: %s", exc)

    return {"fact_id": fact_id, "stance": stance, "confidence": conf}


async def batch_apply_stance(domain: str | None = None, limit: int = 200) -> dict:
    """stance 가 아직 지정되지 않은 사실들을 일괄 분류한다."""
    where: dict[str, Any] = {"stance": None}
    if domain:
        where["domain"] = domain

    try:
        rows = await prisma.knowledgefact.find_many(where=where, take=limit)
    except Exception as exc:  # noqa: BLE001
        logger.warning("batch_apply_stance find failed: %s", exc)
        return {"total": 0, "labeled": 0, "by_stance": {}}

    by_stance: dict[str, int] = {k: 0 for k in _VALID_STANCES}
    labeled = 0
    for row in rows:
        res = await apply_stance(row.id)
        s = res.get("stance")
        if s and s in by_stance:
            by_stance[s] += 1
            labeled += 1
    return {"total": len(rows), "labeled": labeled, "by_stance": by_stance}


async def find_contested_facts(entity: str) -> list[dict]:
    """entity 에 대해 상반된 stance 의 사실들을 찾아낸다.

    같은 entity 에 FACTUAL 과 OPINION / PROPAGANDA 가 공존하면
    사용자에게 "같은 주제에 다양한 입장이 있습니다" 경고에 활용한다.
    """
    try:
        rows = await prisma.knowledgefact.find_many(where={"entity": entity}, take=200)
    except Exception as exc:  # noqa: BLE001
        logger.warning("find_contested_facts failed: %s", exc)
        return []

    grouped: dict[str, list[Any]] = {}
    for row in rows:
        s = getattr(row, "stance", None)
        if s:
            grouped.setdefault(s, []).append(row)

    if len(grouped.keys()) < 2:
        return []

    out: list[dict] = []
    for stance, items in grouped.items():
        for r in items[:5]:  # stance 당 최대 5개
            out.append(
                {
                    "fact_id": r.id,
                    "content": getattr(r, "content", "")[:200],
                    "stance": stance,
                    "stance_label": stance_display_label(stance),
                    "weight": stance_weight_multiplier(stance),
                    "source": getattr(r, "source", ""),
                }
            )
    return out


# ─────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────
def stance_display_label(stance: str) -> str:
    """stance 문자열 → 사용자용 한글 라벨."""
    return _DISPLAY_LABELS.get(stance, "미분류")


def stance_weight_multiplier(stance: str) -> float:
    """stance 별 신뢰도 가중치 배수.

    사용 예: ``final_conf = current_conf * stance_weight_multiplier(fact.stance)``.
    """
    return _WEIGHT_MULTIPLIERS.get(stance, 0.5)


__all__ = [
    "classify_stance",
    "apply_stance",
    "batch_apply_stance",
    "find_contested_facts",
    "stance_display_label",
    "stance_weight_multiplier",
    "STANCE_HEURISTICS",
]
