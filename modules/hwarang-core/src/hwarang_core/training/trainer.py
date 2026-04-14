"""Base trainer class for all training pipelines."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

logger = logging.getLogger(__name__)


@dataclass
class TrainingConfig:
    """Common training configuration."""

    # Optimization
    learning_rate: float = 3e-4
    weight_decay: float = 0.1
    max_grad_norm: float = 1.0
    adam_beta1: float = 0.9
    adam_beta2: float = 0.95
    adam_eps: float = 1e-8

    # Schedule
    warmup_steps: int = 1000
    max_steps: int = 100000
    lr_scheduler: str = "cosine"  # "cosine" or "linear"

    # Batching
    batch_size: int = 8
    gradient_accumulation_steps: int = 4
    num_workers: int = 4

    # Checkpointing
    save_steps: int = 1000
    eval_steps: int = 500
    log_steps: int = 10
    output_dir: str = "./checkpoints"

    # Hardware
    device: str = "auto"
    dtype: str = "bfloat16"  # "float32", "float16", "bfloat16"
    compile_model: bool = False

    def get_device(self) -> torch.device:
        if self.device == "auto":
            if torch.cuda.is_available():
                return torch.device("cuda")
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return torch.device("mps")
            return torch.device("cpu")
        return torch.device(self.device)

    def get_dtype(self) -> torch.dtype:
        return {"float32": torch.float32, "float16": torch.float16, "bfloat16": torch.bfloat16}[
            self.dtype
        ]


class HwarangTrainer:
    """Base trainer with common training logic."""

    def __init__(
        self,
        model: nn.Module,
        config: TrainingConfig,
        train_dataset: Dataset,
        eval_dataset: Dataset | None = None,
        collator=None,
    ):
        self.config = config
        self.device = config.get_device()
        self.dtype = config.get_dtype()

        self.model = model.to(self.device)
        if config.compile_model and hasattr(torch, "compile"):
            self.model = torch.compile(self.model)

        self.train_loader = DataLoader(
            train_dataset,
            batch_size=config.batch_size,
            shuffle=True,
            num_workers=config.num_workers,
            collate_fn=collator,
            pin_memory=True,
            drop_last=True,
        )
        self.eval_loader = None
        if eval_dataset is not None:
            self.eval_loader = DataLoader(
                eval_dataset,
                batch_size=config.batch_size,
                shuffle=False,
                num_workers=config.num_workers,
                collate_fn=collator,
                pin_memory=True,
            )

        self.optimizer = self._create_optimizer()
        self.scheduler = self._create_scheduler()

        self.global_step = 0
        self.best_eval_loss = float("inf")

    def _create_optimizer(self) -> torch.optim.Optimizer:
        """Create AdamW optimizer with weight decay groups."""
        no_decay = {"bias", "layernorm", "rmsnorm", "norm"}
        param_groups = [
            {
                "params": [
                    p
                    for n, p in self.model.named_parameters()
                    if p.requires_grad and not any(nd in n.lower() for nd in no_decay)
                ],
                "weight_decay": self.config.weight_decay,
            },
            {
                "params": [
                    p
                    for n, p in self.model.named_parameters()
                    if p.requires_grad and any(nd in n.lower() for nd in no_decay)
                ],
                "weight_decay": 0.0,
            },
        ]
        return torch.optim.AdamW(
            param_groups,
            lr=self.config.learning_rate,
            betas=(self.config.adam_beta1, self.config.adam_beta2),
            eps=self.config.adam_eps,
        )

    def _create_scheduler(self):
        """Create learning rate scheduler."""
        if self.config.lr_scheduler == "cosine":
            return torch.optim.lr_scheduler.CosineAnnealingLR(
                self.optimizer, T_max=self.config.max_steps, eta_min=self.config.learning_rate * 0.1
            )
        return torch.optim.lr_scheduler.LinearLR(
            self.optimizer, start_factor=1.0, end_factor=0.1, total_iters=self.config.max_steps
        )

    def _warmup_lr(self) -> None:
        """Apply linear warmup to learning rate."""
        if self.global_step < self.config.warmup_steps:
            warmup_factor = self.global_step / max(1, self.config.warmup_steps)
            for pg in self.optimizer.param_groups:
                pg["lr"] = self.config.learning_rate * warmup_factor

    def compute_loss(self, batch: dict[str, torch.Tensor]) -> torch.Tensor:
        """Compute training loss. Override in subclasses for custom objectives."""
        batch = {k: v.to(self.device) for k, v in batch.items()}
        with torch.amp.autocast(device_type=self.device.type, dtype=self.dtype):
            output = self.model(
                input_ids=batch["input_ids"],
                attention_mask=batch.get("attention_mask"),
                labels=batch.get("labels"),
            )
        return output.loss

    def train(self) -> dict:
        """Run the training loop."""
        logger.info(f"Starting training on {self.device} with dtype={self.dtype}")
        logger.info(f"Parameters: {self.model.num_parameters():,}")

        self.model.train()
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        scaler = torch.amp.GradScaler(enabled=(self.dtype == torch.float16))
        accumulation_loss = 0.0
        start_time = time.time()

        data_iter = iter(self.train_loader)

        for step in range(1, self.config.max_steps + 1):
            self.global_step = step
            self._warmup_lr()

            # Gradient accumulation
            self.optimizer.zero_grad()
            for micro_step in range(self.config.gradient_accumulation_steps):
                try:
                    batch = next(data_iter)
                except StopIteration:
                    data_iter = iter(self.train_loader)
                    batch = next(data_iter)

                loss = self.compute_loss(batch)
                loss = loss / self.config.gradient_accumulation_steps
                scaler.scale(loss).backward()
                accumulation_loss += loss.item()

            # Gradient clipping
            scaler.unscale_(self.optimizer)
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.max_grad_norm)

            scaler.step(self.optimizer)
            scaler.update()

            if step >= self.config.warmup_steps:
                self.scheduler.step()

            # Logging
            if step % self.config.log_steps == 0:
                elapsed = time.time() - start_time
                tokens_per_sec = (
                    step
                    * self.config.batch_size
                    * self.config.gradient_accumulation_steps
                    * self.train_loader.dataset[0]["input_ids"].shape[0]
                    / elapsed
                )
                lr = self.optimizer.param_groups[0]["lr"]
                logger.info(
                    f"Step {step}/{self.config.max_steps} | "
                    f"Loss: {accumulation_loss / self.config.log_steps:.4f} | "
                    f"LR: {lr:.2e} | "
                    f"Tokens/s: {tokens_per_sec:.0f}"
                )
                accumulation_loss = 0.0

            # Evaluation
            if self.eval_loader and step % self.config.eval_steps == 0:
                eval_loss = self.evaluate()
                logger.info(f"Eval Loss: {eval_loss:.4f}")
                if eval_loss < self.best_eval_loss:
                    self.best_eval_loss = eval_loss
                    self.save_checkpoint(output_dir / "best")
                self.model.train()

            # Save checkpoint
            if step % self.config.save_steps == 0:
                self.save_checkpoint(output_dir / f"step-{step}")

        # Final save
        self.save_checkpoint(output_dir / "final")
        logger.info("Training complete!")

        return {"final_loss": accumulation_loss, "steps": self.global_step}

    @torch.no_grad()
    def evaluate(self) -> float:
        """Run evaluation and return average loss."""
        self.model.eval()
        total_loss = 0.0
        num_batches = 0

        for batch in self.eval_loader:
            loss = self.compute_loss(batch)
            total_loss += loss.item()
            num_batches += 1

        return total_loss / max(num_batches, 1)

    def save_checkpoint(self, path: str | Path) -> None:
        """Save model checkpoint."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        if hasattr(self.model, "save_pretrained"):
            self.model.save_pretrained(str(path))
        else:
            torch.save({"model_state_dict": self.model.state_dict()}, path / "model.pt")

        torch.save(
            {
                "optimizer_state_dict": self.optimizer.state_dict(),
                "scheduler_state_dict": self.scheduler.state_dict(),
                "global_step": self.global_step,
                "best_eval_loss": self.best_eval_loss,
            },
            path / "trainer_state.pt",
        )
        logger.info(f"Checkpoint saved to {path}")
