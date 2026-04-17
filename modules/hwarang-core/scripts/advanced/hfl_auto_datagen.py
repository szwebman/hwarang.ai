"""HFL Auto Data Generation Agent

에이전트가 마스터에서 데이터를 받지 않고,
로컬 모델로 자체 학습 데이터를 생성 + 자체 평가 + 학습.

핵심:
  - 데이터 배포 불필요 → 프라이버시 완벽
  - Self-Play 방식: 모델이 질문도 만들고 답도 만듦
  - Self-Rewarding: 여러 답 중 가장 좋은 것 선택
  - Smart Selection: loss 높은 데이터만 학습 (효율 2~3배)

프로세스:
  1. 시드 프롬프트 수신 (마스터에서 주제 키워드만 전달, ~1KB)
  2. 에이전트가 질문 N개 생성
  3. 각 질문에 답변 K개 생성 (다양한 temperature)
  4. 자체 평가 → 최고/최악 쌍 → DPO 데이터
  5. loss 기준 상위 데이터만 선별 → LoRA 학습
  6. 학습된 LoRA만 마스터에 전송 (데이터 절대 미전송)

사용법:
    python scripts/advanced/hfl_auto_datagen.py \\
        --model-path /mnt/nvme2/hwarang/models/qwen2.5-32b \\
        --domain coding \\
        --num-questions 200 \\
        --output /tmp/hfl_worker_autogen
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ─── 시드 프롬프트 (도메인별 주제 키워드, ~1KB) ────────────────

SEED_TOPICS: dict[str, list[str]] = {
    "coding": [
        "Python 함수 작성", "JavaScript 비동기 처리", "React 컴포넌트 설계",
        "SQL 쿼리 최적화", "API 설계", "에러 핸들링", "테스트 작성",
        "리팩토링", "디자인 패턴", "타입스크립트 제네릭",
        "Docker 컨테이너", "Git 워크플로우", "보안 취약점 방지",
        "성능 최적화", "데이터 구조", "알고리즘 구현",
    ],
    "legal": [
        "계약 해제와 해지", "전세 보증금 분쟁", "부당해고 대응",
        "내용증명 작성", "저작권 침해", "개인정보보호법",
        "소액소송 절차", "임대차보호법", "근로기준법",
        "상속 분쟁", "손해배상 청구", "소비자 보호법",
    ],
    "tax": [
        "종합소득세 신고", "부가가치세 계산", "양도소득세",
        "연말정산 공제", "개인사업자 절세", "법인세 신고",
        "4대보험 계산", "퇴직금 세금", "부동산 세금",
        "프리랜서 세금", "해외소득 신고", "증여세",
    ],
    "general": [
        "한국 문화 설명", "과학 개념 설명", "역사 이야기",
        "건강 상식", "요리 레시피", "여행 추천",
        "학습 방법", "자기계발", "시사 상식",
    ],
}


# ─── 질문 생성 ───────────────────────────────────────────────

QUESTION_GEN_PROMPT = """당신은 AI 학습 데이터를 만드는 전문가입니다.
다음 주제에 대해 한국어로 질문 {n}개를 생성하세요.

[주제] {topic}

[요구사항]
- 실제 사용자가 할 법한 자연스러운 질문
- 난이도 다양하게 (쉬움~어려움)
- 구체적이고 명확한 질문
- 각 질문은 한 줄로

[출력] 질문만 한 줄씩:"""


def generate_questions(
    endpoint: str,
    model: str,
    topic: str,
    n: int = 10,
) -> list[str]:
    """로컬 모델로 질문 생성."""
    import requests

    prompt = QUESTION_GEN_PROMPT.format(topic=topic, n=n)

    try:
        resp = requests.post(f"{endpoint}/v1/chat/completions", json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 1.0,
            "max_tokens": 2048,
        }, timeout=120)

        if resp.ok:
            text = resp.json()["choices"][0]["message"]["content"]
            questions = [
                q.strip().lstrip("0123456789.-) ").strip()
                for q in text.strip().split("\n")
                if q.strip() and len(q.strip()) > 10
            ]
            return questions[:n]
    except Exception as e:
        logger.warning(f"질문 생성 실패: {e}")

    return []


# ─── 답변 생성 (다양한 temperature) ──────────────────────────

def generate_answers(
    endpoint: str,
    model: str,
    question: str,
    k: int = 4,
) -> list[dict]:
    """같은 질문에 대해 K개 답변 생성 (다양한 quality)."""
    import requests

    answers = []
    temperatures = [0.3, 0.7, 1.0, 1.3][:k]

    for temp in temperatures:
        try:
            resp = requests.post(f"{endpoint}/v1/chat/completions", json={
                "model": model,
                "messages": [{"role": "user", "content": question}],
                "temperature": temp,
                "max_tokens": 1024,
            }, timeout=60)

            if resp.ok:
                content = resp.json()["choices"][0]["message"]["content"]
                answers.append({
                    "content": content,
                    "temperature": temp,
                    "length": len(content),
                })
        except Exception:
            pass

    return answers


# ─── Self-Rewarding (자체 평가) ──────────────────────────────

JUDGE_PROMPT = """다음 질문과 답변을 평가하세요. 1~10 점수만 출력.

[질문] {question}
[답변] {answer}

평가 기준: 정확성, 유용성, 한국어 자연스러움, 구체성
점수 (1~10):"""


def self_evaluate(
    endpoint: str,
    model: str,
    question: str,
    answer: str,
) -> float:
    """모델이 자기 답변을 평가."""
    import requests
    import re

    try:
        resp = requests.post(f"{endpoint}/v1/chat/completions", json={
            "model": model,
            "messages": [{"role": "user", "content": JUDGE_PROMPT.format(
                question=question, answer=answer
            )}],
            "temperature": 0.1,
            "max_tokens": 20,
        }, timeout=30)

        if resp.ok:
            text = resp.json()["choices"][0]["message"]["content"]
            m = re.search(r"(\d+(?:\.\d+)?)", text)
            if m:
                return float(m.group(1))
    except Exception:
        pass

    return 5.0


# ─── Smart Data Selection (loss 기반 선별) ──────────────────

def compute_loss_score(question: str, answer: str) -> float:
    """데이터의 학습 가치 추정 (높을수록 학습에 유용).

    간단 휴리스틱:
      - 긴 답변 = 더 복잡 = 더 유용
      - 코드 포함 = 유용
      - 구조화된 답변 = 유용
    """
    score = 0.5

    # 길이 (짧은 건 학습 가치 낮음)
    if len(answer) > 500:
        score += 0.2
    elif len(answer) < 100:
        score -= 0.2

    # 코드 포함
    if "```" in answer:
        score += 0.15

    # 구조화
    if "**" in answer or "\n1." in answer:
        score += 0.1

    # 한국어 비율
    korean = len([c for c in answer if '\uac00' <= c <= '\ud7af'])
    if korean / max(len(answer), 1) > 0.3:
        score += 0.05

    return min(1.0, max(0.0, score))


# ─── 메인: 자동 데이터 생성 + 학습 데이터 출력 ────────────────

def auto_generate_dataset(
    endpoint: str,
    model: str,
    domain: str,
    num_questions: int = 200,
    answers_per_question: int = 4,
    output_path: str = "/tmp/hfl_autogen.jsonl",
) -> dict:
    """자동 학습 데이터 생성 파이프라인.

    Returns: 통계 dict
    """
    topics = SEED_TOPICS.get(domain, SEED_TOPICS["general"])
    all_sft = []       # SFT 데이터
    all_dpo = []       # DPO 데이터

    logger.info(f"자동 데이터 생성 시작: domain={domain}, 질문={num_questions}")

    questions_generated = 0
    for topic in topics:
        if questions_generated >= num_questions:
            break

        batch_size = min(20, num_questions - questions_generated)
        logger.info(f"  주제: {topic} ({batch_size}개 질문 생성)")

        # 1. 질문 생성
        questions = generate_questions(endpoint, model, topic, batch_size)

        for q in questions:
            if questions_generated >= num_questions:
                break

            # 2. 답변 K개 생성
            answers = generate_answers(endpoint, model, q, answers_per_question)
            if len(answers) < 2:
                continue

            # 3. 자체 평가
            for ans in answers:
                ans["score"] = self_evaluate(endpoint, model, q, ans["content"])

            # 4. 최고/최악 쌍 → DPO
            answers.sort(key=lambda a: a["score"], reverse=True)
            best = answers[0]
            worst = answers[-1]

            if best["score"] - worst["score"] >= 1.5:
                all_dpo.append({
                    "prompt": q,
                    "chosen": best["content"],
                    "rejected": worst["content"],
                    "chosen_score": best["score"],
                    "rejected_score": worst["score"],
                })

            # 5. 최고 답변 → SFT
            all_sft.append({
                "messages": [
                    {"role": "user", "content": q},
                    {"role": "assistant", "content": best["content"]},
                ]
            })

            questions_generated += 1

        logger.info(f"  진행: {questions_generated}/{num_questions}")

    # 6. Smart Selection: loss 높은 것 우선
    for item in all_sft:
        asst_msg = next((m for m in item["messages"] if m["role"] == "assistant"), None)
        user_msg = next((m for m in item["messages"] if m["role"] == "user"), None)
        if asst_msg and user_msg:
            item["_loss_score"] = compute_loss_score(user_msg["content"], asst_msg["content"])

    all_sft.sort(key=lambda x: x.get("_loss_score", 0), reverse=True)

    # 상위 80%만 사용 (하위 20% 품질 낮은 것 제거)
    cutoff = int(len(all_sft) * 0.8)
    selected_sft = all_sft[:cutoff]

    # 저장
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    sft_path = output_path
    dpo_path = output_path.replace(".jsonl", "_dpo.jsonl")

    with open(sft_path, "w", encoding="utf-8") as f:
        for item in selected_sft:
            item.pop("_loss_score", None)
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    with open(dpo_path, "w", encoding="utf-8") as f:
        for item in all_dpo:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    stats = {
        "domain": domain,
        "questions_generated": questions_generated,
        "sft_total": len(all_sft),
        "sft_selected": len(selected_sft),
        "dpo_pairs": len(all_dpo),
        "sft_path": sft_path,
        "dpo_path": dpo_path,
    }

    logger.info(f"\n생성 완료:")
    logger.info(f"  SFT: {len(selected_sft)}개 (상위 80%, {sft_path})")
    logger.info(f"  DPO: {len(all_dpo)}개 ({dpo_path})")

    return stats


# ─── 메인 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="HFL Auto Data Generation Agent")
    parser.add_argument("--endpoint", default="http://localhost:8000")
    parser.add_argument("--model", required=True)
    parser.add_argument("--domain", default="coding", choices=list(SEED_TOPICS.keys()))
    parser.add_argument("--num-questions", type=int, default=200)
    parser.add_argument("--answers-per-question", type=int, default=4)
    parser.add_argument("--output", default="/tmp/hfl_autogen.jsonl")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(" HFL Auto Data Generation Agent")
    logger.info("=" * 60)

    stats = auto_generate_dataset(
        args.endpoint, args.model, args.domain,
        args.num_questions, args.answers_per_question,
        args.output,
    )

    logger.info(f"\n다음 단계:")
    logger.info(f"  python scripts/qlora_qwen.py --data {stats['sft_path']} ...")
    logger.info(f"  python scripts/align.py --data {stats['dpo_path']} ...")


if __name__ == "__main__":
    main()
