"""한국어 코딩 SFT 데이터 수집 스크립트.

소스:
  1. HuggingFace 한국어 코딩 데이터셋
  2. GitHub 한국어 README가 있는 프로젝트에서 코드 추출
  3. 한국어 프로그래밍 Q&A (공개 데이터셋)

사용법:
    python scripts/data/collect_korean_code.py \
        --output data/sft/korean_code.jsonl \
        --max-samples 50000

필요 패키지:
    pip install datasets requests beautifulsoup4
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_hf_dataset(name: str, split: str = "train", max_samples: int = 10000) -> list[dict]:
    """HuggingFace에서 데이터셋 로드."""
    try:
        from datasets import load_dataset
        logger.info(f"  HuggingFace 데이터셋 로드: {name}")
        ds = load_dataset(name, split=split, streaming=True)
        samples = []
        for i, item in enumerate(ds):
            if i >= max_samples:
                break
            samples.append(item)
        logger.info(f"  → {len(samples)}개 로드 완료")
        return samples
    except Exception as e:
        logger.warning(f"  → 로드 실패: {e}")
        return []


def convert_to_chatml(instruction: str, input_text: str, output: str, system: str = "") -> dict:
    """Alpaca 포맷 → ChatML 포맷 변환."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})

    user_content = instruction
    if input_text:
        user_content += f"\n\n{input_text}"

    messages.append({"role": "user", "content": user_content})
    messages.append({"role": "assistant", "content": output})
    return {"messages": messages}


# ─── 1. HuggingFace 한국어 코딩 데이터셋 ────────────────────────

HF_KOREAN_CODE_DATASETS = [
    # 한국어 instruction 데이터
    {"name": "heegyu/korean-chatgpt-multiturn-chat", "type": "multiturn"},
    {"name": "kyujinpy/KOR-OpenOrca-Platypus-v3", "type": "alpaca"},
    {"name": "nlpai-lab/kullm-v2", "type": "alpaca"},
    {"name": "maywell/ko_wikidata_QA", "type": "qa"},
    # 코딩 특화
    {"name": "sahil2801/CodeAlpaca-20k", "type": "alpaca"},
    {"name": "iamtarun/python_code_instructions_18k_alpaca", "type": "alpaca"},
    {"name": "TokenBender/code_instructions_122k_alpaca_style", "type": "alpaca"},
]

SYSTEM_PROMPT_CODE = "당신은 화랑 AI 코딩 어시스턴트입니다. 한국어로 친절하고 정확하게 코딩 질문에 답변해주세요. 코드를 작성할 때는 주석도 한국어로 달아주세요."


def collect_hf_korean_code(max_per_dataset: int = 5000) -> list[dict]:
    """HuggingFace에서 한국어 코딩 데이터 수집."""
    all_data = []

    for ds_info in HF_KOREAN_CODE_DATASETS:
        name = ds_info["name"]
        dtype = ds_info["type"]
        logger.info(f"수집 중: {name} (type={dtype})")

        samples = load_hf_dataset(name, max_samples=max_per_dataset)

        for sample in samples:
            try:
                if dtype == "alpaca":
                    instruction = sample.get("instruction", "")
                    input_text = sample.get("input", "")
                    output = sample.get("output", "")
                    if instruction and output:
                        item = convert_to_chatml(instruction, input_text, output, SYSTEM_PROMPT_CODE)
                        all_data.append(item)

                elif dtype == "multiturn":
                    conversations = sample.get("conversations", sample.get("messages", []))
                    if len(conversations) >= 2:
                        messages = [{"role": "system", "content": SYSTEM_PROMPT_CODE}]
                        for conv in conversations:
                            role = conv.get("role", conv.get("from", ""))
                            content = conv.get("content", conv.get("value", ""))
                            if role in ("human", "user"):
                                messages.append({"role": "user", "content": content})
                            elif role in ("gpt", "assistant"):
                                messages.append({"role": "assistant", "content": content})
                        if len(messages) >= 3:  # system + at least user + assistant
                            all_data.append({"messages": messages})

                elif dtype == "qa":
                    question = sample.get("question", sample.get("instruction", ""))
                    answer = sample.get("answer", sample.get("output", ""))
                    if question and answer:
                        item = convert_to_chatml(question, "", answer, SYSTEM_PROMPT_CODE)
                        all_data.append(item)

            except Exception:
                continue

    logger.info(f"HuggingFace 총 수집: {len(all_data)}개")
    return all_data


# ─── 2. 프로그래밍 언어별 코드 생성 템플릿 ──────────────────────

CODE_TEMPLATES = [
    # Python
    {"lang": "Python", "q": "Python에서 리스트 컴프리헨션으로 짝수만 필터링하는 방법을 알려줘",
     "a": "리스트 컴프리헨션을 사용하면 간결하게 짝수만 필터링할 수 있습니다.\n\n```python\n# 원본 리스트\nnumbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]\n\n# 짝수만 필터링\nevens = [n for n in numbers if n % 2 == 0]\nprint(evens)  # [2, 4, 6, 8, 10]\n```\n\n`if` 조건을 리스트 컴프리헨션 뒤에 붙이면 조건에 맞는 요소만 새 리스트에 포함됩니다."},
    {"lang": "Python", "q": "Python으로 파일을 읽고 각 줄의 단어 수를 세는 코드를 작성해줘",
     "a": "파일을 읽어서 각 줄의 단어 수를 세는 코드입니다.\n\n```python\n# 파일 읽기\nwith open('input.txt', 'r', encoding='utf-8') as f:\n    for i, line in enumerate(f, 1):\n        word_count = len(line.split())\n        print(f'{i}번째 줄: {word_count}개 단어')\n```\n\n`with` 문을 사용하면 파일이 자동으로 닫히고, `split()`은 공백 기준으로 문자열을 분리합니다."},
    # JavaScript
    {"lang": "JavaScript", "q": "JavaScript에서 배열의 중복을 제거하는 여러 가지 방법을 알려줘",
     "a": "JavaScript에서 배열 중복을 제거하는 3가지 방법입니다.\n\n```javascript\nconst arr = [1, 2, 2, 3, 3, 4, 5, 5];\n\n// 방법 1: Set 사용 (가장 간단)\nconst unique1 = [...new Set(arr)];\n\n// 방법 2: filter + indexOf\nconst unique2 = arr.filter((item, index) => arr.indexOf(item) === index);\n\n// 방법 3: reduce\nconst unique3 = arr.reduce((acc, cur) => {\n  if (!acc.includes(cur)) acc.push(cur);\n  return acc;\n}, []);\n\nconsole.log(unique1); // [1, 2, 3, 4, 5]\n```\n\n`Set`을 사용하는 방법이 가장 간결하고 성능도 좋습니다."},
    # TypeScript
    {"lang": "TypeScript", "q": "TypeScript에서 제네릭을 사용한 API 응답 타입을 어떻게 만들어?",
     "a": "제네릭을 활용한 API 응답 타입 정의 방법입니다.\n\n```typescript\n// 공통 API 응답 타입\ninterface ApiResponse<T> {\n  success: boolean;\n  data: T;\n  error?: string;\n  timestamp: number;\n}\n\n// 유저 타입\ninterface User {\n  id: string;\n  name: string;\n  email: string;\n}\n\n// 사용 예시\nasync function fetchUser(id: string): Promise<ApiResponse<User>> {\n  const resp = await fetch(`/api/users/${id}`);\n  return resp.json();\n}\n\n// 리스트 응답\ninterface PaginatedResponse<T> extends ApiResponse<T[]> {\n  total: number;\n  page: number;\n}\n```\n\n제네릭 `<T>`를 사용하면 하나의 응답 구조로 다양한 데이터 타입을 처리할 수 있습니다."},
    # React
    {"lang": "React", "q": "React에서 커스텀 훅으로 API 호출을 관리하는 방법을 알려줘",
     "a": "커스텀 훅으로 API 호출을 깔끔하게 관리할 수 있습니다.\n\n```typescript\nimport { useState, useEffect } from 'react';\n\n// 커스텀 훅\nfunction useFetch<T>(url: string) {\n  const [data, setData] = useState<T | null>(null);\n  const [loading, setLoading] = useState(true);\n  const [error, setError] = useState<string | null>(null);\n\n  useEffect(() => {\n    const controller = new AbortController();\n\n    async function fetchData() {\n      try {\n        setLoading(true);\n        const resp = await fetch(url, { signal: controller.signal });\n        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);\n        const json = await resp.json();\n        setData(json);\n      } catch (e: any) {\n        if (e.name !== 'AbortError') setError(e.message);\n      } finally {\n        setLoading(false);\n      }\n    }\n\n    fetchData();\n    return () => controller.abort();\n  }, [url]);\n\n  return { data, loading, error };\n}\n\n// 사용 예시\nfunction UserList() {\n  const { data, loading, error } = useFetch<User[]>('/api/users');\n\n  if (loading) return <div>로딩 중...</div>;\n  if (error) return <div>오류: {error}</div>;\n\n  return (\n    <ul>\n      {data?.map(user => <li key={user.id}>{user.name}</li>)}\n    </ul>\n  );\n}\n```\n\n`AbortController`로 컴포넌트 언마운트 시 요청을 취소하여 메모리 누수를 방지합니다."},
    # SQL
    {"lang": "SQL", "q": "SQL에서 서브쿼리와 JOIN의 차이를 예제로 설명해줘",
     "a": "같은 결과를 서브쿼리와 JOIN으로 각각 구현한 예제입니다.\n\n```sql\n-- 주문이 있는 고객 조회\n\n-- 방법 1: 서브쿼리\nSELECT name, email\nFROM customers\nWHERE id IN (\n    SELECT DISTINCT customer_id\n    FROM orders\n    WHERE order_date >= '2024-01-01'\n);\n\n-- 방법 2: JOIN\nSELECT DISTINCT c.name, c.email\nFROM customers c\nINNER JOIN orders o ON c.id = o.customer_id\nWHERE o.order_date >= '2024-01-01';\n\n-- 방법 3: EXISTS (대량 데이터에서 성능 우수)\nSELECT name, email\nFROM customers c\nWHERE EXISTS (\n    SELECT 1 FROM orders o\n    WHERE o.customer_id = c.id\n    AND o.order_date >= '2024-01-01'\n);\n```\n\n**차이점:**\n- 서브쿼리: 직관적이지만 대량 데이터에서 느릴 수 있음\n- JOIN: 대부분의 경우 성능이 좋고, 양쪽 테이블 컬럼 모두 접근 가능\n- EXISTS: 대량 데이터에서 가장 효율적 (일치하는 행을 찾으면 즉시 중단)"},
    # Go
    {"lang": "Go", "q": "Go에서 고루틴과 채널을 사용한 동시성 패턴을 알려줘",
     "a": "Go의 고루틴과 채널을 활용한 워커 풀 패턴입니다.\n\n```go\npackage main\n\nimport (\n\t\"fmt\"\n\t\"sync\"\n)\n\n// 작업 처리 워커\nfunc worker(id int, jobs <-chan int, results chan<- int, wg *sync.WaitGroup) {\n\tdefer wg.Done()\n\tfor job := range jobs {\n\t\tfmt.Printf(\"워커 %d: 작업 %d 처리 중\\n\", id, job)\n\t\tresult := job * 2 // 실제 작업\n\t\tresults <- result\n\t}\n}\n\nfunc main() {\n\tjobs := make(chan int, 100)\n\tresults := make(chan int, 100)\n\n\t// 워커 3개 실행\n\tvar wg sync.WaitGroup\n\tfor w := 1; w <= 3; w++ {\n\t\twg.Add(1)\n\t\tgo worker(w, jobs, results, &wg)\n\t}\n\n\t// 작업 전송\n\tfor j := 1; j <= 10; j++ {\n\t\tjobs <- j\n\t}\n\tclose(jobs)\n\n\t// 결과 수집\n\tgo func() {\n\t\twg.Wait()\n\t\tclose(results)\n\t}()\n\n\tfor r := range results {\n\t\tfmt.Println(\"결과:\", r)\n\t}\n}\n```\n\n`chan`으로 작업을 분배하고, `sync.WaitGroup`으로 모든 워커가 완료될 때까지 대기합니다."},
    # Docker
    {"lang": "Docker", "q": "멀티스테이지 빌드로 Go 앱의 Docker 이미지를 최적화하는 방법",
     "a": "멀티스테이지 빌드로 최종 이미지 크기를 크게 줄일 수 있습니다.\n\n```dockerfile\n# 빌드 단계\nFROM golang:1.22-alpine AS builder\nWORKDIR /app\nCOPY go.mod go.sum ./\nRUN go mod download\nCOPY . .\nRUN CGO_ENABLED=0 GOOS=linux go build -o server ./cmd/server\n\n# 실행 단계 (최소 이미지)\nFROM alpine:3.19\nRUN apk --no-cache add ca-certificates tzdata\nWORKDIR /app\nCOPY --from=builder /app/server .\nEXPOSE 8080\nCMD [\"./server\"]\n```\n\n**결과:**\n- 빌드 이미지: ~1GB (Go 컴파일러 포함)\n- 최종 이미지: ~15MB (바이너리 + Alpine만)\n\n`CGO_ENABLED=0`으로 정적 바이너리를 만들면 `scratch` 이미지도 사용 가능합니다."},
]


def generate_code_templates() -> list[dict]:
    """코드 템플릿에서 SFT 데이터 생성."""
    data = []
    for tmpl in CODE_TEMPLATES:
        item = convert_to_chatml(tmpl["q"], "", tmpl["a"], SYSTEM_PROMPT_CODE)
        data.append(item)
    return data


# ─── 메인 ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="한국어 코딩 SFT 데이터 수집")
    parser.add_argument("--output", required=True, help="출력 JSONL 파일 경로")
    parser.add_argument("--max-samples", type=int, default=50000, help="데이터셋당 최대 샘플 수")
    parser.add_argument("--skip-hf", action="store_true", help="HuggingFace 수집 건너뛰기")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("한국어 코딩 SFT 데이터 수집")
    logger.info("=" * 60)

    all_data = []

    # 1. 코드 템플릿
    logger.info("\n[1/2] 코드 템플릿 데이터 생성...")
    templates = generate_code_templates()
    all_data.extend(templates)
    logger.info(f"  → 템플릿: {len(templates)}개")

    # 2. HuggingFace 데이터셋
    if not args.skip_hf:
        logger.info("\n[2/2] HuggingFace 데이터셋 수집...")
        hf_data = collect_hf_korean_code(max_per_dataset=args.max_samples // len(HF_KOREAN_CODE_DATASETS))
        all_data.extend(hf_data)

    # 저장
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in all_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info(f"\n총 {len(all_data)}개 저장 → {args.output}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
