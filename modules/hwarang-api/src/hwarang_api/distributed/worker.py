"""Worker Node - GPU 서버에서 실행되어 추론 요청을 처리합니다.

사용법:
    python -m hwarang_api.distributed.worker \
        --model-path ./exported/hwarang-small \
        --model-id hwarang-small \
        --redis-url redis://api-server:6379 \
        --worker-port 9000

여러 GPU 서버에서 동시에 실행하면 자동으로 로드밸런싱됩니다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
import uuid
from pathlib import Path

import redis.asyncio as aioredis

from hwarang_api.distributed.protocol import (
    InferenceRequest,
    InferenceResponse,
    StreamChunk,
    WorkerInfo,
    WorkerStatus,
)

logger = logging.getLogger(__name__)

# Redis key prefixes
WORKER_REGISTRY = "hwarang:workers"
REQUEST_QUEUE = "hwarang:requests:{model}"
RESPONSE_KEY = "hwarang:response:{request_id}"
STREAM_KEY = "hwarang:stream:{request_id}"
HEARTBEAT_INTERVAL = 5  # seconds
WORKER_TIMEOUT = 15  # seconds before considered dead


class WorkerNode:
    """GPU Worker that processes inference requests from the queue.

    Lifecycle:
    1. Start → register with Redis
    2. Poll request queue → process → send response
    3. Send heartbeats every 5s
    4. Shutdown → deregister
    """

    def __init__(
        self,
        model_path: str,
        model_id: str,
        redis_url: str = "redis://localhost:6379",
        host: str = "0.0.0.0",
        port: int = 9000,
        device: str = "auto",
        dtype: str = "bfloat16",
        max_batch_size: int = 8,
    ):
        self.model_path = model_path
        self.model_id = model_id
        self.redis_url = redis_url
        self.host = host
        self.port = port
        self.device = device
        self.dtype = dtype
        self.max_batch_size = max_batch_size

        self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        self.redis: aioredis.Redis | None = None
        self.engine = None
        self._running = False
        self._current_requests = 0

    async def start(self) -> None:
        """Start the worker node."""
        logger.info(f"Starting worker {self.worker_id}")

        # Connect to Redis
        self.redis = aioredis.from_url(self.redis_url, decode_responses=True)
        await self.redis.ping()
        logger.info(f"Connected to Redis: {self.redis_url}")

        # 모델이 없으면 자동 다운로드
        await self._ensure_model()

        # Load model
        logger.info(f"Loading model: {self.model_id} from {self.model_path}")
        from hwarang_core.inference.engine import InferenceEngine

        self.engine = InferenceEngine(
            model_path=self.model_path,
            device=self.device,
            dtype=self.dtype,
        )
        logger.info("Model loaded successfully")

        # Register worker
        await self._register()

        # Start processing
        self._running = True

        # Run heartbeat and request processing concurrently
        await asyncio.gather(
            self._heartbeat_loop(),
            self._process_loop(),
        )

    async def stop(self) -> None:
        """Gracefully shut down the worker."""
        logger.info(f"Stopping worker {self.worker_id}...")
        self._running = False

        # Update status to draining
        await self._update_status(WorkerStatus.DRAINING)

        # Wait for current requests to finish (max 30s)
        for _ in range(60):
            if self._current_requests == 0:
                break
            await asyncio.sleep(0.5)

        # Deregister
        await self._deregister()
        if self.redis:
            await self.redis.close()

        logger.info(f"Worker {self.worker_id} stopped")

    async def _ensure_model(self) -> None:
        """모델이 로컬에 없으면 자동으로 가져옵니다.

        탐색 순서:
        1. --model-path에 이미 있음 → 바로 사용
        2. Redis에 등록된 모델 소스(마스터/NFS) → rsync로 복사
        3. Hugging Face Hub → 다운로드
        """
        model_dir = Path(self.model_path)

        # 1. 이미 있는지 확인
        if model_dir.exists() and any(model_dir.iterdir()):
            config_exists = (model_dir / "config.yaml").exists() or (model_dir / "model.pt").exists()
            if config_exists:
                logger.info(f"모델 확인: {self.model_path} ✅ (로컬에 존재)")
                return

        logger.warning(f"모델 없음: {self.model_path}")
        model_dir.mkdir(parents=True, exist_ok=True)

        # 2. Redis에서 모델 소스 확인 (마스터가 등록해둠)
        model_source = await self.redis.hget("hwarang:model_sources", self.model_id)

        if model_source:
            source_info = json.loads(model_source)
            source_type = source_info.get("type")

            if source_type == "rsync":
                # rsync로 마스터/NFS에서 복사
                source_path = source_info["path"]
                source_host = source_info.get("host")

                if source_host:
                    cmd = f"rsync -avz --progress {source_host}:{source_path}/ {self.model_path}/"
                else:
                    cmd = f"rsync -avz --progress {source_path}/ {self.model_path}/"

                logger.info(f"모델 다운로드 (rsync): {cmd}")

                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()

                if proc.returncode == 0:
                    logger.info(f"모델 다운로드 완료: {self.model_path}")
                    return
                else:
                    logger.error(f"rsync 실패: {stderr.decode()}")

            elif source_type == "scp":
                source_path = source_info["path"]
                source_host = source_info["host"]
                cmd = f"scp -r {source_host}:{source_path} {self.model_path}"

                logger.info(f"모델 다운로드 (scp): {cmd}")
                proc = await asyncio.create_subprocess_shell(cmd)
                await proc.communicate()

                if proc.returncode == 0:
                    logger.info(f"모델 다운로드 완료: {self.model_path}")
                    return

            elif source_type == "http":
                # HTTP 다운로드 (MinIO/S3 등)
                url = source_info["url"]
                logger.info(f"모델 다운로드 (http): {url}")

                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            # tar.gz로 받아서 풀기
                            tar_path = model_dir / "model.tar.gz"
                            with open(tar_path, "wb") as f:
                                async for chunk in resp.content.iter_chunked(1024 * 1024):
                                    f.write(chunk)

                            # 압축 해제
                            proc = await asyncio.create_subprocess_shell(
                                f"tar xzf {tar_path} -C {self.model_path}",
                            )
                            await proc.communicate()
                            tar_path.unlink()  # 압축 파일 삭제
                            logger.info(f"모델 다운로드 완료: {self.model_path}")
                            return

        # 3. Hugging Face Hub에서 다운로드 시도
        try:
            hf_repo = await self.redis.hget("hwarang:model_hf_repos", self.model_id)
            if hf_repo:
                logger.info(f"모델 다운로드 (Hugging Face): {hf_repo}")
                from huggingface_hub import snapshot_download
                snapshot_download(repo_id=hf_repo, local_dir=str(model_dir))
                logger.info(f"모델 다운로드 완료: {self.model_path}")
                return
        except Exception as e:
            logger.warning(f"HF 다운로드 실패: {e}")

        # 4. 모든 방법 실패
        logger.error(
            f"모델을 가져올 수 없습니다: {self.model_id}\n"
            f"해결 방법:\n"
            f"  1. 직접 복사: scp -r 마스터:/models/{self.model_id} {self.model_path}\n"
            f"  2. 마스터에서 모델 소스 등록:\n"
            f"     redis-cli HSET hwarang:model_sources {self.model_id} "
            f"     '{{\"type\":\"rsync\",\"host\":\"마스터IP\",\"path\":\"/mnt/nvme2/hwarang/models/{self.model_id}\"}}'\n"
            f"  3. NFS 마운트: mount 마스터IP:/models /models"
        )
        raise FileNotFoundError(f"Model not found: {self.model_path}")

    async def _register(self) -> None:
        """Register this worker in the Redis registry."""
        gpu_count, gpu_mem = self._detect_gpu()

        info = WorkerInfo(
            worker_id=self.worker_id,
            host=self.host,
            port=self.port,
            models=[self.model_id],
            gpu_count=gpu_count,
            gpu_memory_mb=gpu_mem,
            max_batch_size=self.max_batch_size,
            status=WorkerStatus.IDLE,
        )

        await self.redis.hset(
            WORKER_REGISTRY,
            self.worker_id,
            info.model_dump_json(),
        )
        logger.info(f"Registered worker: {self.worker_id} (GPU: {gpu_count}x {gpu_mem}MB)")

    async def _deregister(self) -> None:
        """Remove this worker from the registry."""
        await self.redis.hdel(WORKER_REGISTRY, self.worker_id)
        logger.info(f"Deregistered worker: {self.worker_id}")

    async def _update_status(self, status: WorkerStatus) -> None:
        """Update worker status in registry."""
        raw = await self.redis.hget(WORKER_REGISTRY, self.worker_id)
        if raw:
            info = WorkerInfo.model_validate_json(raw)
            info.status = status
            info.last_heartbeat = time.time()
            await self.redis.hset(WORKER_REGISTRY, self.worker_id, info.model_dump_json())

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats."""
        while self._running:
            try:
                status = WorkerStatus.BUSY if self._current_requests > 0 else WorkerStatus.IDLE
                await self._update_status(status)
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    async def _process_loop(self) -> None:
        """Main loop: poll request queue and process."""
        queue_key = REQUEST_QUEUE.format(model=self.model_id)
        logger.info(f"Listening on queue: {queue_key}")

        while self._running:
            try:
                # Blocking pop with 1s timeout
                result = await self.redis.blpop(queue_key, timeout=1)
                if result is None:
                    continue

                _, raw_request = result
                request = InferenceRequest.model_validate_json(raw_request)
                logger.info(f"Processing request {request.request_id[:8]}...")

                self._current_requests += 1
                try:
                    if request.stream:
                        await self._process_stream(request)
                    else:
                        await self._process_request(request)
                finally:
                    self._current_requests -= 1

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Processing error: {e}", exc_info=True)

    async def _process_request(self, request: InferenceRequest) -> None:
        """Process a non-streaming request."""
        start_time = time.time()

        try:
            from hwarang_shared.schemas.chat import ChatCompletionRequest, ChatMessage, Role

            # Build ChatCompletionRequest
            messages = [
                ChatMessage(role=Role(m["role"]), content=m["content"])
                for m in request.messages
            ]
            chat_request = ChatCompletionRequest(
                model=request.model,
                messages=messages,
                temperature=request.temperature,
                top_p=request.top_p,
                max_tokens=request.max_tokens,
            )

            # Run inference
            result = await self.engine.generate(chat_request)
            latency = (time.time() - start_time) * 1000

            response = InferenceResponse(
                request_id=request.request_id,
                worker_id=self.worker_id,
                content=result.choices[0].message.content,
                finish_reason=result.choices[0].finish_reason or "stop",
                prompt_tokens=result.usage.prompt_tokens,
                completion_tokens=result.usage.completion_tokens,
                latency_ms=latency,
            )

        except Exception as e:
            response = InferenceResponse(
                request_id=request.request_id,
                worker_id=self.worker_id,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )

        # Send response back via Redis
        response_key = RESPONSE_KEY.format(request_id=request.request_id)
        await self.redis.set(response_key, response.model_dump_json(), ex=60)
        # Notify the API server
        await self.redis.publish(f"hwarang:done:{request.request_id}", "1")

        logger.info(
            f"Request {request.request_id[:8]} done: "
            f"{response.latency_ms:.0f}ms, {response.completion_tokens} tokens"
        )

    async def _process_stream(self, request: InferenceRequest) -> None:
        """Process a streaming request, sending chunks via Redis."""
        start_time = time.time()
        stream_key = STREAM_KEY.format(request_id=request.request_id)

        try:
            from hwarang_shared.schemas.chat import ChatCompletionRequest, ChatMessage, Role

            messages = [
                ChatMessage(role=Role(m["role"]), content=m["content"])
                for m in request.messages
            ]
            chat_request = ChatCompletionRequest(
                model=request.model,
                messages=messages,
                temperature=request.temperature,
                top_p=request.top_p,
                max_tokens=request.max_tokens,
                stream=True,
            )

            chunk_index = 0
            async for api_chunk in self.engine.generate_stream(chat_request):
                delta = api_chunk.choices[0].delta
                finish = api_chunk.choices[0].finish_reason

                chunk = StreamChunk(
                    request_id=request.request_id,
                    worker_id=self.worker_id,
                    content=delta.content or "",
                    finish_reason=finish,
                    index=chunk_index,
                )

                # Push chunk to Redis list
                await self.redis.rpush(stream_key, chunk.model_dump_json())
                await self.redis.expire(stream_key, 60)
                chunk_index += 1

                if finish:
                    break

        except Exception as e:
            # Send error chunk
            error_chunk = StreamChunk(
                request_id=request.request_id,
                worker_id=self.worker_id,
                content="",
                finish_reason="error",
                index=-1,
            )
            await self.redis.rpush(stream_key, error_chunk.model_dump_json())

        # Signal completion
        await self.redis.publish(f"hwarang:done:{request.request_id}", "stream_done")

        latency = (time.time() - start_time) * 1000
        logger.info(f"Stream {request.request_id[:8]} done: {latency:.0f}ms, {chunk_index} chunks")

    @staticmethod
    def _detect_gpu() -> tuple[int, int]:
        """Detect GPU count and total memory."""
        try:
            import torch
            if torch.cuda.is_available():
                count = torch.cuda.device_count()
                mem = torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
                return count, mem
        except Exception:
            pass
        return 0, 0


async def run_worker(
    model_path: str,
    model_id: str,
    redis_url: str = "redis://localhost:6379",
    host: str = "0.0.0.0",
    port: int = 9000,
    device: str = "auto",
    dtype: str = "bfloat16",
):
    """Run a worker node with graceful shutdown."""
    worker = WorkerNode(
        model_path=model_path,
        model_id=model_id,
        redis_url=redis_url,
        host=host,
        port=port,
        device=device,
        dtype=dtype,
    )

    loop = asyncio.get_event_loop()

    def handle_signal():
        asyncio.ensure_future(worker.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)

    await worker.start()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hwarang Worker Node")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--redis-url", default="redis://localhost:6379")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--dtype", default="bfloat16")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
    asyncio.run(run_worker(**vars(args)))
