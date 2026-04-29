"""Backbone Loader — Layer 2.

베이스 모델 (Qwen, Llama, DeepSeek, EXAONE) 추상화.
AWQ/GPTQ/INT8 양자화 자동 감지 + 로드.
multi-GPU tensor parallelism + pipeline parallelism.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Quantization(str, Enum):
    NONE = "none"
    AWQ = "awq"
    GPTQ = "gptq"
    INT8 = "int8"
    FP8 = "fp8"


@dataclass
class BackboneConfig:
    model_name: str
    quantization: Quantization = Quantization.NONE
    tensor_parallel: int = 1
    pipeline_parallel: int = 1
    dtype: str = "bfloat16"
    trust_remote_code: bool = False
    extra: dict = field(default_factory=dict)


class BackboneLoader:
    """베이스 모델 로더. Phase 4.2 부터 실제 가중치 로드."""

    SUPPORTED = {"qwen", "llama", "deepseek", "exaone", "mistral"}

    def __init__(self, config: BackboneConfig):
        self.config = config
        self.model = None
        self._detect_quantization()

    def _detect_quantization(self) -> Quantization:
        # TODO Phase 4.2: HuggingFace config.json 에서 quantization_config 자동 감지
        return self.config.quantization

    def load(self):
        """모델 가중치 로드. 현재는 stub."""
        # TODO Phase 4.2: transformers + accelerate 로 분산 로드
        raise NotImplementedError("Backbone load — 실 구현은 Phase 4.2")

    def unload(self):
        self.model = None
