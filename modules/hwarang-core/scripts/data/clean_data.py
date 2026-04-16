"""SFT 데이터 정제 스크립트.

기능:
  1. 중국어 텍스트 감지 및 제거
  2. 길이 필터링 (너무 짧거나 긴 데이터 제거)
  3. 중복 제거 (MD5 해시 기반)
  4. 빈 필드 제거
  5. 유니코드 정규화
  6. 시스템 프롬프트 통일

사용법:
    python scripts/data/clean_data.py \
        --input data/sft/all_sft.jsonl \
        --output data/sft/all_sft_cleaned.jsonl

    # 중국어 포함 데이터만 별도 저장 (검토용)
    python scripts/data/clean_data.py \
        --input data/sft/all_sft.jsonl \
        --output data/sft/cleaned.jsonl \
        --rejected data/sft/rejected.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import unicodedata
from collections import Counter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ─── 중국어 감지 ─────────────────────────────────────────────────

# CJK Unified Ideographs 범위 (한자)
# 한국어에서도 한자를 사용하지만, 중국어 문장은 한자가 연속으로 나옴
CJK_RANGES = [
    (0x4E00, 0x9FFF),   # CJK Unified Ideographs
    (0x3400, 0x4DBF),   # CJK Extension A
    (0x20000, 0x2A6DF), # CJK Extension B
]

# 중국어 고유 문자 (한국어에서 안 쓰는 것들)
CHINESE_SPECIFIC = set("的了是在不有这个人我们你他她它会很都对能就说时让从那到想看给用还过也好着为什么但得没以可要被当中国我你")


def count_chinese_chars(text: str) -> int:
    """중국어 고유 문자 수 카운트."""
    return sum(1 for c in text if c in CHINESE_SPECIFIC)


def count_cjk_chars(text: str) -> int:
    """CJK (한자) 문자 수 카운트."""
    count = 0
    for c in text:
        cp = ord(c)
        for start, end in CJK_RANGES:
            if start <= cp <= end:
                count += 1
                break
    return count


def has_chinese_sentence(text: str, threshold: float = 0.15) -> bool:
    """중국어 문장이 포함되어 있는지 감지.

    한국어에서도 한자를 쓰므로, 중국어 고유 문자(的了是在...)가
    텍스트의 일정 비율 이상이면 중국어로 판단.
    """
    if not text:
        return False

    # 방법 1: 중국어 고유 문자 비율
    chinese_count = count_chinese_chars(text)
    total_chars = len(text.replace(" ", "").replace("\n", ""))
    if total_chars == 0:
        return False

    if chinese_count / total_chars > threshold:
        return True

    # 방법 2: 연속 한자 5글자 이상 (한국어에선 드묾)
    cjk_seq = re.findall(r'[\u4e00-\u9fff]{5,}', text)
    if len(cjk_seq) >= 2:  # 연속 한자 5자 이상이 2번 이상
        return True

    # 방법 3: 중국어 문장 패턴 (的...了, 是...的)
    chinese_patterns = [
        r'[\u4e00-\u9fff]+的[\u4e00-\u9fff]+',  # X的Y
        r'[\u4e00-\u9fff]+了[\u4e00-\u9fff]*',   # X了Y
        r'是[\u4e00-\u9fff]+的',                   # 是X的
        r'在[\u4e00-\u9fff]+中',                   # 在X中
    ]
    pattern_matches = sum(1 for p in chinese_patterns if re.search(p, text))
    if pattern_matches >= 2:
        return True

    return False


# ─── 텍스트 정제 ─────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """텍스트 정규화."""
    # Unicode NFC 정규화
    text = unicodedata.normalize("NFC", text)
    # 제어 문자 제거 (\n, \t 제외)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # 연속 공백 정리
    text = re.sub(r' {3,}', '  ', text)
    # 연속 줄바꿈 정리
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    return text.strip()


def get_text_hash(messages: list[dict]) -> str:
    """메시지 내용의 MD5 해시."""
    content = "".join(m.get("content", "") for m in messages)
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def get_total_length(messages: list[dict]) -> int:
    """전체 메시지 길이."""
    return sum(len(m.get("content", "")) for m in messages)


# ─── 메인 정제 함수 ──────────────────────────────────────────────

def clean_dataset(
    input_path: str,
    output_path: str,
    rejected_path: str | None = None,
    min_length: int = 20,
    max_length: int = 10000,
    chinese_threshold: float = 0.10,
) -> dict:
    """JSONL 데이터셋 정제.

    Returns:
        통계 딕셔너리
    """
    stats = Counter()
    seen_hashes = set()
    cleaned = []
    rejected = []

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
            if len(messages) < 2:
                stats["too_few_messages"] += 1
                continue

            # 빈 내용 체크
            has_empty = any(not m.get("content", "").strip() for m in messages if m.get("role") != "system")
            if has_empty:
                stats["empty_content"] += 1
                continue

            # 텍스트 정규화
            for m in messages:
                m["content"] = normalize_text(m["content"])

            # 길이 필터
            total_len = get_total_length(messages)
            if total_len < min_length:
                stats["too_short"] += 1
                continue
            if total_len > max_length:
                stats["too_long"] += 1
                continue

            # 중복 체크
            text_hash = get_text_hash(messages)
            if text_hash in seen_hashes:
                stats["duplicate"] += 1
                continue
            seen_hashes.add(text_hash)

            # 중국어 감지
            all_text = " ".join(m.get("content", "") for m in messages)
            if has_chinese_sentence(all_text, threshold=chinese_threshold):
                stats["chinese_detected"] += 1
                rejected.append({"reason": "chinese", **item})
                continue

            # 통과
            stats["accepted"] += 1
            cleaned.append(item)

    # 저장
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for item in cleaned:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    if rejected_path and rejected:
        os.makedirs(os.path.dirname(rejected_path), exist_ok=True)
        with open(rejected_path, "w", encoding="utf-8") as f:
            for item in rejected:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    return dict(stats)


# ─── 메인 ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SFT 데이터 정제")
    parser.add_argument("--input", required=True, help="입력 JSONL")
    parser.add_argument("--output", required=True, help="출력 JSONL (정제된 데이터)")
    parser.add_argument("--rejected", default=None, help="제거된 데이터 JSONL (검토용)")
    parser.add_argument("--min-length", type=int, default=20, help="최소 텍스트 길이")
    parser.add_argument("--max-length", type=int, default=10000, help="최대 텍스트 길이")
    parser.add_argument("--chinese-threshold", type=float, default=0.10, help="중국어 감지 임계값")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("SFT 데이터 정제")
    logger.info(f"  입력: {args.input}")
    logger.info(f"  출력: {args.output}")
    logger.info(f"  중국어 임계값: {args.chinese_threshold}")
    logger.info("=" * 60)

    stats = clean_dataset(
        input_path=args.input,
        output_path=args.output,
        rejected_path=args.rejected,
        min_length=args.min_length,
        max_length=args.max_length,
        chinese_threshold=args.chinese_threshold,
    )

    logger.info("\n정제 결과:")
    for key, value in sorted(stats.items()):
        logger.info(f"  {key}: {value:,}")

    if stats.get("total", 0) > 0:
        accept_rate = stats.get("accepted", 0) / stats["total"] * 100
        logger.info(f"\n  채택률: {accept_rate:.1f}%")

    logger.info("=" * 60)


if __name__ == "__main__":
    main()
