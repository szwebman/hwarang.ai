"""Supervised Fine-Tuning (SFT) Trainer."""

from __future__ import annotations

from hwarang_core.training.trainer import HwarangTrainer, TrainingConfig


class SFTTrainer(HwarangTrainer):
    """Trainer for supervised fine-tuning on instruction-response data.

    Uses the base trainer's loss computation with label masking
    (instruction tokens have label=-100, only response tokens contribute to loss).
    """

    pass  # SFT uses the same loss as pretraining (CE with label masking)
