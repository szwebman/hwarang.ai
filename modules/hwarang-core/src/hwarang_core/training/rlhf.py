"""RLHF Trainer using Proximal Policy Optimization (PPO).

This is a simplified PPO implementation for LLM alignment.
For most use cases, DPO (dpo.py) is simpler and recommended.
"""

from __future__ import annotations

import logging

import torch
import torch.nn as nn
import torch.nn.functional as F

from hwarang_core.model.heads import RewardHead

logger = logging.getLogger(__name__)


class PPOTrainer:
    """PPO trainer for RLHF.

    Components:
    - Policy model: The LLM being trained
    - Reference model: Frozen copy for KL penalty
    - Reward model: Scores completions (trained separately)
    - Value head: Estimates expected reward

    This is provided for completeness. DPO is preferred for most cases.
    """

    def __init__(
        self,
        policy_model: nn.Module,
        ref_model: nn.Module,
        reward_model: nn.Module,
        tokenizer,
        lr: float = 1e-6,
        clip_eps: float = 0.2,
        kl_coeff: float = 0.1,
        gamma: float = 1.0,
        lam: float = 0.95,
        device: torch.device = torch.device("cpu"),
    ):
        self.policy = policy_model.to(device)
        self.ref = ref_model.to(device)
        self.reward_model = reward_model.to(device)
        self.tokenizer = tokenizer
        self.device = device

        self.clip_eps = clip_eps
        self.kl_coeff = kl_coeff
        self.gamma = gamma
        self.lam = lam

        # Value head for advantage estimation
        hidden_size = policy_model.config.hidden_size
        self.value_head = nn.Linear(hidden_size, 1).to(device)

        # Freeze ref and reward models
        for p in self.ref.parameters():
            p.requires_grad = False
        for p in self.reward_model.parameters():
            p.requires_grad = False

        self.optimizer = torch.optim.AdamW(
            list(self.policy.parameters()) + list(self.value_head.parameters()),
            lr=lr,
        )

    def compute_advantages(
        self,
        rewards: torch.Tensor,
        values: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Compute GAE (Generalized Advantage Estimation).

        Args:
            rewards: Per-token rewards (batch, seq)
            values: Value estimates (batch, seq)

        Returns:
            advantages, returns
        """
        batch_size, seq_len = rewards.shape
        advantages = torch.zeros_like(rewards)
        last_gae = torch.zeros(batch_size, device=self.device)

        for t in reversed(range(seq_len)):
            next_value = values[:, t + 1] if t < seq_len - 1 else torch.zeros(batch_size, device=self.device)
            delta = rewards[:, t] + self.gamma * next_value - values[:, t]
            last_gae = delta + self.gamma * self.lam * last_gae
            advantages[:, t] = last_gae

        returns = advantages + values
        return advantages, returns

    def ppo_loss(
        self,
        old_log_probs: torch.Tensor,
        new_log_probs: torch.Tensor,
        advantages: torch.Tensor,
    ) -> torch.Tensor:
        """Compute clipped PPO policy loss."""
        ratio = torch.exp(new_log_probs - old_log_probs)
        clipped_ratio = torch.clamp(ratio, 1 - self.clip_eps, 1 + self.clip_eps)

        loss1 = ratio * advantages
        loss2 = clipped_ratio * advantages

        return -torch.min(loss1, loss2).mean()

    def kl_penalty(
        self,
        policy_logits: torch.Tensor,
        ref_logits: torch.Tensor,
    ) -> torch.Tensor:
        """Compute KL divergence penalty between policy and reference."""
        policy_probs = F.softmax(policy_logits, dim=-1)
        ref_probs = F.softmax(ref_logits, dim=-1)

        kl = (policy_probs * (policy_probs.log() - ref_probs.log())).sum(dim=-1)
        return kl.mean()
