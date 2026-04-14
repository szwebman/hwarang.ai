"""GPU Agent - 유저 PC에서 실행되는 에이전트.

유저가 이 프로그램을 실행하면:
1. GPU 정보 감지 (모델, VRAM, 성능)
2. 마스터에 등록
3. GPU 사용률 모니터링
4. 유저가 GPU 안 쓸 때 → 작업 수신 → 처리 → 결과 전송
5. 유저가 GPU 쓰기 시작 → 즉시 작업 반환
6. 작업량에 따라 토큰 적립

사용법:
    # 유저 PC에서 실행
    hwarang-grid start --api-key hk-xxxxx

    # 시스템 트레이에 상주
    # GPU 안 쓸 때 자동으로 작업 수행
    # 토큰 적립 현황 표시
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import signal
import sys
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GPUInfo:
    """감지된 GPU 정보."""
    name: str
    vram_mb: int
    compute_capability: str
    driver_version: str
    cuda_version: str
    performance_score: float  # 상대 성능 (RTX 3060=1.0 기준)


@dataclass
class AgentConfig:
    """에이전트 설정."""
    api_key: str
    master_url: str = "https://grid.hwarang.ai"
    max_gpu_usage: float = 0.9     # GPU 90% 이상이면 작업 중단
    max_gpu_temp: int = 85         # 85도 이상이면 작업 중단
    idle_threshold: float = 0.1    # GPU 10% 미만이면 '놀고 있음'
    check_interval: float = 5.0   # 5초마다 상태 확인
    auto_start: bool = True       # PC 부팅 시 자동 시작
    power_mode: str = "balanced"  # "aggressive", "balanced", "gentle"


# GPU 성능 점수 테이블 (RTX 3060 = 1.0 기준)
GPU_PERFORMANCE = {
    "RTX 3060": 1.0,
    "RTX 3060 Ti": 1.2,
    "RTX 3070": 1.4,
    "RTX 3070 Ti": 1.5,
    "RTX 3080": 1.8,
    "RTX 3080 Ti": 1.9,
    "RTX 3090": 2.2,
    "RTX 3090 Ti": 2.3,
    "RTX 4060": 1.3,
    "RTX 4060 Ti": 1.5,
    "RTX 4070": 1.7,
    "RTX 4070 Ti": 2.0,
    "RTX 4070 Ti Super": 2.1,
    "RTX 4080": 2.5,
    "RTX 4080 Super": 2.6,
    "RTX 4090": 3.5,
    "RTX 5060": 1.4,
    "RTX 5070": 2.0,
    "RTX 5070 Ti": 2.5,
    "RTX 5080": 3.0,
    "RTX 5090": 4.5,
}

# 토큰 보상 (시간당, RTX 3060 기준)
BASE_TOKENS_PER_HOUR = 200  # RTX 3060으로 1시간 = 200 토큰


class GPUAgent:
    """유저 PC에서 실행되는 GPU 에이전트."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.agent_id = f"grid-{uuid.uuid4().hex[:8]}"
        self.gpu_info: GPUInfo | None = None
        self._running = False
        self._working = False
        self._total_tokens_earned = 0
        self._session_start = time.time()
        self._work_seconds = 0

    async def start(self):
        """에이전트 시작."""
        logger.info("=" * 50)
        logger.info("Hwarang Grid Agent 시작")
        logger.info("=" * 50)

        # 1. GPU 감지
        self.gpu_info = self._detect_gpu()
        if not self.gpu_info:
            logger.error("GPU를 감지할 수 없습니다")
            return

        logger.info(f"  GPU: {self.gpu_info.name}")
        logger.info(f"  VRAM: {self.gpu_info.vram_mb}MB")
        logger.info(f"  성능: {self.gpu_info.performance_score:.1f}x (RTX 3060 기준)")
        logger.info(f"  시간당 토큰: ~{self._tokens_per_hour()}")

        # 2. 마스터에 등록
        registered = await self._register()
        if not registered:
            logger.error("마스터 서버에 등록 실패")
            return

        logger.info(f"  등록 완료: {self.agent_id}")
        logger.info("")
        logger.info("GPU가 놀고 있을 때 자동으로 작업을 수행합니다")
        logger.info("게임/작업 시작하면 즉시 중단됩니다")
        logger.info("종료: Ctrl+C")
        logger.info("")

        # 3. 메인 루프
        self._running = True
        await asyncio.gather(
            self._monitor_loop(),
            self._heartbeat_loop(),
            self._stats_loop(),
        )

    async def stop(self):
        """에이전트 종료."""
        logger.info("에이전트 종료 중...")
        self._running = False

        # 진행 중 작업 반환
        if self._working:
            await self._return_current_work()

        # 마스터에서 등록 해제
        await self._deregister()

        # 최종 통계
        session_hours = (time.time() - self._session_start) / 3600
        logger.info(f"세션 요약:")
        logger.info(f"  실행 시간: {session_hours:.1f}시간")
        logger.info(f"  작업 시간: {self._work_seconds / 3600:.1f}시간")
        logger.info(f"  적립 토큰: {self._total_tokens_earned:,}")

    # ---- 메인 루프 ----

    async def _monitor_loop(self):
        """GPU 상태를 모니터링하고 작업을 수행."""
        while self._running:
            try:
                gpu_usage = self._get_gpu_usage()
                gpu_temp = self._get_gpu_temp()

                # GPU가 놀고 있는가?
                is_idle = (
                    gpu_usage < self.config.idle_threshold
                    and gpu_temp < self.config.max_gpu_temp
                )

                if is_idle and not self._working:
                    # 작업 요청
                    work = await self._request_work()
                    if work:
                        self._working = True
                        asyncio.create_task(self._execute_work(work))

                elif not is_idle and self._working:
                    # 유저가 GPU 사용 시작 → 즉시 중단
                    logger.info("GPU 사용 감지 → 작업 일시 중단")
                    await self._pause_current_work()
                    self._working = False

            except Exception as e:
                logger.error(f"모니터 오류: {e}")

            await asyncio.sleep(self.config.check_interval)

    async def _execute_work(self, work: dict):
        """작업 실행."""
        work_type = work.get("type")
        start_time = time.time()

        try:
            if work_type == "inference":
                result = await self._do_inference(work)
            elif work_type == "finetune_batch":
                result = await self._do_finetune_batch(work)
            else:
                logger.warning(f"알 수 없는 작업 유형: {work_type}")
                return

            # 결과 전송
            await self._submit_result(work["id"], result)

            # 토큰 적립
            elapsed = time.time() - start_time
            self._work_seconds += elapsed
            tokens = self._calculate_reward(elapsed)
            self._total_tokens_earned += tokens

            logger.info(f"작업 완료: +{tokens} 토큰 (총 {self._total_tokens_earned:,})")

        except Exception as e:
            logger.error(f"작업 실패: {e}")
            await self._report_failure(work["id"], str(e))
        finally:
            self._working = False

    async def _do_inference(self, work: dict) -> dict:
        """추론 작업 수행."""
        # 모델 조각을 받아서 로컬에서 추론
        model_shard = work.get("model_shard")
        input_data = work.get("input")

        # 실제 추론 로직 (간소화)
        import torch

        # 모델 조각 로드 (이미 캐시되어 있으면 재사용)
        # TODO: 모델 조각 캐시 시스템
        logger.info(f"추론 작업 수행: {work['id'][:8]}...")

        # 결과 반환
        return {
            "output": "inference_result",
            "tokens_used": work.get("estimated_tokens", 100),
        }

    async def _do_finetune_batch(self, work: dict) -> dict:
        """파인튜닝 배치 작업 수행."""
        # gradient 계산 후 반환
        logger.info(f"파인튜닝 배치: {work['id'][:8]}...")

        return {
            "gradients": "gradient_data",
            "loss": 0.5,
            "batch_size": work.get("batch_size", 1),
        }

    # ---- 토큰 보상 계산 ----

    def _tokens_per_hour(self) -> int:
        """시간당 예상 토큰 보상."""
        if not self.gpu_info:
            return 0
        return int(BASE_TOKENS_PER_HOUR * self.gpu_info.performance_score)

    def _calculate_reward(self, work_seconds: float) -> int:
        """작업 시간에 따른 토큰 보상."""
        hours = work_seconds / 3600
        return int(self._tokens_per_hour() * hours)

    # ---- GPU 유틸리티 ----

    def _detect_gpu(self) -> GPUInfo | None:
        """GPU 정보 감지."""
        try:
            import torch
            if not torch.cuda.is_available():
                return None

            device = torch.cuda.current_device()
            props = torch.cuda.get_device_properties(device)
            name = props.name

            # 성능 점수 매핑
            score = 1.0
            for gpu_name, perf in GPU_PERFORMANCE.items():
                if gpu_name.lower() in name.lower():
                    score = perf
                    break

            return GPUInfo(
                name=name,
                vram_mb=props.total_mem // (1024 * 1024),
                compute_capability=f"{props.major}.{props.minor}",
                driver_version=torch.version.cuda or "unknown",
                cuda_version=torch.version.cuda or "unknown",
                performance_score=score,
            )
        except Exception as e:
            logger.error(f"GPU 감지 실패: {e}")
            return None

    def _get_gpu_usage(self) -> float:
        """현재 GPU 사용률 (0.0 ~ 1.0)."""
        try:
            import subprocess
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                text=True,
            )
            return float(output.strip()) / 100
        except Exception:
            return 0.0

    def _get_gpu_temp(self) -> int:
        """현재 GPU 온도."""
        try:
            import subprocess
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=temperature.gpu",
                 "--format=csv,noheader"],
                text=True,
            )
            return int(output.strip())
        except Exception:
            return 0

    # ---- 마스터 통신 ----

    async def _register(self) -> bool:
        """마스터에 등록."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                resp = await session.post(
                    f"{self.config.master_url}/grid/register",
                    json={
                        "agent_id": self.agent_id,
                        "api_key": self.config.api_key,
                        "gpu": asdict(self.gpu_info) if self.gpu_info else {},
                        "os": platform.system(),
                        "hostname": platform.node(),
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                )
                return resp.status == 200
        except Exception as e:
            logger.warning(f"등록 실패: {e}")
            return False

    async def _deregister(self):
        """마스터에서 등록 해제."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{self.config.master_url}/grid/deregister",
                    json={"agent_id": self.agent_id},
                    timeout=aiohttp.ClientTimeout(total=5),
                )
        except Exception:
            pass

    async def _heartbeat_loop(self):
        """30초마다 하트비트."""
        while self._running:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    await session.post(
                        f"{self.config.master_url}/grid/heartbeat",
                        json={
                            "agent_id": self.agent_id,
                            "gpu_usage": self._get_gpu_usage(),
                            "gpu_temp": self._get_gpu_temp(),
                            "is_working": self._working,
                            "tokens_earned": self._total_tokens_earned,
                        },
                        timeout=aiohttp.ClientTimeout(total=5),
                    )
            except Exception:
                pass
            await asyncio.sleep(30)

    async def _request_work(self) -> dict | None:
        """마스터에 작업 요청."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                resp = await session.post(
                    f"{self.config.master_url}/grid/request-work",
                    json={
                        "agent_id": self.agent_id,
                        "gpu_vram_mb": self.gpu_info.vram_mb if self.gpu_info else 0,
                        "gpu_score": self.gpu_info.performance_score if self.gpu_info else 0,
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                )
                if resp.status == 200:
                    return await resp.json()
                return None  # 작업 없음
        except Exception:
            return None

    async def _submit_result(self, work_id: str, result: dict):
        """작업 결과 전송."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{self.config.master_url}/grid/submit-result",
                    json={
                        "agent_id": self.agent_id,
                        "work_id": work_id,
                        "result": result,
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                )
        except Exception as e:
            logger.error(f"결과 전송 실패: {e}")

    async def _report_failure(self, work_id: str, error: str):
        """작업 실패 보고."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{self.config.master_url}/grid/report-failure",
                    json={"agent_id": self.agent_id, "work_id": work_id, "error": error},
                )
        except Exception:
            pass

    async def _pause_current_work(self):
        """현재 작업 일시 중단."""
        # TODO: 진행 중인 작업 상태 저장 + 반환
        pass

    async def _return_current_work(self):
        """진행 중인 작업 마스터에 반환."""
        pass

    # ---- 통계 표시 ----

    async def _stats_loop(self):
        """5분마다 통계 표시."""
        while self._running:
            await asyncio.sleep(300)
            hours = (time.time() - self._session_start) / 3600
            work_hours = self._work_seconds / 3600
            logger.info(
                f"[통계] 실행: {hours:.1f}h | "
                f"작업: {work_hours:.1f}h ({work_hours/max(hours,0.01)*100:.0f}%) | "
                f"적립: {self._total_tokens_earned:,} 토큰"
            )


# ============================================================
# CLI 진입점
# ============================================================

async def run_agent(api_key: str, master_url: str = "https://grid.hwarang.ai"):
    config = AgentConfig(api_key=api_key, master_url=master_url)
    agent = GPUAgent(config)

    loop = asyncio.get_event_loop()
    def handle_signal():
        asyncio.ensure_future(agent.stop())
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)

    await agent.start()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Hwarang Grid Agent")
    parser.add_argument("--api-key", required=True, help="Hwarang API 키")
    parser.add_argument("--master", default="https://grid.hwarang.ai")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    asyncio.run(run_agent(args.api_key, args.master))
