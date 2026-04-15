"""Qwen2.5-32B QLoRA 파인튜닝 스크립트.

RTX 5090 32GB 1장에서 실행 가능.
GPTQ-Int4 모델 사용 (~16GB) + LoRA 어댑터(~2GB) = ~20GB VRAM.

사용법:
    poetry run python scripts/qlora_qwen.py \
        --model-path /mnt/nvme2/hwarang/models/qwen2.5-32b-int4 \
        --data ../../data/sft/all_sft.jsonl \
        --output /mnt/nvme2/hwarang/lora_adapters/hwarang-code-v1 \
        --epochs 3

필요 패키지:
    poetry run pip install transformers accelerate peft trl auto-gptq optimum
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Qwen2.5-32B QLoRA 파인튜닝")
    parser.add_argument("--model-path", required=True, help="Qwen2.5 GPTQ 모델 경로")
    parser.add_argument("--data", required=True, help="SFT 데이터 (JSONL)")
    parser.add_argument("--output", required=True, help="LoRA 어댑터 저장 경로")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--max-length", type=int, default=2048)
    args = parser.parse_args()

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from trl import SFTTrainer
        from datasets import Dataset
    except ImportError as e:
        logger.error(f"필수 패키지 없음: {e}")
        logger.error("실행: poetry run pip install transformers accelerate peft trl auto-gptq optimum")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Hwarang QLoRA 파인튜닝 (GPTQ)")
    logger.info(f"  모델: {args.model_path}")
    logger.info(f"  데이터: {args.data}")
    logger.info(f"  출력: {args.output}")
    logger.info(f"  에포크: {args.epochs}")
    logger.info(f"  LoRA r={args.lora_r}, alpha={args.lora_alpha}")
    logger.info("=" * 60)

    # ============================================================
    # 1. 데이터 로드
    # ============================================================
    logger.info("데이터 로드 중...")

    conversations = []
    with open(args.data, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                messages = item.get("messages", [])
                if len(messages) >= 2:
                    conversations.append(messages)
            except json.JSONDecodeError:
                continue

    logger.info(f"  대화 수: {len(conversations):,}")

    def format_conversation(messages):
        text = ""
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            text += f"<|im_start|>{role}\n{content}<|im_end|>\n"
        return text

    formatted = [{"text": format_conversation(conv)} for conv in conversations]
    dataset = Dataset.from_list(formatted)
    logger.info(f"  데이터셋 준비 완료: {len(dataset)} 예제")

    # ============================================================
    # 2. GPTQ 모델 로드 (이미 INT4 양자화됨, bitsandbytes 불필요)
    # ============================================================
    logger.info("GPTQ 모델 로드 중... 약 2~3분 소요")

    import torch

    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        device_map="auto",
        torch_dtype=torch.float16,
        trust_remote_code=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        args.model_path,
        trust_remote_code=True,
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    logger.info(f"  모델 로드 완료")
    logger.info(f"  VRAM 사용: {torch.cuda.memory_allocated() / 1e9:.1f}GB")

    # ============================================================
    # 3. LoRA 설정
    # ============================================================
    logger.info("LoRA 어댑터 적용 중...")

    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        bias="none",
        task_type="CAUSAL_LM",
    )

    model = get_peft_model(model, lora_config)

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    logger.info(f"  학습 파라미터: {trainable:,} ({trainable/total*100:.2f}%)")
    logger.info(f"  전체 파라미터: {total:,}")
    logger.info(f"  VRAM 사용: {torch.cuda.memory_allocated() / 1e9:.1f}GB")

    # ============================================================
    # 4. 학습 설정
    # ============================================================
    effective_batch = args.batch_size * args.grad_accum
    total_steps = (len(dataset) // effective_batch) * args.epochs

    training_args = TrainingArguments(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        weight_decay=0.01,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        logging_steps=10,
        save_steps=500,
        save_total_limit=3,
        fp16=True,
        max_grad_norm=0.3,
        optim="adamw_torch",
        report_to="none",
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )

    logger.info(f"  실효 배치: {effective_batch}")
    logger.info(f"  총 스텝: {total_steps:,}")
    logger.info(f"  예상 시간: ~{total_steps * 3 / 3600:.1f}시간")

    # ============================================================
    # 5. 학습 실행
    # ============================================================
    logger.info("학습 시작!")

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        processing_class=tokenizer,
        max_seq_length=args.max_length,
    )

    trainer.train()

    # ============================================================
    # 6. LoRA 어댑터 저장
    # ============================================================
    logger.info(f"LoRA 어댑터 저장: {args.output}")
    model.save_pretrained(args.output)
    tokenizer.save_pretrained(args.output)

    metadata = {
        "base_model": args.model_path,
        "quantization": "GPTQ-Int4",
        "data": args.data,
        "data_count": len(dataset),
        "epochs": args.epochs,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "trainable_params": trainable,
        "total_params": total,
        "training_steps": total_steps,
    }
    with open(os.path.join(args.output, "hwarang_metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info("=" * 60)
    logger.info("학습 완료!")
    logger.info(f"  LoRA 어댑터: {args.output}")
    logger.info(f"  VRAM 최종: {torch.cuda.memory_allocated() / 1e9:.1f}GB")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
