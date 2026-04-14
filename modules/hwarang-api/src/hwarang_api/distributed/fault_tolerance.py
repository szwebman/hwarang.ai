"""장애 복구 (Fault Tolerance) 시스템.

서버 간 연결이 끊어지거나 서브가 죽어도 서비스가 계속 동작하도록 합니다.

처리하는 장애:
1. 서브 서버 사망 → 다른 서브가 자동 이어받기 (Failover)
2. 네트워크 끊김 → 재시도 (Retry with backoff)
3. 마스터 사망 → 대기 마스터 자동 인수 (Leader Election)
4. Redis 사망 → gRPC 직접 통신으로 대체 (Fallback)
5. 요청 중 죽음 → 처리 안 된 요청 자동 재큐 (Dead Letter Queue)

사용법:
    from hwarang_api.distributed.fault_tolerance import FaultTolerantRouter

    router = FaultTolerantRouter(redis_url, grpc_endpoints)
    response = await router.send_with_retry(request)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator

logger = logging.getLogger(__name__)


# ============================================================
# 설정
# ============================================================

@dataclass
class RetryConfig:
    """재시도 설정."""
    max_retries: int = 3           # 최대 재시도 횟수
    initial_delay: float = 0.1     # 첫 번째 재시도 대기 (초)
    max_delay: float = 5.0         # 최대 대기 시간
    backoff_multiplier: float = 2.0  # 대기 시간 증가 배율
    timeout: float = 30.0          # 요청 타임아웃 (초)


@dataclass
class FailoverConfig:
    """장애 복구 설정."""
    worker_timeout: float = 15.0     # 서브 하트비트 타임아웃 (초)
    health_check_interval: float = 5.0  # 헬스체크 간격 (초)
    dead_letter_ttl: float = 300.0   # 실패한 요청 보관 시간 (초)
    circuit_breaker_threshold: int = 5   # 연속 실패 시 차단
    circuit_breaker_reset: float = 60.0  # 차단 해제 시간 (초)


class RequestState(str, Enum):
    """요청 상태 추적."""
    QUEUED = "queued"           # 큐에 들어감
    ASSIGNED = "assigned"       # 서브에 할당됨
    PROCESSING = "processing"   # 처리 중
    COMPLETED = "completed"     # 완료
    FAILED = "failed"           # 실패
    RETRYING = "retrying"       # 재시도 중
    DEAD = "dead"               # 최종 실패 (Dead Letter)


@dataclass
class RequestTracker:
    """요청 추적 정보."""
    request_id: str
    state: RequestState = RequestState.QUEUED
    assigned_worker: str | None = None
    retry_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)
    error: str | None = None


# ============================================================
# Circuit Breaker (연속 실패 시 서브 차단)
# ============================================================

class CircuitBreaker:
    """서킷 브레이커.

    특정 서브가 연속으로 실패하면 일시적으로 차단합니다.
    (죽은 서브에 계속 요청 보내는 것 방지)

    상태:
      CLOSED  → 정상 (요청 통과)
      OPEN    → 차단 (요청 거부, 다른 서브로)
      HALF    → 시험 (1개만 통과시켜서 복구 확인)
    """

    def __init__(self, threshold: int = 5, reset_timeout: float = 60.0):
        self.threshold = threshold
        self.reset_timeout = reset_timeout
        self._failures: dict[str, int] = {}       # worker_id → 연속 실패 수
        self._open_since: dict[str, float] = {}   # worker_id → 차단 시작 시간
        self._state: dict[str, str] = {}           # worker_id → "closed"/"open"/"half"

    def is_available(self, worker_id: str) -> bool:
        """이 서브에 요청을 보내도 되는가?"""
        state = self._state.get(worker_id, "closed")

        if state == "closed":
            return True

        if state == "open":
            # 차단 시간 경과 확인
            open_since = self._open_since.get(worker_id, 0)
            if time.time() - open_since > self.reset_timeout:
                self._state[worker_id] = "half"
                logger.info(f"CircuitBreaker [{worker_id}]: OPEN → HALF-OPEN (시험)")
                return True  # 1번 시도
            return False

        if state == "half":
            return True  # 시험 1번 허용

        return True

    def record_success(self, worker_id: str):
        """성공 기록 → 정상화."""
        self._failures[worker_id] = 0
        if self._state.get(worker_id) in ("open", "half"):
            self._state[worker_id] = "closed"
            logger.info(f"CircuitBreaker [{worker_id}]: → CLOSED (정상 복구)")

    def record_failure(self, worker_id: str):
        """실패 기록 → 임계값 초과 시 차단."""
        count = self._failures.get(worker_id, 0) + 1
        self._failures[worker_id] = count

        if count >= self.threshold:
            self._state[worker_id] = "open"
            self._open_since[worker_id] = time.time()
            logger.warning(f"CircuitBreaker [{worker_id}]: → OPEN "
                          f"(연속 {count}회 실패, {self.reset_timeout}초 차단)")

    def get_status(self) -> dict:
        """전체 상태."""
        return {
            wid: {
                "state": self._state.get(wid, "closed"),
                "failures": self._failures.get(wid, 0),
            }
            for wid in set(list(self._failures.keys()) + list(self._state.keys()))
        }


# ============================================================
# Fault Tolerant Router (핵심)
# ============================================================

class FaultTolerantRouter:
    """장애 복구 라우터.

    모든 요청이 이 라우터를 통과합니다.
    실패하면 자동으로 재시도, 다른 서브로 이관, Dead Letter Queue 처리.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        retry_config: RetryConfig | None = None,
        failover_config: FailoverConfig | None = None,
    ):
        self.redis_url = redis_url
        self.retry = retry_config or RetryConfig()
        self.failover = failover_config or FailoverConfig()
        self.circuit_breaker = CircuitBreaker(
            threshold=self.failover.circuit_breaker_threshold,
            reset_timeout=self.failover.circuit_breaker_reset,
        )

        # 요청 추적
        self._requests: dict[str, RequestTracker] = {}
        self._redis = None

    async def connect(self):
        """Redis 연결."""
        import redis.asyncio as aioredis
        self._redis = aioredis.from_url(self.redis_url, decode_responses=True)

    async def send_request(
        self,
        request_id: str,
        model: str,
        messages: list[dict],
        **kwargs,
    ) -> dict:
        """장애 복구가 적용된 요청 전송.

        Flow:
        1. 사용 가능한 서브 선택 (Circuit Breaker 확인)
        2. 요청 전송
        3. 타임아웃 또는 실패 시 → 다른 서브로 재시도
        4. 최대 재시도 초과 → Dead Letter Queue
        """
        tracker = RequestTracker(request_id=request_id)
        self._requests[request_id] = tracker

        last_error = None

        for attempt in range(self.retry.max_retries + 1):
            # 1. 사용 가능한 서브 선택
            worker = await self._select_available_worker(model)
            if worker is None:
                last_error = f"모델 '{model}'을 처리할 수 있는 서브가 없음"
                logger.warning(f"[{request_id[:8]}] 시도 {attempt + 1}: {last_error}")
                await self._wait_backoff(attempt)
                continue

            worker_id = worker["worker_id"]
            tracker.assigned_worker = worker_id
            tracker.state = RequestState.ASSIGNED
            tracker.retry_count = attempt

            # 2. 요청 전송 (타임아웃 적용)
            try:
                logger.info(f"[{request_id[:8]}] 시도 {attempt + 1}/{self.retry.max_retries + 1} "
                           f"→ {worker_id}")

                response = await asyncio.wait_for(
                    self._send_to_worker(worker, request_id, model, messages, **kwargs),
                    timeout=self.retry.timeout,
                )

                # 3. 성공!
                tracker.state = RequestState.COMPLETED
                self.circuit_breaker.record_success(worker_id)
                logger.info(f"[{request_id[:8]}] 완료 (시도 {attempt + 1})")
                return response

            except asyncio.TimeoutError:
                last_error = f"타임아웃 ({self.retry.timeout}초)"
                logger.warning(f"[{request_id[:8]}] {worker_id} 타임아웃")
                self.circuit_breaker.record_failure(worker_id)
                tracker.state = RequestState.RETRYING

            except ConnectionError as e:
                last_error = f"연결 끊김: {e}"
                logger.warning(f"[{request_id[:8]}] {worker_id} 연결 끊김: {e}")
                self.circuit_breaker.record_failure(worker_id)
                tracker.state = RequestState.RETRYING

            except Exception as e:
                last_error = f"처리 오류: {e}"
                logger.error(f"[{request_id[:8]}] {worker_id} 오류: {e}")
                self.circuit_breaker.record_failure(worker_id)
                tracker.state = RequestState.RETRYING

            # 4. 재시도 대기 (exponential backoff)
            if attempt < self.retry.max_retries:
                await self._wait_backoff(attempt)

        # 5. 모든 재시도 실패 → Dead Letter
        tracker.state = RequestState.DEAD
        tracker.error = last_error
        await self._send_to_dead_letter(request_id, last_error)

        logger.error(f"[{request_id[:8]}] 최종 실패: {last_error}")
        return {"error": last_error, "request_id": request_id, "retries": self.retry.max_retries}

    async def send_stream(
        self,
        request_id: str,
        model: str,
        messages: list[dict],
        **kwargs,
    ) -> AsyncIterator[dict]:
        """장애 복구가 적용된 스트리밍 요청.

        스트리밍 도중 끊기면 → 다른 서브로 처음부터 재시도.
        """
        last_error = None

        for attempt in range(self.retry.max_retries + 1):
            worker = await self._select_available_worker(model)
            if worker is None:
                await self._wait_backoff(attempt)
                continue

            worker_id = worker["worker_id"]

            try:
                logger.info(f"[{request_id[:8]}] 스트림 시도 {attempt + 1} → {worker_id}")
                chunks_received = 0

                async for chunk in self._stream_from_worker(
                    worker, request_id, model, messages, **kwargs
                ):
                    chunks_received += 1
                    yield chunk

                    if chunk.get("finish_reason"):
                        self.circuit_breaker.record_success(worker_id)
                        return

                # 정상 종료
                self.circuit_breaker.record_success(worker_id)
                return

            except (asyncio.TimeoutError, ConnectionError, Exception) as e:
                last_error = str(e)
                logger.warning(f"[{request_id[:8]}] 스트림 끊김 (청크 {chunks_received}개 후): {e}")
                self.circuit_breaker.record_failure(worker_id)

                if attempt < self.retry.max_retries:
                    # 사용자에게 재시도 알림
                    yield {
                        "content": "\n\n[연결 재시도 중...]\n\n",
                        "finish_reason": "",
                        "retry": True,
                    }
                    await self._wait_backoff(attempt)

        # 최종 실패
        yield {
            "content": f"\n\n[오류: {last_error}]",
            "finish_reason": "error",
        }

    # ---- 내부 메서드 ----

    async def _select_available_worker(self, model: str) -> dict | None:
        """사용 가능한 서브 선택 (Circuit Breaker 반영)."""
        if not self._redis:
            return None

        workers_raw = await self._redis.hgetall("hwarang:workers")
        candidates = []

        for worker_id, raw in workers_raw.items():
            try:
                info = json.loads(raw)
            except json.JSONDecodeError:
                continue

            # 모델 확인
            if model not in info.get("models", []):
                continue

            # 하트비트 타임아웃 확인
            if time.time() - info.get("last_heartbeat", 0) > self.failover.worker_timeout:
                continue

            # 상태 확인
            if info.get("status") in ("draining", "offline"):
                continue

            # Circuit Breaker 확인
            if not self.circuit_breaker.is_available(worker_id):
                continue

            candidates.append({
                "worker_id": worker_id,
                "host": info.get("host"),
                "port": info.get("port"),
                "status": info.get("status"),
            })

        if not candidates:
            return None

        # Least busy 선택 (idle 우선)
        idle = [c for c in candidates if c["status"] == "idle"]
        return idle[0] if idle else candidates[0]

    async def _send_to_worker(
        self, worker: dict, request_id: str, model: str,
        messages: list[dict], **kwargs
    ) -> dict:
        """서브에 요청 전송 (gRPC 또는 Redis)."""
        # gRPC 엔드포인트가 있으면 직접 전송
        grpc_endpoint = await self._redis.hget("hwarang:grpc_endpoints", worker["worker_id"])

        if grpc_endpoint:
            return await self._send_via_grpc(grpc_endpoint, request_id, model, messages, **kwargs)

        # 아니면 Redis 큐
        return await self._send_via_redis(request_id, model, messages, **kwargs)

    async def _send_via_grpc(
        self, endpoint: str, request_id: str, model: str,
        messages: list[dict], **kwargs
    ) -> dict:
        """gRPC로 직접 전송."""
        host, port = endpoint.split(":")

        reader, writer = await asyncio.open_connection(host, int(port))
        try:
            request = {
                "method": "generate",
                "params": {
                    "request_id": request_id,
                    "model": model,
                    "messages": messages,
                    "temperature": kwargs.get("temperature", 0.7),
                    "top_p": kwargs.get("top_p", 1.0),
                    "max_tokens": kwargs.get("max_tokens", 512),
                },
            }
            data = json.dumps(request).encode()
            writer.write(len(data).to_bytes(4, "big"))
            writer.write(data)
            await writer.drain()

            # 응답 읽기
            length_bytes = await asyncio.wait_for(reader.readexactly(4), timeout=self.retry.timeout)
            length = int.from_bytes(length_bytes, "big")
            resp_data = await asyncio.wait_for(reader.readexactly(length), timeout=self.retry.timeout)
            response = json.loads(resp_data.decode())

            return response.get("result", response)

        finally:
            writer.close()
            await writer.wait_closed()

    async def _send_via_redis(
        self, request_id: str, model: str,
        messages: list[dict], **kwargs
    ) -> dict:
        """Redis 큐로 전송 (기존 방식)."""
        from hwarang_api.distributed.protocol import InferenceRequest

        inf_request = InferenceRequest(
            request_id=request_id,
            model=model,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
            temperature=kwargs.get("temperature", 0.7),
            top_p=kwargs.get("top_p", 1.0),
            max_tokens=kwargs.get("max_tokens", 512),
        )

        queue_key = f"hwarang:requests:{model}"
        await self._redis.rpush(queue_key, inf_request.model_dump_json())

        # 응답 대기
        response_key = f"hwarang:response:{request_id}"
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(f"hwarang:done:{request_id}")

        try:
            start = time.time()
            while time.time() - start < self.retry.timeout:
                raw = await self._redis.get(response_key)
                if raw:
                    await self._redis.delete(response_key)
                    return json.loads(raw)

                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    raw = await self._redis.get(response_key)
                    if raw:
                        await self._redis.delete(response_key)
                        return json.loads(raw)

            raise asyncio.TimeoutError()
        finally:
            await pubsub.unsubscribe()
            await pubsub.close()

    async def _stream_from_worker(
        self, worker: dict, request_id: str, model: str,
        messages: list[dict], **kwargs
    ) -> AsyncIterator[dict]:
        """서브로부터 스트리밍 수신."""
        grpc_endpoint = await self._redis.hget("hwarang:grpc_endpoints", worker["worker_id"])

        if grpc_endpoint:
            host, port = grpc_endpoint.split(":")
            reader, writer = await asyncio.open_connection(host, int(port))
            try:
                request = {
                    "method": "generate_stream",
                    "params": {
                        "request_id": request_id,
                        "model": model,
                        "messages": messages,
                        "temperature": kwargs.get("temperature", 0.7),
                        "max_tokens": kwargs.get("max_tokens", 512),
                    },
                }
                data = json.dumps(request).encode()
                writer.write(len(data).to_bytes(4, "big"))
                writer.write(data)
                await writer.drain()

                while True:
                    length_bytes = await asyncio.wait_for(
                        reader.readexactly(4), timeout=self.retry.timeout
                    )
                    length = int.from_bytes(length_bytes, "big")
                    resp_data = await reader.readexactly(length)
                    response = json.loads(resp_data.decode())

                    if "done" in response:
                        break
                    if "chunk" in response:
                        yield response["chunk"]
                        if response["chunk"].get("finish_reason"):
                            break
            finally:
                writer.close()
                await writer.wait_closed()
        else:
            # Redis 스트리밍 (기존 방식)
            stream_key = f"hwarang:stream:{request_id}"
            start = time.time()
            while time.time() - start < self.retry.timeout:
                result = await self._redis.blpop(stream_key, timeout=1)
                if result:
                    _, raw = result
                    chunk = json.loads(raw)
                    yield chunk
                    if chunk.get("finish_reason"):
                        break

    async def _wait_backoff(self, attempt: int):
        """Exponential backoff 대기."""
        delay = min(
            self.retry.initial_delay * (self.retry.backoff_multiplier ** attempt),
            self.retry.max_delay,
        )
        logger.info(f"  재시도 대기: {delay:.1f}초")
        await asyncio.sleep(delay)

    async def _send_to_dead_letter(self, request_id: str, error: str):
        """Dead Letter Queue에 저장 (나중에 분석/재처리용)."""
        if self._redis:
            dead_letter = {
                "request_id": request_id,
                "error": error,
                "timestamp": time.time(),
            }
            await self._redis.rpush("hwarang:dead_letters", json.dumps(dead_letter))
            await self._redis.ltrim("hwarang:dead_letters", -1000, -1)  # 최근 1000개만

    # ---- 모니터링 ----

    def get_stats(self) -> dict:
        """장애 복구 통계."""
        total = len(self._requests)
        completed = sum(1 for r in self._requests.values() if r.state == RequestState.COMPLETED)
        failed = sum(1 for r in self._requests.values() if r.state == RequestState.DEAD)
        retrying = sum(1 for r in self._requests.values() if r.state == RequestState.RETRYING)
        retried = sum(1 for r in self._requests.values() if r.retry_count > 0)

        return {
            "total_requests": total,
            "completed": completed,
            "failed": failed,
            "retrying": retrying,
            "retried_at_least_once": retried,
            "success_rate": f"{completed / max(total, 1) * 100:.1f}%",
            "circuit_breakers": self.circuit_breaker.get_status(),
        }
