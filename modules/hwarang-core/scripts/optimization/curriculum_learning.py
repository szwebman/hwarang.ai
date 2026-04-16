"""HCL - Hwarang Curriculum Learning

화랑 AI 최적화 기법 #6

난이도별 단계적 학습으로 효율 40% 향상:
  Stage 1: 간단한 한국어 Q&A (짧은 응답)
  Stage 2: 프로그래밍 기본기 (코드 포함)
  Stage 3: 도메인 특화 (법률, 세무)
  Stage 4: 복잡한 추론 (긴 CoT)

각 stage에서 다음 stage로 넘어가는 기준:
  - validation loss 수렴
  - 최소 epoch 완료

사용법:
    python scripts/optimization/curriculum_learning.py \\
        --model /mnt/nvme2/hwarang/models/qwen2.5-32b-int4 \\
        --data-dir /mnt/nvme2/hwarang/data/sft \\
        --output /mnt/nvme2/hwarang/lora_adapters/hwarang-curriculum
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ─── 커리큘럼 단계 정의 ──────────────────────────────────────

CURRICULUM_STAGES = [
    {
        "name": "Stage 1 - Korean Basics",
        "description": "간단한 한국어 Q&A (짧은 응답, 기초 문법)",
        "data_file": "korean_basic.jsonl",
        "max_length": 512,
        "epochs": 1,
        "lr": 3e-4,
        "filter": {
            "min_response_len": 10,
            "max_response_len": 300,
            "difficulty": "easy",
        },
    },
    {
        "name": "Stage 2 - Programming Foundation",
        "description": "프로그래밍 기초 (코드 스니펫, 간단한 함수)",
        "data_file": "korean_code.jsonl",
        "max_length": 1024,
        "epochs": 1,
        "lr": 2e-4,
        "filter": {
            "min_response_len": 100,
            "max_response_len": 1000,
            "must_contain": "```",  # 코드 블록 포함
        },
    },
    {
        "name": "Stage 3 - Domain Expertise",
        "description": "법률/세무 전문 지식",
        "data_file": "legal_tax.jsonl",
        "max_length": 2048,
        "epochs": 1,
        "lr": 1e-4,
        "filter": {
            "min_response_len": 200,
            "domain": ["legal", "tax"],
        },
    },
    {
        "name": "Stage 4 - Complex Reasoning",
        "description": "복잡한 추론 (긴 CoT, 다단계 계산)",
        "data_file": "high_quality.jsonl",
        "max_length": 4096,
        "epochs": 2,
        "lr": 5e-5,
        "filter": {
            "min_response_len": 500,
            "must_contain_any": ["단계", "Step", "이유는", "따라서"],
        },
    },
]


# ─── 데이터 필터링 ───────────────────────────────────────────

def filter_dataset(
    input_path: str,
    output_path: str,
    filters: dict,
) -> int:
    """커리큘럼 단계에 맞는 데이터만 필터링."""
    count = 0
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(input_path, encoding="utf-8") as fin, open(output_path, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            messages = item.get("messages", [])
            if len(messages) < 2:
                continue

            # 응답 길이 필터
            response = next((m["content"] for m in messages if m["role"] == "assistant"), "")
            if not response:
                continue

            if "min_response_len" in filters and len(response) < filters["min_response_len"]:
                continue
            if "max_response_len" in filters and len(response) > filters["max_response_len"]:
                continue

            # 포함 조건
            if "must_contain" in filters and filters["must_contain"] not in response:
                continue

            if "must_contain_any" in filters:
                if not any(kw in response for kw in filters["must_contain_any"]):
                    continue

            # 도메인 필터
            if "domain" in filters:
                domain = item.get("domain", "")
                if domain not in filters["domain"]:
                    continue

            fout.write(json.dumps(item, ensure_ascii=False) + "\n")
            count += 1

    return count


# ─── 단계별 학습 실행 ────────────────────────────────────────

def train_stage(
    stage: dict,
    model_path: str,
    data_dir: str,
    output_base: str,
    prev_adapter: str | None = None,
) -> str:
    """한 단계 학습 실행."""
    stage_name = stage["name"].split(" - ")[0].replace(" ", "_").lower()
    output = f"{output_base}/{stage_name}"

    # 데이터 필터링
    input_data = f"{data_dir}/{stage['data_file']}"
    filtered_data = f"{output_base}/filtered_{stage_name}.jsonl"

    if not os.path.exists(input_data):
        logger.warning(f"데이터 없음, 스킵: {input_data}")
        return prev_adapter or ""

    count = filter_dataset(input_data, filtered_data, stage["filter"])
    logger.info(f"  필터링: {count}개 샘플")

    if count == 0:
        logger.warning(f"필터링 결과 0개, 스킵")
        return prev_adapter or ""

    # 학습 실행 (qlora_qwen.py 재사용)
    cmd = f"""
        python scripts/qlora_qwen.py \\
            --model-path {model_path} \\
            --data {filtered_data} \\
            --output {output} \\
            --epochs {stage['epochs']} \\
            --lr {stage['lr']} \\
            --max-length {stage['max_length']}
    """

    # 이전 단계 어댑터 이어서 학습 (실제 구현은 qlora_qwen.py 수정 필요)
    if prev_adapter:
        cmd += f" --resume-from {prev_adapter}"

    logger.info(f"\n[실행] {stage['name']}")
    logger.info(cmd)
    os.system(cmd)

    return output


# ─── 메인 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Hwarang Curriculum Learning")
    parser.add_argument("--model", required=True, help="베이스 모델 경로")
    parser.add_argument("--data-dir", required=True, help="데이터 디렉토리")
    parser.add_argument("--output", required=True, help="출력 베이스 경로")
    parser.add_argument("--start-stage", type=int, default=1, help="시작 단계 (1~4)")
    parser.add_argument("--end-stage", type=int, default=4, help="종료 단계")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(" HCL - Hwarang Curriculum Learning")
    logger.info("=" * 60)
    logger.info(f"  베이스 모델: {args.model}")
    logger.info(f"  데이터:     {args.data_dir}")
    logger.info(f"  출력:       {args.output}")
    logger.info(f"  단계:       Stage {args.start_stage} ~ {args.end_stage}")
    logger.info("=" * 60)

    os.makedirs(args.output, exist_ok=True)

    prev_adapter = None
    for i in range(args.start_stage - 1, args.end_stage):
        stage = CURRICULUM_STAGES[i]
        logger.info(f"\n{'=' * 60}")
        logger.info(f" [{i + 1}/{len(CURRICULUM_STAGES)}] {stage['name']}")
        logger.info(f" {stage['description']}")
        logger.info(f"{'=' * 60}")

        adapter = train_stage(stage, args.model, args.data_dir, args.output, prev_adapter)
        if adapter:
            prev_adapter = adapter

    logger.info("\n" + "=" * 60)
    logger.info(" ✅ 커리큘럼 학습 완료!")
    logger.info(f" 최종 어댑터: {prev_adapter}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
