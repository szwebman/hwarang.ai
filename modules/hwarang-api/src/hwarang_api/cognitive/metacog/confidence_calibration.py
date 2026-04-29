"""Confidence Calibration — 답변 신뢰도 재보정 (Phase 9.ζ).

LLM 의 자체 자신감 (raw) × 도메인 과거 정확도 (historical) → calibrated.

도메인 과거 정확도는 Prisma 의 ``CognitiveAudit`` (환각 점수) 와
``ConstitutionalCritique`` 등 가용 테이블을 best-effort 로 조회하며,
DB 실패 또는 데이터 없음 시 0.7 폴백.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from hwarang_api.knowledge.llm import _chat

logger = logging.getLogger(__name__)


_PREDICT_SYSTEM = (
    "너는 사실 검증 보조자다. 주어진 답변이 사실일 가능성을 0.0~1.0 사이 숫자로만 답하라. "
    "다른 말 금지. 예: 0.83"
)

_DEFAULT_HISTORICAL = 0.7


def _parse_float(text: str) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"([0-9]*\.?[0-9]+)", text.strip())
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    if v != v:  # NaN
        return None
    return max(0.0, min(1.0, v))


def _suggestion_for(calibrated: float) -> str:
    if calibrated < 0.4:
        return "출처 검색 필요"
    if calibrated <= 0.7:
        return "추가 검증 권장"
    return "신뢰 가능"


class ConfidenceCalibrator:
    """답변 신뢰도 재보정기."""

    def __init__(self, default_historical: float = _DEFAULT_HISTORICAL) -> None:
        self.default_historical = default_historical

    async def predict_correctness(self, question: str, answer: str) -> float:
        """LLM 이 평가하는 raw 사실가능성 (0~1)."""
        prompt = (
            "다음 답변이 사실일 가능성을 0.0 ~ 1.0 숫자 한 개로만 답하라.\n\n"
            f"질문:\n{question.strip()[:3000]}\n\n"
            f"답변:\n{answer.strip()[:5000]}"
        )
        try:
            raw = await _chat(prompt, system=_PREDICT_SYSTEM, max_tokens=12)
        except Exception as exc:  # noqa: BLE001
            logger.warning("predict_correctness LLM 실패: %s", exc)
            return 0.5

        v = _parse_float(raw or "")
        return v if v is not None else 0.5

    async def historical_accuracy(self, domain: str) -> float:
        """도메인 별 과거 정확도.

        Prisma 에서 Constitutional 비판/분쟁 결과를 best-effort 로 집계한다.
        데이터 없거나 DB 실패 → ``default_historical`` (0.7).
        """
        domain_clean = (domain or "").strip()
        if not domain_clean:
            return self.default_historical

        try:
            from hwarang_api.db import prisma  # type: ignore
        except Exception as exc:  # noqa: BLE001
            logger.warning("historical_accuracy: prisma import 실패: %s", exc)
            return self.default_historical

        # 1) CognitiveAudit 의 평균 (1 - hallucinationScore)
        try:
            audits = await prisma.cognitiveaudit.find_many(
                take=200,
                order={"auditedAt": "desc"},
            )
            scores: list[float] = []
            for a in audits or []:
                hs = getattr(a, "hallucinationScore", None)
                if hs is None:
                    continue
                try:
                    hsf = float(hs)
                except (TypeError, ValueError):
                    continue
                scores.append(max(0.0, min(1.0, 1.0 - hsf)))
            if scores:
                return max(0.0, min(1.0, sum(scores) / len(scores)))
        except Exception as exc:  # noqa: BLE001
            logger.warning("historical_accuracy: cognitiveaudit 조회 실패: %s", exc)

        # 2) AgentReputation 평균 trustScore (도메인 무관 폴백 신호)
        try:
            reps = await prisma.agentreputation.find_many(take=100)
            ts = [
                float(getattr(r, "trustScore", 0.5))
                for r in reps or []
                if getattr(r, "trustScore", None) is not None
            ]
            if ts:
                return max(0.0, min(1.0, sum(ts) / len(ts)))
        except Exception as exc:  # noqa: BLE001
            logger.debug("historical_accuracy: agentreputation 폴백 실패: %s", exc)

        return self.default_historical

    async def calibrated_confidence(
        self, question: str, answer: str, domain: str
    ) -> dict:
        """raw × historical → calibrated + suggestion."""
        raw = await self.predict_correctness(question, answer)
        hist = await self.historical_accuracy(domain)
        calibrated = max(0.0, min(1.0, raw * hist))
        return {
            "raw_confidence": raw,
            "historical_accuracy": hist,
            "calibrated": calibrated,
            "suggestion": _suggestion_for(calibrated),
            "domain": domain,
        }


__all__ = ["ConfidenceCalibrator"]
