"""Supervised Fine-Tuning (SFT) script."""

from __future__ import annotations

import argparse
import logging

import yaml

from hwarang_core.data.collator import PaddingCollator
from hwarang_core.data.dataset import SFTDataset
from hwarang_core.model.config import HwarangConfig
from hwarang_core.model.transformer import HwarangForCausalLM
from hwarang_core.tokenizer import HwarangTokenizer
from hwarang_core.training.sft import SFTTrainer
from hwarang_core.training.trainer import TrainingConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Fine-tune Hwarang LLM")
    parser.add_argument("--checkpoint", required=True, help="Path to pretrained checkpoint")
    parser.add_argument("--train-config", default="configs/training/sft.yaml")
    parser.add_argument("--data", required=True, help="Path to SFT JSONL data")
    parser.add_argument("--eval-data", default=None)
    parser.add_argument("--max-length", type=int, default=2048)
    args = parser.parse_args()

    # Load training config
    with open(args.train_config) as f:
        train_config = TrainingConfig(**yaml.safe_load(f))

    # Load model from checkpoint
    logger.info(f"Loading model from {args.checkpoint}")
    model = HwarangForCausalLM.from_pretrained(args.checkpoint)
    logger.info(f"Parameters: {model.num_parameters():,}")

    # Load tokenizer
    tokenizer = HwarangTokenizer(f"{args.checkpoint}/tokenizer")

    # Create datasets
    train_dataset = SFTDataset(args.data, tokenizer, max_length=args.max_length)
    eval_dataset = SFTDataset(args.eval_data, tokenizer, max_length=args.max_length) if args.eval_data else None
    logger.info(f"Training samples: {len(train_dataset):,}")

    collator = PaddingCollator(pad_token_id=tokenizer.pad_token_id)

    # Train
    trainer = SFTTrainer(
        model=model,
        config=train_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        collator=collator,
    )
    trainer.train()


if __name__ == "__main__":
    main()
