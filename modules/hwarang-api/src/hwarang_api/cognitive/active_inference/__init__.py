"""Active Inference (Phase 9.η) — Friston Free Energy Principle for LLM Agents.

Hwarang Cognitive Layer 의 통합 수학 프레임워크. 에이전트의 행동(action),
지각(perception), 학습(learning) 을 모두 ``예측 오차(prediction error) =
Free Energy proxy`` 의 최소화로 환원한다. LLM 에이전트에 맞춰 단순화된
형태:

* **Generative model**: LLM 이 다음 관찰/사용자 반응을 예측한다.
* **Recognition model**: 관찰 후 belief 를 갱신한다 (perception).
* **Action selection**: 예상 자유에너지 (expected free energy) 가
  최소가 되는 행동을 고른다. pragmatic value(목표 도달) +
  epistemic value(정보 획득) - risk(부작용) 합산 점수.
* **Precision weighting**: 각 belief 의 신뢰도(증거 수, 최신성).
* **Free Energy Monitor**: surprise + uncertainty + goal-distance 의
  합으로 현재 자유에너지를 추정하고, 임계 초과 시 행동을 권고한다.

본 패키지는 NumPy/Torch 가 필요 없다. LLM 호출 (
:func:`hwarang_api.knowledge.llm._chat`) + 메모리 캐시로 구현되어
HCL master_loop 에 가볍게 통합된다.
"""

from hwarang_api.cognitive.active_inference.free_energy import FreeEnergyMonitor
from hwarang_api.cognitive.active_inference.generative_model import (
    GenerativeModel,
    Prediction,
)
from hwarang_api.cognitive.active_inference.policy_selection import (
    ActionChoice,
    PolicySelector,
)
from hwarang_api.cognitive.active_inference.precision_weighting import (
    PrecisionWeighter,
)
from hwarang_api.cognitive.active_inference.prediction_error import (
    ErrorMetrics,
    PredictionErrorTracker,
)

__all__ = [
    "ActionChoice",
    "ErrorMetrics",
    "FreeEnergyMonitor",
    "GenerativeModel",
    "PolicySelector",
    "Prediction",
    "PrecisionWeighter",
    "PredictionErrorTracker",
]
