"""Export model for serving (with optional quantization)."""

from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path

import torch

from hwarang_core.model.transformer import HwarangForCausalLM

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Export Hwarang model for serving")
    parser.add_argument("--checkpoint", required=True, help="Path to trained checkpoint")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--quantize", choices=["none", "int8"], default="none")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Loading model from {args.checkpoint}")
    model = HwarangForCausalLM.from_pretrained(args.checkpoint)
    logger.info(f"Parameters: {model.num_parameters():,}")

    if args.quantize == "int8":
        logger.info("Applying INT8 dynamic quantization...")
        model = torch.quantization.quantize_dynamic(
            model, {torch.nn.Linear}, dtype=torch.qint8
        )
        logger.info("Quantization complete")

    # Save model
    model.save_pretrained(str(output_dir))

    # Copy tokenizer
    src_tokenizer = Path(args.checkpoint) / "tokenizer"
    if src_tokenizer.exists():
        dst_tokenizer = output_dir / "tokenizer"
        if dst_tokenizer.exists():
            shutil.rmtree(dst_tokenizer)
        shutil.copytree(src_tokenizer, dst_tokenizer)
        logger.info("Tokenizer copied")

    logger.info(f"Model exported to {output_dir}")


if __name__ == "__main__":
    main()
