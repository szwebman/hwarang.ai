"""HSD Speculative Decoding — Layer 6.

Draft model: Qwen 0.5B (CPU 가능, INT4).
Target model: Qwen 30B / DeepSeek V3 (GPU).
N-gram + lookup table 추가 (화랑 코퍼스 기반).
평균 2-3x 속도, 코드 생성 시 최대 5x.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SpeculativeConfig:
    draft_model_name: str = "Qwen/Qwen2-0.5B-Instruct"
    target_model_name: str = "Qwen/Qwen2.5-32B-Instruct"
    speculate_tokens: int = 5  # draft 가 한번에 제안하는 토큰 수
    use_ngram: bool = True
    ngram_max_n: int = 4


class SpeculativeDraftModel:
    """Draft 모델 + n-gram lookup. Phase 4.2 부터 실제 verify loop 구현."""

    def __init__(self, config: Optional[SpeculativeConfig] = None):
        self.config = config or SpeculativeConfig()
        self._draft = None  # Phase 4.2: HuggingFace AutoModelForCausalLM
        self._ngram_table: dict[tuple[int, ...], list[int]] = {}

    def propose(self, prefix_ids: list[int]) -> list[int]:
        """draft 모델 + n-gram 으로 토큰 시퀀스 제안."""
        # TODO Phase 4.2: 실제 draft.generate() 호출 + n-gram fallback
        raise NotImplementedError("Speculative propose — 실 구현은 Phase 4.2")

    def verify(self, target_logits, draft_ids: list[int]) -> int:
        """target 모델 logits 와 비교하여 accept count 반환."""
        # TODO Phase 4.2: rejection sampling
        raise NotImplementedError("Speculative verify — 실 구현은 Phase 4.2")

    def update_ngram(self, sequence: list[int]) -> None:
        """sliding window 로 n-gram 통계 갱신."""
        n = self.config.ngram_max_n
        for i in range(len(sequence) - n):
            key = tuple(sequence[i : i + n - 1])
            self._ngram_table.setdefault(key, []).append(sequence[i + n - 1])
