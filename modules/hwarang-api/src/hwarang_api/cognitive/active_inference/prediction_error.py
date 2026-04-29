"""Prediction Error Tracker — 예측 vs 실제 일치도(Surprise) 추적.

Free Energy Principle 의 핵심: prediction error 가 곧 ``surprise`` 이며,
누적된 surprise 는 generative model 이 갱신되어야 한다는 신호다.

본 모듈은 :class:`Prediction` 과 실제 관찰을 받아 LLM-as-judge 로 일치도
점수를 산출하고 최근 N 개 surprise 의 이동평균을 제공한다.

TODO: 메모리 deque 는 in-memory. 영속화는 Prisma ``PredictionError`` 테이블.
"""

from __future__ import annotations

import json
import logging
import re
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from hwarang_api.cognitive.active_inference.generative_model import Prediction
from hwarang_api.knowledge.llm import _chat

logger = logging.getLogger(__name__)


@dataclass
class ErrorMetrics:
    """LLM judge 가 매긴 일치도 메트릭."""

    match_score: float  # 0~1, 1 = 완벽 일치
    surprise_level: float  # 0~1, 1 = 매우 놀람 (= 1 - match 와 비슷)
    mismatch_dimensions: list[str] = field(default_factory=list)
    raw: str = ""
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except Exception:
        return None


def _to_float(v: Any, default: float = 0.5) -> float:
    try:
        f = float(v)
        return max(0.0, min(1.0, f))
    except Exception:
        return default


class PredictionErrorTracker:
    """예측 오차 추적기. 최근 surprise 슬라이딩 윈도우 보유."""

    SURPRISE_THRESHOLD = 0.7

    def __init__(self, window: int = 50) -> None:
        # prediction_id -> {"actual": str, "metrics": ErrorMetrics}
        self._records: dict[str, dict[str, Any]] = {}
        self._surprise_history: deque[float] = deque(maxlen=window)

    # --------------------------------------------------------------- record
    def record_actual(self, prediction_id: str, actual_observation: str) -> None:
        """예측 ID 에 대응하는 실제 관찰을 기록 (compute_error 와 별개로
        보관). compute_error 는 두 인자를 직접 받아 동작한다."""
        self._records[prediction_id] = {
            "actual": actual_observation,
            "metrics": None,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_record(self, prediction_id: str) -> dict[str, Any] | None:
        return self._records.get(prediction_id)

    # -------------------------------------------------------------- compute
    async def compute_error(
        self, predicted: Prediction, actual: str
    ) -> ErrorMetrics:
        """LLM-as-judge: 예측 vs 실제 일치도 평가."""
        system = (
            "너는 예측 평가관이다. 모델 예측과 실제 관찰을 받아 일치도를 "
            "0~1 사이 점수로 평가한다."
        )
        prompt = (
            f"예측: {predicted.predicted_text}\n"
            f"예측 intent: {predicted.predicted_intent}\n"
            f"예측 sentiment: {predicted.predicted_sentiment}\n"
            f"실제: {actual}\n"
            "0~1 점수로 일치도 평가. JSON 만 응답: "
            "{\"match_score\": float, "
            "\"mismatch_dimensions\": [<불일치 차원 문자열들>], "
            "\"surprise_level\": float}"
        )
        raw = await _chat(prompt, system=system, max_tokens=240)
        data = _safe_json(raw)
        if data is None:
            retry_system = system + " 반드시 JSON 객체만 응답."
            raw = await _chat(prompt, system=retry_system, max_tokens=240)
            data = _safe_json(raw)
        if data is None:
            # fallback: zero-info
            metrics = ErrorMetrics(
                match_score=0.5,
                surprise_level=0.5,
                mismatch_dimensions=["llm_judge_failed"],
                raw=raw or "",
            )
        else:
            mm = data.get("mismatch_dimensions") or []
            if not isinstance(mm, list):
                mm = [str(mm)]
            metrics = ErrorMetrics(
                match_score=_to_float(data.get("match_score", 0.5)),
                surprise_level=_to_float(data.get("surprise_level", 0.5)),
                mismatch_dimensions=[str(x) for x in mm][:8],
                raw=raw or "",
            )

        # 캐시 업데이트
        rec = self._records.setdefault(
            predicted.prediction_id,
            {
                "actual": actual,
                "metrics": None,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        rec["actual"] = actual
        rec["metrics"] = metrics
        self._surprise_history.append(metrics.surprise_level)
        return metrics

    # ---------------------------------------------------------- aggregation
    def aggregate_recent_surprise(self, window: int = 20) -> float:
        """최근 N 개 surprise 의 평균. 데이터 부족 시 0.0."""
        if not self._surprise_history:
            return 0.0
        recent = list(self._surprise_history)[-max(1, window) :]
        return sum(recent) / len(recent)

    def surprise_threshold_breached(self, window: int = 20) -> bool:
        """최근 평균 surprise 가 임계 (0.7) 를 초과하면 True.
        => world model 갱신이 필요하다는 신호."""
        return self.aggregate_recent_surprise(window) > self.SURPRISE_THRESHOLD

    def history_snapshot(self) -> list[float]:
        return list(self._surprise_history)


__all__ = ["ErrorMetrics", "PredictionErrorTracker"]
