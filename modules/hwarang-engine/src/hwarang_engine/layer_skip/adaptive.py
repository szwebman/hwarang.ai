"""Layer-Skip Engine — 화랑 독자 핵심.

복잡도 score 에 따라 model layers 동적 선택.
실제 구현은 PyTorch model.layers[:n] forward 로 대체 가능.
현재는 plan / interface 만 정의.

복잡도 score: prompt embedding + classifier head (별도 학습).
- Easy (score < 0.3): 16 layers — 간단한 한국어 인사, FAQ
- Medium (0.3~0.6): 32 layers — 일반 코딩, 요약
- Complex (>0.6): 64 layers — 복잡 추론, 법률, 의료
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class LayerSkipPolicy:
    easy_layers: int = 16
    medium_layers: int = 32
    complex_layers: int = 64

    def select_layers(self, complexity: float) -> int:
        if complexity < 0.3:
            return self.easy_layers
        elif complexity < 0.6:
            return self.medium_layers
        return self.complex_layers


class LayerSkipEngine:
    """현재는 stub. 실제 구현은 vLLM fork 단계에서."""

    def __init__(self, model, policy: Optional[LayerSkipPolicy] = None):
        self.model = model
        self.policy = policy or LayerSkipPolicy()

    def estimate_complexity(self, input_ids) -> float:
        """prompt 복잡도 추정. Phase 4.2 에서 classifier head 학습."""
        # TODO Phase 4.2: 별도 학습된 classifier 사용
        return 0.5

    def forward(self, input_ids, complexity: Optional[float] = None):
        if complexity is None:
            complexity = self.estimate_complexity(input_ids)
        n = self.policy.select_layers(complexity)
        # TODO Phase 4.2: 실제 model.layers[:n] forward 로 dispatch
        raise NotImplementedError(
            f"Layer-skip forward (n={n}) — 실 구현은 Phase 4.2"
        )
