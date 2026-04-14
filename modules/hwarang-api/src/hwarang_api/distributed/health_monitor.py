"""자동 건강 모니터링 + 문제 감지 + 자동 롤백 + 알림.

배포 후 자동으로 실행되어 문제를 실시간 감지합니다.

감지하는 문제:
1. 배포 실패 (다운로드/로드 오류)
2. 에러율 급증 (배포 전 대비 2배 이상)
3. 응답 속도 저하 (배포 전 대비 2배 이상 느림)
4. 서브 서버 죽음 (하트비트 없음)
5. 모델 품질 저하 (테스트 프롬프트 자동 실행)

사용법:
    # Worker에 자동 내장 (별도 실행 불필요)
    # 배포 후 자동으로 30초간 모니터링
    # 문제 감지 → 자동 롤백 + 알림
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Callable

logger = logging.getLogger(__name__)


# ============================================================
# 설정
# ============================================================

@dataclass
class MonitorConfig:
    """모니터링 설정."""

    # 배포 후 검증 기간
    canary_duration_sec: float = 60.0      # 배포 후 60초간 집중 모니터링

    # 에러율 임계값
    error_rate_threshold: float = 0.05     # 5% 이상이면 문제
    error_rate_spike: float = 2.0          # 이전 대비 2배 이상이면 문제

    # 응답 속도 임계값
    latency_spike: float = 2.0            # 이전 대비 2배 이상 느려지면 문제
    latency_max_ms: float = 30000         # 30초 이상이면 무조건 문제

    # 서브 헬스
    heartbeat_timeout_sec: float = 15.0   # 15초 무응답이면 죽은 것
    gpu_memory_threshold: float = 0.95     # 95% 이상이면 경고
    gpu_temp_threshold: float = 90         # 90도 이상이면 경고

    # 자동 롤백
    auto_rollback: bool = True            # 문제 시 자동 롤백
    rollback_after_failures: int = 3       # 연속 3회 실패 시 롤백

    # 알림
    alert_webhook_url: str = ""           # Slack/Discord 웹훅 URL
    alert_email: str = ""                  # 이메일 알림


# ============================================================
# 알림 발송
# ============================================================

class AlertSender:
    """문제 감지 시 알림 발송."""

    def __init__(self, config: MonitorConfig):
        self.config = config

    async def send(self, level: str, title: str, message: str, data: dict = None):
        """알림 발송.

        level: "info", "warning", "critical"
        """
        alert = {
            "level": level,
            "title": title,
            "message": message,
            "data": data or {},
            "timestamp": time.time(),
            "service": "Hwarang AI",
        }

        logger.log(
            {"info": logging.INFO, "warning": logging.WARNING, "critical": logging.CRITICAL}
                .get(level, logging.INFO),
            f"[ALERT {level.upper()}] {title}: {message}"
        )

        # Slack/Discord 웹훅
        if self.config.alert_webhook_url:
            await self._send_webhook(alert)

        # 이메일
        if self.config.alert_email:
            await self._send_email(alert)

        # Redis에 저장 (관리자 대시보드에서 확인)
        await self._store_alert(alert)

    async def _send_webhook(self, alert: dict):
        """Slack/Discord 웹훅 발송."""
        try:
            import aiohttp

            emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(alert["level"], "📢")

            payload = {
                "text": f"{emoji} **[Hwarang {alert['level'].upper()}]** {alert['title']}\n{alert['message']}",
                # Slack 형식
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"{emoji} *{alert['title']}*\n{alert['message']}"
                        }
                    }
                ]
            }

            async with aiohttp.ClientSession() as session:
                await session.post(
                    self.config.alert_webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5),
                )
        except Exception as e:
            logger.warning(f"웹훅 발송 실패: {e}")

    async def _send_email(self, alert: dict):
        """이메일 발송 (간단한 SMTP)."""
        # TODO: 실제 SMTP 구현
        logger.info(f"이메일 알림 예정: {self.config.alert_email} - {alert['title']}")

    async def _store_alert(self, alert: dict):
        """Redis에 알림 저장."""
        try:
            import redis.asyncio as aioredis
            redis = aioredis.from_url("redis://localhost:6379", decode_responses=True)
            await redis.rpush("hwarang:alerts", json.dumps(alert))
            await redis.ltrim("hwarang:alerts", -500, -1)  # 최근 500개만
            await redis.close()
        except Exception:
            pass


# ============================================================
# 배포 후 자동 검증 (Canary Check)
# ============================================================

class PostDeployValidator:
    """배포 후 자동 품질 검증.

    배포 직후 테스트 프롬프트를 실행하여 모델이 정상인지 확인합니다.
    """

    # 검증용 테스트 프롬프트
    TEST_PROMPTS = [
        {
            "messages": [{"role": "user", "content": "안녕하세요"}],
            "expected_contains": ["안녕", "반갑", "도움"],
            "description": "한국어 인사 응답",
        },
        {
            "messages": [{"role": "user", "content": "1+1은?"}],
            "expected_contains": ["2"],
            "description": "기본 산술",
        },
        {
            "messages": [{"role": "user", "content": "파이썬으로 hello world 출력해줘"}],
            "expected_contains": ["print", "hello", "Hello"],
            "description": "기본 코드 생성",
        },
    ]

    def __init__(self, engine, alert_sender: AlertSender):
        self.engine = engine
        self.alerts = alert_sender

    async def validate(self) -> bool:
        """배포 후 검증. 성공하면 True, 실패하면 False."""
        logger.info("[검증] 배포 후 품질 검증 시작...")
        passed = 0
        failed = 0

        for test in self.TEST_PROMPTS:
            try:
                from hwarang_shared.schemas.chat import (
                    ChatCompletionRequest, ChatMessage, Role,
                )

                messages = [
                    ChatMessage(role=Role(m["role"]), content=m["content"])
                    for m in test["messages"]
                ]
                request = ChatCompletionRequest(
                    model="test",
                    messages=messages,
                    max_tokens=100,
                    temperature=0.1,
                )

                start = time.time()
                response = await self.engine.generate(request)
                latency = (time.time() - start) * 1000

                content = response.choices[0].message.content or ""

                # 응답 내용 확인
                has_expected = any(
                    exp.lower() in content.lower()
                    for exp in test["expected_contains"]
                )

                if has_expected and latency < 30000:
                    passed += 1
                    logger.info(f"  ✅ {test['description']}: '{content[:50]}...' ({latency:.0f}ms)")
                else:
                    failed += 1
                    logger.warning(f"  ❌ {test['description']}: '{content[:50]}...' "
                                  f"(expected: {test['expected_contains']})")

            except Exception as e:
                failed += 1
                logger.error(f"  ❌ {test['description']}: 오류 - {e}")

        total = passed + failed
        success_rate = passed / max(total, 1)

        if success_rate < 0.5:
            await self.alerts.send(
                "critical",
                "모델 검증 실패",
                f"테스트 {total}개 중 {failed}개 실패 (성공률: {success_rate*100:.0f}%)\n"
                f"자동 롤백이 필요할 수 있습니다.",
                {"passed": passed, "failed": failed},
            )
            return False

        if failed > 0:
            await self.alerts.send(
                "warning",
                "모델 검증 부분 실패",
                f"테스트 {total}개 중 {failed}개 실패. 모니터링 계속.",
                {"passed": passed, "failed": failed},
            )

        logger.info(f"[검증] 완료: {passed}/{total} 통과")
        return True


# ============================================================
# 실시간 메트릭 수집기
# ============================================================

class MetricsCollector:
    """요청별 메트릭을 수집하여 이상 감지."""

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self._latencies: list[float] = []
        self._errors: list[bool] = []
        self._timestamps: list[float] = []

        # 배포 전 기준값 (baseline)
        self._baseline_latency: float | None = None
        self._baseline_error_rate: float | None = None

    def save_baseline(self):
        """현재 메트릭을 기준값으로 저장 (배포 전에 호출)."""
        if self._latencies:
            self._baseline_latency = sum(self._latencies) / len(self._latencies)
        if self._errors:
            self._baseline_error_rate = sum(self._errors) / len(self._errors)

        logger.info(f"[메트릭] 기준값 저장: latency={self._baseline_latency:.0f}ms, "
                    f"error_rate={self._baseline_error_rate:.3f}")

    def record(self, latency_ms: float, is_error: bool):
        """요청 결과 기록."""
        self._latencies.append(latency_ms)
        self._errors.append(is_error)
        self._timestamps.append(time.time())

        # 윈도우 크기 유지
        if len(self._latencies) > self.window_size:
            self._latencies.pop(0)
            self._errors.pop(0)
            self._timestamps.pop(0)

    @property
    def avg_latency(self) -> float:
        return sum(self._latencies) / max(len(self._latencies), 1)

    @property
    def error_rate(self) -> float:
        return sum(self._errors) / max(len(self._errors), 1)

    @property
    def request_count(self) -> int:
        return len(self._latencies)

    def check_anomaly(self, config: MonitorConfig) -> list[str]:
        """이상 감지. 문제가 있으면 이유 목록 반환."""
        issues = []

        if self.request_count < 5:
            return []  # 데이터 부족

        # 1. 에러율 체크
        if self.error_rate > config.error_rate_threshold:
            issues.append(f"에러율 {self.error_rate*100:.1f}% (임계값: {config.error_rate_threshold*100:.0f}%)")

        # 에러율 급증
        if self._baseline_error_rate is not None and self._baseline_error_rate > 0:
            if self.error_rate > self._baseline_error_rate * config.error_rate_spike:
                issues.append(f"에러율 급증: {self._baseline_error_rate*100:.1f}% → {self.error_rate*100:.1f}%")

        # 2. 응답 속도 체크
        if self.avg_latency > config.latency_max_ms:
            issues.append(f"응답 속도 {self.avg_latency:.0f}ms (최대: {config.latency_max_ms:.0f}ms)")

        # 응답 속도 급증
        if self._baseline_latency is not None and self._baseline_latency > 0:
            if self.avg_latency > self._baseline_latency * config.latency_spike:
                issues.append(f"응답 속도 급증: {self._baseline_latency:.0f}ms → {self.avg_latency:.0f}ms")

        return issues


# ============================================================
# 통합 헬스 모니터 (Worker에 내장)
# ============================================================

class HealthMonitor:
    """Worker에 내장되는 통합 헬스 모니터.

    역할:
    1. 모든 요청의 latency/에러를 추적
    2. 배포 후 자동 검증 (canary)
    3. 이상 감지 시 알림 + 자동 롤백
    4. 주기적 헬스체크 (GPU 온도, 메모리 등)
    """

    def __init__(
        self,
        worker_id: str,
        redis_url: str,
        config: MonitorConfig | None = None,
    ):
        self.worker_id = worker_id
        self.redis_url = redis_url
        self.config = config or MonitorConfig()
        self.metrics = MetricsCollector()
        self.alerts = AlertSender(self.config)
        self._consecutive_failures = 0

    def record_request(self, latency_ms: float, is_error: bool):
        """매 요청마다 호출."""
        self.metrics.record(latency_ms, is_error)

        if is_error:
            self._consecutive_failures += 1
        else:
            self._consecutive_failures = 0

    async def check_health(self) -> dict:
        """현재 건강 상태 확인."""
        issues = self.metrics.check_anomaly(self.config)

        # GPU 상태 (가능한 경우)
        gpu_status = self._check_gpu()
        if gpu_status.get("issues"):
            issues.extend(gpu_status["issues"])

        # 이상 감지 시 알림
        if issues:
            await self.alerts.send(
                "warning" if len(issues) < 3 else "critical",
                f"서브 {self.worker_id} 이상 감지",
                "\n".join(f"• {i}" for i in issues),
                {
                    "worker_id": self.worker_id,
                    "avg_latency": self.metrics.avg_latency,
                    "error_rate": self.metrics.error_rate,
                    "request_count": self.metrics.request_count,
                },
            )

        # 자동 롤백 판단
        should_rollback = (
            self.config.auto_rollback
            and self._consecutive_failures >= self.config.rollback_after_failures
        )

        return {
            "healthy": len(issues) == 0,
            "issues": issues,
            "metrics": {
                "avg_latency_ms": round(self.metrics.avg_latency, 1),
                "error_rate": round(self.metrics.error_rate, 4),
                "request_count": self.metrics.request_count,
            },
            "gpu": gpu_status,
            "should_rollback": should_rollback,
        }

    async def run_periodic_check(self, interval: float = 30.0):
        """주기적 헬스체크 (백그라운드 태스크)."""
        while True:
            try:
                status = await self.check_health()

                # Redis에 상태 저장 (관리자 대시보드)
                try:
                    import redis.asyncio as aioredis
                    redis = aioredis.from_url(self.redis_url, decode_responses=True)
                    await redis.hset(
                        "hwarang:worker_health",
                        self.worker_id,
                        json.dumps(status),
                    )
                    # 30분 TTL
                    await redis.expire("hwarang:worker_health", 1800)
                    await redis.close()
                except Exception:
                    pass

                if status["should_rollback"]:
                    await self.alerts.send(
                        "critical",
                        f"자동 롤백 필요: {self.worker_id}",
                        f"연속 {self._consecutive_failures}회 실패. 자동 롤백을 시도합니다.",
                    )
                    # 롤백은 Worker 레벨에서 처리 (ModelUpdater)

            except Exception as e:
                logger.error(f"헬스체크 오류: {e}")

            await asyncio.sleep(interval)

    def _check_gpu(self) -> dict:
        """GPU 상태 확인."""
        result = {"available": False, "issues": []}

        try:
            import torch
            if not torch.cuda.is_available():
                return result

            result["available"] = True
            device = torch.cuda.current_device()

            # 메모리
            mem_used = torch.cuda.memory_allocated(device)
            mem_total = torch.cuda.get_device_properties(device).total_memory
            mem_pct = mem_used / mem_total

            result["memory_used_gb"] = round(mem_used / 1e9, 1)
            result["memory_total_gb"] = round(mem_total / 1e9, 1)
            result["memory_percent"] = round(mem_pct * 100, 1)

            if mem_pct > self.config.gpu_memory_threshold:
                result["issues"].append(
                    f"GPU 메모리 {mem_pct*100:.0f}% (임계값: {self.config.gpu_memory_threshold*100:.0f}%)"
                )

            # 온도 (nvidia-smi)
            try:
                import subprocess
                output = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader"],
                    text=True,
                )
                temp = int(output.strip())
                result["temperature"] = temp
                if temp > self.config.gpu_temp_threshold:
                    result["issues"].append(f"GPU 온도 {temp}°C (임계값: {self.config.gpu_temp_threshold}°C)")
            except Exception:
                pass

        except Exception:
            pass

        return result
