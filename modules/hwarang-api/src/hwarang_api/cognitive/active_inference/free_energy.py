"""Free Energy Monitor — surprise + uncertainty + goal-distance 통합.

Active Inference 의 자유에너지를 LLM 에이전트용으로 단순화::

    F ≈ surprise + 0.5 * uncertainty + 0.7 * goal_distance

* **surprise**:    :class:`PredictionErrorTracker` 의 최근 평균
* **uncertainty**: belief 들의 평균 (1 - precision)
* **goal_distance**: LLM 에 ``현재 상태가 목표에서 얼마나 떨어져 있는가`` 묻기

threshold 초과 시 행동 권고. 어느 항이 가장 크냐에 따라
``explore / exploit / consolidate`` 중 하나를 추천한다.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from hwarang_api.cognitive.active_inference.precision_weighting import (
    PrecisionWeighter,
)
from hwarang_api.cognitive.active_inference.prediction_error import (
    PredictionErrorTracker,
)
from hwarang_api.knowledge.llm import _chat

logger = logging.getLogger(__name__)


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


@dataclass
class _Belief:
    text: str
    evidence_count: int
    recency_days: int
    weight: float = 0.5
    added_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class FreeEnergyMonitor:
    """현재 자유에너지를 추적하고 행동 모드를 권고."""

    SURPRISE_W = 1.0
    UNCERTAINTY_W = 0.5
    GOAL_DISTANCE_W = 0.7

    def __init__(
        self,
        error_tracker: PredictionErrorTracker | None = None,
        weighter: PrecisionWeighter | None = None,
    ) -> None:
        self.error_tracker = error_tracker or PredictionErrorTracker()
        self.weighter = weighter or PrecisionWeighter()
        self._beliefs: list[_Belief] = []
        self._goal: str = ""
        self._current_state: str = ""

    # ---------------------------------------------------------- belief mgmt
    def register_belief(
        self, text: str, evidence_count: int = 1, recency_days: int = 0
    ) -> None:
        if not text.strip():
            return
        w = self.weighter.weight_belief(text, evidence_count, recency_days)
        self._beliefs.append(
            _Belief(
                text=text.strip(),
                evidence_count=int(evidence_count),
                recency_days=int(recency_days),
                weight=w,
            )
        )
        # cap memory footprint
        if len(self._beliefs) > 200:
            self._beliefs = self._beliefs[-200:]

    def set_goal(self, goal: str, current_state: str = "") -> None:
        self._goal = goal.strip()
        self._current_state = current_state.strip()

    def _avg_uncertainty(self) -> float:
        if not self._beliefs:
            return 0.5  # 정보 없음 → 중립
        avg_precision = sum(b.weight for b in self._beliefs) / len(self._beliefs)
        return max(0.0, min(1.0, 1.0 - avg_precision))

    # ----------------------------------------------------------- goal dist
    async def _llm_goal_distance(self) -> float:
        if not self._goal:
            return 0.5
        system = (
            "너는 목표 도달 평가관이다. 현재 상태와 목표를 보고 현재가 목표에서 "
            "얼마나 떨어져 있는지 0~1 로 답한다. 1 = 매우 멀다, 0 = 이미 도달."
        )
        prompt = (
            f"목표: {self._goal}\n"
            f"현재 상태: {self._current_state or '(미지정)'}\n"
            "JSON 만 응답: {\"goal_distance\": float}"
        )
        raw = await _chat(prompt, system=system, max_tokens=80)
        data = _safe_json(raw)
        if data is None:
            retry_system = system + " 반드시 JSON 객체만."
            raw = await _chat(prompt, system=retry_system, max_tokens=80)
            data = _safe_json(raw)
        if data is None:
            return 0.5
        return _to_float(data.get("goal_distance", 0.5))

    # -------------------------------------------------------- main metric
    async def current_free_energy(self) -> dict[str, Any]:
        surprise = self.error_tracker.aggregate_recent_surprise(window=20)
        uncertainty = self._avg_uncertainty()
        goal_distance = await self._llm_goal_distance()
        total = (
            self.SURPRISE_W * surprise
            + self.UNCERTAINTY_W * uncertainty
            + self.GOAL_DISTANCE_W * goal_distance
        )
        return {
            "surprise_level": round(surprise, 4),
            "belief_uncertainty": round(uncertainty, 4),
            "goal_distance": round(goal_distance, 4),
            "total": round(total, 4),
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    # --------------------------------------------------------- action hint
    async def should_act_to_reduce(self, threshold: float = 1.5) -> bool:
        fe = await self.current_free_energy()
        return float(fe["total"]) > threshold

    async def recommended_action_type(self) -> str:
        """가장 큰 항을 줄이는 방향으로 행동 모드 추천."""
        fe = await self.current_free_energy()
        components = {
            "explore": fe["surprise_level"],  # 큰 surprise → 새 정보로 탐색
            "consolidate": fe["belief_uncertainty"],  # 불확실 → 정리/검증
            "exploit": fe["goal_distance"],  # 목표 멀다 → 직접 행동
        }
        # 가장 큰 컴포넌트가 추천 모드
        return max(components.items(), key=lambda kv: kv[1])[0]

    # ----------------------------------------------------------- snapshots
    def beliefs_snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "text": b.text,
                "evidence_count": b.evidence_count,
                "recency_days": b.recency_days,
                "weight": round(b.weight, 4),
                "added_at": b.added_at,
            }
            for b in self._beliefs
        ]

    def goal_snapshot(self) -> dict[str, str]:
        return {"goal": self._goal, "current_state": self._current_state}


# ────────────────────────────────────────────────────────────────────────
# HCL master_loop 통합 힌트 (참고용 — master_loop.py 는 수정하지 않는다)
# ────────────────────────────────────────────────────────────────────────
# ``modules/hwarang-api/src/hwarang_api/cognitive/master_loop.py`` 의
# ``cognitive_cycle()`` 함수는 단계 4 (일일 액션 한도 체크) 와 단계 5
# (reason_about_state) 사이에서 다음 hook 을 추가하면 자연스럽다::
#
#     monitor = FreeEnergyMonitor(...)  # 싱글턴 또는 DI
#     if await monitor.should_act_to_reduce(threshold=1.5):
#         next_mode = await monitor.recommended_action_type()
#         # next_mode ∈ {explore, consolidate, exploit}
#         # → reason_about_state 프롬프트에 "현재 모드={next_mode}" 주입
#
# 이렇게 하면 자유에너지가 임계 초과일 때만 새 결정을 내리고, 그 외에는
# 사이클이 no-op 으로 마칠 수 있어 비용 절약이 가능하다.

__all__ = ["FreeEnergyMonitor"]
