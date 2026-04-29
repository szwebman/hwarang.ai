"""Multi-MoE Router — Layer 7.

도메인별 LoRA 5+ 동시 로드.
토큰 단위 routing (TACS 도메인 신호 입력).
Top-2 expert activation. Load balancing loss.
HNTL (Hwarang Neural Turing Logic) 의 라우팅 정책 자료구조 사용.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Expert:
    name: str
    domain: str
    lora_slot: Optional[str] = None  # LoraHotSwapManager 의 slot name
    weight: float = 1.0


@dataclass
class RouterConfig:
    top_k: int = 2
    load_balance_alpha: float = 0.01
    domain_signal_dim: int = 32  # TACS domain embedding dim


class MultiMoERouter:
    """도메인 신호 + 토큰 임베딩 기반 라우팅. Phase 4.2 부터 실 dispatch."""

    def __init__(self, experts: Optional[list[Expert]] = None, config: Optional[RouterConfig] = None):
        self.experts: list[Expert] = experts or []
        self.config = config or RouterConfig()
        self._load_counter: dict[str, int] = {}

    def add_expert(self, expert: Expert) -> None:
        self.experts.append(expert)
        self._load_counter[expert.name] = 0

    def route(self, token_embedding, domain_signal=None) -> list[tuple[Expert, float]]:
        """token 마다 top-k expert + gating weight 반환."""
        # TODO Phase 4.2:
        #   1. token_embedding @ gate_W → logits per expert
        #   2. domain_signal 으로 logits bias 추가
        #   3. top-k softmax → (expert, weight)
        #   4. _load_counter 증가, load balancing loss 누적
        raise NotImplementedError("MoE route — 실 구현은 Phase 4.2")

    def stats(self) -> dict[str, int]:
        return dict(self._load_counter)
