"""Train a BPE tokenizer from a text corpus."""

from __future__ import annotations

import argparse
import logging

from hwarang_core.tokenizer.trainer import BPETrainer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Train Hwarang BPE Tokenizer")
    parser.add_argument("--data", required=True, help="Path to text file or directory of text files")
    parser.add_argument("--output", default="./tokenizer_output", help="Output directory")
    parser.add_argument("--vocab-size", type=int, default=32000, help="Target vocabulary size")
    parser.add_argument("--min-frequency", type=int, default=2, help="Minimum pair frequency for merge")
    args = parser.parse_args()

    logger.info(f"Training tokenizer: vocab_size={args.vocab_size}, min_freq={args.min_frequency}")
    logger.info(f"Data: {args.data}")

    trainer = BPETrainer(
        vocab_size=args.vocab_size,
        min_frequency=args.min_frequency,
    )

    result = trainer.train(args.data, args.output)
    logger.info(f"Done! vocab_size={result['vocab_size']}, merges={result['num_merges']}")


if __name__ == "__main__":
    main()
