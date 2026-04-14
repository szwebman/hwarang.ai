"""Checkpoint save/load utilities."""

from __future__ import annotations

import logging
from pathlib import Path

import torch

logger = logging.getLogger(__name__)


def save_checkpoint(
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer | None = None,
    step: int = 0,
    path: str | Path = "./checkpoint",
) -> None:
    """Save a training checkpoint."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    state = {"model_state_dict": model.state_dict(), "step": step}
    if optimizer is not None:
        state["optimizer_state_dict"] = optimizer.state_dict()

    torch.save(state, path / "checkpoint.pt")

    if hasattr(model, "config"):
        model.config.to_yaml(str(path / "config.yaml"))

    logger.info(f"Checkpoint saved to {path} (step {step})")


def load_checkpoint(
    model: torch.nn.Module,
    path: str | Path,
    optimizer: torch.optim.Optimizer | None = None,
    map_location: str = "cpu",
) -> int:
    """Load a training checkpoint. Returns the step number."""
    path = Path(path)
    state = torch.load(path / "checkpoint.pt", map_location=map_location, weights_only=True)

    model.load_state_dict(state["model_state_dict"])
    if optimizer is not None and "optimizer_state_dict" in state:
        optimizer.load_state_dict(state["optimizer_state_dict"])

    step = state.get("step", 0)
    logger.info(f"Checkpoint loaded from {path} (step {step})")
    return step
