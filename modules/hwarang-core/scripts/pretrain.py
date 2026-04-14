"""Pretraining script for Hwarang LLM."""

from __future__ import annotations

import argparse
import logging

import yaml

from hwarang_core.data.collator import PaddingCollator
from hwarang_core.data.dataset import PretrainDataset
from hwarang_core.model.config import HwarangConfig
from hwarang_core.model.transformer import HwarangForCausalLM
from hwarang_core.training.trainer import HwarangTrainer, TrainingConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Pretrain Hwarang LLM")
    parser.add_argument("--model-config", default="configs/model/small.yaml")
    parser.add_argument("--train-config", default="configs/training/pretrain.yaml")
    parser.add_argument("--data", required=True, help="Path to tokenized data (.bin)")
    parser.add_argument("--eval-data", default=None)
    parser.add_argument("--seq-length", type=int, default=2048)
    args = parser.parse_args()

    # Load configs
    model_config = HwarangConfig.from_yaml(args.model_config)
    with open(args.train_config) as f:
        train_config = TrainingConfig(**yaml.safe_load(f))

    logger.info(f"Model: hidden={model_config.hidden_size}, layers={model_config.num_hidden_layers}")

    # Create model
    model = HwarangForCausalLM(model_config)
    logger.info(f"Parameters: {model.num_parameters():,}")

    # Create datasets
    train_dataset = PretrainDataset(args.data, seq_length=args.seq_length)
    eval_dataset = PretrainDataset(args.eval_data, seq_length=args.seq_length) if args.eval_data else None

    logger.info(f"Training samples: {len(train_dataset):,}")

    # Train
    trainer = HwarangTrainer(
        model=model,
        config=train_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
    )
    trainer.train()


if __name__ == "__main__":
    main()
