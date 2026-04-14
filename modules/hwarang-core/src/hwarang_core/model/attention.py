"""Grouped Query Attention with Rotary Position Embeddings (RoPE)."""

from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F


def precompute_rope_frequencies(
    head_dim: int,
    max_seq_len: int,
    theta: float = 10000.0,
    device: torch.device | None = None,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Precompute cos and sin for RoPE.

    Returns:
        cos, sin tensors of shape (max_seq_len, head_dim)
    """
    freqs = 1.0 / (theta ** (torch.arange(0, head_dim, 2, device=device).float() / head_dim))
    positions = torch.arange(max_seq_len, device=device).float()
    angles = torch.outer(positions, freqs)  # (seq_len, head_dim/2)
    # Duplicate for pairs: [cos0, cos0, cos1, cos1, ...]
    cos = torch.cos(angles).repeat(1, 2)  # (seq_len, head_dim)
    sin = torch.sin(angles).repeat(1, 2)  # (seq_len, head_dim)
    return cos, sin


def apply_rope(
    x: torch.Tensor,
    cos: torch.Tensor,
    sin: torch.Tensor,
    position_ids: torch.Tensor | None = None,
) -> torch.Tensor:
    """Apply rotary position embeddings to input tensor.

    Args:
        x: Input tensor of shape (batch, num_heads, seq_len, head_dim)
        cos: Cosine frequencies (max_seq_len, head_dim)
        sin: Sine frequencies (max_seq_len, head_dim)
        position_ids: Optional position indices (batch, seq_len)

    Returns:
        Tensor with RoPE applied, same shape as input.
    """
    seq_len = x.shape[2]

    if position_ids is not None:
        cos = cos[position_ids].unsqueeze(1)  # (batch, 1, seq_len, head_dim)
        sin = sin[position_ids].unsqueeze(1)
    else:
        cos = cos[:seq_len].unsqueeze(0).unsqueeze(0)  # (1, 1, seq_len, head_dim)
        sin = sin[:seq_len].unsqueeze(0).unsqueeze(0)

    # Rotate pairs: [x0, x1, x2, x3, ...] -> [-x1, x0, -x3, x2, ...]
    x_rotated = torch.stack([-x[..., 1::2], x[..., ::2]], dim=-1).flatten(-2)
    return x * cos + x_rotated * sin


class GroupedQueryAttention(nn.Module):
    """Multi-head attention with Grouped Query Attention (GQA) and RoPE.

    GQA uses fewer key-value heads than query heads, reducing KV cache memory
    while maintaining model quality.
    """

    def __init__(
        self,
        hidden_size: int,
        num_attention_heads: int,
        num_key_value_heads: int,
        head_dim: int,
        max_position_embeddings: int = 4096,
        rope_theta: float = 10000.0,
        attention_dropout: float = 0.0,
    ):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_heads = num_attention_heads
        self.num_kv_heads = num_key_value_heads
        self.head_dim = head_dim
        self.num_kv_groups = num_attention_heads // num_key_value_heads

        # Q/K/V projections
        self.q_proj = nn.Linear(hidden_size, num_attention_heads * head_dim, bias=False)
        self.k_proj = nn.Linear(hidden_size, num_key_value_heads * head_dim, bias=False)
        self.v_proj = nn.Linear(hidden_size, num_key_value_heads * head_dim, bias=False)
        self.o_proj = nn.Linear(num_attention_heads * head_dim, hidden_size, bias=False)

        self.attention_dropout = attention_dropout

        # Precompute RoPE frequencies
        cos, sin = precompute_rope_frequencies(
            head_dim, max_position_embeddings, rope_theta
        )
        self.register_buffer("rope_cos", cos, persistent=False)
        self.register_buffer("rope_sin", sin, persistent=False)

    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: torch.Tensor | None = None,
        position_ids: torch.Tensor | None = None,
        past_key_value: tuple[torch.Tensor, torch.Tensor] | None = None,
        use_cache: bool = False,
    ) -> tuple[torch.Tensor, tuple[torch.Tensor, torch.Tensor] | None]:
        batch_size, seq_len, _ = hidden_states.shape

        # Project Q, K, V
        q = self.q_proj(hidden_states)
        k = self.k_proj(hidden_states)
        v = self.v_proj(hidden_states)

        # Reshape: (batch, seq, num_heads * head_dim) -> (batch, num_heads, seq, head_dim)
        q = q.view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        k = k.view(batch_size, seq_len, self.num_kv_heads, self.head_dim).transpose(1, 2)
        v = v.view(batch_size, seq_len, self.num_kv_heads, self.head_dim).transpose(1, 2)

        # Apply RoPE to Q and K
        q = apply_rope(q, self.rope_cos, self.rope_sin, position_ids)
        k = apply_rope(k, self.rope_cos, self.rope_sin, position_ids)

        # KV Cache
        if past_key_value is not None:
            past_k, past_v = past_key_value
            k = torch.cat([past_k, k], dim=2)
            v = torch.cat([past_v, v], dim=2)

        new_cache = (k, v) if use_cache else None

        # Expand KV heads to match Q heads for GQA
        if self.num_kv_groups > 1:
            k = k.unsqueeze(2).expand(-1, -1, self.num_kv_groups, -1, -1)
            k = k.reshape(batch_size, self.num_heads, -1, self.head_dim)
            v = v.unsqueeze(2).expand(-1, -1, self.num_kv_groups, -1, -1)
            v = v.reshape(batch_size, self.num_heads, -1, self.head_dim)

        # Scaled dot-product attention
        scale = 1.0 / math.sqrt(self.head_dim)
        attn_weights = torch.matmul(q, k.transpose(-2, -1)) * scale

        # Apply causal mask
        if attention_mask is not None:
            attn_weights = attn_weights + attention_mask

        attn_weights = F.softmax(attn_weights, dim=-1, dtype=torch.float32).to(q.dtype)

        if self.training and self.attention_dropout > 0:
            attn_weights = F.dropout(attn_weights, p=self.attention_dropout)

        attn_output = torch.matmul(attn_weights, v)

        # Reshape back: (batch, num_heads, seq, head_dim) -> (batch, seq, hidden_size)
        attn_output = attn_output.transpose(1, 2).contiguous()
        attn_output = attn_output.view(batch_size, seq_len, -1)
        attn_output = self.o_proj(attn_output)

        return attn_output, new_cache
