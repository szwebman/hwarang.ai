"""Direct Preference Optimization (DPO) Trainer.

Implements DPO loss for alignment training without a reward model.
Reference: https://arxiv.org/abs/2305.18290
"""

from __future__ import annotations

import copy

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset

from hwarang_core.training.trainer import HwarangTrainer, TrainingConfig


class DPOTrainer(HwarangTrainer):
    """DPO trainer for preference alignment."""

    def __init__(
        self,
        model: nn.Module,
        config: TrainingConfig,
        train_dataset: Dataset,
        eval_dataset: Dataset | None = None,
        collator=None,
        beta: float = 0.1,
    ):
        super().__init__(model, config, train_dataset, eval_dataset, collator)
        self.beta = beta

        # Create frozen reference model
        self.ref_model = copy.deepcopy(model)
        self.ref_model.eval()
        for param in self.ref_model.parameters():
            param.requires_grad = False
        self.ref_model.to(self.device)

    def _get_log_probs(
        self,
        model: nn.Module,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        prompt_length: int,
    ) -> torch.Tensor:
        """Compute per-token log probabilities for the response portion."""
        with torch.amp.autocast(device_type=self.device.type, dtype=self.dtype):
            output = model(input_ids=input_ids, attention_mask=attention_mask)

        logits = output.logits  # (batch, seq, vocab)

        # Shift logits and labels for next-token prediction
        shift_logits = logits[:, :-1, :]
        shift_labels = input_ids[:, 1:]

        log_probs = F.log_softmax(shift_logits, dim=-1)
        token_log_probs = log_probs.gather(-1, shift_labels.unsqueeze(-1)).squeeze(-1)

        # Mask: only count response tokens (after prompt)
        response_mask = torch.zeros_like(token_log_probs)
        response_mask[:, prompt_length - 1 :] = 1.0
        if attention_mask is not None:
            response_mask = response_mask * attention_mask[:, 1:]

        # Sum log probs over response tokens
        return (token_log_probs * response_mask).sum(dim=-1)

    def compute_loss(self, batch: dict[str, torch.Tensor]) -> torch.Tensor:
        """Compute DPO loss.

        loss = -log(sigma(beta * (log_pi_chosen - log_pi_rejected
                                   - log_ref_chosen + log_ref_rejected)))
        """
        batch = {k: v.to(self.device) for k, v in batch.items()}

        chosen_ids = batch["chosen_input_ids"]
        chosen_mask = batch["chosen_attention_mask"]
        rejected_ids = batch["rejected_input_ids"]
        rejected_mask = batch["rejected_attention_mask"]
        prompt_lengths = batch["prompt_lengths"]

        # Use first prompt length (same for all in batch)
        prompt_len = prompt_lengths[0].item()

        # Policy model log probs
        pi_chosen = self._get_log_probs(self.model, chosen_ids, chosen_mask, prompt_len)
        pi_rejected = self._get_log_probs(self.model, rejected_ids, rejected_mask, prompt_len)

        # Reference model log probs
        with torch.no_grad():
            ref_chosen = self._get_log_probs(self.ref_model, chosen_ids, chosen_mask, prompt_len)
            ref_rejected = self._get_log_probs(
                self.ref_model, rejected_ids, rejected_mask, prompt_len
            )

        # DPO loss
        logits = self.beta * (
            (pi_chosen - ref_chosen) - (pi_rejected - ref_rejected)
        )
        loss = -F.logsigmoid(logits).mean()

        return loss
