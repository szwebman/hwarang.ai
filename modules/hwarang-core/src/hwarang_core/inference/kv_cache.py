"""KV Cache management for efficient autoregressive generation."""

from __future__ import annotations

import torch


class KVCache:
    """Pre-allocated KV cache for efficient inference.

    Instead of dynamically growing lists of tensors,
    pre-allocates a fixed-size cache and tracks the current position.
    """

    def __init__(
        self,
        num_layers: int,
        num_kv_heads: int,
        head_dim: int,
        max_seq_len: int,
        batch_size: int = 1,
        dtype: torch.dtype = torch.bfloat16,
        device: torch.device = torch.device("cpu"),
    ):
        self.num_layers = num_layers
        self.max_seq_len = max_seq_len
        self.current_len = 0

        # Pre-allocate: (num_layers, 2, batch, num_kv_heads, max_seq, head_dim)
        # 2 is for key and value
        self.cache = torch.zeros(
            num_layers, 2, batch_size, num_kv_heads, max_seq_len, head_dim,
            dtype=dtype, device=device,
        )

    def update(
        self,
        layer_idx: int,
        key: torch.Tensor,
        value: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Update cache for a layer and return the full cached K, V.

        Args:
            layer_idx: Which transformer layer.
            key: New key tensor (batch, num_kv_heads, new_seq, head_dim)
            value: New value tensor (batch, num_kv_heads, new_seq, head_dim)

        Returns:
            Full cached key and value up to current position.
        """
        new_len = key.shape[2]
        end_pos = self.current_len + new_len

        self.cache[layer_idx, 0, :, :, self.current_len:end_pos, :] = key
        self.cache[layer_idx, 1, :, :, self.current_len:end_pos, :] = value

        # Only update current_len after the last layer
        if layer_idx == self.num_layers - 1:
            self.current_len = end_pos

        return (
            self.cache[layer_idx, 0, :, :, :end_pos, :],
            self.cache[layer_idx, 1, :, :, :end_pos, :],
        )

    def reset(self) -> None:
        """Reset cache for a new sequence."""
        self.current_len = 0
        self.cache.zero_()

    @property
    def seq_len(self) -> int:
        """Current cached sequence length."""
        return self.current_len

    @property
    def memory_bytes(self) -> int:
        """Memory used by the cache in bytes."""
        return self.cache.nelement() * self.cache.element_size()

    def __repr__(self) -> str:
        mb = self.memory_bytes / (1024 * 1024)
        return (
            f"KVCache(layers={self.num_layers}, seq={self.current_len}/{self.max_seq_len}, "
            f"memory={mb:.1f}MB)"
        )
