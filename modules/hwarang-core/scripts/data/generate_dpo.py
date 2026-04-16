"""DPO (Direct Preference Optimization) 쌍 데이터 생성 스크립트.

기능:
  1. 기존 SFT 데이터에서 DPO 쌍 자동 생성
  2. 품질 기준으로 chosen/rejected 분류
  3. 의도적으로 나쁜 응답 생성 (규칙 기반)

DPO 데이터 형식:
  {"prompt": "질문", "chosen": "좋은 응답", "rejected": "나쁜 응답"}

사용법:
    python scripts/data/generate_dpo.py \
        --input data/sft/all_sft_cleaned.jsonl \
        --output data/dpo/dpo_pairs.jsonl \
        --max-pairs 10000
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ─── 품질 점수 계산 ──────────────────────────────────────────────

def score_response(response: str, question: str = "") -> float:
    """응답 품질 점수 (0~1)."""
    score = 0.5  # 기본 점수

    # 길이 점수 (너무 짧거나 길면 감점)
    rlen = len(response)
    if rlen < 10:
        score -= 0.3
    elif rlen < 50:
        score -= 0.1
    elif 100 <= rlen <= 2000:
        score += 0.1
    elif rlen > 5000:
        score -= 0.1

    # 코드 블록 포함 (코딩 질문에서 가산)
    if "```" in response:
        score += 0.15

    # 구조화된 응답 (마크다운, 리스트 등)
    if re.search(r'^\d+\.', response, re.MULTILINE):
        score += 0.05
    if re.search(r'^[-*]', response, re.MULTILINE):
        score += 0.05
    if "**" in response:
        score += 0.05

    # 한국어 비율
    korean_chars = len(re.findall(r'[\uac00-\ud7af]', response))
    total_alpha = len(re.findall(r'[a-zA-Z\uac00-\ud7af]', response))
    if total_alpha > 0:
        kr_ratio = korean_chars / total_alpha
        if kr_ratio > 0.3:  # 한국어 비율 높으면 가산
            score += 0.1

    # 중국어 포함 감점
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', response))
    if chinese_chars > 5:
        score -= 0.3

    # 면책 조항 포함 (법률/세무에서 가산)
    if any(w in response for w in ["상담하세요", "전문가", "참고용", "변호사", "세무사"]):
        score += 0.05

    # 에러/쓰레기 응답 감점
    if response.strip() in ("", ".", "...", "없음", "모름"):
        score = 0.0

    return max(0.0, min(1.0, score))


# ─── 나쁜 응답 생성 (규칙 기반) ──────────────────────────────────

def generate_bad_response(good_response: str, question: str = "") -> str:
    """좋은 응답에서 나쁜 응답을 생성."""
    strategies = [
        _truncate_response,
        _remove_structure,
        _add_wrong_language,
        _vague_response,
        _remove_code,
    ]

    # 랜덤 전략 선택
    strategy = random.choice(strategies)
    return strategy(good_response, question)


def _truncate_response(response: str, question: str) -> str:
    """응답을 중간에 잘라서 불완전하게."""
    cut_point = len(response) // 3
    if cut_point < 20:
        cut_point = min(20, len(response))
    return response[:cut_point] + "..."


def _remove_structure(response: str, question: str) -> str:
    """마크다운/구조 제거."""
    text = response
    text = re.sub(r'```[\s\S]*?```', '[코드 생략]', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'^\d+\.\s', '- ', text, flags=re.MULTILINE)
    text = re.sub(r'\n{2,}', '\n', text)
    return text.strip()


def _add_wrong_language(response: str, question: str) -> str:
    """중국어/영어를 섞어서 나쁜 응답."""
    lines = response.split('\n')
    result = []
    for i, line in enumerate(lines):
        if i % 3 == 0 and len(line) > 10:
            # 일부 문장을 영어로 대체
            result.append("I think this is a good question. Let me explain.")
        else:
            result.append(line)
    return '\n'.join(result)


def _vague_response(response: str, question: str) -> str:
    """모호한 응답 생성."""
    vague_templates = [
        "그건 상황에 따라 다릅니다.",
        "좀 더 구체적으로 질문해 주시면 답변드리겠습니다.",
        "네, 그렇습니다.",
        "관련 문서를 참고하시기 바랍니다.",
        "그 부분은 잘 모르겠습니다. 다른 질문이 있으시면 말씀해 주세요.",
    ]
    return random.choice(vague_templates)


def _remove_code(response: str, question: str) -> str:
    """코드 블록을 제거하고 설명만 남김."""
    text = re.sub(r'```[\s\S]*?```', '', response)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip() or "코드 예시는 생략합니다."


# ─── DPO 쌍 생성 ─────────────────────────────────────────────────

def generate_dpo_pairs(input_path: str, max_pairs: int = 10000) -> list[dict]:
    """SFT 데이터에서 DPO 쌍 생성."""
    pairs = []
    all_items = []

    # 데이터 로드
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                messages = item.get("messages", [])
                if len(messages) >= 2:
                    all_items.append(messages)
            except json.JSONDecodeError:
                continue

    logger.info(f"로드: {len(all_items)}개 대화")

    # 품질 점수 계산 및 정렬
    scored_items = []
    for messages in all_items:
        user_msgs = [m for m in messages if m["role"] == "user"]
        asst_msgs = [m for m in messages if m["role"] == "assistant"]
        if user_msgs and asst_msgs:
            question = user_msgs[0]["content"]
            response = asst_msgs[0]["content"]
            score = score_response(response, question)
            scored_items.append((question, response, score))

    scored_items.sort(key=lambda x: x[2], reverse=True)

    # 방법 1: 상위 응답 vs 나쁜 응답 생성
    count = 0
    for question, good_response, score in scored_items:
        if count >= max_pairs:
            break
        if score < 0.4:  # 품질 낮은 건 건너뜀
            continue

        bad_response = generate_bad_response(good_response, question)

        pairs.append({
            "prompt": question,
            "chosen": good_response,
            "rejected": bad_response,
        })
        count += 1

    # 방법 2: 같은 질문에 다른 품질 응답 쌍
    # (같은 질문이 여러 개 있을 때)
    question_groups: dict[str, list] = {}
    for q, r, s in scored_items:
        q_short = q[:100]  # 앞 100자로 그룹핑
        if q_short not in question_groups:
            question_groups[q_short] = []
        question_groups[q_short].append((r, s))

    for q_short, responses in question_groups.items():
        if len(responses) >= 2 and count < max_pairs:
            responses.sort(key=lambda x: x[1], reverse=True)
            best = responses[0]
            worst = responses[-1]
            if best[1] - worst[1] > 0.2:  # 품질 차이가 충분할 때만
                pairs.append({
                    "prompt": q_short,
                    "chosen": best[0],
                    "rejected": worst[0],
                })
                count += 1

    random.shuffle(pairs)
    return pairs[:max_pairs]


# ─── 메인 ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="DPO 쌍 데이터 생성")
    parser.add_argument("--input", required=True, help="입력 SFT JSONL")
    parser.add_argument("--output", required=True, help="출력 DPO JSONL")
    parser.add_argument("--max-pairs", type=int, default=10000, help="최대 쌍 수")
    parser.add_argument("--seed", type=int, default=42, help="랜덤 시드")
    args = parser.parse_args()

    random.seed(args.seed)

    logger.info("=" * 60)
    logger.info("DPO 쌍 데이터 생성")
    logger.info(f"  입력: {args.input}")
    logger.info(f"  출력: {args.output}")
    logger.info(f"  최대 쌍: {args.max_pairs:,}")
    logger.info("=" * 60)

    pairs = generate_dpo_pairs(args.input, max_pairs=args.max_pairs)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for pair in pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    logger.info(f"\n총 {len(pairs):,}개 DPO 쌍 생성 → {args.output}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
