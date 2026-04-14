"""Additional model heads for training objectives."""

from __future__ import annotations

import torch
import torch.nn as nn


class RewardHead(nn.Module):
    """Reward model head for RLHF training.

    Takes the last hidden state and produces a scalar reward.
    """

    def __init__(self, hidden_size: int):
        super().__init__()
        self.linear = nn.Linear(hidden_size, 1, bias=False)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """Compute reward from the last token's hidden state.

        Args:
            hidden_states: (batch, seq_len, hidden_size)

        Returns:
            Scalar rewards of shape (batch,)
        """
        # Use last token's hidden state
        last_hidden = hidden_states[:, -1, :]
        reward = self.linear(last_hidden).squeeze(-1)
        return reward
