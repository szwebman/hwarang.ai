"""화랑 AI AI/LLM 심화 학습 데이터

RAG 최적화, 환각 감소, 멀티모달, 평가지표, 에이전트 메모리, 양자화 등.

사용법:
    python scripts/data/build_deep_ai.py --output data/sft/deep_ai.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
AI/ML 전문가 수준의 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    m("RAG에서 환각 줄이는 구체적 방법 알려줘",
'''RAG 환각(Hallucination) 감소를 위한 실무 기법입니다.

```python
# ═══ 1. 프롬프트 레벨 환각 방지 ═══

RAG_PROMPT = """다음 문서를 참고하여 질문에 답변하세요.

## 규칙
1. 반드시 제공된 문서 내용만 기반으로 답변하세요
2. 문서에 없는 내용은 "제공된 문서에서 해당 정보를 찾을 수 없습니다"라고 답하세요
3. 추측하지 마세요. 확실한 내용만 답변하세요
4. 답변의 근거가 되는 문서 번호를 [출처: 문서X]로 표시하세요
5. 여러 문서의 정보가 상충하면, 가장 최신 문서를 우선하세요

## 참고 문서
{context}

## 질문
{question}

## 답변 (출처 포함):"""

# ═══ 2. 검색 품질 향상 (환각의 근본 원인) ═══

# 문제: 관련 없는 문서가 검색되면 → 환각 증가
# 해결: 검색 정밀도 향상

# 2-1. 유사도 임계값 적용
def retrieve_with_threshold(query: str, min_score: float = 0.7):
    results = vectorstore.similarity_search_with_score(query, k=10)
    # 유사도가 낮은 결과 제거
    filtered = [(doc, score) for doc, score in results if score >= min_score]

    if not filtered:
        return None, "관련 문서를 찾을 수 없습니다"

    return [doc for doc, _ in filtered[:5]], None

# 2-2. 하이브리드 검색 + 리랭킹
from langchain.retrievers import EnsembleRetriever, ContextualCompressionRetriever
from langchain_cohere import CohereRerank

# 키워드(BM25) + 벡터 검색 결합
hybrid = EnsembleRetriever(
    retrievers=[bm25_retriever, vector_retriever],
    weights=[0.3, 0.7],
)

# 리랭커로 최종 순위 조정
reranker = CohereRerank(model="rerank-v3.5", top_n=3)
final_retriever = ContextualCompressionRetriever(
    base_compressor=reranker,
    base_retriever=hybrid,
)

# ═══ 3. 청킹 최적화 (의미 보존) ═══
from langchain.text_splitter import RecursiveCharacterTextSplitter

# ❌ 나쁜 청킹: 고정 크기로 자르면 문맥 끊김
bad_splitter = RecursiveCharacterTextSplitter(chunk_size=200)

# ✅ 좋은 청킹: 충분한 크기 + 오버랩
good_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,    # 충분한 문맥
    chunk_overlap=200,  # 경계에서 정보 손실 방지
    separators=["\\n\\n", "\\n", ". ", " "],  # 자연스러운 경계
)

# ✅✅ 시맨틱 청킹 (의미 단위 분할)
from langchain_experimental.text_splitter import SemanticChunker

semantic_splitter = SemanticChunker(
    embeddings=embedding_model,
    breakpoint_threshold_type="percentile",
    breakpoint_threshold_amount=90,
)

# ═══ 4. 답변 검증 (Self-RAG) ═══

async def verified_rag(query: str) -> dict:
    # 1단계: 검색
    docs = await retriever.get_relevant_documents(query)

    if not docs:
        return {"answer": "관련 정보를 찾을 수 없습니다", "confidence": 0}

    # 2단계: 생성
    context = "\\n\\n".join([d.page_content for d in docs])
    answer = await llm.generate(RAG_PROMPT.format(context=context, question=query))

    # 3단계: 검증 (환각 탐지)
    verification_prompt = f"""
    다음 답변이 제공된 문서에 근거하는지 검증하세요.

    문서: {context}

    답변: {answer}

    각 문장에 대해:
    - SUPPORTED: 문서에 근거함
    - NOT_SUPPORTED: 문서에 근거하지 않음
    - PARTIALLY: 부분적으로 근거함

    JSON으로 응답하세요.
    """

    verification = await llm.generate(verification_prompt)

    # 4단계: 환각 제거
    supported_count = verification.count("SUPPORTED")
    total_claims = supported_count + verification.count("NOT_SUPPORTED")
    confidence = supported_count / max(total_claims, 1)

    if confidence < 0.5:
        return {
            "answer": "충분히 신뢰할 수 있는 답변을 생성하지 못했습니다. "
                      "다른 방식으로 질문해 주세요.",
            "confidence": confidence,
            "sources": [],
        }

    return {
        "answer": answer,
        "confidence": confidence,
        "sources": [{"title": d.metadata.get("title"), "page": d.metadata.get("page")} for d in docs],
    }

# ═══ 5. 출처 추적 (Citation) ═══

CITATION_PROMPT = """참고 문서:
{numbered_contexts}

질문: {question}

규칙: 답변의 각 문장 끝에 [1], [2] 등 문서 번호를 표시하세요.
문서에 없는 내용은 포함하지 마세요.

답변:"""

def format_with_numbers(docs):
    return "\\n\\n".join([
        f"[{i+1}] {doc.page_content}"
        for i, doc in enumerate(docs)
    ])
```

환각 감소 체크리스트:
| 단계 | 방법 | 효과 |
|------|------|------|
| 검색 | 유사도 임계값 | ⭐⭐⭐⭐ |
| 검색 | 하이브리드 + 리랭킹 | ⭐⭐⭐⭐⭐ |
| 청킹 | 시맨틱 청킹 | ⭐⭐⭐ |
| 프롬프트 | "모르면 모른다고" 지시 | ⭐⭐⭐⭐ |
| 검증 | Self-RAG (답변 검증) | ⭐⭐⭐⭐⭐ |
| 출처 | Citation 추적 | ⭐⭐⭐ |'''),

    m("LLM 양자화 기법 비교해줘 GPTQ AWQ bitsandbytes GGUF",
'''LLM 양자화 기법별 특성과 사용법 비교입니다.

```python
# ═══ 양자화 기법 비교 ═══

# ┌──────────────┬─────────┬──────────┬───────────┬──────────┐
# │ 기법         │ 비트    │ 품질     │ 속도      │ GPU 필요 │
# ├──────────────┼─────────┼──────────┼───────────┼──────────┤
# │ FP16 (원본)  │ 16bit   │ ⭐⭐⭐⭐⭐ │ 기준      │ 풀 VRAM  │
# │ bitsandbytes │ 4/8bit  │ ⭐⭐⭐⭐  │ 느림      │ 절반     │
# │ GPTQ         │ 4bit    │ ⭐⭐⭐⭐  │ 빠름      │ 1/4      │
# │ AWQ          │ 4bit    │ ⭐⭐⭐⭐⭐ │ 가장 빠름 │ 1/4      │
# │ GGUF         │ 2-8bit  │ 다양     │ CPU 가능  │ 없어도됨 │
# │ SqueezeLLM   │ 3-4bit  │ ⭐⭐⭐⭐  │ 보통      │ 1/4      │
# └──────────────┴─────────┴──────────┴───────────┴──────────┘

# ═══ 1. bitsandbytes (가장 쉬움, 학습 가능) ═══
# 장점: QLoRA 학습 가능, 설정 간단
# 단점: 추론 속도가 느림 (GPTQ/AWQ 대비)

from transformers import AutoModelForCausalLM, BitsAndBytesConfig

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",        # NormalFloat4 (최적)
    bnb_4bit_compute_dtype="bfloat16", # 연산은 bf16
    bnb_4bit_use_double_quant=True,    # 이중 양자화 (추가 메모리 절약)
)

model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-32B",
    quantization_config=bnb_config,
    device_map="auto",
)
# 32B 모델: FP16 ~64GB → INT4 ~18GB

# vLLM 서빙
# vllm serve model_path --quantization bitsandbytes --load-format bitsandbytes

# ═══ 2. GPTQ (사전 양자화, 빠른 추론) ═══
# 장점: 추론 빠름, vLLM 최적화
# 단점: 양자화에 캘리브레이션 데이터 필요 (수 시간)

# 양자화 수행
from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig

quantize_config = BaseQuantizeConfig(
    bits=4,
    group_size=128,
    damp_percent=0.1,
    desc_act=True,
)

model = AutoGPTQForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-32B",
    quantize_config,
)

# 캘리브레이션 데이터로 양자화
model.quantize(calibration_data, batch_size=1)
model.save_quantized("Qwen2.5-32B-GPTQ")

# vLLM 서빙
# vllm serve Qwen2.5-32B-GPTQ --quantization gptq

# ═══ 3. AWQ (최고 품질 + 빠른 추론) ═══
# 장점: 품질 최고 (활성화 인식 양자화), 추론 빠름
# 단점: 양자화 시간 오래 걸림

from awq import AutoAWQForCausalLM

model = AutoAWQForCausalLM.from_pretrained("Qwen/Qwen2.5-32B")

quant_config = {
    "zero_point": True,
    "q_group_size": 128,
    "w_bit": 4,
    "version": "GEMM",
}

model.quantize(
    tokenizer,
    quant_config=quant_config,
    calib_data=calibration_dataset,
)
model.save_quantized("Qwen2.5-32B-AWQ")

# vLLM 서빙 (AWQ가 가장 빠름!)
# vllm serve Qwen2.5-32B-AWQ --quantization awq

# ═══ 4. GGUF (CPU/Apple Silicon 서빙) ═══
# 장점: GPU 없어도 됨, llama.cpp 사용
# 단점: GPU 대비 느림

# 변환: HuggingFace → GGUF
# python convert_hf_to_gguf.py Qwen2.5-32B --outtype f16

# 양자화 (다양한 레벨)
# ./llama-quantize model.gguf model-Q4_K_M.gguf Q4_K_M

# GGUF 양자화 레벨:
# Q2_K: 2비트 (매우 작지만 품질 낮음)
# Q4_K_M: 4비트 (권장 - 품질/크기 균형)
# Q5_K_M: 5비트 (좋은 품질)
# Q6_K: 6비트 (높은 품질)
# Q8_0: 8비트 (거의 원본 수준)

# llama.cpp로 서빙
# ./llama-server -m model-Q4_K_M.gguf -c 4096 -ngl 99 --host 0.0.0.0

# Python에서 사용
from llama_cpp import Llama
llm = Llama(model_path="model-Q4_K_M.gguf", n_gpu_layers=-1, n_ctx=4096)
output = llm("안녕하세요", max_tokens=512)

# ═══ 5. 서빙 방식 선택 가이드 ═══
#
# RTX 5090 (32GB) 기준:
# - 7B 모델: FP16 OK (14GB)
# - 13B 모델: AWQ 4bit (8GB) → vLLM
# - 32B 모델: bitsandbytes 4bit (18GB) → vLLM
# - 70B 모델: GGUF Q4 → llama.cpp (GPU 오프로딩)
# - 70B 모델: AWQ 4bit → vLLM (2x GPU 필요)
```

양자화 선택 가이드:
| 상황 | 추천 | 이유 |
|------|------|------|
| 학습 (QLoRA) | bitsandbytes | 학습 가능한 유일한 양자화 |
| 프로덕션 서빙 | AWQ | 최고 품질 + 빠른 추론 |
| 빠른 테스트 | GPTQ | 사전 양자화 모델 많음 |
| CPU/Mac 서빙 | GGUF | GPU 없이 실행 |
| 메모리 극한 | GGUF Q2_K | 가장 작음 (품질 저하) |'''),

    m("AI 에이전트 메모리 시스템 구현 방법 심화 알려줘",
'''AI 에이전트의 장기/단기 메모리 시스템 구현입니다.

```python
# ═══ 에이전트 메모리 아키텍처 ═══
#
# [사용자 입력]
#     │
#     ▼
# [작업 메모리 (Working Memory)]  ← 현재 대화 컨텍스트
#     │
#     ├─── [단기 메모리 (Short-term)]  ← 최근 N턴 대화
#     │
#     ├─── [장기 메모리 (Long-term)]   ← 벡터 DB에 저장
#     │         ├── 사실 (Facts)
#     │         ├── 선호도 (Preferences)
#     │         └── 에피소드 (Episodes)
#     │
#     └─── [절차 메모리 (Procedural)]  ← 도구 사용법, 패턴

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import chromadb
from openai import AsyncOpenAI

class MemoryType(Enum):
    FACT = "fact"           # "사용자는 파이썬 개발자다"
    PREFERENCE = "preference"  # "코드 설명은 한국어로"
    EPISODE = "episode"     # "지난번에 로그인 버그를 수정했다"
    PROCEDURE = "procedure" # "이 프로젝트는 pytest를 사용한다"

@dataclass
class Memory:
    content: str
    memory_type: MemoryType
    importance: float  # 0-1 (중요도)
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    metadata: dict = field(default_factory=dict)

class AgentMemory:
    """에이전트 장기 메모리 시스템."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.client = AsyncOpenAI()

        # 벡터 DB
        self.chroma = chromadb.PersistentClient(path=f"./memory/{user_id}")
        self.collection = self.chroma.get_or_create_collection(
            name="memories",
            metadata={"hnsw:space": "cosine"},
        )

        # 단기 메모리 (최근 대화)
        self.short_term: list[dict] = []
        self.max_short_term = 20  # 최근 20턴

    # ═══ 메모리 저장 ═══
    async def add_memory(self, content: str, memory_type: MemoryType,
                          importance: float = 0.5, metadata: dict = None):
        """장기 메모리에 저장."""
        memory_id = f"mem_{datetime.now().timestamp()}"

        self.collection.add(
            ids=[memory_id],
            documents=[content],
            metadatas=[{
                "type": memory_type.value,
                "importance": importance,
                "created_at": datetime.now().isoformat(),
                "access_count": 0,
                **(metadata or {}),
            }],
        )

    # ═══ 메모리 검색 ═══
    async def recall(self, query: str, n: int = 5,
                      memory_type: MemoryType = None) -> list[dict]:
        """관련 메모리를 검색합니다."""
        where_filter = None
        if memory_type:
            where_filter = {"type": memory_type.value}

        results = self.collection.query(
            query_texts=[query],
            n_results=n,
            where=where_filter,
        )

        memories = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            score = 1 - results["distances"][0][i]  # 코사인 유사도

            # 접근 횟수 증가
            self.collection.update(
                ids=[results["ids"][0][i]],
                metadatas=[{**meta, "access_count": meta.get("access_count", 0) + 1}],
            )

            memories.append({
                "content": doc,
                "type": meta["type"],
                "importance": meta["importance"],
                "relevance": score,
                "created_at": meta["created_at"],
            })

        return memories

    # ═══ 대화에서 자동 메모리 추출 ═══
    async def extract_memories(self, conversation: list[dict]):
        """대화에서 기억할 만한 정보를 자동 추출."""
        extraction_prompt = """다음 대화에서 기억할 만한 정보를 추출하세요.

대화:
{conversation}

다음 JSON 형식으로 추출하세요:
[
  {{"content": "기억할 내용", "type": "fact|preference|episode|procedure", "importance": 0.0-1.0}}
]

기억할 것:
- 사용자의 이름, 직업, 기술 스택 (fact)
- 선호하는 코딩 스타일, 설명 방식 (preference)
- 해결한 문제, 논의한 주제 (episode)
- 프로젝트 규칙, 도구 설정 (procedure)

중요하지 않은 것은 추출하지 마세요."""

        conv_text = "\\n".join([
            f"{m['role']}: {m['content'][:200]}" for m in conversation[-10:]
        ])

        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": extraction_prompt.format(conversation=conv_text)}],
            response_format={"type": "json_object"},
        )

        memories = json.loads(response.choices[0].message.content)
        for mem in memories.get("memories", memories if isinstance(memories, list) else []):
            await self.add_memory(
                content=mem["content"],
                memory_type=MemoryType(mem["type"]),
                importance=mem.get("importance", 0.5),
            )

    # ═══ 컨텍스트 구성 ═══
    async def build_context(self, query: str) -> str:
        """현재 질문에 관련된 메모리를 컨텍스트로 구성."""
        memories = await self.recall(query, n=5)

        if not memories:
            return ""

        context = "## 이전 대화에서 기억하는 정보\\n"
        for mem in memories:
            if mem["relevance"] > 0.3:  # 관련도 30% 이상만
                context += f"- [{mem['type']}] {mem['content']}\\n"

        return context

# ═══ 에이전트에서 사용 ═══
class SmartAgent:
    def __init__(self, user_id: str):
        self.memory = AgentMemory(user_id)
        self.conversation: list[dict] = []

    async def chat(self, user_message: str) -> str:
        # 1. 관련 메모리 검색
        memory_context = await self.memory.build_context(user_message)

        # 2. 시스템 프롬프트에 메모리 포함
        system = f"""당신은 화랑 AI입니다.

{memory_context}

위 정보를 자연스럽게 활용하되, 직접 언급하지 마세요."""

        # 3. LLM 호출
        messages = [
            {"role": "system", "content": system},
            *self.conversation[-10:],  # 최근 10턴
            {"role": "user", "content": user_message},
        ]

        response = await self.client.chat.completions.create(
            model="gpt-4o", messages=messages,
        )

        assistant_msg = response.choices[0].message.content

        # 4. 대화 기록
        self.conversation.append({"role": "user", "content": user_message})
        self.conversation.append({"role": "assistant", "content": assistant_msg})

        # 5. 메모리 추출 (5턴마다)
        if len(self.conversation) % 10 == 0:
            await self.memory.extract_memories(self.conversation)

        return assistant_msg
```

에이전트 메모리 핵심:
- **단기 메모리**: 최근 N턴 (슬라이딩 윈도우)
- **장기 메모리**: 벡터 DB에 임베딩 저장
- **자동 추출**: 대화에서 중요 정보 자동 저장
- **중요도**: 자주 접근되는 메모리 우선순위 상승
- **망각**: 오래되고 접근 안 되는 메모리 자동 정리'''),

    m("RAG 평가 지표 RAGAS 사용법 알려줘",
'''RAGAS로 RAG 시스템의 품질을 정량적으로 평가합니다.

```python
# pip install ragas

from ragas import evaluate
from ragas.metrics import (
    faithfulness,           # 충실도 (환각 방지)
    answer_relevancy,       # 답변 관련성
    context_precision,      # 검색 정밀도
    context_recall,         # 검색 재현율
    context_relevancy,      # 검색 관련성
    answer_correctness,     # 답변 정확도
    answer_similarity,      # 답변 유사도
)
from datasets import Dataset

# ═══ 1. 평가 데이터 준비 ═══
eval_data = {
    "question": [
        "화랑 AI의 주요 기능은 무엇인가요?",
        "파이썬 리스트 정렬 방법은?",
        "React와 Vue의 차이점은?",
    ],
    "answer": [
        "화랑 AI는 코딩, 디자인, 문서 작성을 도와주는 AI입니다.",  # RAG가 생성한 답변
        "sorted() 함수나 .sort() 메서드를 사용합니다.",
        "React는 JSX를 사용하고, Vue는 템플릿 문법을 사용합니다.",
    ],
    "contexts": [
        ["화랑 AI는 퍼시스모어가 개발한 한국형 AI 어시스턴트로, 코딩 도움과 디자인 지원 기능을 제공합니다."],
        ["파이썬에서 리스트를 정렬하려면 sorted() 내장 함수나 list.sort() 메서드를 사용할 수 있습니다."],
        ["React는 Facebook이 만든 UI 라이브러리로 JSX 문법을 사용합니다. Vue는 Evan You가 만든 프레임워크로 HTML 템플릿을 사용합니다."],
    ],
    "ground_truth": [
        "화랑 AI는 코딩, 디자인, 문서 작성을 지원하는 한국형 AI 어시스턴트입니다.",
        "sorted() 내장 함수 또는 list.sort() 메서드로 정렬합니다.",
        "React는 JSX 기반, Vue는 템플릿 기반이며, React는 단방향, Vue는 양방향 데이터 바인딩을 사용합니다.",
    ],
}

dataset = Dataset.from_dict(eval_data)

# ═══ 2. 평가 실행 ═══
results = evaluate(
    dataset,
    metrics=[
        faithfulness,         # 답변이 문서에 근거하는가? (환각 탐지)
        answer_relevancy,     # 답변이 질문에 관련있는가?
        context_precision,    # 검색된 문서가 정확한가?
        context_recall,       # 필요한 문서를 다 찾았는가?
        answer_correctness,   # 정답과 얼마나 일치하는가?
    ],
)

print(results)
# {
#   'faithfulness': 0.92,        # 92% 문서 기반 (8% 환각)
#   'answer_relevancy': 0.88,    # 88% 질문 관련
#   'context_precision': 0.85,   # 85% 검색 정확
#   'context_recall': 0.90,      # 90% 검색 재현
#   'answer_correctness': 0.83,  # 83% 정답 일치
# }

# ═══ 3. 각 지표 해석 ═══
# faithfulness (충실도): 0.92
# → 답변의 92%가 검색된 문서에 근거
# → 8%는 문서에 없는 내용 (환각 가능성)
# → 목표: 0.90 이상

# context_precision (검색 정밀도): 0.85
# → 검색된 문서 중 85%가 질문에 관련
# → 15%는 무관한 문서 (노이즈)
# → 개선: 임계값 조정, 리랭킹

# context_recall (검색 재현율): 0.90
# → 정답에 필요한 정보의 90%를 검색
# → 10%는 놓침
# → 개선: 청킹 크기 조정, 임베딩 모델 변경

# ═══ 4. 자동 테스트 세트 생성 ═══
from ragas.testset.generator import TestsetGenerator
from ragas.testset.evolutions import simple, reasoning, multi_context
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

generator = TestsetGenerator.from_langchain(
    generator_llm=ChatOpenAI(model="gpt-4o"),
    critic_llm=ChatOpenAI(model="gpt-4o"),
    embeddings=OpenAIEmbeddings(),
)

# 문서에서 자동으로 테스트 Q&A 생성
testset = generator.generate_with_langchain_docs(
    documents=my_documents,
    test_size=50,  # 50개 테스트 케이스
    distributions={
        simple: 0.5,        # 간단한 질문 50%
        reasoning: 0.25,    # 추론 필요 25%
        multi_context: 0.25, # 여러 문서 필요 25%
    },
)

# ═══ 5. CI/CD에서 자동 품질 검사 ═══
def test_rag_quality():
    results = evaluate(test_dataset, metrics=[faithfulness, answer_relevancy])

    assert results["faithfulness"] >= 0.85, \\
        f"충실도 미달: {results['faithfulness']:.2f} (기준: 0.85)"
    assert results["answer_relevancy"] >= 0.80, \\
        f"관련성 미달: {results['answer_relevancy']:.2f} (기준: 0.80)"
```

RAGAS 지표 요약:
| 지표 | 의미 | 목표 | 개선 방법 |
|------|------|------|-----------|
| faithfulness | 환각 없는 정도 | ≥0.90 | 프롬프트, 검증 |
| answer_relevancy | 질문 관련도 | ≥0.85 | 프롬프트 개선 |
| context_precision | 검색 정확도 | ≥0.80 | 리랭킹, 임계값 |
| context_recall | 검색 완전성 | ≥0.85 | 청킹, 임베딩 |
| answer_correctness | 정답 일치도 | ≥0.80 | 모델 + 검색 종합 |'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/deep_ai.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI AI/LLM 심화 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  AI 심화: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
