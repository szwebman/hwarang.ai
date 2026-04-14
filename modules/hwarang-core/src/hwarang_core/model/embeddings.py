"""Token embeddings for the Hwarang model."""

from __future__ import annotations

import torch
import torch.nn as nn


class HwarangEmbeddings(nn.Module):
    """Token embedding layer.

    RoPE handles positional encoding, so this only needs token embeddings.
    """

    def __init__(self, vocab_size: int, hidden_size: int, pad_token_id: int = 0):
        super().__init__()
        self.token_embedding = nn.Embedding(vocab_size, hidden_size, padding_idx=pad_token_id)

    def forward(self, input_ids: torch.LongTensor) -> torch.Tensor:
        return self.token_embedding(input_ids)
