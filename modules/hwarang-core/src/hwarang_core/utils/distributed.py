"""Distributed training helpers for multi-GPU training."""

from __future__ import annotations

import logging
import os

import torch
import torch.distributed as dist

logger = logging.getLogger(__name__)


def setup_distributed() -> tuple[int, int, int]:
    """Initialize distributed training.

    Returns:
        (rank, local_rank, world_size)
    """
    if not dist.is_initialized():
        rank = int(os.environ.get("RANK", 0))
        local_rank = int(os.environ.get("LOCAL_RANK", 0))
        world_size = int(os.environ.get("WORLD_SIZE", 1))

        if world_size > 1:
            dist.init_process_group("nccl")
            torch.cuda.set_device(local_rank)
            logger.info(f"Distributed: rank={rank}, local_rank={local_rank}, world_size={world_size}")
        else:
            logger.info("Single-GPU training")

        return rank, local_rank, world_size

    return dist.get_rank(), int(os.environ.get("LOCAL_RANK", 0)), dist.get_world_size()


def cleanup_distributed() -> None:
    """Clean up distributed training."""
    if dist.is_initialized():
        dist.destroy_process_group()


def is_main_process() -> bool:
    """Check if this is the main process (rank 0)."""
    if not dist.is_initialized():
        return True
    return dist.get_rank() == 0


def wrap_model_ddp(model: torch.nn.Module, local_rank: int) -> torch.nn.Module:
    """Wrap model with DistributedDataParallel."""
    if dist.is_initialized() and dist.get_world_size() > 1:
        model = torch.nn.parallel.DistributedDataParallel(
            model,
            device_ids=[local_rank],
            output_device=local_rank,
        )
    return model


def wrap_model_fsdp(model: torch.nn.Module) -> torch.nn.Module:
    """Wrap model with FullyShardedDataParallel (FSDP).

    FSDP shards model parameters across GPUs for memory efficiency.
    Recommended for training models that don't fit on a single GPU.
    """
    from torch.distributed.fsdp import FullyShardedDataParallel as FSDP
    from torch.distributed.fsdp import MixedPrecision

    mixed_precision = MixedPrecision(
        param_dtype=torch.bfloat16,
        reduce_dtype=torch.bfloat16,
        buffer_dtype=torch.bfloat16,
    )

    model = FSDP(
        model,
        mixed_precision=mixed_precision,
        use_orig_params=True,
    )
    return model
