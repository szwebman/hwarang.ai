"""DPO alignment training script."""

from __future__ import annotations

import argparse
import logging

import yaml

from hwarang_core.data.collator import DPOCollator
from hwarang_core.data.dataset import DPODataset
from hwarang_core.model.transformer import HwarangForCausalLM
from hwarang_core.tokenizer import HwarangTokenizer
from hwarang_core.training.dpo import DPOTrainer
from hwarang_core.training.trainer import TrainingConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Align Hwarang LLM with DPO")
    parser.add_argument("--checkpoint", required=True, help="Path to SFT checkpoint")
    parser.add_argument("--train-config", default="configs/training/dpo.yaml")
    parser.add_argument("--data", required=True, help="Path to DPO JSONL data")
    parser.add_argument("--eval-data", default=None)
    parser.add_argument("--beta", type=float, default=0.1, help="DPO beta parameter")
    parser.add_argument("--max-length", type=int, default=2048)
    args = parser.parse_args()

    with open(args.train_config) as f:
        train_config = TrainingConfig(**yaml.safe_load(f))

    logger.info(f"Loading model from {args.checkpoint}")
    model = HwarangForCausalLM.from_pretrained(args.checkpoint)
    logger.info(f"Parameters: {model.num_parameters():,}")

    tokenizer = HwarangTokenizer(f"{args.checkpoint}/tokenizer")

    train_dataset = DPODataset(args.data, tokenizer, max_length=args.max_length)
    eval_dataset = DPODataset(args.eval_data, tokenizer, max_length=args.max_length) if args.eval_data else None
    logger.info(f"Training samples: {len(train_dataset):,}")

    collator = DPOCollator(pad_token_id=tokenizer.pad_token_id)

    trainer = DPOTrainer(
        model=model,
        config=train_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        collator=collator,
        beta=args.beta,
    )
    trainer.train()


if __name__ == "__main__":
    main()
