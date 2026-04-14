"""Load Balancer - API 서버에서 Worker들에게 요청을 분배합니다.

전략:
1. Round-Robin: 기본, 순서대로 분배
2. Least-Connections: 가장 한가한 Worker에게 우선 분배
3. Model-Aware: 해당 모델이 로드된 Worker에게만 분배

API 서버가 직접 추론하지 않고, Redis 큐를 통해 Worker에게 위임합니다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator

import redis.asyncio as aioredis

from hwarang_api.distributed.protocol import (
    InferenceRequest,
    InferenceResponse,
    StreamChunk,
    WorkerInfo,
    WorkerStatus,
    WORKER_REGISTRY,
    WORKER_TIMEOUT,
)

logger = logging.getLogger(__name__)

# Redis keys (must match worker.py)
REQUEST_QUEUE = "hwarang:requests:{model}"
RESPONSE_KEY = "hwarang:response:{request_id}"
STREAM_KEY = "hwarang:stream:{request_id}"


class LoadBalancer:
    """Distributes inference requests across worker nodes via Redis."""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None

    async def connect(self) -> None:
        """Connect to Redis."""
        self.redis = aioredis.from_url(self.redis_url, decode_responses=True)
        await self.redis.ping()
        logger.info(f"LoadBalancer connected to Redis: {self.redis_url}")

    async def close(self) -> None:
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()

    async def get_workers(self, model_id: str | None = None) -> list[WorkerInfo]:
        """Get all registered workers, optionally filtered by model."""
        raw_workers = await self.redis.hgetall(WORKER_REGISTRY)
        workers = []
        now = time.time()

        for worker_id, raw in raw_workers.items():
            info = WorkerInfo.model_validate_json(raw)

            # Skip dead workers (no heartbeat in WORKER_TIMEOUT seconds)
            if now - info.last_heartbeat > WORKER_TIMEOUT:
                logger.debug(f"Worker {worker_id} timed out, removing")
                await self.redis.hdel(WORKER_REGISTRY, worker_id)
                continue

            # Filter by model
            if model_id and model_id not in info.models:
                continue

            workers.append(info)

        return workers

    async def get_available_workers(self, model_id: str) -> list[WorkerInfo]:
        """Get workers that can accept requests for a given model."""
        workers = await self.get_workers(model_id)
        return [w for w in workers if w.status in (WorkerStatus.IDLE, WorkerStatus.BUSY)]

    async def submit_request(self, request: InferenceRequest) -> InferenceResponse:
        """Submit a non-streaming request and wait for the response.

        Flow:
        1. Push request to model-specific Redis queue
        2. Subscribe to completion notification
        3. Read response from Redis
        """
        # Check if any worker can handle this model
        workers = await self.get_available_workers(request.model)
        if not workers:
            return InferenceResponse(
                request_id=request.request_id,
                worker_id="none",
                error=f"No workers available for model '{request.model}'. "
                      f"Available workers: {len(await self.get_workers())}",
            )

        # Push to model queue
        queue_key = REQUEST_QUEUE.format(model=request.model)
        await self.redis.rpush(queue_key, request.model_dump_json())

        # Wait for response
        response_key = RESPONSE_KEY.format(request_id=request.request_id)
        timeout_s = request.timeout_ms / 1000

        # Poll for response (with pub/sub notification)
        pubsub = self.redis.pubsub()
        channel = f"hwarang:done:{request.request_id}"
        await pubsub.subscribe(channel)

        try:
            start = time.time()
            while time.time() - start < timeout_s:
                # Check if response already exists
                raw = await self.redis.get(response_key)
                if raw:
                    await self.redis.delete(response_key)
                    return InferenceResponse.model_validate_json(raw)

                # Wait for notification
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    raw = await self.redis.get(response_key)
                    if raw:
                        await self.redis.delete(response_key)
                        return InferenceResponse.model_validate_json(raw)

            # Timeout
            return InferenceResponse(
                request_id=request.request_id,
                worker_id="timeout",
                error=f"Request timed out after {timeout_s}s",
            )

        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    async def submit_stream(
        self, request: InferenceRequest
    ) -> AsyncIterator[StreamChunk]:
        """Submit a streaming request and yield chunks as they arrive.

        Flow:
        1. Push request to queue
        2. Poll Redis list for stream chunks
        3. Yield each chunk
        """
        workers = await self.get_available_workers(request.model)
        if not workers:
            yield StreamChunk(
                request_id=request.request_id,
                worker_id="none",
                content="",
                finish_reason="error",
            )
            return

        # Push request
        request.stream = True
        queue_key = REQUEST_QUEUE.format(model=request.model)
        await self.redis.rpush(queue_key, request.model_dump_json())

        # Read stream chunks
        stream_key = STREAM_KEY.format(request_id=request.request_id)
        timeout_s = request.timeout_ms / 1000
        start = time.time()

        while time.time() - start < timeout_s:
            # Blocking pop with 1s timeout
            result = await self.redis.blpop(stream_key, timeout=1)
            if result is None:
                continue

            _, raw = result
            chunk = StreamChunk.model_validate_json(raw)
            yield chunk

            if chunk.finish_reason:
                break

        # Cleanup
        await self.redis.delete(stream_key)

    async def get_cluster_status(self) -> dict:
        """Get overall cluster status."""
        workers = await self.get_workers()
        models: dict[str, int] = {}
        for w in workers:
            for m in w.models:
                models[m] = models.get(m, 0) + 1

        idle_count = sum(1 for w in workers if w.status == WorkerStatus.IDLE)
        busy_count = sum(1 for w in workers if w.status == WorkerStatus.BUSY)
        total_gpu = sum(w.gpu_count for w in workers)
        total_gpu_mem = sum(w.gpu_memory_mb for w in workers)

        return {
            "total_workers": len(workers),
            "idle_workers": idle_count,
            "busy_workers": busy_count,
            "total_gpus": total_gpu,
            "total_gpu_memory_mb": total_gpu_mem,
            "models": models,
            "workers": [
                {
                    "id": w.worker_id,
                    "host": w.host,
                    "status": w.status.value,
                    "models": w.models,
                    "gpu_count": w.gpu_count,
                    "last_heartbeat": w.last_heartbeat,
                }
                for w in workers
            ],
        }
