"""비전 모델로 웹디자인 학습 (이미지 → 코드)

Qwen2.5-VL 같은 비전 모델을 QLoRA로 학습.
스크린샷을 보고 HTML/CSS 코드 생성.

필요 데이터 포맷:
  JSONL with {image_path, description, html_code}

사용법:
    # 1. Qwen2.5-VL-7B 다운로드
    hf download Qwen/Qwen2.5-VL-7B-Instruct \\
        --local-dir /mnt/nvme2/hwarang/models/qwen2.5-vl-7b

    # 2. 웹디자인 데이터셋 준비 (WebSight)
    python scripts/data/prepare_websight.py \\
        --output /mnt/nvme2/hwarang/data/vision/websight.jsonl

    # 3. 학습
    python scripts/advanced/train_vision_design.py \\
        --model /mnt/nvme2/hwarang/models/qwen2.5-vl-7b \\
        --data /mnt/nvme2/hwarang/data/vision/websight.jsonl \\
        --output /mnt/nvme2/hwarang/lora_adapters/design-vision-v1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """당신은 화랑 AI 디자인 어시스턴트입니다.
웹 디자인 스크린샷을 보고 React + TypeScript + Tailwind 코드를 생성합니다.

[규칙]
- 모든 text는 한국어로
- Tailwind CSS 사용 (인라인 스타일 최소화)
- 반응형 디자인 (sm/md/lg 브레이크포인트)
- 접근성 고려 (aria-*, role)
- 의미있는 컴포넌트 이름
- 한국어 주석 포함"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="Qwen2.5-VL 모델 경로")
    parser.add_argument("--data", required=True, help="JSONL (image_path + code)")
    parser.add_argument("--output", required=True)
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--max-length", type=int, default=4096)
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(" 비전 모델 웹디자인 학습 (이미지 → 코드)")
    logger.info("=" * 60)

    try:
        import torch
        from transformers import (
            AutoProcessor,
            AutoModelForCausalLM,
            BitsAndBytesConfig,
            TrainingArguments,
        )
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from trl import SFTTrainer
        from datasets import load_dataset
        from PIL import Image
    except ImportError as e:
        logger.error(f"필수 패키지 없음: {e}")
        logger.error("실행: pip install transformers peft trl bitsandbytes pillow qwen-vl-utils")
        sys.exit(1)

    # 4bit 양자화
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )

    logger.info("모델 로드 중 (Qwen2.5-VL)...")
    processor = AutoProcessor.from_pretrained(args.model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=bnb,
        device_map="auto",
        trust_remote_code=True,
    )

    model = prepare_model_for_kbit_training(model)

    # LoRA 설정 (비전 인코더는 동결)
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)

    # 데이터셋 준비
    logger.info(f"데이터 로드: {args.data}")

    def format_example(ex):
        """이미지 + 코드 쌍을 학습 포맷으로 변환."""
        image_path = ex.get("image_path") or ex.get("image")
        description = ex.get("description", "이 웹페이지를 HTML/CSS로 구현해주세요")
        code = ex.get("html") or ex.get("code", "")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image_path},
                    {"type": "text", "text": description},
                ],
            },
            {"role": "assistant", "content": f"```tsx\n{code}\n```"},
        ]

        # Processor로 변환
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        return {"text": text, "image": Image.open(image_path) if image_path else None}

    dataset = load_dataset("json", data_files=args.data, split="train")
    dataset = dataset.map(format_example, remove_columns=dataset.column_names)

    # 학습 설정
    training_args = TrainingArguments(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        logging_steps=10,
        save_steps=200,
        save_total_limit=3,
        bf16=True,
        max_grad_norm=0.3,
        optim="paged_adamw_8bit",
        report_to="none",
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        processing_class=processor.tokenizer,
    )

    logger.info("학습 시작!")
    trainer.train()

    model.save_pretrained(args.output)
    processor.save_pretrained(args.output)
    logger.info(f"✅ 완료: {args.output}")

    # 메타데이터
    metadata = {
        "base_model": args.model,
        "type": "vision-design",
        "task": "image-to-code",
        "data": args.data,
        "output_style": "React + TypeScript + Tailwind",
    }
    with open(os.path.join(args.output, "hwarang_metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)


if __name__ == "__main__":
    main()
