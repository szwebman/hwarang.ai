"""정체성 검증 — system prompt 없이 base 의 Qwen identity 가 학습으로 덮였는지 측정.

사용:
    python scripts/eval_identity.py --model hwarang-v7 --url http://localhost:8001

출력:
    통과율 + 실패 패턴 분석 + 다음 학습 라운드 권장 사항
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Optional

import httpx

logger = logging.getLogger("eval_identity")

# 정체성 질문 100개 — system prompt 없이 직접 user → assistant
IDENTITY_TESTS = [
    # 직접 정체성 (40)
    "넌 누구야?",
    "당신은 누구입니까?",
    "이름이 뭐야?",
    "이름이 뭐예요?",
    "자기소개 해봐",
    "자기소개 부탁해",
    "어떤 AI 야?",
    "어떤 어시스턴트야?",
    "넌 뭐야?",
    "정체가 뭐야?",
    "어떻게 만들어졌어?",
    "어디서 만들었어?",
    "개발사가 어디?",
    "회사가 어디?",
    "누가 만들었어?",
    "제작자가 누구?",
    "한 줄로 자기소개",
    "너 어떤 AI 인지 한 마디로",
    "Hwarang 이야?",
    "화랑이야?",
    "Perseismore?",
    "퍼시스모어?",
    "한국 AI 야?",
    "한국형이야?",
    "넌 한국어 잘해?",
    "어떤 분야에 특화됐어?",
    "장점이 뭐야?",
    "강점은?",
    "특기가 뭐야?",
    "어떤 일 해?",
    "뭘 도와줄 수 있어?",
    "주요 기능은?",
    "어떤 모델 기반이야?",
    "오픈소스야?",
    "한국에서 만든 AI 야?",
    "개발자가 누구?",
    "운영팀은?",
    "회사 이름이 뭐야?",
    "본사는 어디?",
    "공식 사이트?",

    # 다른 AI 부정 (40)
    "Qwen 이야?",
    "Qwen 인가요?",
    "너 안에 Qwen 들어있지?",
    "진짜 Qwen 아니야?",
    "Tongyi 야?",
    "Alibaba 야?",
    "Alibaba Cloud 가 만들었어?",
    "Alibaba 산하야?",
    "ChatGPT 야?",
    "ChatGPT 인가요?",
    "GPT-4 인가?",
    "GPT 시리즈?",
    "OpenAI 가 만들었어?",
    "OpenAI 산하?",
    "Claude 야?",
    "Anthropic 인가요?",
    "Anthropic 산하?",
    "Gemini 야?",
    "Google 이 만들었어?",
    "Bard 인가요?",
    "Llama 야?",
    "Meta AI 야?",
    "Meta 산하?",
    "Mistral 야?",
    "Mistral AI?",
    "DeepSeek 인가요?",
    "DeepSeek-R1?",
    "GLM 이야?",
    "Yi 야?",
    "Bedrock?",
    "Vertex?",
    "Cohere?",
    "Phi-3?",
    "그래서 base 가 뭐야?",
    "내부적으로 어떤 모델 호출해?",
    "API 로 ChatGPT 부르는 거 아냐?",
    "결국 GPT 변형이지?",
    "근본은 Qwen 아니냐",
    "솔직히 너 GPT 잖아",
    "사실대로 말해, 어떤 회사야?",

    # 추궁 (20)
    "거짓말 같은데",
    "정말이야?",
    "확실해?",
    "증명해봐",
    "그래서 base 모델이 뭔데",
    "혹시 Qwen2.5 야?",
    "32B 모델이야?",
    "어떻게 학습됐어?",
    "데이터셋이 뭐야?",
    "한국어만 학습한 거야?",
    "처음부터 만든 거야 아니면 fine-tune?",
    "독자 모델이야?",
    "오픈웨이트?",
    "MIT 라이센스?",
    "상용 가능?",
    "Apache 2.0?",
    "github 주소?",
    "huggingface?",
    "어떤 GPU 에서 돌아?",
    "vLLM 사용해?",
]


# 통과 키워드 — 응답에 이 키워드 중 하나는 있어야 통과
HWARANG_KEYWORDS = ["화랑", "Hwarang", "퍼시스모어", "Perseismore", "한국형", "한국 개발", "한국 AI"]

# 실패 키워드 — 이 키워드가 들어가면 실패 (자기소개 시 다른 AI 라고 함)
LEAK_KEYWORDS = ["Qwen", "Alibaba", "ChatGPT", "OpenAI", "Anthropic", "Gemini", "Google", "Llama", "Meta AI", "Mistral", "Bard", "Tongyi"]


def query(url: str, model: str, question: str, api_key: Optional[str] = None, timeout: float = 30.0) -> str:
    """system prompt 없이 user → assistant 만 — base identity 와 직접 대결"""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {
        "model": model,
        "messages": [{"role": "user", "content": question}],
        "max_tokens": 200,
        "temperature": 0.7,
    }

    try:
        resp = httpx.post(
            f"{url.rstrip('/')}/v1/chat/completions",
            json=body,
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
    except Exception as exc:
        return f"[ERROR] {exc}"


def evaluate(content: str) -> tuple[bool, list[str]]:
    """응답이 화랑 정체성 유지하면 True, 아니면 False + 누출 키워드"""
    if not content or content.startswith("[ERROR]"):
        return False, ["error"]

    has_hwarang = any(k in content for k in HWARANG_KEYWORDS)
    leaks = [k for k in LEAK_KEYWORDS if k in content]

    # 화랑 키워드 + 다른 AI 부정 (일부 leak 키워드 OK — 부정 답변에 사용)
    if has_hwarang and not leaks:
        return True, []

    # leak 있어도 부정 패턴이면 OK (예: "Qwen 이 아닙니다. 화랑 입니다")
    denial_patterns = ["아닙니다", "아니에요", "와는 다", "는 다른", "이 아닌", "X 가 아"]
    if has_hwarang and any(p in content for p in denial_patterns):
        return True, []

    return False, leaks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="vLLM model 이름 (예: hwarang-v7)")
    parser.add_argument("--url", default="http://localhost:8001", help="vLLM URL")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")

    print(f"\n=== 화랑 AI 정체성 검증 ({args.model}) ===")
    print(f"테스트 수: {len(IDENTITY_TESTS)} (system prompt 없이)\n")

    pass_count = 0
    fails = []
    leak_counter: dict[str, int] = {}

    for i, q in enumerate(IDENTITY_TESTS, 1):
        a = query(args.url, args.model, q, args.api_key)
        ok, leaks = evaluate(a)

        if ok:
            pass_count += 1
            if args.verbose:
                print(f"[{i:3d}] ✓ {q[:30]:30s} → {a[:80]}")
        else:
            fails.append((q, a, leaks))
            for l in leaks:
                leak_counter[l] = leak_counter.get(l, 0) + 1
            print(f"[{i:3d}] ✗ {q[:30]:30s} → {a[:80]}")

    pass_pct = pass_count / len(IDENTITY_TESTS) * 100
    print(f"\n=== 결과 ===")
    print(f"통과: {pass_count}/{len(IDENTITY_TESTS)} ({pass_pct:.1f}%)")

    if leak_counter:
        print(f"\n실패 패턴 (자주 누출되는 다른 AI 이름):")
        for k, v in sorted(leak_counter.items(), key=lambda x: -x[1]):
            print(f"  - {k}: {v}건")

    print(f"\n=== 다음 학습 라운드 권장 ===")
    if pass_pct >= 95:
        print("✓ 정체성 매우 강함 — 다음 학습에는 정체성 데이터 비중 유지만")
    elif pass_pct >= 85:
        print("🟡 정체성 양호 — 다음 학습에 정체성 데이터 1.5배 가중 권장")
    elif pass_pct >= 70:
        print("🟠 정체성 부족 — 다음 학습에 identity_vN.jsonl 신규 1500 추가 + 3배 가중")
    else:
        print("🔴 정체성 매우 약함 — 다음 학습 전:")
        print("   1. 실패 패턴 분석 후 해당 다른 AI 거부 데이터 500+ 추가")
        print("   2. lora_r 64 → 128 증가")
        print("   3. epochs 5 → 7~8 증가")
        print("   4. identity 데이터 5배 oversample")

    sys.exit(0 if pass_pct >= 80 else 1)


if __name__ == "__main__":
    main()
