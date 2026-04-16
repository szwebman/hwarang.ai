"""DDP - Direct Distillation from Preferences

강한 모델(V3, Claude)의 응답을 약한 모델(Qwen 32B)에게 직접 증류.
RLHF보다 간단하고 빠름.

프로세스:
  1. 같은 프롬프트를 강한 모델에 입력
  2. 강한 모델 응답 수집 → "golden answer"
  3. 약한 모델이 golden answer를 타겟으로 SFT 학습

사용법:
    python scripts/advanced/train_ddp.py \\
        --teacher-endpoint http://v3-server:8000 \\
        --teacher-model deepseek-v3 \\
        --student-model /mnt/nvme2/hwarang/models/qwen2.5-32b \\
        --prompts data/prompts.jsonl \\
        --output /mnt/nvme2/hwarang/lora/distilled-v1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def collect_teacher_responses(
    endpoint: str,
    model: str,
    prompts: list[str],
    output_path: str,
    max_tokens: int = 2048,
):
    """교사 모델로부터 응답 수집."""
    import requests

    logger.info(f"교사 모델 응답 수집: {len(prompts)}개 프롬프트")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for i, prompt in enumerate(prompts):
            if i % 50 == 0:
                logger.info(f"  {i}/{len(prompts)}")

            try:
                r = requests.post(f"{endpoint}/v1/chat/completions", json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": max_tokens,
                }, timeout=120)
                if r.ok:
                    response = r.json()["choices"][0]["message"]["content"]
                    f.write(json.dumps({
                        "messages": [
                            {"role": "user", "content": prompt},
                            {"role": "assistant", "content": response},
                        ]
                    }, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.warning(f"실패: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--teacher-endpoint", required=True, help="교사 모델 vLLM 주소")
    parser.add_argument("--teacher-model", required=True, help="교사 모델 이름")
    parser.add_argument("--student-model", required=True, help="학생 모델 (QLoRA 학습 대상)")
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--teacher-data", default=None, help="교사 응답 저장 경로 (기본 auto)")
    parser.add_argument("--skip-collect", action="store_true", help="교사 수집 스킵 (이미 수집됨)")
    parser.add_argument("--limit", type=int, default=10000)
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(" DDP - Direct Distillation from Preferences")
    logger.info("=" * 60)
    logger.info(f"  교사: {args.teacher_model} @ {args.teacher_endpoint}")
    logger.info(f"  학생: {args.student_model}")

    teacher_data = args.teacher_data or f"{args.output}/teacher_responses.jsonl"

    # Step 1: 교사 응답 수집
    if not args.skip_collect:
        prompts = []
        with open(args.prompts, encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line.strip())
                    p = item.get("prompt") or item.get("question")
                    if p:
                        prompts.append(p)
                except Exception:
                    continue
                if len(prompts) >= args.limit:
                    break

        collect_teacher_responses(
            args.teacher_endpoint, args.teacher_model, prompts, teacher_data
        )
    else:
        logger.info(f"교사 수집 스킵, 기존 파일 사용: {teacher_data}")

    # Step 2: 학생 모델 SFT 학습 (기존 qlora_qwen.py 활용)
    logger.info("\n학생 모델 SFT 학습 시작...")
    cmd = f"""
        python scripts/qlora_qwen.py \\
            --model-path {args.student_model} \\
            --data {teacher_data} \\
            --output {args.output} \\
            --epochs 2 \\
            --lr 1e-4
    """
    logger.info(cmd)
    os.system(cmd)

    logger.info(f"\n✅ DDP 완료: {args.output}")


if __name__ == "__main__":
    main()
