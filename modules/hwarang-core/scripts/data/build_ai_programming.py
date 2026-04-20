"""화랑 AI AI/LLM 프로그래밍 학습 데이터

LangChain, RAG, 벡터DB, AI 에이전트, 프롬프트 엔지니어링, 파인튜닝 등.

사용법:
    python scripts/data/build_ai_programming.py \
        --output data/sft/ai_programming.jsonl
"""

import json, os, logging, argparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

S = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.
AI/ML 시니어 엔지니어 수준의 어시스턴트입니다.
설명과 주석은 한국어로, 코드는 실무 수준으로 작성합니다."""

def m(q, a):
    return {"messages": [{"role": "system", "content": S}, {"role": "user", "content": q}, {"role": "assistant", "content": a}]}

DATA = [
    # ═══ RAG (검색 증강 생성) ═══
    m("RAG 시스템 구현 방법 알려줘 최신으로",
'''RAG(Retrieval-Augmented Generation) 파이프라인 구현입니다.

```python
# ═══ 1. 문서 로딩 & 청킹 ═══
from langchain_community.document_loaders import (
    PyPDFLoader, TextLoader, WebBaseLoader,
    UnstructuredMarkdownLoader,
)
from langchain.text_splitter import RecursiveCharacterTextSplitter

# 다양한 소스에서 문서 로딩
def load_documents(paths: list[str]) -> list[Document]:
    docs = []
    for path in paths:
        if path.endswith(".pdf"):
            loader = PyPDFLoader(path)
        elif path.endswith(".md"):
            loader = UnstructuredMarkdownLoader(path)
        elif path.startswith("http"):
            loader = WebBaseLoader(path)
        else:
            loader = TextLoader(path, encoding="utf-8")
        docs.extend(loader.load())
    return docs

# 시맨틱 청킹 (의미 단위로 분할)
splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,        # 청크 크기
    chunk_overlap=200,      # 오버랩 (문맥 유지)
    separators=["\n\n", "\n", ".", " "],  # 분할 우선순위
    length_function=len,
)

chunks = splitter.split_documents(docs)

# ═══ 2. 벡터 임베딩 & 저장 ═══
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma, FAISS

# 임베딩 모델
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# ChromaDB에 저장
vectorstore = Chroma.from_documents(
    documents=chunks,
    embedding=embeddings,
    persist_directory="./chroma_db",
    collection_name="my_docs",
)

# 또는 FAISS (로컬, 빠름)
vectorstore = FAISS.from_documents(chunks, embeddings)
vectorstore.save_local("./faiss_index")

# ═══ 3. 검색 + 생성 ═══
from langchain_openai import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain.prompts import ChatPromptTemplate

# 검색기 설정
retriever = vectorstore.as_retriever(
    search_type="mmr",          # MMR: 다양성 + 관련성 균형
    search_kwargs={
        "k": 5,                  # 상위 5개 문서
        "fetch_k": 20,           # MMR 후보 20개
        "lambda_mult": 0.7,      # 관련성 70%, 다양성 30%
    },
)

# 프롬프트
prompt = ChatPromptTemplate.from_template("""
다음 문서를 참고하여 질문에 답변하세요.
문서에 없는 내용은 "해당 정보를 찾을 수 없습니다"라고 답변하세요.

참고 문서:
{context}

질문: {question}

답변:""")

# LLM
llm = ChatOpenAI(model="gpt-4o", temperature=0)

# RAG 체인
chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=retriever,
    chain_type_kwargs={"prompt": prompt},
    return_source_documents=True,
)

# 질의
result = chain.invoke({"query": "화랑 AI의 주요 기능은?"})
print(result["result"])
for doc in result["source_documents"]:
    print(f"  출처: {doc.metadata['source']} (p.{doc.metadata.get('page', '?')})")

# ═══ 4. 하이브리드 검색 (키워드 + 벡터) ═══
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever

# BM25 (키워드 기반)
bm25_retriever = BM25Retriever.from_documents(chunks, k=5)

# 벡터 검색
vector_retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

# 하이브리드 (50:50)
hybrid_retriever = EnsembleRetriever(
    retrievers=[bm25_retriever, vector_retriever],
    weights=[0.4, 0.6],  # 벡터에 더 가중치
)

# ═══ 5. 리랭킹 (Reranking) ═══
from langchain.retrievers import ContextualCompressionRetriever
from langchain_cohere import CohereRerank

reranker = CohereRerank(model="rerank-v3.5", top_n=3)
compression_retriever = ContextualCompressionRetriever(
    base_compressor=reranker,
    base_retriever=hybrid_retriever,
)
```

RAG 최적화 체크리스트:
1. **청킹**: 의미 단위 분할 (1000자 + 200 오버랩)
2. **임베딩**: 다국어 모델 사용 (한국어 지원)
3. **하이브리드 검색**: 벡터 + BM25 조합
4. **리랭킹**: Cohere Rerank로 최종 순위 조정
5. **프롬프트**: "문서에 없으면 모른다고 답하라" 지시'''),

    # ═══ AI 에이전트 ═══
    m("AI 에이전트 만드는 방법 알려줘 도구 사용 포함",
'''AI 에이전트는 스스로 판단하고 도구를 사용하는 시스템입니다.

```python
# ═══ LangChain Agent (2025 최신) ═══
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# 1. 도구 정의
@tool
def search_web(query: str) -> str:
    """웹에서 최신 정보를 검색합니다."""
    # Tavily, Serper 등 API 사용
    from tavily import TavilyClient
    client = TavilyClient()
    results = client.search(query, max_results=3)
    return "\\n".join([r["content"] for r in results["results"]])

@tool
def execute_python(code: str) -> str:
    """파이썬 코드를 실행하고 결과를 반환합니다."""
    import subprocess
    result = subprocess.run(
        ["python3", "-c", code],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout or result.stderr

@tool
def read_file(path: str) -> str:
    """파일 내용을 읽습니다."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()[:5000]  # 최대 5000자

@tool
def write_file(path: str, content: str) -> str:
    """파일에 내용을 씁니다."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"파일 저장 완료: {path}"

@tool
def query_database(sql: str) -> str:
    """PostgreSQL 데이터베이스에 쿼리를 실행합니다. SELECT만 허용."""
    if not sql.strip().upper().startswith("SELECT"):
        return "오류: SELECT 쿼리만 실행 가능합니다"
    import asyncpg
    # ... DB 연결 및 실행
    return str(rows)

# 2. 에이전트 프롬프트
prompt = ChatPromptTemplate.from_messages([
    ("system", """당신은 화랑 AI 어시스턴트입니다.
사용자의 요청을 단계적으로 분석하고, 필요한 도구를 사용하여 해결합니다.

규칙:
- 복잡한 작업은 단계로 나누어 처리
- 코드 실행 전 안전성 확인
- DB 쿼리는 SELECT만 허용
- 결과를 한국어로 명확하게 설명"""),
    MessagesPlaceholder(variable_name="chat_history", optional=True),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# 3. 에이전트 생성
llm = ChatOpenAI(model="gpt-4o", temperature=0)
tools = [search_web, execute_python, read_file, write_file, query_database]

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,        # 추론 과정 출력
    max_iterations=10,   # 최대 반복
    handle_parsing_errors=True,
)

# 4. 실행
result = executor.invoke({
    "input": "현재 디렉토리의 Python 파일을 분석하고 개선점을 알려줘",
})
print(result["output"])

# ═══ ReAct 패턴 직접 구현 ═══
class SimpleAgent:
    def __init__(self, llm, tools: dict):
        self.llm = llm
        self.tools = tools
        self.max_steps = 10

    async def run(self, task: str) -> str:
        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": task},
        ]

        for step in range(self.max_steps):
            response = await self.llm.chat(messages, tools=self._tool_schemas())

            # 도구 호출이 없으면 최종 답변
            if not response.tool_calls:
                return response.content

            # 도구 실행
            for call in response.tool_calls:
                tool_fn = self.tools[call.function.name]
                result = await tool_fn(**json.loads(call.function.arguments))

                messages.append({"role": "assistant", "tool_calls": [call]})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": str(result),
                })

        return "최대 단계 초과"

# 5. 멀티 에이전트 (CrewAI 스타일)
from crewai import Agent, Task, Crew

researcher = Agent(
    role="조사원",
    goal="주제에 대한 최신 정보를 수집합니다",
    backstory="당신은 철저한 리서치 전문가입니다",
    tools=[search_web],
    llm=llm,
)

writer = Agent(
    role="작성자",
    goal="조사 결과를 바탕으로 보고서를 작성합니다",
    backstory="당신은 명확한 기술 문서 작성 전문가입니다",
    tools=[write_file],
    llm=llm,
)

research_task = Task(
    description="AI 에이전트 최신 동향을 조사하세요",
    agent=researcher,
)

write_task = Task(
    description="조사 결과를 보고서로 작성하세요",
    agent=writer,
    context=[research_task],  # 조사 결과 참조
)

crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, write_task],
    verbose=True,
)

result = crew.kickoff()
```

AI 에이전트 핵심:
- **ReAct**: 생각(Reason) → 행동(Act) → 관찰(Observe) 반복
- **도구 호출**: LLM이 필요한 도구를 스스로 선택
- **메모리**: 대화 히스토리 + 장기 기억
- **멀티 에이전트**: 역할별 에이전트 협업'''),

    # ═══ 프롬프트 엔지니어링 ═══
    m("프롬프트 엔지니어링 기법 알려줘 실무 코드로",
'''프롬프트 엔지니어링 핵심 기법입니다.

```python
# ═══ 1. 구조화된 출력 (Structured Output) ═══
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

class ProductReview(BaseModel):
    """상품 리뷰 분석 결과."""
    sentiment: str = Field(description="긍정/부정/중립")
    score: float = Field(ge=0, le=1, description="감성 점수 (0~1)")
    keywords: list[str] = Field(description="핵심 키워드 3-5개")
    summary: str = Field(description="한 줄 요약")
    aspects: dict[str, str] = Field(description="측면별 평가 (품질, 배송, 가격)")

llm = ChatOpenAI(model="gpt-4o", temperature=0)
structured_llm = llm.with_structured_output(ProductReview)

result = structured_llm.invoke(
    "리뷰: 배송은 빨랐는데 품질이 별로예요. 가격 대비 아쉽습니다."
)
# result.sentiment = "부정"
# result.score = 0.3
# result.keywords = ["배송", "품질", "가격 대비"]

# ═══ 2. Few-Shot 프롬프트 ═══
from langchain_core.prompts import FewShotChatMessagePromptTemplate

examples = [
    {"input": "서울 날씨 알려줘", "output": '{"intent": "weather", "location": "서울"}'},
    {"input": "오늘 뉴스 뭐 있어?", "output": '{"intent": "news", "topic": "general"}'},
    {"input": "파이썬 정렬 방법", "output": '{"intent": "coding", "language": "python", "topic": "sorting"}'},
]

few_shot = FewShotChatMessagePromptTemplate(
    example_prompt=ChatPromptTemplate.from_messages([
        ("human", "{input}"),
        ("ai", "{output}"),
    ]),
    examples=examples,
)

prompt = ChatPromptTemplate.from_messages([
    ("system", "사용자 의도를 JSON으로 분류하세요."),
    few_shot,
    ("human", "{input}"),
])

# ═══ 3. Chain of Thought (CoT) ═══
cot_prompt = """
문제를 단계별로 분석하세요.

질문: {question}

단계별 분석:
1. 먼저 문제를 이해합니다.
2. 핵심 요소를 파악합니다.
3. 각 요소를 분석합니다.
4. 결론을 도출합니다.

분석 결과:
"""

# ═══ 4. 자기 일관성 (Self-Consistency) ═══
async def self_consistency(question: str, n: int = 5) -> str:
    """여러 번 답변을 생성하고 다수결로 최종 답변 선택."""
    responses = await asyncio.gather(*[
        llm.ainvoke(question) for _ in range(n)
    ])
    # 가장 많이 나온 답변 선택
    from collections import Counter
    answers = [extract_answer(r.content) for r in responses]
    most_common = Counter(answers).most_common(1)[0][0]
    return most_common

# ═══ 5. 시스템 프롬프트 설계 ═══
SYSTEM_PROMPT = """당신은 화랑 AI입니다. 퍼시스모어가 만든 한국형 AI 어시스턴트입니다.

## 역할
- 코딩, 디자인, 문서 작성을 도와드립니다
- 한국어를 기본으로 사용하되, 요청 시 해당 언어로 응답합니다

## 응답 규칙
1. 정확하고 실무적인 답변을 제공합니다
2. 코드는 주석과 설명을 한국어로 작성합니다
3. 모르는 것은 모른다고 솔직하게 답합니다
4. 보안에 위험한 코드는 작성하지 않습니다

## 형식
- 코드 블록에는 언어 태그를 포함합니다
- 긴 답변은 제목과 목록으로 구조화합니다
- 비교는 표로 정리합니다

## 금지 사항
- 불법적이거나 비윤리적인 내용
- 허위 정보나 확인되지 않은 의료/법률 조언
- 개인정보 수집이나 악성 코드
"""

# ═══ 6. 가드레일 (Guardrails) ═══
from pydantic import validator

class SafeResponse(BaseModel):
    response: str
    is_safe: bool = True
    refused_reason: str | None = None

    @validator("response")
    def check_safety(cls, v):
        dangerous_patterns = ["rm -rf", "DROP TABLE", "eval(", "exec("]
        for pattern in dangerous_patterns:
            if pattern.lower() in v.lower():
                raise ValueError(f"위험한 패턴 감지: {pattern}")
        return v
```

프롬프트 엔지니어링 핵심:
| 기법 | 사용 시나리오 |
|------|-------------|
| 구조화 출력 | JSON/객체 응답 필요 시 |
| Few-Shot | 패턴 학습 (분류, 변환) |
| CoT | 복잡한 추론/수학 |
| Self-Consistency | 정확도가 중요한 판단 |
| 시스템 프롬프트 | 역할/규칙 정의 |
| 가드레일 | 안전성 보장 |'''),

    # ═══ 벡터 DB ═══
    m("벡터 데이터베이스 비교해줘 실무 사용법 포함",
'''2025년 기준 벡터 DB 비교와 실무 사용법입니다.

```python
# ═══ 1. ChromaDB (로컬, 가장 쉬움) ═══
import chromadb
from chromadb.utils import embedding_functions

# 클라이언트 생성
client = chromadb.PersistentClient(path="./chroma_db")

# 임베딩 함수
ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="intfloat/multilingual-e5-large"  # 한국어 지원
)

# 컬렉션 생성
collection = client.get_or_create_collection(
    name="documents",
    embedding_function=ef,
    metadata={"hnsw:space": "cosine"},  # 코사인 유사도
)

# 문서 추가
collection.add(
    ids=["doc1", "doc2", "doc3"],
    documents=["화랑 AI 소개", "코딩 도움", "디자인 어시스턴트"],
    metadatas=[
        {"source": "intro", "category": "about"},
        {"source": "features", "category": "coding"},
        {"source": "features", "category": "design"},
    ],
)

# 검색
results = collection.query(
    query_texts=["AI 코딩 도우미"],
    n_results=3,
    where={"category": "coding"},  # 메타데이터 필터
)

# ═══ 2. Pinecone (클라우드, 프로덕션) ═══
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="xxx")

# 인덱스 생성
pc.create_index(
    name="hwarang-docs",
    dimension=1024,
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
)

index = pc.Index("hwarang-docs")

# 업서트
index.upsert(
    vectors=[
        {
            "id": "doc1",
            "values": embedding_vector,  # [0.1, 0.2, ...]
            "metadata": {"text": "원본 텍스트", "source": "manual"},
        },
    ],
    namespace="production",
)

# 검색
results = index.query(
    vector=query_embedding,
    top_k=5,
    include_metadata=True,
    filter={"source": {"$eq": "manual"}},
    namespace="production",
)

# ═══ 3. Qdrant (하이브리드 검색) ═══
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue,
)

client = QdrantClient(url="http://localhost:6333")

# 컬렉션 생성
client.create_collection(
    collection_name="documents",
    vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
)

# 포인트 추가
client.upsert(
    collection_name="documents",
    points=[
        PointStruct(
            id=1,
            vector=embedding,
            payload={"text": "내용", "category": "coding", "date": "2025-04-20"},
        ),
    ],
)

# 필터 + 벡터 검색
results = client.search(
    collection_name="documents",
    query_vector=query_embedding,
    limit=5,
    query_filter=Filter(
        must=[FieldCondition(key="category", match=MatchValue(value="coding"))],
    ),
)

# ═══ 4. pgvector (PostgreSQL 확장) ═══
-- SQL로 벡터 검색 (기존 DB에 추가)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(1024),  -- 1024차원 벡터
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW 인덱스 (빠른 검색)
CREATE INDEX ON documents
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 200);

-- 유사도 검색
SELECT id, content, metadata,
       1 - (embedding <=> $1::vector) AS similarity
FROM documents
WHERE metadata->>'category' = 'coding'
ORDER BY embedding <=> $1::vector
LIMIT 5;
```

벡터 DB 비교:
| DB | 특징 | 가격 | 추천 |
|----|------|------|------|
| ChromaDB | 로컬, 쉬움 | 무료 | 프로토타입, 소규모 |
| Pinecone | 클라우드, 관리형 | 유료 | 프로덕션, 대규모 |
| Qdrant | 하이브리드, 필터링 강력 | 무료/유료 | 복잡한 검색 |
| pgvector | PostgreSQL 확장 | 무료 | 기존 PG 사용 시 |
| Weaviate | GraphQL API | 무료/유료 | 멀티모달 |
| Milvus | 대규모, 분산 | 무료 | 수십억 벡터 |'''),

    # ═══ LLM API 활용 ═══
    m("OpenAI API 실무 활용 패턴 알려줘 스트리밍 포함",
'''OpenAI API 실무 활용 패턴입니다 (2025 최신).

```python
# ═══ 1. 기본 호출 ═══
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key="sk-xxx")

# 단일 호출
response = await client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "한국어로 답변하세요."},
        {"role": "user", "content": "파이썬 리스트 정렬 방법 알려줘"},
    ],
    temperature=0.7,
    max_tokens=2000,
)
print(response.choices[0].message.content)

# ═══ 2. 스트리밍 ═══
async def stream_chat(messages: list[dict]) -> AsyncGenerator[str, None]:
    """스트리밍으로 실시간 응답."""
    stream = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta

# FastAPI SSE 스트리밍
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

@app.post("/api/chat")
async def chat(request: ChatRequest):
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    async def event_stream():
        async for token in stream_chat(messages):
            yield f"data: {json.dumps({'token': token})}\\n\\n"
        yield "data: [DONE]\\n\\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

# ═══ 3. 도구 호출 (Function Calling) ═══
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "특정 도시의 현재 날씨를 조회합니다",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "도시 이름 (예: 서울)"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
                "required": ["city"],
            },
        },
    },
]

response = await client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "서울 날씨 알려줘"}],
    tools=tools,
    tool_choice="auto",
)

# 도구 호출 처리
if response.choices[0].message.tool_calls:
    for call in response.choices[0].message.tool_calls:
        args = json.loads(call.function.arguments)
        result = get_weather(**args)  # 실제 함수 실행

        # 결과를 다시 LLM에 전달
        messages.append(response.choices[0].message)
        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": json.dumps(result),
        })

    final = await client.chat.completions.create(
        model="gpt-4o", messages=messages,
    )

# ═══ 4. 비전 (이미지 분석) ═══
response = await client.chat.completions.create(
    model="gpt-4o",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "이 이미지를 분석해주세요"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
        ],
    }],
)

# ═══ 5. 배치 처리 (비용 절감) ═══
async def batch_process(items: list[str], concurrency: int = 5):
    """세마포어로 동시 요청 제한."""
    sem = asyncio.Semaphore(concurrency)

    async def process_one(item: str) -> str:
        async with sem:
            response = await client.chat.completions.create(
                model="gpt-4o-mini",  # 배치는 저렴한 모델
                messages=[{"role": "user", "content": item}],
            )
            return response.choices[0].message.content

    return await asyncio.gather(*[process_one(item) for item in items])

# ═══ 6. 에러 처리 + 재시도 ═══
from openai import RateLimitError, APIError
import tenacity

@tenacity.retry(
    retry=tenacity.retry_if_exception_type((RateLimitError, APIError)),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=60),
    stop=tenacity.stop_after_attempt(5),
)
async def robust_chat(messages):
    return await client.chat.completions.create(
        model="gpt-4o", messages=messages,
    )
```

비용 최적화:
| 전략 | 절감 효과 |
|------|-----------|
| gpt-4o-mini 사용 | 90% (간단한 작업) |
| 캐싱 (Redis) | 중복 요청 제거 |
| 배치 처리 | API 비용 50% |
| 프롬프트 최적화 | 토큰 수 줄이기 |
| 스트리밍 | 체감 속도 향상 |'''),

    # ═══ 파인튜닝 ═══
    m("LLM 파인튜닝 방법 알려줘 LoRA QLoRA",
'''LLM 파인튜닝의 핵심 기법입니다.

```python
# ═══ 1. QLoRA 파인튜닝 (GPU 메모리 절약) ═══
from transformers import (
    AutoModelForCausalLM, AutoTokenizer,
    TrainingArguments, BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer
from datasets import load_dataset

# 4비트 양자화 설정
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype="bfloat16",
    bnb_4bit_use_double_quant=True,
)

# 모델 로드 (4비트)
model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-32B",
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True,
)
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-32B")

# LoRA 설정
lora_config = LoraConfig(
    r=16,                    # LoRA 랭크 (8~64)
    lora_alpha=32,           # 스케일링 (보통 r*2)
    target_modules=[         # 적용할 레이어
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)

# 모델 준비
model = prepare_model_for_kbit_training(model)
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()
# 학습 파라미터: ~0.1% (32B 중 ~30M만 학습)

# 학습 설정
training_args = TrainingArguments(
    output_dir="./outputs/hwarang-lora",
    num_train_epochs=10,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=8,  # 실질 배치 8
    learning_rate=2e-4,
    warmup_ratio=0.1,
    lr_scheduler_type="cosine",
    bf16=True,
    logging_steps=10,
    save_steps=100,
    save_total_limit=3,
    optim="paged_adamw_8bit",
    gradient_checkpointing=True,
    max_grad_norm=0.3,
)

# ═══ 2. 데이터셋 준비 ═══
# ChatML 형식
def format_chat(example):
    messages = example["messages"]
    text = tokenizer.apply_chat_template(messages, tokenize=False)
    return {"text": text}

dataset = load_dataset("json", data_files="data/sft/hwarang_all_v2.jsonl")
dataset = dataset["train"].map(format_chat)

# ═══ 3. 학습 실행 ═══
trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
    tokenizer=tokenizer,
    max_seq_length=4096,
    dataset_text_field="text",
    packing=True,  # 짧은 샘플을 합쳐서 효율적 학습
)

trainer.train()
trainer.save_model("./outputs/hwarang-lora")

# ═══ 4. LoRA 머지 (CPU) ═══
from peft import PeftModel

# CPU에서 머지 (메모리 절약)
base_model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-32B",
    device_map="cpu",
    torch_dtype="float16",
)
model = PeftModel.from_pretrained(base_model, "./outputs/hwarang-lora")
merged = model.merge_and_unload()
merged.save_pretrained("./outputs/hwarang-merged")
tokenizer.save_pretrained("./outputs/hwarang-merged")

# ═══ 5. vLLM 서빙 ═══
# vllm serve ./outputs/hwarang-merged \\
#   --quantization bitsandbytes \\
#   --load-format bitsandbytes \\
#   --port 8000
```

파인튜닝 핵심:
| 항목 | 권장값 |
|------|--------|
| LoRA r | 16 (소규모 데이터), 64 (대규모) |
| 학습률 | 1e-4 ~ 2e-4 |
| 에포크 | 3~10 (데이터 크기에 따라) |
| 배치 크기 | 가능한 크게 (gradient accumulation) |
| 데이터 품질 | 양보다 질! 100건 고품질 > 10만건 저품질 |'''),

    # ═══ 임베딩 & 시맨틱 검색 ═══
    m("임베딩 모델 사용법이랑 시맨틱 검색 알려줘",
'''임베딩과 시맨틱 검색 실무 구현입니다.

```python
# ═══ 1. 임베딩 모델 비교 ═══

# OpenAI 임베딩 (가장 쉬움, 유료)
from openai import OpenAI
client = OpenAI()

response = client.embeddings.create(
    model="text-embedding-3-small",  # 1536차원, 저렴
    input=["화랑 AI는 한국형 AI 어시스턴트입니다"],
)
embedding = response.data[0].embedding  # list[float]

# 로컬 임베딩 (무료, 한국어 최적)
from sentence_transformers import SentenceTransformer

# 한국어 최적 모델들
model = SentenceTransformer("intfloat/multilingual-e5-large")
# 또는
model = SentenceTransformer("BAAI/bge-m3")

# 단일 임베딩
embedding = model.encode("화랑 AI는 한국형 AI 어시스턴트입니다")

# 배치 임베딩
texts = ["문서1", "문서2", "문서3"]
embeddings = model.encode(texts, batch_size=32, show_progress_bar=True)

# ═══ 2. 시맨틱 검색 구현 ═══
import numpy as np
from numpy.linalg import norm

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """코사인 유사도 계산."""
    return np.dot(a, b) / (norm(a) * norm(b))

class SemanticSearch:
    def __init__(self, model_name: str = "intfloat/multilingual-e5-large"):
        self.model = SentenceTransformer(model_name)
        self.documents: list[dict] = []
        self.embeddings: np.ndarray | None = None

    def add_documents(self, docs: list[dict]):
        """문서 추가 및 임베딩."""
        self.documents.extend(docs)
        texts = [d["content"] for d in docs]
        new_embeddings = self.model.encode(texts, normalize_embeddings=True)

        if self.embeddings is None:
            self.embeddings = new_embeddings
        else:
            self.embeddings = np.vstack([self.embeddings, new_embeddings])

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """시맨틱 검색."""
        query_embedding = self.model.encode(query, normalize_embeddings=True)

        # 코사인 유사도 (정규화된 벡터의 내적)
        similarities = self.embeddings @ query_embedding

        # 상위 k개
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            results.append({
                **self.documents[idx],
                "score": float(similarities[idx]),
            })
        return results

# 사용
search = SemanticSearch()
search.add_documents([
    {"id": 1, "content": "파이썬 리스트 정렬 방법", "category": "python"},
    {"id": 2, "content": "React 상태 관리 패턴", "category": "react"},
    {"id": 3, "content": "SQL 쿼리 최적화 기법", "category": "database"},
])

results = search.search("배열을 어떻게 정렬하나요?")
# results[0] = {"id": 1, "content": "파이썬 리스트 정렬 방법", "score": 0.87}

# ═══ 3. FastAPI 시맨틱 검색 API ═══
from fastapi import FastAPI

app = FastAPI()
search_engine = SemanticSearch()

@app.post("/index")
async def index_documents(docs: list[Document]):
    search_engine.add_documents([d.dict() for d in docs])
    return {"indexed": len(docs)}

@app.get("/search")
async def search(q: str, top_k: int = 5):
    results = search_engine.search(q, top_k)
    return {"query": q, "results": results}
```

임베딩 모델 선택:
| 모델 | 차원 | 한국어 | 비용 | 추천 |
|------|------|--------|------|------|
| text-embedding-3-small | 1536 | ⭐⭐⭐ | 유료 | 빠른 시작 |
| multilingual-e5-large | 1024 | ⭐⭐⭐⭐ | 무료 | 한국어 최적 |
| bge-m3 | 1024 | ⭐⭐⭐⭐⭐ | 무료 | 다국어 최고 |
| KoSimCSE | 768 | ⭐⭐⭐⭐⭐ | 무료 | 한국어 전용 |'''),

]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/sft/ai_programming.jsonl")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in DATA:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info("=" * 60)
    logger.info(" 화랑 AI AI/LLM 프로그래밍 학습 데이터")
    logger.info("=" * 60)
    logger.info(f"  AI 프로그래밍: {len(DATA)}건")
    logger.info(f"\n총 {len(DATA)}건 → {args.output}")

if __name__ == "__main__":
    main()
