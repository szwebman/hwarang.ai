"""gRPC Worker - Redis보다 빠른 직접 통신 Worker.

Redis Worker와의 차이:
  Redis Worker: 마스터 → Redis 큐 → Worker (간접, ~200μs)
  gRPC Worker: 마스터 → Worker 직접 호출 (직접, ~100μs)

사용법:
    # gRPC Worker 시작 (서브 서버에서)
    python -m hwarang_api.distributed.grpc_worker \\
        --model-path ./exported/hwarang-code-30b \\
        --model-id hwarang-code-30b \\
        --port 50051 \\
        --redis-url redis://마스터:6379

    # Redis는 Worker 등록/발견에만 사용 (하트비트)
    # 실제 추론 데이터는 gRPC로 직접 전송
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from concurrent import futures
from typing import AsyncIterator

import grpc

from hwarang_api.distributed.protocol import WorkerInfo, WorkerStatus

logger = logging.getLogger(__name__)

# gRPC 서비스 구현 (proto 컴파일 없이 동적으로 구현)
# 프로덕션에서는 proto 컴파일 후 사용

# 메시지 클래스 (proto 대체)
from dataclasses import dataclass


@dataclass
class GrpcGenerateRequest:
    request_id: str
    model: str
    messages: list[dict]
    temperature: float = 0.7
    top_p: float = 1.0
    max_tokens: int = 512
    priority: int = 0


@dataclass
class GrpcGenerateResponse:
    request_id: str
    worker_id: str
    content: str = ""
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0
    error: str = ""


class GrpcInferenceServicer:
    """gRPC 추론 서비스 구현.

    마스터가 이 서비스를 직접 호출하면
    Redis를 거치지 않고 바로 추론 처리.
    """

    def __init__(self, engine, worker_id: str):
        self.engine = engine
        self.worker_id = worker_id
        self.active_requests = 0

    async def generate(self, request: GrpcGenerateRequest) -> GrpcGenerateResponse:
        """비스트리밍 추론."""
        start_time = time.time()
        self.active_requests += 1

        try:
            from hwarang_shared.schemas.chat import (
                ChatCompletionRequest, ChatMessage, Role,
            )

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

            result = await self.engine.generate(chat_request)
            latency = (time.time() - start_time) * 1000

            return GrpcGenerateResponse(
                request_id=request.request_id,
                worker_id=self.worker_id,
                content=result.choices[0].message.content or "",
                finish_reason=result.choices[0].finish_reason or "stop",
                prompt_tokens=result.usage.prompt_tokens,
                completion_tokens=result.usage.completion_tokens,
                latency_ms=latency,
            )

        except Exception as e:
            return GrpcGenerateResponse(
                request_id=request.request_id,
                worker_id=self.worker_id,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000,
            )
        finally:
            self.active_requests -= 1

    async def generate_stream(
        self, request: GrpcGenerateRequest
    ) -> AsyncIterator[dict]:
        """스트리밍 추론 - 청크를 직접 yield."""
        self.active_requests += 1

        try:
            from hwarang_shared.schemas.chat import (
                ChatCompletionRequest, ChatMessage, Role,
            )

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

                yield {
                    "request_id": request.request_id,
                    "content": delta.content or "",
                    "finish_reason": finish or "",
                    "index": chunk_index,
                }
                chunk_index += 1

                if finish:
                    break

        except Exception as e:
            yield {
                "request_id": request.request_id,
                "content": "",
                "finish_reason": "error",
                "index": -1,
                "error": str(e),
            }
        finally:
            self.active_requests -= 1


class GrpcWorkerNode:
    """gRPC 기반 Worker 노드.

    역할 분리:
    - Redis: Worker 등록, 하트비트, 발견 (변경 없음)
    - gRPC: 실제 추론 데이터 전송 (빠름)
    """

    def __init__(
        self,
        model_path: str,
        model_id: str,
        grpc_port: int = 50051,
        redis_url: str = "redis://localhost:6379",
        device: str = "auto",
        dtype: str = "bfloat16",
    ):
        self.model_path = model_path
        self.model_id = model_id
        self.grpc_port = grpc_port
        self.redis_url = redis_url
        self.device = device
        self.dtype = dtype
        self.worker_id = f"grpc-worker-{uuid.uuid4().hex[:8]}"

    async def start(self):
        """Worker 시작."""
        import redis.asyncio as aioredis

        # 1. Redis 연결 (등록/하트비트용)
        self.redis = aioredis.from_url(self.redis_url, decode_responses=True)
        await self.redis.ping()
        logger.info(f"Redis 연결: {self.redis_url}")

        # 2. 모델 로드
        logger.info(f"모델 로드: {self.model_path}")
        from hwarang_core.inference.engine import InferenceEngine
        self.engine = InferenceEngine(
            model_path=self.model_path,
            device=self.device,
            dtype=self.dtype,
        )

        # 3. gRPC 서비스 준비
        self.servicer = GrpcInferenceServicer(self.engine, self.worker_id)

        # 4. Redis에 등록 (gRPC 주소 포함)
        await self._register()

        # 5. 하트비트 + gRPC 서버 동시 실행
        logger.info(f"gRPC Worker 시작: port={self.grpc_port}")
        await asyncio.gather(
            self._heartbeat_loop(),
            self._serve_grpc(),
        )

    async def _register(self):
        """Redis에 Worker 등록 (gRPC 주소 포함)."""
        import socket
        hostname = socket.gethostname()

        try:
            # 외부 IP 감지
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            host_ip = s.getsockname()[0]
            s.close()
        except Exception:
            host_ip = "127.0.0.1"

        info = WorkerInfo(
            worker_id=self.worker_id,
            host=host_ip,
            port=self.grpc_port,
            models=[self.model_id],
            status=WorkerStatus.IDLE,
        )

        # GPU 정보
        try:
            import torch
            if torch.cuda.is_available():
                info.gpu_count = torch.cuda.device_count()
                info.gpu_memory_mb = torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
        except Exception:
            pass

        await self.redis.hset("hwarang:workers", self.worker_id, info.model_dump_json())

        # gRPC 주소도 별도 저장 (마스터가 직접 연결할 때 사용)
        await self.redis.hset(
            "hwarang:grpc_endpoints",
            self.worker_id,
            f"{host_ip}:{self.grpc_port}",
        )

        logger.info(f"등록 완료: {self.worker_id} @ {host_ip}:{self.grpc_port}")

    async def _heartbeat_loop(self):
        """5초마다 하트비트."""
        while True:
            try:
                raw = await self.redis.hget("hwarang:workers", self.worker_id)
                if raw:
                    info = WorkerInfo.model_validate_json(raw)
                    info.last_heartbeat = time.time()
                    info.status = (
                        WorkerStatus.BUSY
                        if self.servicer.active_requests > 0
                        else WorkerStatus.IDLE
                    )
                    await self.redis.hset(
                        "hwarang:workers", self.worker_id, info.model_dump_json()
                    )
            except Exception as e:
                logger.warning(f"하트비트 실패: {e}")
            await asyncio.sleep(5)

    async def _serve_grpc(self):
        """gRPC 서버 실행 (간소화 버전).

        프로덕션에서는 grpcio 기반으로 구현.
        여기서는 asyncio TCP 서버로 JSON-RPC 스타일 구현.
        (proto 컴파일 없이도 동작하도록)
        """
        import json

        async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            """클라이언트 연결 처리."""
            try:
                while True:
                    # 길이 + JSON 프로토콜
                    length_bytes = await reader.readexactly(4)
                    length = int.from_bytes(length_bytes, "big")
                    data = await reader.readexactly(length)
                    request = json.loads(data.decode())

                    method = request.get("method")

                    if method == "generate":
                        req = GrpcGenerateRequest(**request["params"])
                        resp = await self.servicer.generate(req)
                        response = {"result": resp.__dict__}

                    elif method == "generate_stream":
                        req = GrpcGenerateRequest(**request["params"])
                        async for chunk in self.servicer.generate_stream(req):
                            chunk_data = json.dumps({"chunk": chunk}).encode()
                            writer.write(len(chunk_data).to_bytes(4, "big"))
                            writer.write(chunk_data)
                            await writer.drain()
                        # 스트림 종료 마커
                        response = {"done": True}

                    elif method == "health":
                        response = {
                            "result": {
                                "worker_id": self.worker_id,
                                "status": "idle" if self.servicer.active_requests == 0 else "busy",
                                "active_requests": self.servicer.active_requests,
                                "models": [self.model_id],
                            }
                        }
                    else:
                        response = {"error": f"Unknown method: {method}"}

                    resp_data = json.dumps(response).encode()
                    writer.write(len(resp_data).to_bytes(4, "big"))
                    writer.write(resp_data)
                    await writer.drain()

            except (asyncio.IncompleteReadError, ConnectionResetError):
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(
            handle_client, "0.0.0.0", self.grpc_port,
        )

        logger.info(f"gRPC-like 서버 시작: 0.0.0.0:{self.grpc_port}")

        async with server:
            await server.serve_forever()


async def run_grpc_worker(
    model_path: str,
    model_id: str,
    grpc_port: int = 50051,
    redis_url: str = "redis://localhost:6379",
    device: str = "auto",
    dtype: str = "bfloat16",
):
    worker = GrpcWorkerNode(
        model_path=model_path,
        model_id=model_id,
        grpc_port=grpc_port,
        redis_url=redis_url,
        device=device,
        dtype=dtype,
    )
    await worker.start()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Hwarang gRPC Worker")
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--redis-url", default="redis://localhost:6379")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--dtype", default="bfloat16")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
    asyncio.run(run_grpc_worker(
        model_path=args.model_path,
        model_id=args.model_id,
        grpc_port=args.port,
        redis_url=args.redis_url,
        device=args.device,
        dtype=args.dtype,
    ))
