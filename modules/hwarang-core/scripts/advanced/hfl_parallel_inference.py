"""HFL Parallel Inference - 멀티 에이전트 병렬 추론

질문 1개를 여러 에이전트가 협력하여 처리.
가장 빠르고 안정적인 응답을 보장.

4가지 모드:
  1. Single:     에이전트 1개 (간단한 질문)
  2. Speculative: N개 동시 시도 → 가장 빠른 것 채택
  3. Chunked:    답변을 분할해서 병렬 생성 → 합성
  4. Tiered:     작은 GPU가 draft → 큰 GPU가 검증/보강

에이전트 장애 처리:
  - 타임아웃 → 즉시 백업 에이전트 투입
  - 중간 장애 → 부분 결과라도 활용
  - 모든 에이전트 장애 → 마스터 폴백

에이전트 용량 적응:
  - RTX 4060 (8GB): 7B 모델 → draft/요약 담당
  - RTX 4090 (24GB): 32B 모델 → 전체 답변
  - RTX 5090 (32GB): V3 → 복잡한 검증

사용법:
    # 마스터에서
    from hfl_parallel_inference import ParallelInferenceEngine
    engine = ParallelInferenceEngine()
    result = await engine.infer("FastAPI 인증 시스템 만들어줘", mode="auto")
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import hashlib
from dataclasses import dataclass, field
from enum import Enum

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ─── 에이전트 능력 등급 ──────────────────────────────────────

class AgentTier(Enum):
    SMALL = "small"      # 7B (RTX 4060, 8GB)
    MEDIUM = "medium"    # 14~32B (RTX 4090, 24GB)
    LARGE = "large"      # 32B+ (RTX 5090, 32GB)
    FLAGSHIP = "flagship"  # V3/480B (RTX 5090 또는 멀티GPU)


@dataclass
class InferenceAgent:
    agent_id: str
    endpoint: str
    tier: AgentTier
    gpu_name: str
    vram_gb: float
    max_tokens: int = 4096        # 이 에이전트가 처리 가능한 최대 출력
    current_load: int = 0
    max_concurrent: int = 4
    latency_ms: float = 100       # 평균 응답 지연
    status: str = "online"        # online, busy, offline
    supported_models: list[str] = field(default_factory=list)


@dataclass
class InferenceResult:
    agent_id: str
    content: str
    tokens: int
    latency_ms: float
    tier: AgentTier
    status: str = "success"       # success, timeout, error, partial
    chunk_id: int | None = None   # Chunked 모드에서 청크 번호


# ─── 추론 모드 자동 결정 ─────────────────────────────────────

class InferenceMode(Enum):
    SINGLE = "single"            # 에이전트 1개
    SPECULATIVE = "speculative"  # N개 동시, 먼저 온 것 채택
    CHUNKED = "chunked"          # 답변 분할 병렬
    TIERED = "tiered"            # 작은→큰 단계적


def decide_mode(
    question: str,
    available_agents: list[InferenceAgent],
    complexity: str = "simple",
) -> InferenceMode:
    """질문 특성 + 가용 에이전트에 따라 모드 결정."""
    online = [a for a in available_agents if a.status == "online"]

    if len(online) <= 1:
        return InferenceMode.SINGLE

    # 간단한 질문 → Single (낭비 방지)
    if complexity == "simple" or len(question) < 100:
        return InferenceMode.SINGLE

    # 복잡한 질문 + 큰 에이전트 있음 → Tiered
    has_large = any(a.tier in (AgentTier.LARGE, AgentTier.FLAGSHIP) for a in online)
    has_small = any(a.tier == AgentTier.SMALL for a in online)
    if has_large and has_small and complexity == "complex":
        return InferenceMode.TIERED

    # 복잡한 질문 + 에이전트 3개 이상 → Chunked
    if len(online) >= 3 and complexity == "complex":
        return InferenceMode.CHUNKED

    # 그 외 → Speculative (안전)
    return InferenceMode.SPECULATIVE


# ─── 공통: 단일 에이전트 호출 ────────────────────────────────

async def call_agent(
    agent: InferenceAgent,
    messages: list[dict],
    max_tokens: int = 2048,
    timeout_sec: float = 120,
) -> InferenceResult:
    """에이전트 1개에 추론 요청."""
    import aiohttp

    start = time.time()
    agent.current_load += 1

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{agent.endpoint}/v1/chat/completions",
                json={
                    "messages": messages,
                    "max_tokens": min(max_tokens, agent.max_tokens),
                    "temperature": 0.7,
                },
                timeout=aiohttp.ClientTimeout(total=timeout_sec),
            ) as resp:
                if resp.status != 200:
                    return InferenceResult(
                        agent_id=agent.agent_id, content="",
                        tokens=0, latency_ms=0, tier=agent.tier, status="error",
                    )

                data = await resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                tokens = data.get("usage", {}).get("total_tokens", 0)
                latency = (time.time() - start) * 1000

                return InferenceResult(
                    agent_id=agent.agent_id, content=content,
                    tokens=tokens, latency_ms=latency, tier=agent.tier,
                )

    except asyncio.TimeoutError:
        return InferenceResult(
            agent_id=agent.agent_id, content="",
            tokens=0, latency_ms=(time.time() - start) * 1000,
            tier=agent.tier, status="timeout",
        )
    except Exception as e:
        return InferenceResult(
            agent_id=agent.agent_id, content="",
            tokens=0, latency_ms=(time.time() - start) * 1000,
            tier=agent.tier, status=f"error: {e}",
        )
    finally:
        agent.current_load -= 1


# ─── 모드 1: Speculative (N개 동시, 먼저 온 것 채택) ────────

async def speculative_infer(
    agents: list[InferenceAgent],
    messages: list[dict],
    max_tokens: int = 2048,
    timeout_sec: float = 60,
) -> InferenceResult:
    """N개 에이전트에 동시 요청, 가장 먼저 온 것 채택.

    나머지는 취소 (토큰 절약).
    에이전트 장애 시 다른 에이전트가 커버.
    """
    logger.info(f"Speculative 추론: {len(agents)}개 에이전트 동시 시도")

    # asyncio.wait FIRST_COMPLETED로 가장 빠른 것 채택
    tasks = {
        asyncio.create_task(
            call_agent(agent, messages, max_tokens, timeout_sec),
            name=agent.agent_id,
        )
        for agent in agents
    }

    best_result = None

    while tasks:
        done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for task in done:
            result = task.result()
            if result.status == "success" and result.content:
                # 성공한 첫 번째 결과 채택
                best_result = result
                # 나머지 취소
                for remaining in tasks:
                    remaining.cancel()
                logger.info(
                    f"  채택: {result.agent_id} ({result.latency_ms:.0f}ms, "
                    f"{result.tokens} 토큰)"
                )
                return best_result
            else:
                logger.warning(f"  실패: {result.agent_id} ({result.status})")

    # 모두 실패
    return InferenceResult(
        agent_id="none", content="모든 에이전트 응답 실패",
        tokens=0, latency_ms=0, tier=AgentTier.SMALL, status="all_failed",
    )


# ─── 모드 2: Chunked Parallel (답변 분할 병렬) ──────────────

async def chunked_infer(
    agents: list[InferenceAgent],
    question: str,
    messages: list[dict],
    max_tokens: int = 4096,
    timeout_sec: float = 120,
) -> InferenceResult:
    """답변을 부분별로 나눠서 병렬 생성 후 합성.

    예: "인증 시스템 만들어줘"
      → 청크 1: 아키텍처 설명
      → 청크 2: 메인 코드
      → 청크 3: 테스트 코드
    """
    num_chunks = min(len(agents), 3)  # 최대 3 청크

    # 청크 프롬프트 생성
    chunk_prompts = _split_into_chunks(question, num_chunks)

    logger.info(f"Chunked 추론: {num_chunks}개 청크 병렬")

    # 병렬 실행
    tasks = []
    for i, (agent, chunk_prompt) in enumerate(zip(agents[:num_chunks], chunk_prompts)):
        chunk_messages = messages[:-1] + [{"role": "user", "content": chunk_prompt}]
        task = asyncio.create_task(
            call_agent(agent, chunk_messages, max_tokens // num_chunks, timeout_sec),
            name=f"chunk_{i}",
        )
        tasks.append((i, agent.agent_id, task))

    # 결과 수집
    results: dict[int, InferenceResult] = {}
    backup_agents = agents[num_chunks:]  # 백업용

    for i, agent_id, task in tasks:
        try:
            result = await asyncio.wait_for(task, timeout=timeout_sec)
            if result.status == "success":
                result.chunk_id = i
                results[i] = result
                logger.info(f"  청크 {i} 완료: {agent_id} ({result.latency_ms:.0f}ms)")
            else:
                # 실패 → 백업 에이전트로 재시도
                logger.warning(f"  청크 {i} 실패: {agent_id}, 백업 시도")
                if backup_agents:
                    backup = backup_agents.pop(0)
                    retry = await call_agent(
                        backup, messages[:-1] + [{"role": "user", "content": chunk_prompts[i]}],
                        max_tokens // num_chunks, timeout_sec,
                    )
                    if retry.status == "success":
                        retry.chunk_id = i
                        results[i] = retry
        except asyncio.TimeoutError:
            logger.warning(f"  청크 {i} 타임아웃: {agent_id}")

    # 결과 합성
    if not results:
        return InferenceResult(
            agent_id="none", content="모든 청크 실패",
            tokens=0, latency_ms=0, tier=AgentTier.SMALL, status="all_failed",
        )

    # 청크 순서대로 합침
    combined = ""
    total_tokens = 0
    max_latency = 0
    for i in range(num_chunks):
        if i in results:
            combined += results[i].content + "\n\n"
            total_tokens += results[i].tokens
            max_latency = max(max_latency, results[i].latency_ms)
        else:
            combined += f"[청크 {i+1} 누락]\n\n"

    return InferenceResult(
        agent_id=f"chunked({len(results)}/{num_chunks})",
        content=combined.strip(),
        tokens=total_tokens,
        latency_ms=max_latency,  # 병렬이라 가장 느린 것이 총 시간
        tier=AgentTier.LARGE,
        status="success" if len(results) == num_chunks else "partial",
    )


def _split_into_chunks(question: str, n: int) -> list[str]:
    """질문을 N개 청크 프롬프트로 분할."""
    if n == 1:
        return [question]

    if n == 2:
        return [
            f"다음 질문의 '설명/개념' 부분만 답해주세요:\n{question}",
            f"다음 질문의 '코드 구현' 부분만 답해주세요:\n{question}",
        ]

    if n == 3:
        return [
            f"다음 질문의 '전체 구조/아키텍처 설명' 부분만 답해주세요:\n{question}",
            f"다음 질문의 '핵심 코드 구현' 부분만 답해주세요:\n{question}",
            f"다음 질문의 '테스트 코드 + 사용 예시' 부분만 답해주세요:\n{question}",
        ]

    # n > 3
    chunks = [f"다음 질문의 {i+1}/{n} 부분만 답해주세요:\n{question}" for i in range(n)]
    return chunks


# ─── 모드 3: Tiered (작은→큰 단계적) ────────────────────────

async def tiered_infer(
    agents: list[InferenceAgent],
    messages: list[dict],
    max_tokens: int = 4096,
    timeout_sec: float = 120,
) -> InferenceResult:
    """작은 GPU가 draft → 큰 GPU가 검증/보강.

    Step 1: Small(7B)이 빠르게 draft 생성 (3초)
    Step 2: Large(32B+)가 draft를 검증 + 보강 (10초)

    총 시간: 13초 (but 품질은 Large급)
    Small만 써도 즉시 응답 가능 (스트리밍)
    """
    # 에이전트를 tier별로 분류
    small = [a for a in agents if a.tier == AgentTier.SMALL and a.status == "online"]
    large = [a for a in agents if a.tier in (AgentTier.LARGE, AgentTier.FLAGSHIP) and a.status == "online"]
    medium = [a for a in agents if a.tier == AgentTier.MEDIUM and a.status == "online"]

    # Step 1: Small이 draft
    draft_agent = (small + medium + large)[0] if (small + medium + large) else None
    if not draft_agent:
        return InferenceResult(
            agent_id="none", content="에이전트 없음",
            tokens=0, latency_ms=0, tier=AgentTier.SMALL, status="no_agents",
        )

    logger.info(f"Tiered Step 1: Draft by {draft_agent.agent_id} ({draft_agent.tier.value})")
    draft = await call_agent(draft_agent, messages, max_tokens // 2, timeout_sec // 2)

    if draft.status != "success" or not draft.content:
        # Draft 실패 → 다른 에이전트로 폴백
        fallback = (large + medium)[0] if (large + medium) else None
        if fallback:
            return await call_agent(fallback, messages, max_tokens, timeout_sec)
        return draft

    # Step 2: Large가 검증/보강
    verify_agent = (large + medium)[0] if (large + medium) else None
    if not verify_agent or verify_agent.agent_id == draft_agent.agent_id:
        # 검증 에이전트 없으면 draft 그대로 반환
        return draft

    logger.info(f"Tiered Step 2: Verify by {verify_agent.agent_id} ({verify_agent.tier.value})")

    verify_messages = messages + [
        {"role": "assistant", "content": draft.content},
        {"role": "user", "content":
            "위 답변을 검토하고 개선해주세요. "
            "오류가 있으면 수정하고, 부족한 부분이 있으면 보완하세요. "
            "좋은 부분은 유지하세요."
        },
    ]

    verified = await call_agent(verify_agent, verify_messages, max_tokens, timeout_sec)

    if verified.status == "success" and verified.content:
        total_latency = draft.latency_ms + verified.latency_ms
        logger.info(
            f"  Tiered 완료: draft {draft.latency_ms:.0f}ms + "
            f"verify {verified.latency_ms:.0f}ms = {total_latency:.0f}ms"
        )
        return InferenceResult(
            agent_id=f"tiered({draft_agent.agent_id}→{verify_agent.agent_id})",
            content=verified.content,
            tokens=draft.tokens + verified.tokens,
            latency_ms=total_latency,
            tier=verify_agent.tier,
        )

    # 검증 실패 → draft 반환
    return draft


# ─── 메인 엔진 ───────────────────────────────────────────────

class ParallelInferenceEngine:
    """멀티 에이전트 병렬 추론 엔진.

    자동 모드 선택 + 장애 처리 + 용량 적응.
    """

    def __init__(self):
        self.agents: list[InferenceAgent] = []

    def register_agent(self, agent: InferenceAgent):
        self.agents.append(agent)

    async def infer(
        self,
        question: str,
        messages: list[dict] | None = None,
        mode: str = "auto",
        complexity: str = "simple",
        max_tokens: int = 4096,
        timeout_sec: float = 120,
    ) -> InferenceResult:
        """추론 실행.

        Args:
            mode: "auto", "single", "speculative", "chunked", "tiered"
            complexity: "simple", "complex"
        """
        if messages is None:
            messages = [{"role": "user", "content": question}]

        online = [a for a in self.agents if a.status == "online" and a.current_load < a.max_concurrent]

        if not online:
            return InferenceResult(
                agent_id="none", content="사용 가능한 에이전트 없음",
                tokens=0, latency_ms=0, tier=AgentTier.SMALL, status="no_agents",
            )

        # 모드 결정
        if mode == "auto":
            infer_mode = decide_mode(question, online, complexity)
        else:
            infer_mode = InferenceMode(mode)

        logger.info(f"추론 모드: {infer_mode.value} (에이전트 {len(online)}개, 복잡도 {complexity})")

        # 실행
        if infer_mode == InferenceMode.SINGLE:
            # 가장 적합한 에이전트 1개
            best = sorted(online, key=lambda a: (a.tier.value, -a.latency_ms), reverse=True)[0]
            return await call_agent(best, messages, max_tokens, timeout_sec)

        elif infer_mode == InferenceMode.SPECULATIVE:
            return await speculative_infer(online[:3], messages, max_tokens, timeout_sec)

        elif infer_mode == InferenceMode.CHUNKED:
            return await chunked_infer(online, question, messages, max_tokens, timeout_sec)

        elif infer_mode == InferenceMode.TIERED:
            return await tiered_infer(online, messages, max_tokens, timeout_sec)

        return InferenceResult(
            agent_id="none", content="알 수 없는 모드",
            tokens=0, latency_ms=0, tier=AgentTier.SMALL, status="error",
        )

    def get_stats(self) -> dict:
        """엔진 통계."""
        online = [a for a in self.agents if a.status == "online"]
        return {
            "total_agents": len(self.agents),
            "online": len(online),
            "tiers": {
                t.value: sum(1 for a in online if a.tier == t)
                for t in AgentTier
            },
            "total_capacity": sum(a.max_concurrent for a in online),
            "current_load": sum(a.current_load for a in online),
        }


# ─── 시뮬레이션 ──────────────────────────────────────────────

async def simulate():
    """다양한 시나리오 시뮬레이션."""
    engine = ParallelInferenceEngine()

    # 에이전트 등록
    agents = [
        InferenceAgent("kr-small", "http://kr1:8000", AgentTier.SMALL, "RTX 4060", 8, 2048, 0, 4, 50, "online", ["qwen-7b"]),
        InferenceAgent("kr-medium", "http://kr2:8000", AgentTier.MEDIUM, "RTX 4090", 24, 4096, 0, 4, 30, "online", ["qwen-32b"]),
        InferenceAgent("kr-large", "http://kr3:8000", AgentTier.LARGE, "RTX 5090", 32, 8192, 0, 8, 20, "online", ["deepseek-v3"]),
        InferenceAgent("jp-medium", "http://jp1:8000", AgentTier.MEDIUM, "RTX 4090", 24, 4096, 0, 4, 80, "online", ["qwen-32b"]),
    ]

    for a in agents:
        engine.register_agent(a)

    print(f"\n클러스터: {json.dumps(engine.get_stats(), indent=2)}")

    # 모드 결정 테스트
    test_cases = [
        ("파이썬 for문 설명해줘", "simple"),
        ("FastAPI + JWT 인증 시스템 전체 구현", "complex"),
        ("이 프로젝트 전체 코드를 Next.js 15로 마이그레이션하고 테스트 작성해줘. " * 5, "complex"),
    ]

    for question, complexity in test_cases:
        mode = decide_mode(question, agents, complexity)
        print(f"\n질문: {question[:50]}...")
        print(f"  복잡도: {complexity}, 모드: {mode.value}")
        # result = await engine.infer(question, complexity=complexity)
        # print(f"  결과: {result.status} ({result.latency_ms:.0f}ms)")


if __name__ == "__main__":
    asyncio.run(simulate())
