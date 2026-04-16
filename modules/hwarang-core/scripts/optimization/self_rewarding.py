"""HSR - Hwarang Self-Rewarding

화랑 AI 최적화 기법 #7

AI가 스스로 답변 쌍을 만들고 평가 → DPO 학습 데이터 자동 생성.
사람 레이블링 최소화.

프로세스:
  1. 프롬프트로 N개 응답 생성 (temperature 다르게)
  2. AI가 각 응답 평가 (1~10점)
  3. 점수 차이 큰 쌍 → DPO chosen/rejected
  4. DPO 학습 → 개선된 모델
  5. 반복 (self-improvement loop)

사용법:
    python scripts/optimization/self_rewarding.py \\
        --model http://localhost:8000 \\
        --prompts data/prompts/sft_prompts.jsonl \\
        --output data/dpo/self_rewarded.jsonl \\
        --iterations 3
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ─── AI 평가 프롬프트 ────────────────────────────────────────

JUDGE_PROMPT_TEMPLATE = """다음 질문과 응답을 평가해주세요.

[질문]
{question}

[응답]
{response}

다음 기준으로 1~10점 평가하세요:
- 정확성 (사실 오류 없음)
- 유용성 (실제 도움이 됨)
- 명확성 (이해하기 쉬움)
- 한국어 자연스러움
- 중국어/외국어 혼용 없음

[출력 형식 - 반드시 JSON]
{{
  "score": 1~10,
  "strengths": ["장점1", "장점2"],
  "weaknesses": ["단점1", "단점2"],
  "summary": "간단 평가"
}}

JSON만 출력:"""


def call_vllm(
    endpoint: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """vLLM API 호출."""
    import requests

    try:
        resp = requests.post(
            f"{endpoint}/v1/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=60,
        )
        if resp.ok:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"API 호출 실패: {e}")
    return ""


def generate_candidates(
    endpoint: str,
    model: str,
    question: str,
    n: int = 4,
) -> list[dict]:
    """다양한 temperature로 N개 응답 생성."""
    temperatures = [0.3, 0.7, 1.0, 1.2][:n]
    candidates = []

    for temp in temperatures:
        response = call_vllm(
            endpoint,
            model,
            [{"role": "user", "content": question}],
            temperature=temp,
        )
        if response:
            candidates.append({"response": response, "temperature": temp})

    return candidates


def judge_response(
    endpoint: str,
    model: str,
    question: str,
    response: str,
) -> dict:
    """AI가 응답을 평가."""
    judge_prompt = JUDGE_PROMPT_TEMPLATE.format(question=question, response=response)

    result_text = call_vllm(
        endpoint,
        model,
        [{"role": "user", "content": judge_prompt}],
        temperature=0.1,  # 일관된 평가
        max_tokens=500,
    )

    # JSON 파싱
    try:
        # JSON 블록 추출
        import re
        json_match = re.search(r'\{[\s\S]*\}', result_text)
        if json_match:
            return json.loads(json_match.group(0))
    except Exception as e:
        logger.debug(f"JSON 파싱 실패: {e}")

    return {"score": 5, "summary": "parse_failed"}


def create_dpo_pair(
    question: str,
    candidates: list[dict],
    min_score_diff: float = 2.0,
) -> dict | None:
    """점수 차이 큰 쌍으로 DPO 데이터 생성."""
    if len(candidates) < 2:
        return None

    # 점수순 정렬
    scored = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)
    best = scored[0]
    worst = scored[-1]

    diff = best.get("score", 0) - worst.get("score", 0)
    if diff < min_score_diff:
        return None

    return {
        "prompt": question,
        "chosen": best["response"],
        "rejected": worst["response"],
        "metadata": {
            "chosen_score": best.get("score"),
            "rejected_score": worst.get("score"),
            "score_diff": diff,
        },
    }


def self_rewarding_iteration(
    endpoint: str,
    model: str,
    prompts: list[str],
    output_path: str,
    candidates_per_prompt: int = 4,
) -> int:
    """한 번의 Self-Rewarding 반복."""
    pairs_created = 0
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "a", encoding="utf-8") as fout:
        for i, prompt in enumerate(prompts):
            logger.info(f"  [{i + 1}/{len(prompts)}] 생성 중...")

            # 1. 후보 생성
            candidates = generate_candidates(endpoint, model, prompt, candidates_per_prompt)
            if len(candidates) < 2:
                continue

            # 2. 각 후보 평가
            for cand in candidates:
                judgment = judge_response(endpoint, model, prompt, cand["response"])
                cand["score"] = judgment.get("score", 5)
                cand["judgment"] = judgment

            # 3. DPO 쌍 생성
            pair = create_dpo_pair(prompt, candidates)
            if pair:
                fout.write(json.dumps(pair, ensure_ascii=False) + "\n")
                fout.flush()
                pairs_created += 1

            time.sleep(0.3)  # Rate limit

    return pairs_created


def main():
    parser = argparse.ArgumentParser(description="Hwarang Self-Rewarding")
    parser.add_argument("--endpoint", default="http://localhost:8000", help="vLLM 엔드포인트")
    parser.add_argument("--model", required=True, help="모델 이름 또는 경로")
    parser.add_argument("--prompts", required=True, help="입력 프롬프트 JSONL (각 라인에 {prompt: ...})")
    parser.add_argument("--output", required=True, help="출력 DPO JSONL")
    parser.add_argument("--iterations", type=int, default=1, help="반복 횟수")
    parser.add_argument("--candidates", type=int, default=4, help="프롬프트당 생성 응답 수")
    parser.add_argument("--limit", type=int, default=1000, help="최대 프롬프트 수")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(" HSR - Hwarang Self-Rewarding")
    logger.info("=" * 60)
    logger.info(f"  엔드포인트: {args.endpoint}")
    logger.info(f"  모델:       {args.model}")
    logger.info(f"  프롬프트:   {args.prompts}")
    logger.info(f"  출력:       {args.output}")
    logger.info(f"  반복:       {args.iterations}")
    logger.info(f"  후보/프롬프트: {args.candidates}")
    logger.info("=" * 60)

    # 프롬프트 로드
    prompts = []
    with open(args.prompts, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                # 다양한 포맷 지원
                if "prompt" in item:
                    prompts.append(item["prompt"])
                elif "messages" in item:
                    user_msg = next((m["content"] for m in item["messages"] if m["role"] == "user"), None)
                    if user_msg:
                        prompts.append(user_msg)
                elif "question" in item:
                    prompts.append(item["question"])
            except json.JSONDecodeError:
                continue

            if len(prompts) >= args.limit:
                break

    logger.info(f"\n로드된 프롬프트: {len(prompts)}개")

    total_pairs = 0
    for iter_num in range(args.iterations):
        logger.info(f"\n{'=' * 60}")
        logger.info(f" Iteration {iter_num + 1}/{args.iterations}")
        logger.info(f"{'=' * 60}")

        pairs = self_rewarding_iteration(
            args.endpoint, args.model, prompts, args.output, args.candidates
        )
        total_pairs += pairs
        logger.info(f"\n  이번 반복: {pairs}개 쌍 생성")

    logger.info("\n" + "=" * 60)
    logger.info(f" ✅ Self-Rewarding 완료!")
    logger.info(f"  총 DPO 쌍: {total_pairs}")
    logger.info(f"  파일:      {args.output}")
    logger.info("=" * 60)
    logger.info("\n다음 단계:")
    logger.info(f"  python scripts/align.py --data {args.output} --output ...")


if __name__ == "__main__":
    main()
