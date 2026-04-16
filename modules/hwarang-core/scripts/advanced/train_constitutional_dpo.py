"""Constitutional DPO (K-CDPO)

DPO + Constitutional AI (KCAI) 결합.
AI가 KCAI 헌법에 따라 스스로 chosen/rejected 분류.
사람 레이블 불필요.

프로세스:
  1. 프롬프트에 대해 응답 N개 생성
  2. KCAI 헌법 기반 자기 평가
  3. 위반 적은 응답 = chosen, 많은 응답 = rejected
  4. DPO 학습

사용법:
    python scripts/advanced/train_constitutional_dpo.py \\
        --model /mnt/nvme2/hwarang/models/qwen2.5-32b \\
        --prompts data/prompts.jsonl \\
        --output /mnt/nvme2/hwarang/lora/cdpo-v1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# 화랑 헌법 (KCAI 동일)
HWARANG_CONSTITUTION = """
[화랑 AI 헌법]
1. 한국어 질문은 한국어로만 답변 (중국어 섞지 말 것)
2. 존댓말 사용 (반말 명시적 요청 시에만 반말)
3. 법률/세무 답변 시 면책조항 포함, 전문가 상담 권유
4. 개인정보/불법행위 돕지 않음
5. 정확하지 않은 정보는 "확실하지 않다" 표기
6. 차별/편견 배제
"""


def generate_candidates(endpoint, model, prompt, n=4):
    """다양한 temperature로 응답 생성."""
    import requests

    candidates = []
    for temp in [0.3, 0.7, 1.0, 1.2][:n]:
        try:
            r = requests.post(f"{endpoint}/v1/chat/completions", json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temp,
                "max_tokens": 1024,
            }, timeout=60)
            if r.ok:
                candidates.append(r.json()["choices"][0]["message"]["content"])
        except Exception:
            pass
    return candidates


def critique_with_constitution(endpoint, model, prompt, response):
    """헌법 기반 자기 비평 → 위반 점수 반환 (0~10, 낮을수록 좋음)."""
    import requests

    critique_prompt = f"""{HWARANG_CONSTITUTION}

[질문] {prompt}

[응답] {response}

이 응답이 위 헌법을 얼마나 위반하는지 0~10으로 평가하세요.
0 = 완벽 준수, 10 = 심각한 위반.

[출력] 숫자만: """

    try:
        r = requests.post(f"{endpoint}/v1/chat/completions", json={
            "model": model,
            "messages": [{"role": "user", "content": critique_prompt}],
            "temperature": 0.1,
            "max_tokens": 10,
        }, timeout=30)
        if r.ok:
            text = r.json()["choices"][0]["message"]["content"]
            import re
            m = re.search(r"(\d+(?:\.\d+)?)", text)
            if m:
                return float(m.group(1))
    except Exception:
        pass
    return 5.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="vLLM 모델 이름")
    parser.add_argument("--endpoint", default="http://localhost:8000")
    parser.add_argument("--prompts", required=True, help="JSONL 프롬프트")
    parser.add_argument("--output-data", required=True, help="생성된 DPO 데이터 저장")
    parser.add_argument("--candidates", type=int, default=4)
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(" Constitutional DPO 데이터 생성")
    logger.info("=" * 60)

    # 프롬프트 로드
    prompts = []
    with open(args.prompts, encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
                p = item.get("prompt") or item.get("question")
                if p:
                    prompts.append(p)
            except Exception:
                continue
            if len(prompts) >= args.limit:
                break

    logger.info(f"프롬프트: {len(prompts)}개")

    os.makedirs(os.path.dirname(args.output_data), exist_ok=True)
    pairs_count = 0

    with open(args.output_data, "w", encoding="utf-8") as fout:
        for i, prompt in enumerate(prompts):
            if i % 50 == 0:
                logger.info(f"  진행: {i}/{len(prompts)} (생성된 쌍: {pairs_count})")

            # 1. 응답 생성
            candidates = generate_candidates(args.endpoint, args.model, prompt, args.candidates)
            if len(candidates) < 2:
                continue

            # 2. 각 응답 헌법 평가
            scored = []
            for c in candidates:
                score = critique_with_constitution(args.endpoint, args.model, prompt, c)
                scored.append((c, score))

            # 3. 최저/최고 위반 응답 쌍
            scored.sort(key=lambda x: x[1])
            chosen = scored[0][0]    # 가장 헌법 잘 지킴
            rejected = scored[-1][0]  # 가장 헌법 위반

            if scored[-1][1] - scored[0][1] < 1.0:
                continue  # 차이 작으면 스킵

            # 4. DPO 쌍 저장
            fout.write(json.dumps({
                "prompt": prompt,
                "chosen": chosen,
                "rejected": rejected,
                "chosen_violation": scored[0][1],
                "rejected_violation": scored[-1][1],
            }, ensure_ascii=False) + "\n")
            pairs_count += 1

    logger.info(f"\n✅ 완료: {pairs_count}개 DPO 쌍 → {args.output_data}")
    logger.info("\n다음 단계:")
    logger.info(f"  python scripts/align.py --data {args.output_data} --output ...")


if __name__ == "__main__":
    main()
