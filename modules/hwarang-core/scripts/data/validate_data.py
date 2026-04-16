"""데이터 품질 검증 스크립트.

SFT/DPO 데이터의 품질을 분석하고 리포트 생성.

사용법:
    python scripts/data/validate_data.py --input data/sft/all_sft_cleaned.jsonl
    python scripts/data/validate_data.py --input data/dpo/dpo_pairs.jsonl --format dpo
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def detect_language(text: str) -> str:
    """텍스트의 주요 언어 감지."""
    korean = len(re.findall(r'[\uac00-\ud7af]', text))
    chinese = len(re.findall(r'[\u4e00-\u9fff]', text))
    english = len(re.findall(r'[a-zA-Z]', text))
    total = korean + chinese + english
    if total == 0:
        return "unknown"
    if korean / total > 0.4:
        return "ko"
    if chinese / total > 0.3:
        return "zh"
    if english / total > 0.5:
        return "en"
    return "mixed"


def validate_sft(input_path: str):
    """SFT 데이터 검증."""
    stats = Counter()
    lengths = []
    turn_counts = []
    roles_found = Counter()
    languages = Counter()
    has_system = 0
    has_code = 0
    samples_by_quality = {"good": 0, "medium": 0, "poor": 0}

    with open(input_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            stats["total"] += 1

            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                stats["invalid_json"] += 1
                continue

            messages = item.get("messages", [])
            if not messages:
                stats["no_messages"] += 1
                continue

            # 턴 수
            turn_counts.append(len(messages))

            # 역할 분석
            for m in messages:
                role = m.get("role", "unknown")
                roles_found[role] += 1
                if role == "system":
                    has_system += 1

            # 전체 텍스트
            all_text = " ".join(m.get("content", "") for m in messages)
            total_len = len(all_text)
            lengths.append(total_len)

            # 언어 감지
            lang = detect_language(all_text)
            languages[lang] += 1

            # 코드 포함 여부
            if "```" in all_text:
                has_code += 1

            # 품질 분류
            asst_msgs = [m for m in messages if m.get("role") == "assistant"]
            if asst_msgs:
                asst_len = sum(len(m["content"]) for m in asst_msgs)
                if asst_len > 200 and ("```" in all_text or "**" in all_text):
                    samples_by_quality["good"] += 1
                elif asst_len > 50:
                    samples_by_quality["medium"] += 1
                else:
                    samples_by_quality["poor"] += 1

    # 리포트 출력
    total = stats["total"]
    print("\n" + "=" * 60)
    print(f"SFT 데이터 검증 리포트: {input_path}")
    print("=" * 60)

    print(f"\n총 샘플 수: {total:,}")
    if stats["invalid_json"]:
        print(f"  JSON 오류: {stats['invalid_json']:,}")
    if stats["no_messages"]:
        print(f"  메시지 없음: {stats['no_messages']:,}")

    print(f"\n--- 메시지 분석 ---")
    print(f"  시스템 프롬프트 포함: {has_system:,} ({has_system/max(total,1)*100:.1f}%)")
    print(f"  코드 블록 포함: {has_code:,} ({has_code/max(total,1)*100:.1f}%)")
    print(f"  평균 턴 수: {sum(turn_counts)/max(len(turn_counts),1):.1f}")
    print(f"  역할 분포: {dict(roles_found)}")

    print(f"\n--- 길이 분석 ---")
    if lengths:
        lengths.sort()
        print(f"  평균: {sum(lengths)/len(lengths):.0f}자")
        print(f"  중앙값: {lengths[len(lengths)//2]:,}자")
        print(f"  최소: {lengths[0]:,}자")
        print(f"  최대: {lengths[-1]:,}자")
        print(f"  P10: {lengths[len(lengths)//10]:,}자")
        print(f"  P90: {lengths[9*len(lengths)//10]:,}자")

    print(f"\n--- 언어 분포 ---")
    for lang, count in languages.most_common():
        label = {"ko": "한국어", "en": "영어", "zh": "중국어", "mixed": "혼합", "unknown": "불명"}.get(lang, lang)
        print(f"  {label}: {count:,} ({count/max(total,1)*100:.1f}%)")

    print(f"\n--- 품질 분포 ---")
    for quality, count in samples_by_quality.items():
        label = {"good": "우수", "medium": "보통", "poor": "미흡"}.get(quality, quality)
        print(f"  {label}: {count:,} ({count/max(total,1)*100:.1f}%)")

    # 경고
    print(f"\n--- 경고 ---")
    warnings = 0
    if languages.get("zh", 0) > 0:
        print(f"  ⚠️ 중국어 데이터 {languages['zh']}개 발견!")
        warnings += 1
    if samples_by_quality["poor"] > total * 0.2:
        print(f"  ⚠️ 미흡 품질 데이터 {samples_by_quality['poor']/total*100:.0f}% (20% 초과)")
        warnings += 1
    if has_system < total * 0.5:
        print(f"  ⚠️ 시스템 프롬프트 없는 데이터 {(total-has_system)/total*100:.0f}%")
        warnings += 1
    if warnings == 0:
        print("  ✓ 경고 없음")

    print("=" * 60)


def validate_dpo(input_path: str):
    """DPO 데이터 검증."""
    total = 0
    chosen_longer = 0
    avg_chosen_len = 0
    avg_rejected_len = 0

    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            total += 1
            chosen = item.get("chosen", "")
            rejected = item.get("rejected", "")
            avg_chosen_len += len(chosen)
            avg_rejected_len += len(rejected)
            if len(chosen) > len(rejected):
                chosen_longer += 1

    print("\n" + "=" * 60)
    print(f"DPO 데이터 검증 리포트: {input_path}")
    print("=" * 60)
    print(f"\n총 쌍 수: {total:,}")
    if total > 0:
        print(f"  chosen 평균 길이: {avg_chosen_len/total:.0f}자")
        print(f"  rejected 평균 길이: {avg_rejected_len/total:.0f}자")
        print(f"  chosen이 더 긴 비율: {chosen_longer/total*100:.1f}%")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="데이터 품질 검증")
    parser.add_argument("--input", required=True, help="입력 JSONL")
    parser.add_argument("--format", choices=["sft", "dpo"], default="sft", help="데이터 형식")
    args = parser.parse_args()

    if args.format == "sft":
        validate_sft(args.input)
    else:
        validate_dpo(args.input)


if __name__ == "__main__":
    main()
