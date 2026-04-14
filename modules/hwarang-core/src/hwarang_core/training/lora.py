"""LoRA (Low-Rank Adaptation) 모듈.

도메인별 어댑터를 학습할 때 사용합니다.
풀 파인튜닝 대신 LoRA를 쓰면:
- 학습 가능 파라미터 99% 감소 (7B → 50MB)
- 학습 시간 5~10배 단축
- 한 베이스 모델에 여러 도메인 어댑터 동시 로드 가능

논문: https://arxiv.org/abs/2106.09685
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class LoRAConfig:
    """LoRA 학습 설정."""

    # LoRA 하이퍼파라미터
    r: int = 16                  # 랭크 (낮을수록 작고 빠름, 일반적으로 8~64)
    alpha: int = 32              # 스케일 (보통 r의 2배)
    dropout: float = 0.05

    # 어떤 레이어에 적용할지
    target_modules: list[str] = None  # None이면 모든 Linear

    # 베이스 모델 동결 여부
    freeze_base: bool = True

    def __post_init__(self):
        if self.target_modules is None:
            # LLaMA-family 기본: Q, K, V, O 프로젝션
            self.target_modules = ["q_proj", "k_proj", "v_proj", "o_proj"]


class LoRALayer(nn.Module):
    """LoRA 어댑터 레이어.

    원본 Linear 레이어를 감싸서 저차원 행렬 두 개(A, B)로 가중치 변화를 학습.

    원본:    y = x @ W
    LoRA:    y = x @ W + (x @ A @ B) * (alpha / r)

    학습 시: A, B만 업데이트, W는 동결
    """

    def __init__(
        self,
        base_layer: nn.Linear,
        r: int = 16,
        alpha: int = 32,
        dropout: float = 0.0,
    ):
        super().__init__()
        self.base_layer = base_layer
        self.r = r
        self.alpha = alpha
        self.scaling = alpha / r

        in_features = base_layer.in_features
        out_features = base_layer.out_features

        # LoRA A: (in_features, r) - 가우시안 초기화
        self.lora_A = nn.Parameter(torch.zeros(in_features, r))
        nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))

        # LoRA B: (r, out_features) - 0 초기화 (학습 시작 시 영향 없음)
        self.lora_B = nn.Parameter(torch.zeros(r, out_features))

        # Dropout
        self.lora_dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()

        # 베이스 레이어 동결
        for p in self.base_layer.parameters():
            p.requires_grad = False

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # 원본 출력
        result = self.base_layer(x)

        # LoRA 추가
        lora_x = self.lora_dropout(x)
        lora_out = (lora_x @ self.lora_A) @ self.lora_B
        result = result + lora_out * self.scaling

        return result

    def merge(self) -> nn.Linear:
        """LoRA 가중치를 베이스 모델에 병합 (추론 속도 ↑)."""
        merged_weight = self.base_layer.weight.data.clone()
        delta = (self.lora_A @ self.lora_B).T * self.scaling
        merged_weight += delta

        new_layer = nn.Linear(
            self.base_layer.in_features,
            self.base_layer.out_features,
            bias=self.base_layer.bias is not None,
        )
        new_layer.weight.data = merged_weight
        if self.base_layer.bias is not None:
            new_layer.bias.data = self.base_layer.bias.data.clone()
        return new_layer


def apply_lora_to_model(
    model: nn.Module,
    config: LoRAConfig,
) -> tuple[nn.Module, int]:
    """모델에 LoRA를 적용.

    Args:
        model: 베이스 모델
        config: LoRA 설정

    Returns:
        (LoRA 적용된 모델, 학습 가능 파라미터 수)
    """
    # 1. 모든 파라미터 동결
    if config.freeze_base:
        for p in model.parameters():
            p.requires_grad = False

    # 2. 타겟 모듈을 LoRA 레이어로 교체
    target_modules = config.target_modules
    replaced_count = 0

    for name, module in model.named_modules():
        # 부모 모듈 찾기
        for target in target_modules:
            if name.endswith(target):
                # nn.Linear인지 확인
                if isinstance(module, nn.Linear):
                    # LoRA 레이어로 교체
                    parent_name = ".".join(name.split(".")[:-1])
                    child_name = name.split(".")[-1]

                    parent = model
                    if parent_name:
                        for part in parent_name.split("."):
                            parent = getattr(parent, part)

                    lora_layer = LoRALayer(
                        base_layer=module,
                        r=config.r,
                        alpha=config.alpha,
                        dropout=config.dropout,
                    )
                    setattr(parent, child_name, lora_layer)
                    replaced_count += 1
                break

    # 3. 학습 가능 파라미터 수 계산
    trainable_params = sum(
        p.numel() for p in model.parameters() if p.requires_grad
    )
    total_params = sum(p.numel() for p in model.parameters())

    print(f"LoRA 적용 완료:")
    print(f"  교체된 레이어: {replaced_count}")
    print(f"  학습 가능 파라미터: {trainable_params:,} ({trainable_params/1e6:.2f}M)")
    print(f"  전체 파라미터: {total_params:,} ({total_params/1e9:.2f}B)")
    print(f"  학습 비율: {trainable_params/total_params*100:.4f}%")

    return model, trainable_params


def save_lora_weights(model: nn.Module, save_path: str):
    """LoRA 가중치만 저장 (작은 파일)."""
    lora_state = {}
    for name, param in model.named_parameters():
        if "lora_A" in name or "lora_B" in name:
            lora_state[name] = param.data.cpu()

    torch.save(lora_state, save_path)
    print(f"LoRA 가중치 저장: {save_path}")
    print(f"  파일 크기: {sum(t.numel() * t.element_size() for t in lora_state.values()) / 1e6:.1f}MB")


def load_lora_weights(model: nn.Module, load_path: str):
    """LoRA 가중치 로드."""
    lora_state = torch.load(load_path, map_location="cpu", weights_only=True)
    model_state = model.state_dict()

    loaded = 0
    for name, param in lora_state.items():
        if name in model_state:
            model_state[name].copy_(param)
            loaded += 1

    print(f"LoRA 가중치 로드: {loaded}개 텐서")
