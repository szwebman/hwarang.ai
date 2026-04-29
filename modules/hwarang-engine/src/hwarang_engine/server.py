"""HSEE Server — vLLM-호환 OpenAI API 서버 (얇은 wrapper).

Phase 4.0 / 4.1: vLLM 으로 위임.
Phase 4.2 ~ : 7 layer 직접 호출.

OpenAI 호환 엔드포인트:
- POST /v1/chat/completions
- POST /v1/completions
- GET  /v1/models
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    backend: str = "vllm"  # "vllm" | "hsee" (Phase 4.2+)
    model: str = "Qwen/Qwen2.5-32B-Instruct"


class HSEEServer:
    """얇은 wrapper. 현재는 vLLM 으로 위임."""

    def __init__(self, config: Optional[ServerConfig] = None):
        self.config = config or ServerConfig()

    def start(self) -> None:
        if self.config.backend == "vllm":
            # TODO Phase 4.0: 기존 vLLM serve 호출
            raise NotImplementedError(
                "Phase 4.0 의 vLLM 위임은 modules/hwarang-api 의 기존 서빙 사용"
            )
        else:
            # TODO Phase 4.2: 자체 7 layer 추론 루프 + FastAPI
            raise NotImplementedError("HSEE native backend — Phase 4.2")
