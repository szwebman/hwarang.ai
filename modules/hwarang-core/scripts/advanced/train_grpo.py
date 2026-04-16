"""DeepSeek GRPO - Group Relative Policy Optimization

DPO의 진화형. 여러 응답 그룹으로 비교 학습.
DeepSeek-R1의 핵심 기법. 메모리 50% 절감, 성능 향상.

사용법:
    python scripts/advanced/train_grpo.py \\
        --model /mnt/nvme2/hwarang/models/qwen2.5-32b \\
        --data data/grpo/pairs.jsonl \\
        --output /mnt/nvme2/hwarang/lora/grpo-v1
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--data", required=True, help="JSONL: {prompt, responses: [{content, reward}], ...}")
    parser.add_argument("--output", required=True)
    parser.add_argument("--group-size", type=int, default=4)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--beta", type=float, default=0.1, help="KL penalty")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(" DeepSeek GRPO 학습")
    logger.info("=" * 60)

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from trl import GRPOTrainer, GRPOConfig  # trl 0.15+ 필요
        from datasets import load_dataset
    except ImportError as e:
        logger.error(f"필수 패키지 없음: {e}")
        logger.error("실행: pip install transformers peft trl>=0.15 bitsandbytes datasets")
        sys.exit(1)

    # 4bit 로드
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )

    logger.info("모델 로드 중...")
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=bnb,
        device_map="auto",
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = prepare_model_for_kbit_training(model)
    lora_config = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)

    # 데이터셋
    logger.info(f"데이터 로드: {args.data}")
    dataset = load_dataset("json", data_files=args.data, split="train")

    # Reward function (응답에 보상 점수 주기)
    def reward_fn(samples, **kwargs):
        # samples: [{prompt, response, ...}, ...]
        # 실제로는 Reward Model 또는 휴리스틱
        rewards = []
        for s in samples:
            r = 0.5
            if len(s.get("response", "")) > 100:
                r += 0.1
            if "```" in s.get("response", ""):
                r += 0.1
            rewards.append(r)
        return rewards

    training_args = GRPOConfig(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=8,
        learning_rate=args.lr,
        logging_steps=10,
        save_steps=200,
        bf16=True,
        max_grad_norm=0.3,
        optim="paged_adamw_8bit",
        report_to="none",
        # GRPO 특화
        num_generations=args.group_size,
        beta=args.beta,
    )

    trainer = GRPOTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        reward_funcs=[reward_fn],
        processing_class=tokenizer,
    )

    logger.info("GRPO 학습 시작!")
    trainer.train()
    model.save_pretrained(args.output)
    tokenizer.save_pretrained(args.output)
    logger.info(f"✅ 완료: {args.output}")


if __name__ == "__main__":
    main()
