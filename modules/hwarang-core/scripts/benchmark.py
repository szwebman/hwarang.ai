"""Benchmark model inference speed."""

from __future__ import annotations

import argparse
import logging
import time

import torch

from hwarang_core.model.config import HwarangConfig
from hwarang_core.model.transformer import HwarangForCausalLM
from hwarang_core.inference.sampler import sample_next_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def benchmark_generation(
    model: HwarangForCausalLM,
    device: torch.device,
    dtype: torch.dtype,
    prompt_len: int = 64,
    gen_len: int = 128,
    num_runs: int = 5,
):
    """Benchmark autoregressive generation speed."""
    model.eval()
    model.to(device=device, dtype=dtype)

    input_ids = torch.randint(0, model.config.vocab_size, (1, prompt_len), device=device)

    # Warmup
    logger.info("Warming up...")
    with torch.no_grad():
        past = None
        current = input_ids
        for _ in range(10):
            out = model(current, past_key_values=past, use_cache=True)
            past = out.past_key_values
            current = sample_next_token(out.logits[:, -1, :], temperature=0)

    # Benchmark
    times = []
    for run in range(num_runs):
        torch.cuda.synchronize() if device.type == "cuda" else None
        start = time.perf_counter()

        past = None
        current = input_ids
        # Prefill
        with torch.no_grad(), torch.amp.autocast(device_type=device.type, dtype=dtype):
            out = model(current, use_cache=True)
            past = out.past_key_values
            current = sample_next_token(out.logits[:, -1, :], temperature=0)

            # Generate
            for _ in range(gen_len - 1):
                out = model(current, past_key_values=past, use_cache=True)
                past = out.past_key_values
                current = sample_next_token(out.logits[:, -1, :], temperature=0)

        torch.cuda.synchronize() if device.type == "cuda" else None
        elapsed = time.perf_counter() - start
        times.append(elapsed)

        tokens_per_sec = gen_len / elapsed
        logger.info(f"Run {run + 1}: {elapsed:.2f}s ({tokens_per_sec:.1f} tokens/s)")

    avg_time = sum(times) / len(times)
    avg_tps = gen_len / avg_time
    logger.info(f"\nAverage: {avg_time:.2f}s ({avg_tps:.1f} tokens/s)")
    logger.info(f"Prompt: {prompt_len} tokens, Generated: {gen_len} tokens")

    return avg_tps


def main():
    parser = argparse.ArgumentParser(description="Benchmark Hwarang model")
    parser.add_argument("--checkpoint", default=None, help="Model checkpoint (uses random init if not provided)")
    parser.add_argument("--model-size", choices=["small", "medium", "large"], default="small")
    parser.add_argument("--prompt-len", type=int, default=64)
    parser.add_argument("--gen-len", type=int, default=128)
    parser.add_argument("--num-runs", type=int, default=5)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--dtype", choices=["float32", "float16", "bfloat16"], default="bfloat16")
    args = parser.parse_args()

    # Device
    if args.device == "auto":
        if torch.cuda.is_available():
            device = torch.device("cuda")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = torch.device("mps")
        else:
            device = torch.device("cpu")
    else:
        device = torch.device(args.device)

    dtype_map = {"float32": torch.float32, "float16": torch.float16, "bfloat16": torch.bfloat16}
    dtype = dtype_map[args.dtype]

    logger.info(f"Device: {device}, dtype: {args.dtype}")

    # Load or create model
    if args.checkpoint:
        model = HwarangForCausalLM.from_pretrained(args.checkpoint)
    else:
        config_fn = {"small": HwarangConfig.small, "medium": HwarangConfig.medium, "large": HwarangConfig.large}
        config = config_fn[args.model_size]()
        model = HwarangForCausalLM(config)

    logger.info(f"Model: {args.model_size}, params: {model.num_parameters():,}")

    benchmark_generation(
        model, device, dtype,
        prompt_len=args.prompt_len,
        gen_len=args.gen_len,
        num_runs=args.num_runs,
    )


if __name__ == "__main__":
    main()
