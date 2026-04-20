"""화랑 AI LoRA 머지 스크립트

학습된 LoRA 어댑터를 베이스 모델에 합쳐서 독립 모델로 만듦.
CPU에서 실행 (128GB RAM이면 32B 모델도 가능).

사용법:
    poetry run python scripts/merge_lora.py \
        --base-model /mnt/nvme2/hwarang/models/qwen2.5-32b \
        --lora-path /mnt/nvme2/hwarang/models/hwarang-all-v2 \
        --output /mnt/nvme2/hwarang/models/hwarang-merged-v2 \
        --device cpu

머지 후 서빙:
    poetry run vllm serve /mnt/nvme2/hwarang/models/hwarang-merged-v2 \
        --quantization bitsandbytes \
        --load-format bitsandbytes \
        --port 8000
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import shutil

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="화랑 AI LoRA 머지")
    parser.add_argument("--base-model", required=True, help="베이스 모델 경로 (Qwen2.5-32B 등)")
    parser.add_argument("--lora-path", required=True, help="LoRA 어댑터 경로")
    parser.add_argument("--output", required=True, help="머지된 모델 저장 경로")
    parser.add_argument("--device", default="cpu", choices=["cpu", "auto"], help="머지 디바이스 (cpu 권장)")
    parser.add_argument("--dtype", default="float16", choices=["float16", "bfloat16", "float32"], help="출력 dtype")
    args = parser.parse_args()

    # 경로 확인
    if not os.path.exists(args.base_model):
        logger.error(f"베이스 모델 없음: {args.base_model}")
        sys.exit(1)

    if not os.path.exists(args.lora_path):
        logger.error(f"LoRA 경로 없음: {args.lora_path}")
        sys.exit(1)

    # 필수 패키지
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
    except ImportError as e:
        logger.error(f"필수 패키지 없음: {e}")
        logger.error("설치: pip install transformers peft torch accelerate")
        sys.exit(1)

    dtype_map = {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }
    torch_dtype = dtype_map[args.dtype]

    logger.info("=" * 60)
    logger.info(" 화랑 AI LoRA 머지")
    logger.info("=" * 60)
    logger.info(f"  베이스 모델: {args.base_model}")
    logger.info(f"  LoRA 경로:  {args.lora_path}")
    logger.info(f"  출력 경로:  {args.output}")
    logger.info(f"  디바이스:   {args.device}")
    logger.info(f"  dtype:      {args.dtype}")
    logger.info("=" * 60)

    start_time = time.time()

    # ═══ 1단계: 베이스 모델 로드 ═══
    logger.info("")
    logger.info("1단계: 베이스 모델 로드 중... (수 분 소요)")

    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=torch_dtype,
        device_map=args.device,
        trust_remote_code=True,
        low_cpu_mem_usage=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        args.base_model,
        trust_remote_code=True,
    )

    logger.info(f"  모델 로드 완료 ({time.time() - start_time:.0f}초)")

    # ═══ 2단계: LoRA 어댑터 적용 ═══
    logger.info("")
    logger.info("2단계: LoRA 어댑터 적용 중...")

    model = PeftModel.from_pretrained(
        model,
        args.lora_path,
        torch_dtype=torch_dtype,
        device_map=args.device,
    )

    logger.info(f"  LoRA 적용 완료 ({time.time() - start_time:.0f}초)")

    # ═══ 3단계: 머지 ═══
    logger.info("")
    logger.info("3단계: 모델 머지 중 (merge_and_unload)... (수 분 소요)")

    model = model.merge_and_unload()

    logger.info(f"  머지 완료 ({time.time() - start_time:.0f}초)")

    # ═══ 4단계: 저장 ═══
    logger.info("")
    logger.info(f"4단계: 머지된 모델 저장 중... → {args.output}")

    os.makedirs(args.output, exist_ok=True)

    model.save_pretrained(
        args.output,
        safe_serialization=True,  # safetensors 형식
        max_shard_size="4GB",
    )

    tokenizer.save_pretrained(args.output)

    # 메타데이터 저장
    metadata = {
        "base_model": args.base_model,
        "lora_path": args.lora_path,
        "merge_dtype": args.dtype,
        "merge_device": args.device,
        "merged_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "merge_duration_sec": round(time.time() - start_time),
    }

    # LoRA 메타데이터가 있으면 포함
    lora_meta_path = os.path.join(args.lora_path, "hwarang_metadata.json")
    if os.path.exists(lora_meta_path):
        with open(lora_meta_path) as f:
            metadata["lora_metadata"] = json.load(f)
    else:
        meta2 = os.path.join(args.lora_path, "metadata.json")
        if os.path.exists(meta2):
            with open(meta2) as f:
                metadata["lora_metadata"] = json.load(f)

    with open(os.path.join(args.output, "merge_info.json"), "w") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    # 출력 크기 확인
    total_size = 0
    file_count = 0
    for root, _, files in os.walk(args.output):
        for fname in files:
            fpath = os.path.join(root, fname)
            total_size += os.path.getsize(fpath)
            file_count += 1

    elapsed = time.time() - start_time

    logger.info("")
    logger.info("=" * 60)
    logger.info(" 머지 완료!")
    logger.info("=" * 60)
    logger.info(f"  출력 경로: {args.output}")
    logger.info(f"  파일 수:   {file_count}개")
    logger.info(f"  총 크기:   {total_size / 1024 / 1024 / 1024:.1f}GB")
    logger.info(f"  소요 시간: {elapsed / 60:.1f}분")
    logger.info("")
    logger.info("서빙 명령어:")
    logger.info(f"  poetry run vllm serve {args.output} \\")
    logger.info(f"    --quantization bitsandbytes \\")
    logger.info(f"    --load-format bitsandbytes \\")
    logger.info(f"    --port 8000")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
