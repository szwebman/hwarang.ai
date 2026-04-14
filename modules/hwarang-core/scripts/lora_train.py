"""LoRA 도메인 어댑터 학습 스크립트.

베이스 모델에 도메인 특화 LoRA를 학습합니다.
- Tax LoRA: 세무 데이터로 학습
- Legal LoRA: 법률 데이터로 학습
- Code LoRA: 추가 코드 데이터로 학습 (이미 베이스가 코드 특화면 생략 가능)

사용법:
    python scripts/lora_train.py \\
        --checkpoint ./checkpoints/pretrain_7b/final \\
        --data ../../data/sft/tax.jsonl \\
        --output ./lora_adapters/tax \\
        --r 16 \\
        --epochs 3
"""

from __future__ import annotations

import argparse
import logging

import yaml

from hwarang_core.data.collator import PaddingCollator
from hwarang_core.data.dataset import SFTDataset
from hwarang_core.model.transformer import HwarangForCausalLM
from hwarang_core.tokenizer import HwarangTokenizer
from hwarang_core.training.lora import (
    LoRAConfig,
    apply_lora_to_model,
    save_lora_weights,
)
from hwarang_core.training.sft import SFTTrainer
from hwarang_core.training.trainer import TrainingConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="LoRA 도메인 어댑터 학습")
    parser.add_argument("--checkpoint", required=True, help="베이스 모델 체크포인트")
    parser.add_argument("--data", required=True, help="SFT JSONL 데이터")
    parser.add_argument("--eval-data", default=None)
    parser.add_argument("--output", required=True, help="LoRA 가중치 저장 경로")
    parser.add_argument("--train-config", default="configs/training/lora.yaml")
    parser.add_argument("--max-length", type=int, default=2048)

    # LoRA 하이퍼파라미터
    parser.add_argument("--r", type=int, default=16, help="LoRA 랭크")
    parser.add_argument("--alpha", type=int, default=32, help="LoRA 알파")
    parser.add_argument("--dropout", type=float, default=0.05)
    parser.add_argument("--target-modules", nargs="+",
                       default=["q_proj", "k_proj", "v_proj", "o_proj"])
    args = parser.parse_args()

    # 학습 config
    if args.train_config:
        try:
            with open(args.train_config) as f:
                train_config = TrainingConfig(**yaml.safe_load(f))
        except FileNotFoundError:
            logger.warning(f"{args.train_config} 없음, 기본 설정 사용")
            train_config = TrainingConfig(
                learning_rate=2.0e-4,
                weight_decay=0.0,
                warmup_steps=100,
                max_steps=2000,
                batch_size=4,
                gradient_accumulation_steps=4,
                save_steps=200,
                eval_steps=100,
                output_dir=args.output,
            )

    # 베이스 모델 로드
    logger.info(f"베이스 모델 로드: {args.checkpoint}")
    model = HwarangForCausalLM.from_pretrained(args.checkpoint)
    logger.info(f"파라미터: {model.num_parameters():,}")

    # LoRA 적용
    lora_config = LoRAConfig(
        r=args.r,
        alpha=args.alpha,
        dropout=args.dropout,
        target_modules=args.target_modules,
        freeze_base=True,
    )
    model, trainable = apply_lora_to_model(model, lora_config)

    # 토크나이저
    tokenizer = HwarangTokenizer(f"{args.checkpoint}/tokenizer")

    # 데이터셋
    train_dataset = SFTDataset(args.data, tokenizer, max_length=args.max_length)
    eval_dataset = SFTDataset(args.eval_data, tokenizer, max_length=args.max_length) if args.eval_data else None
    logger.info(f"학습 샘플: {len(train_dataset):,}")

    collator = PaddingCollator(pad_token_id=tokenizer.pad_token_id)

    # 학습
    trainer = SFTTrainer(
        model=model,
        config=train_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        collator=collator,
    )
    trainer.train()

    # LoRA 가중치만 저장 (베이스는 저장 안 함)
    save_lora_weights(model, f"{args.output}/lora_weights.pt")

    # 메타데이터 저장
    import json
    from pathlib import Path
    Path(args.output).mkdir(parents=True, exist_ok=True)

    metadata = {
        "base_model": args.checkpoint,
        "lora_config": {
            "r": args.r,
            "alpha": args.alpha,
            "dropout": args.dropout,
            "target_modules": args.target_modules,
        },
        "trainable_params": trainable,
        "data": args.data,
    }
    with open(f"{args.output}/metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"LoRA 학습 완료! 저장 위치: {args.output}")


if __name__ == "__main__":
    main()
