"""PRM - Process Reward Model

최종 답뿐 아니라 "추론 과정 각 단계"를 평가.
수학/코딩에서 정확도 큰 폭 상승.
o1, Claude 3.7의 핵심 기법.

이 스크립트는:
  1. Step별 정답 여부 레이블링된 데이터 수집
  2. 별도 PRM 모델 학습 (작은 모델, 7B)
  3. 추론 시 PRM이 각 스텝 평가 → 나쁜 경로 가지치기

사용법:
    python scripts/advanced/train_prm.py \\
        --base-model /mnt/nvme2/hwarang/models/qwen2.5-7b \\
        --data data/prm/step_labels.jsonl \\
        --output /mnt/nvme2/hwarang/models/hwarang-prm
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ─── PRM 데이터 포맷 ─────────────────────────────────────────────
#
# {
#   "question": "...",
#   "steps": [
#     {"text": "단계 1...", "label": "positive" | "negative" | "neutral"},
#     {"text": "단계 2...", "label": "positive"},
#     ...
#   ],
#   "final_answer": "...",
#   "is_correct": true
# }


def prepare_prm_data(input_path: str, output_path: str):
    """Step-level 데이터를 분류 학습 형태로 변환."""
    count = 0
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(input_path, encoding="utf-8") as fin, open(output_path, "w", encoding="utf-8") as fout:
        for line in fin:
            try:
                item = json.loads(line.strip())
            except Exception:
                continue

            question = item["question"]
            steps = item.get("steps", [])

            # 각 step을 독립 샘플로 만듬 (prefix = 이전 steps 포함)
            prefix = f"질문: {question}\n"
            for step in steps:
                prefix += f"{step['text']}\n"

                label_map = {"positive": 1, "negative": 0, "neutral": 0.5}
                label = label_map.get(step.get("label", "neutral"), 0.5)

                fout.write(json.dumps({
                    "text": prefix,
                    "label": label,
                }, ensure_ascii=False) + "\n")
                count += 1

    logger.info(f"PRM 데이터 준비: {count}개 step")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", required=True, help="PRM 베이스 모델 (7B 권장)")
    parser.add_argument("--data", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--batch-size", type=int, default=4)
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(" PRM (Process Reward Model) 학습")
    logger.info("=" * 60)

    try:
        import torch
        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
            TrainingArguments,
            Trainer,
        )
        from datasets import load_dataset
    except ImportError as e:
        logger.error(f"패키지 없음: {e}")
        sys.exit(1)

    # 데이터 준비
    prm_data_path = args.data + ".prm"
    prepare_prm_data(args.data, prm_data_path)

    # 토크나이저 + 모델 (regression head)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForSequenceClassification.from_pretrained(
        args.base_model,
        num_labels=1,  # regression
        problem_type="regression",
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
    )

    # 데이터셋
    dataset = load_dataset("json", data_files=prm_data_path, split="train")

    def tokenize(ex):
        enc = tokenizer(ex["text"], truncation=True, max_length=1024, padding="max_length")
        enc["labels"] = ex["label"]
        return enc

    dataset = dataset.map(tokenize)

    training_args = TrainingArguments(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=4,
        learning_rate=args.lr,
        weight_decay=0.01,
        warmup_ratio=0.03,
        bf16=True,
        logging_steps=10,
        save_steps=200,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        tokenizer=tokenizer,
    )

    logger.info("PRM 학습 시작!")
    trainer.train()
    model.save_pretrained(args.output)
    tokenizer.save_pretrained(args.output)
    logger.info(f"✅ 완료: {args.output}")
    logger.info("\n사용법 (추론 시):")
    logger.info("  각 step 생성 후 PRM 점수 확인 → 낮으면 재생성")


if __name__ == "__main__":
    main()
