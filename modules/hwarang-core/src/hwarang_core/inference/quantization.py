"""Post-training quantization for inference optimization."""

from __future__ import annotations

import logging
from pathlib import Path

import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


def quantize_dynamic_int8(model: nn.Module) -> nn.Module:
    """Apply dynamic INT8 quantization to Linear layers.

    This reduces model size ~4x and improves CPU inference speed.
    GPU inference typically uses other techniques (e.g., GPTQ, AWQ).

    Args:
        model: The model to quantize.

    Returns:
        Quantized model (operates on CPU).
    """
    logger.info("Applying dynamic INT8 quantization...")

    model_cpu = model.cpu()
    quantized = torch.quantization.quantize_dynamic(
        model_cpu,
        {nn.Linear},
        dtype=torch.qint8,
    )

    # Count size reduction
    orig_size = sum(p.numel() * p.element_size() for p in model.parameters())
    quant_size = sum(
        p.numel() * p.element_size()
        for p in quantized.parameters()
    )
    # Note: quantized tensors report different sizes through parameters()
    logger.info(f"Original model size: {orig_size / 1e6:.1f} MB")
    logger.info("Quantization complete (INT8)")

    return quantized


class WeightOnlyQuantizer:
    """Weight-only quantization for GPU inference.

    Quantizes weights to INT4/INT8 while keeping activations in float.
    Uses per-group quantization for better accuracy.
    """

    def __init__(self, bits: int = 8, group_size: int = 128):
        assert bits in (4, 8), f"Unsupported bit width: {bits}"
        self.bits = bits
        self.group_size = group_size
        self.max_val = 2 ** (bits - 1) - 1

    def quantize_tensor(self, weight: torch.Tensor) -> dict:
        """Quantize a weight tensor with per-group scaling.

        Args:
            weight: Float weight tensor of shape (out_features, in_features).

        Returns:
            Dict with quantized weight, scales, and zeros.
        """
        out_features, in_features = weight.shape

        # Pad to group_size boundary
        pad_size = (self.group_size - in_features % self.group_size) % self.group_size
        if pad_size > 0:
            weight = torch.nn.functional.pad(weight, (0, pad_size))

        # Reshape into groups
        weight_groups = weight.reshape(-1, self.group_size)

        # Compute per-group scale and zero point
        group_max = weight_groups.abs().max(dim=-1, keepdim=True).values
        scale = group_max / self.max_val
        scale = scale.clamp(min=1e-10)

        # Quantize
        quantized = torch.round(weight_groups / scale).clamp(-self.max_val, self.max_val)

        if self.bits == 4:
            quantized = quantized.to(torch.int8)
        else:
            quantized = quantized.to(torch.int8)

        return {
            "quantized": quantized,
            "scale": scale.squeeze(-1),
            "original_shape": (out_features, in_features),
        }

    def dequantize_tensor(self, qdata: dict) -> torch.Tensor:
        """Dequantize a weight tensor."""
        quantized = qdata["quantized"].float()
        scale = qdata["scale"].unsqueeze(-1)
        out_features, in_features = qdata["original_shape"]

        weight = quantized * scale
        weight = weight.reshape(-1, weight.shape[-1])

        # Remove padding
        return weight[:out_features, :in_features]
