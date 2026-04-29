"""Policy Selector — Expected Free Energy 최소화로 행동 선택.

Active Inference 의 행동 선택 규칙:

    π* = argmin_π  G(π)

여기서 G(π) = 기대 자유에너지 = -pragmatic - epistemic + risk.
LLM 단순화 버전:

    score(π) = pragmatic + 0.3 * epistemic - 0.5 * risk
    π* = argmax_π score(π)

각 후보 행동에 대해 :class:`GenerativeModel.predict_external_state` 로
예측을 만든 뒤 LLM 에 세 가지 평가(목표 도달 / 정보 획득 / 부작용 위험)
를 묻는다. 불확실성이 높을 때는 epistemic 쪽으로 기울도록
:meth:`explore_vs_exploit_balance` 가 정책 모드를 반환한다.

TODO: 후보 행동/점수 로그는 in-memory. 영속화는 Prisma ``ActionChoice``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from hwarang_api.cognitive.active_inference.generative_model import (
    GenerativeModel,
    Prediction,
)
from hwarang_api.knowledge.llm import _chat

logger = logging.getLogger(__name__)


@dataclass
class ActionChoice:
    """단일 행동의 expected free energy 분해 + 합성 점수."""

    action: str
    expected_pragmatic: float
    expected_epistemic: float
    expected_risk: float
    total_score: float
    reasoning: str
    predicted: Prediction | None = None
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.predicted is not None:
            d["predicted"] = self.predicted.to_dict()
        return d


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


class PolicySelector:
    """Expected free energy 기반 행동 선택기."""

    PRAGMATIC_W = 1.0
    EPISTEMIC_W = 0.3
    RISK_W = 0.5

    def __init__(
        self, generative_model: GenerativeModel | None = None
    ) -> None:
        self.generative = generative_model or GenerativeModel()
        self._history: list[ActionChoice] = []

    # ------------------------------------------------------------- evaluate
    async def _evaluate_candidate(
        self,
        situation: dict[str, Any],
        action: str,
        goal: str,
        prediction: Prediction,
    ) -> ActionChoice:
        system = (
            "너는 행동 평가관이다. 주어진 상황/목표/행동/예상 결과를 보고 "
            "세 가지 차원을 0~1 로 평가한다: pragmatic(목표 달성에 도움), "
            "epistemic(새 정보 획득), risk(예상치 못한 부작용 위험)."
        )
        sit_str = json.dumps(situation, ensure_ascii=False)[:1200]
        prompt = (
            f"목표: {goal}\n"
            f"상황: {sit_str}\n"
            f"행동: {action}\n"
            f"예상 결과: {prediction.predicted_text}\n"
            "JSON 만 응답: "
            "{\"pragmatic\": float, \"epistemic\": float, "
            "\"risk\": float, \"reasoning\": str}"
        )
        raw = await _chat(prompt, system=system, max_tokens=300)
        data = _safe_json(raw)
        if data is None:
            retry_system = system + " 반드시 JSON 객체만 응답."
            raw = await _chat(prompt, system=retry_system, max_tokens=300)
            data = _safe_json(raw)
        if data is None:
            data = {
                "pragmatic": 0.5,
                "epistemic": 0.5,
                "risk": 0.5,
                "reasoning": "(LLM judge 실패: 중립값 사용)",
            }

        prag = _to_float(data.get("pragmatic", 0.5))
        epis = _to_float(data.get("epistemic", 0.5))
        risk = _to_float(data.get("risk", 0.5))
        score = (
            self.PRAGMATIC_W * prag
            + self.EPISTEMIC_W * epis
            - self.RISK_W * risk
        )
        return ActionChoice(
            action=action,
            expected_pragmatic=prag,
            expected_epistemic=epis,
            expected_risk=risk,
            total_score=score,
            reasoning=str(data.get("reasoning", ""))[:500],
            predicted=prediction,
        )

    # --------------------------------------------------------------- select
    async def select_action(
        self,
        situation: dict[str, Any],
        candidate_actions: list[str],
        goal: str,
    ) -> ActionChoice:
        """모든 후보 행동을 평가하고 최고점 선택."""
        if not candidate_actions:
            raise ValueError("candidate_actions 는 비어 있을 수 없다.")

        domain = str(situation.get("domain", "general"))
        evaluated: list[ActionChoice] = []
        for action in candidate_actions:
            try:
                pred = await self.generative.predict_external_state(
                    domain=domain, action=action
                )
                choice = await self._evaluate_candidate(
                    situation=situation,
                    action=action,
                    goal=goal,
                    prediction=pred,
                )
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(
                    "후보 평가 실패 (action=%s): %s", action, e
                )
                choice = ActionChoice(
                    action=action,
                    expected_pragmatic=0.0,
                    expected_epistemic=0.0,
                    expected_risk=1.0,
                    total_score=-1.0,
                    reasoning=f"evaluation failed: {e}",
                    predicted=None,
                )
            evaluated.append(choice)

        # 최고점 선택. 동률은 입력 순서 유지.
        best = max(evaluated, key=lambda c: c.total_score)
        self._history.append(best)
        # 너무 길어지지 않게 잘라낸다
        if len(self._history) > 200:
            self._history = self._history[-200:]
        return best

    # --------------------------------------------------------- explore mode
    def explore_vs_exploit_balance(self, uncertainty_level: float) -> str:
        """uncertainty 수준으로 정책 모드 결정.

        * uncertainty >= 0.7 → ``explore`` (epistemic 우선)
        * uncertainty <= 0.3 → ``exploit`` (pragmatic 우선)
        * 그 사이 → ``balanced``
        """
        u = max(0.0, min(1.0, uncertainty_level))
        if u >= 0.7:
            return "explore"
        if u <= 0.3:
            return "exploit"
        return "balanced"

    def history_snapshot(self) -> list[ActionChoice]:
        return list(self._history)


__all__ = ["ActionChoice", "PolicySelector"]
