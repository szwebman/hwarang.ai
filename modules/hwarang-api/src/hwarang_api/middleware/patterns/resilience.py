"""Resilience Patterns - 복원력 패턴 모음.

1. Health Check: /health, /ready, /live
2. Graceful Shutdown: 진행 중 요청 완료 후 종료
3. Request ID Tracing: 요청 추적 ID
4. Idempotency: 중복 요청 방지
5. Backpressure: 과부하 시 요청 거부
6. Bulkhead: 도메인별 자원 격리
7. Saga Pattern: 분산 트랜잭션
8. Observability: 메트릭 + 트레이싱
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import signal
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================
# 1. Health Check
# ============================================================

class HealthChecker:
    """서비스 상태 확인."""

    def __init__(self):
        self._checks: dict[str, callable] = {}

    def register(self, name: str, check_fn):
        self._checks[name] = check_fn

    async def health(self) -> dict:
        """전체 상태."""
        results = {}
        for name, fn in self._checks.items():
            try:
                if asyncio.iscoroutinefunction(fn):
                    ok = await fn()
                else:
                    ok = fn()
                results[name] = "ok" if ok else "unhealthy"
            except Exception as e:
                results[name] = f"error: {e}"

        all_ok = all(v == "ok" for v in results.values())
        return {"status": "healthy" if all_ok else "unhealthy", "checks": results}

    async def ready(self) -> bool:
        """서비스 준비 완료 여부."""
        result = await self.health()
        return result["status"] == "healthy"

    async def live(self) -> bool:
        """프로세스 살아있는지."""
        return True


# ============================================================
# 2. Graceful Shutdown
# ============================================================

class GracefulShutdown:
    """서버 종료 시 진행 중 요청 완료 후 종료."""

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self._active_requests = 0
        self._shutting_down = False

    def request_started(self):
        self._active_requests += 1

    def request_finished(self):
        self._active_requests -= 1

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down

    async def shutdown(self):
        """안전한 종료."""
        self._shutting_down = True
        logger.info(f"Graceful shutdown 시작 (활성 요청: {self._active_requests})")

        start = time.time()
        while self._active_requests > 0:
            if time.time() - start > self.timeout:
                logger.warning(f"Shutdown timeout! 강제 종료 (남은 요청: {self._active_requests})")
                break
            await asyncio.sleep(0.5)

        logger.info("Shutdown 완료")

    def setup_signals(self):
        """SIGTERM/SIGINT 시그널 핸들러 등록."""
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.ensure_future(self.shutdown()))


# ============================================================
# 3. Request ID Tracing
# ============================================================

class RequestTracer:
    """요청 추적 ID 관리. 마스터→서브→로그 전체 연결."""

    @staticmethod
    def generate_id() -> str:
        return f"req-{uuid.uuid4().hex[:16]}"

    @staticmethod
    def get_trace_headers(request_id: str) -> dict:
        return {
            "X-Request-ID": request_id,
            "X-Trace-ID": request_id,
        }


# ============================================================
# 4. Idempotency (중복 요청 방지)
# ============================================================

class IdempotencyStore:
    """동일 요청 중복 처리 방지.

    클라이언트가 같은 idempotency_key로 재요청하면 이전 결과 반환.
    네트워크 재시도 시 안전.
    """

    def __init__(self, ttl: float = 3600, max_size: int = 10_000):
        self.ttl = ttl
        self._store: OrderedDict[str, tuple[dict, float]] = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> dict | None:
        entry = self._store.get(key)
        if entry and time.time() - entry[1] < self.ttl:
            return entry[0]
        if entry:
            del self._store[key]
        return None

    def set(self, key: str, response: dict):
        if len(self._store) >= self._max_size:
            self._store.popitem(last=False)
        self._store[key] = (response, time.time())


# ============================================================
# 5. Backpressure (과부하 방지)
# ============================================================

class BackpressureController:
    """서버 과부하 시 요청 거부 (503)."""

    def __init__(self, max_concurrent: int = 100, max_queue: int = 500):
        self.max_concurrent = max_concurrent
        self.max_queue = max_queue
        self._active = 0
        self._queued = 0

    def can_accept(self) -> tuple[bool, str]:
        if self._active >= self.max_concurrent:
            if self._queued >= self.max_queue:
                return False, f"서버 과부하: {self._active} 처리 중, {self._queued} 대기 중"
        return True, ""

    def request_started(self):
        self._active += 1

    def request_finished(self):
        self._active = max(0, self._active - 1)

    @property
    def load_percent(self) -> float:
        return (self._active / max(self.max_concurrent, 1)) * 100

    @property
    def stats(self) -> dict:
        return {
            "active": self._active,
            "max_concurrent": self.max_concurrent,
            "load_percent": f"{self.load_percent:.1f}%",
        }


# ============================================================
# 6. Bulkhead (도메인별 자원 격리)
# ============================================================

class Bulkhead:
    """도메인별 독립적인 자원 풀.

    법률 도메인 장애가 코딩 도메인에 영향 주지 않도록 격리.
    """

    def __init__(self, partitions: dict[str, int] = None):
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        partitions = partitions or {
            "code": 50,     # 코딩: 동시 50개
            "legal": 30,    # 법률: 동시 30개
            "tax": 30,      # 세무: 동시 30개
            "general": 40,  # 일반: 동시 40개
        }
        for name, limit in partitions.items():
            self._semaphores[name] = asyncio.Semaphore(limit)

    async def acquire(self, domain: str = "general") -> bool:
        sem = self._semaphores.get(domain, self._semaphores.get("general"))
        if sem:
            return await asyncio.wait_for(sem.acquire(), timeout=5.0)
        return True

    def release(self, domain: str = "general"):
        sem = self._semaphores.get(domain, self._semaphores.get("general"))
        if sem:
            sem.release()


# ============================================================
# 7. Saga Pattern (분산 트랜잭션)
# ============================================================

@dataclass
class SagaStep:
    name: str
    action: callable           # 정방향 실행
    compensate: callable       # 보상 (롤백)
    completed: bool = False


class SagaOrchestrator:
    """Saga 패턴: 여러 단계의 트랜잭션을 관리.

    결제 → 토큰 충전 → 플랜 변경
    중간에 실패하면 → 이전 단계들 보상(롤백)
    """

    async def execute(self, steps: list[SagaStep]) -> bool:
        completed = []
        try:
            for step in steps:
                if asyncio.iscoroutinefunction(step.action):
                    await step.action()
                else:
                    step.action()
                step.completed = True
                completed.append(step)
            return True
        except Exception as e:
            logger.error(f"Saga 실패 at {step.name}: {e}")
            # 보상 (역순)
            for comp_step in reversed(completed):
                try:
                    if asyncio.iscoroutinefunction(comp_step.compensate):
                        await comp_step.compensate()
                    else:
                        comp_step.compensate()
                    logger.info(f"Saga 보상: {comp_step.name}")
                except Exception as ce:
                    logger.error(f"Saga 보상 실패: {comp_step.name}: {ce}")
            return False


# ============================================================
# 8. Observability (메트릭 + 트레이싱)
# ============================================================

class MetricsCollector:
    """Prometheus 호환 메트릭 수집."""

    def __init__(self):
        self._counters: dict[str, int] = {}
        self._histograms: dict[str, list[float]] = {}
        self._gauges: dict[str, float] = {}

    def increment(self, name: str, value: int = 1, labels: dict = None):
        key = f"{name}_{json.dumps(labels or {}, sort_keys=True)}"
        self._counters[key] = self._counters.get(key, 0) + value

    def observe(self, name: str, value: float, labels: dict = None):
        key = f"{name}_{json.dumps(labels or {}, sort_keys=True)}"
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)
        # 최근 1000개만 유지
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-1000:]

    def set_gauge(self, name: str, value: float):
        self._gauges[name] = value

    def get_prometheus_text(self) -> str:
        """Prometheus 텍스트 형식으로 내보내기."""
        lines = []
        for key, value in self._counters.items():
            name = key.split("_{}")[0] if "_{}" in key else key
            lines.append(f"{name} {value}")
        for key, values in self._histograms.items():
            name = key.split("_{}")[0] if "_{}" in key else key
            if values:
                avg = sum(values) / len(values)
                lines.append(f"{name}_avg {avg:.4f}")
                lines.append(f"{name}_count {len(values)}")
        for name, value in self._gauges.items():
            lines.append(f"{name} {value}")
        return "\n".join(lines)

    @property
    def summary(self) -> dict:
        result = {}
        for key, values in self._histograms.items():
            if values:
                result[key] = {
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "count": len(values),
                }
        return result


# 싱글턴
_metrics: MetricsCollector | None = None

def get_metrics() -> MetricsCollector:
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics
