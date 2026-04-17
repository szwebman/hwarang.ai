"""HFL Network-Aware Scheduler

이종 GPU/네트워크 환경에서 워커별 최적 학습량 동적 할당.

핵심:
  - 빠른 GPU(5090) + 빠른 인터넷 → 800 step
  - 느린 GPU(4060) + 느린 인터넷 → 200 step
  - 마스터가 실시간으로 라운드 시간 내 최적 배분
  - Straggler(느린 워커) 자동 처리

프로세스:
  1. 워커 등록 시 GPU 벤치마크 + 네트워크 측정
  2. 마스터가 워커별 능력치 프로파일 생성
  3. 라운드 시간(10분) 내 최대 step 수 계산
  4. 능력치에 비례한 step 할당
  5. 빠른 워커 완료 → 추가 배치 할당 (비동기)
  6. 느린 워커 타임아웃 → 스킵 (페널티 없음)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ─── 워커 프로파일 ───────────────────────────────────────────

@dataclass
class WorkerProfile:
    worker_id: str

    # GPU 능력
    gpu_name: str = "unknown"
    gpu_vram_gb: float = 0
    gpu_benchmark_tps: float = 0     # tokens per second (벤치마크)

    # 네트워크
    upload_mbps: float = 10
    download_mbps: float = 50

    # 산출된 값
    estimated_step_time_sec: float = 1.0  # 1 step 소요 시간
    max_steps_per_round: int = 500
    lora_rank: int = 16
    transfer_time_sec: float = 5.0

    # 실적
    rounds_completed: int = 0
    total_steps: int = 0
    avg_loss_improvement: float = 0.0
    reliability: float = 1.0  # 0~1 (타임아웃 비율)

    # 보상 배율
    reward_multiplier: float = 1.0


# ─── GPU 벤치마크 (추정치) ──────────────────────────────────

GPU_BENCHMARKS = {
    # GPU명: (tokens/sec for 32B INT4, VRAM GB)
    "RTX 4060": (15, 8),
    "RTX 4070": (25, 12),
    "RTX 4080": (40, 16),
    "RTX 4090": (55, 24),
    "RTX 5060": (25, 16),
    "RTX 5070": (45, 12),
    "RTX 5080": (60, 16),
    "RTX 5090": (80, 32),
    "A100": (90, 80),
    "H100": (150, 80),
}


def estimate_gpu_capability(gpu_name: str) -> tuple[float, float]:
    """GPU 이름으로 능력치 추정."""
    for key, (tps, vram) in GPU_BENCHMARKS.items():
        if key.lower() in gpu_name.lower():
            return tps, vram
    return 20, 8  # 기본값


# ─── 스케줄러 ────────────────────────────────────────────────

class NetworkAwareScheduler:
    """워커별 최적 학습량 동적 할당.

    목표: 라운드 시간(round_time_sec) 내에
          모든 워커가 학습 + 전송을 완료하도록 step 수 배분.
    """

    def __init__(
        self,
        round_time_sec: float = 600,   # 10분
        min_steps: int = 50,
        max_steps: int = 2000,
        base_lora_size_mb: float = 50,
    ):
        self.round_time_sec = round_time_sec
        self.min_steps = min_steps
        self.max_steps = max_steps
        self.base_lora_size_mb = base_lora_size_mb
        self.workers: dict[str, WorkerProfile] = {}

    def register_worker(
        self,
        worker_id: str,
        gpu_name: str,
        upload_mbps: float,
        download_mbps: float,
    ) -> WorkerProfile:
        """워커 등록 + 프로파일 생성."""
        tps, vram = estimate_gpu_capability(gpu_name)

        # 1 step 시간 추정
        # QLoRA: 대략 tokens_per_step / tps
        tokens_per_step = 2048  # max_length
        step_time = tokens_per_step / max(tps, 1) * 3  # forward + backward + optim ≈ 3x

        # LoRA 랭크 결정 (네트워크 기반 - hfl_adaptive.py 참조)
        from hfl_adaptive import NetworkProbe
        lora_rank = NetworkProbe.decide_lora_rank(upload_mbps, max_transfer_sec=60)

        # 전송 시간 추정
        rank_to_compressed = {4: 2.0, 8: 4.0, 16: 8.0, 32: 16.0, 64: 32.0}
        compressed_mb = rank_to_compressed.get(lora_rank, 8.0)
        transfer_time = compressed_mb / (upload_mbps / 8)

        # 라운드 내 가용 학습 시간
        available_time = self.round_time_sec - transfer_time - 30  # 30초 버퍼
        max_steps = int(available_time / max(step_time, 0.1))
        max_steps = max(self.min_steps, min(self.max_steps, max_steps))

        # 보상 배율 (더 많이 학습 = 더 많은 보상)
        reward_multiplier = max_steps / 500  # 500 step 기준 1.0x

        profile = WorkerProfile(
            worker_id=worker_id,
            gpu_name=gpu_name,
            gpu_vram_gb=vram,
            gpu_benchmark_tps=tps,
            upload_mbps=upload_mbps,
            download_mbps=download_mbps,
            estimated_step_time_sec=step_time,
            max_steps_per_round=max_steps,
            lora_rank=lora_rank,
            transfer_time_sec=transfer_time,
            reward_multiplier=reward_multiplier,
        )

        self.workers[worker_id] = profile

        logger.info(
            f"워커 등록: {worker_id}\n"
            f"  GPU: {gpu_name} ({tps} tok/s, {vram}GB)\n"
            f"  네트워크: ↑{upload_mbps}Mbps ↓{download_mbps}Mbps\n"
            f"  할당: {max_steps} step/round (r={lora_rank})\n"
            f"  전송: ~{compressed_mb:.1f}MB ({transfer_time:.1f}초)\n"
            f"  보상 배율: {reward_multiplier:.1f}x"
        )

        return profile

    def get_round_assignment(self, worker_id: str) -> dict:
        """워커에게 이번 라운드 할당 정보 반환."""
        profile = self.workers.get(worker_id)
        if not profile:
            return {"error": "미등록 워커"}

        return {
            "worker_id": worker_id,
            "steps": profile.max_steps_per_round,
            "lora_rank": profile.lora_rank,
            "round_time_sec": self.round_time_sec,
            "deadline": time.time() + self.round_time_sec,
            "reward_multiplier": profile.reward_multiplier,
        }

    def handle_completion(self, worker_id: str, actual_steps: int, loss: float) -> dict:
        """워커 라운드 완료 처리."""
        profile = self.workers.get(worker_id)
        if not profile:
            return {"error": "미등록"}

        profile.rounds_completed += 1
        profile.total_steps += actual_steps
        profile.reliability = min(1.0, profile.reliability + 0.01)

        # 기대치 대비 달성률
        completion_rate = actual_steps / max(profile.max_steps_per_round, 1)

        # 빠르게 끝낸 워커 → 추가 배치 가능
        extra_assignment = None
        if completion_rate >= 0.9:
            remaining_time = self.round_time_sec * 0.3  # 남은 시간 30%
            extra_steps = int(remaining_time / max(profile.estimated_step_time_sec, 0.1))
            if extra_steps >= self.min_steps:
                extra_assignment = {
                    "extra_steps": extra_steps,
                    "bonus_reward": 0.3,  # 추가 배치 30% 보너스
                }

        # 보상 계산
        base_reward = int(actual_steps * 0.2 * profile.reward_multiplier)

        return {
            "status": "completed",
            "steps_done": actual_steps,
            "completion_rate": completion_rate,
            "reward": base_reward,
            "extra_assignment": extra_assignment,
        }

    def handle_timeout(self, worker_id: str) -> dict:
        """워커 타임아웃 처리 (페널티 최소화)."""
        profile = self.workers.get(worker_id)
        if not profile:
            return {"error": "미등록"}

        profile.reliability = max(0.0, profile.reliability - 0.1)

        # 다음 라운드 step 수 감소 (20%)
        profile.max_steps_per_round = max(
            self.min_steps,
            int(profile.max_steps_per_round * 0.8)
        )

        logger.warning(
            f"워커 타임아웃: {worker_id} "
            f"(신뢰도 {profile.reliability:.2f}, "
            f"다음 라운드 {profile.max_steps_per_round} step)"
        )

        return {
            "status": "timeout",
            "penalty": "step 감소",
            "new_max_steps": profile.max_steps_per_round,
            "reliability": profile.reliability,
        }

    def get_cluster_stats(self) -> dict:
        """클러스터 전체 통계."""
        if not self.workers:
            return {"workers": 0}

        profiles = list(self.workers.values())
        total_steps = sum(p.max_steps_per_round for p in profiles)
        avg_reliability = sum(p.reliability for p in profiles) / len(profiles)

        return {
            "workers": len(profiles),
            "total_steps_per_round": total_steps,
            "avg_reliability": avg_reliability,
            "gpu_distribution": {p.gpu_name: p.max_steps_per_round for p in profiles},
            "network_distribution": {
                p.worker_id: f"↑{p.upload_mbps}Mbps → r={p.lora_rank} → {p.max_steps_per_round} step"
                for p in profiles
            },
        }

    def print_schedule(self):
        """라운드 스케줄 출력."""
        print("\n" + "=" * 70)
        print(f" HFL Network-Aware Schedule (라운드 {self.round_time_sec}초)")
        print("=" * 70)
        print(f"{'워커':<15} {'GPU':<12} {'네트워크':>8} {'랭크':>5} {'Step':>6} {'전송':>8} {'보상':>5}")
        print("-" * 70)

        for p in sorted(self.workers.values(), key=lambda x: x.max_steps_per_round, reverse=True):
            print(
                f"  {p.worker_id:<13} {p.gpu_name:<12} {p.upload_mbps:>5.0f}M  "
                f"r={p.lora_rank:<3} {p.max_steps_per_round:>5}  "
                f"{p.transfer_time_sec:>5.1f}초  {p.reward_multiplier:>4.1f}x"
            )

        stats = self.get_cluster_stats()
        print("-" * 70)
        print(f"  총 step/라운드: {stats['total_steps_per_round']}")
        print(f"  워커 수: {stats['workers']}")
        print("=" * 70)


# ─── 시뮬레이션 ──────────────────────────────────────────────

def simulate():
    """다양한 워커 환경 시뮬레이션."""
    scheduler = NetworkAwareScheduler(round_time_sec=600)

    # 다양한 워커 등록
    workers = [
        ("worker_kr_01", "RTX 5090", 100, 500),    # 한국 고성능
        ("worker_kr_02", "RTX 4090", 50, 200),     # 한국 중간
        ("worker_kr_03", "RTX 4060", 10, 50),      # 한국 저성능
        ("worker_jp_01", "RTX 4080", 30, 100),     # 일본
        ("worker_us_01", "RTX 4070", 20, 80),      # 미국
        ("worker_mobile", "RTX 4060", 1, 5),       # 모바일 테더링
    ]

    for wid, gpu, up, down in workers:
        scheduler.register_worker(wid, gpu, up, down)

    scheduler.print_schedule()


# ─── 메인 ────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HFL Network-Aware Scheduler")
    parser.add_argument("mode", nargs="?", default="simulate", choices=["master", "simulate"])
    parser.add_argument("--round-time", type=int, default=600, help="라운드 시간 (초)")
    args = parser.parse_args()

    if args.mode == "simulate":
        simulate()
    else:
        scheduler = NetworkAwareScheduler(round_time_sec=args.round_time)
        logger.info(f"스케줄러 시작 (라운드 {args.round_time}초)")
