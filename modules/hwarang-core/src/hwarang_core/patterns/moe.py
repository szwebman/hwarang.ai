"""Mixture of Experts (MoE) - 전문가 혼합 모델.

모든 파라미터를 매번 사용하는 대신,
입력에 따라 일부 전문가(Expert)만 활성화합니다.

효과:
- 전체 30B 파라미터이지만 추론 시 8B만 활성화
- = 30B 품질 + 8B 속도

구조:
  FFN 레이어를 N개의 Expert로 분할
  Router가 각 토큰마다 top-K Expert 선택
  선택된 Expert만 계산 → 나머지는 건너뜀

예시: Mixtral 8x7B = 8개의 7B Expert, 매번 2개만 활성화 = 총 47B 중 13B만 사용
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
import logging

logger = logging.getLogger(__name__)


class MoERouter(nn.Module):
    """토큰별 Expert 선택 라우터.

    각 토큰의 hidden state를 보고 어떤 Expert를 활성화할지 결정합니다.
    """

    def __init__(
        self,
        hidden_size: int,
        num_experts: int = 8,
        top_k: int = 2,
        noise_std: float = 0.1,  # 탐색을 위한 노이즈
    ):
        super().__init__()
        self.num_experts = num_experts
        self.top_k = top_k
        self.noise_std = noise_std
        self.gate = nn.Linear(hidden_size, num_experts, bias=False)

    def forward(self, hidden_states: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Expert 선택.

        Args:
            hidden_states: (batch, seq_len, hidden_size)

        Returns:
            router_weights: (batch, seq_len, top_k) - 선택된 Expert 가중치
            selected_experts: (batch, seq_len, top_k) - 선택된 Expert 인덱스
        """
        # 라우터 로짓 계산
        logits = self.gate(hidden_states)  # (batch, seq, num_experts)

        # 학습 시 노이즈 추가 (탐색 유도)
        if self.training and self.noise_std > 0:
            noise = torch.randn_like(logits) * self.noise_std
            logits = logits + noise

        # Top-K 선택
        weights, indices = torch.topk(logits, self.top_k, dim=-1)
        weights = F.softmax(weights, dim=-1)

        return weights, indices


class MoELayer(nn.Module):
    """Mixture of Experts FFN 레이어.

    기존 SwiGLUFFN 대신 사용합니다.
    N개의 Expert(각각 SwiGLUFFN) 중 top-K만 활성화.
    """

    def __init__(
        self,
        hidden_size: int,
        intermediate_size: int,
        num_experts: int = 8,
        top_k: int = 2,
    ):
        super().__init__()
        self.num_experts = num_experts
        self.top_k = top_k

        # 라우터
        self.router = MoERouter(hidden_size, num_experts, top_k)

        # N개의 Expert (각각 독립적인 FFN)
        from hwarang_core.model.layers import SwiGLUFFN
        self.experts = nn.ModuleList([
            SwiGLUFFN(hidden_size, intermediate_size)
            for _ in range(num_experts)
        ])

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """MoE forward pass.

        각 토큰마다 top-K Expert만 활성화하여 계산.
        """
        batch, seq_len, hidden_size = hidden_states.shape

        # 라우터가 Expert 선택
        weights, indices = self.router(hidden_states)
        # weights: (batch, seq, top_k), indices: (batch, seq, top_k)

        # 출력 초기화
        output = torch.zeros_like(hidden_states)

        # 각 Expert에 대해
        for expert_idx in range(self.num_experts):
            # 이 Expert가 선택된 위치 찾기
            mask = (indices == expert_idx).any(dim=-1)  # (batch, seq)

            if not mask.any():
                continue

            # 선택된 토큰만 추출
            expert_input = hidden_states[mask]  # (num_selected, hidden)

            # Expert 계산
            expert_output = self.experts[expert_idx](expert_input)

            # 가중치 적용
            for k in range(self.top_k):
                k_mask = indices[..., k] == expert_idx
                combined_mask = mask & k_mask
                if combined_mask.any():
                    w = weights[..., k][combined_mask].unsqueeze(-1)
                    output[combined_mask] += expert_output[:combined_mask.sum()] * w

        return output

    @property
    def total_params(self) -> int:
        return sum(p.numel() for p in self.parameters())

    @property
    def active_params(self) -> int:
        """실제 활성화되는 파라미터 수 (추론 시)."""
        single_expert = sum(p.numel() for p in self.experts[0].parameters())
        return single_expert * self.top_k + sum(p.numel() for p in self.router.parameters())
