"""HWARANG 적응형 발행 알고리즘

3중 균형 메커니즘:
  1. 고정 상한 (10억 HWR)
  2. 적응형 발행 (네트워크 상태 기반)
  3. 소각 (서비스 이용 시 30%)

스마트 컨트랙트로 배포 시 이 로직 그대로 Solidity로 변환.
여기서는 Python으로 시뮬레이션.

사용법:
    python scripts/blockchain/adaptive_emission.py simulate --years 5
    python scripts/blockchain/adaptive_emission.py calculate --gpu-util 0.85 --demand-growth 0.2
"""

from __future__ import annotations

import argparse
import json
import logging
import math

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 상수 (스마트 컨트랙트에 하드코딩될 값)
# ═══════════════════════════════════════════════════════════════

TOTAL_SUPPLY_CAP = 1_000_000_000  # 10억 HWR 절대 상한
BASE_REWARD_PER_HOUR = 10         # RTX 5090 기준 시간당 기본 보상 (10 HWR)

# 반감기 마일스톤 (누적 발행량 기준)
HALVING_MILESTONES = [
    100_000_000,   # 1억: 반감기 1
    200_000_000,   # 2억: 반감기 2
    300_000_000,   # 3억: 반감기 3
    400_000_000,   # 4억: 반감기 4
]

# 소각률
BURN_RATES = {
    "ai_usage": 0.30,       # AI 서비스 이용 시 30%
    "api_call": 0.30,       # API 호출 시 30%
    "subscription": 0.20,   # 구독 결제 시 20%
    "purchase": 0.05,       # 토큰 구매 시 5%
    "transfer": 0.01,       # P2P 이전 시 1%
}

# GPU 상대 성능 (RTX 5090 = 1.0)
GPU_PERFORMANCE = {
    "RTX 4060": 0.15,
    "RTX 4070": 0.25,
    "RTX 4080": 0.45,
    "RTX 4090": 0.70,
    "RTX 5060": 0.30,
    "RTX 5070": 0.50,
    "RTX 5080": 0.65,
    "RTX 5090": 1.00,
    "A100": 1.20,
    "H100": 1.80,
}

# 작업 배율
TASK_MULTIPLIER = {
    "serving": 1.0,      # 추론 서빙
    "training_sft": 2.0, # SFT 학습
    "training_dpo": 2.5, # DPO 학습
    "validation": 0.5,   # 피드백 검증
    "data_gen": 1.5,     # 데이터 생성
}


# ═══════════════════════════════════════════════════════════════
# 적응형 발행 계산 (핵심 알고리즘)
# ═══════════════════════════════════════════════════════════════

def calculate_halving_factor(total_emitted: int) -> float:
    """누적 발행량 기반 반감기 계수."""
    factor = 1.0
    for milestone in HALVING_MILESTONES:
        if total_emitted >= milestone:
            factor *= 0.5
    return factor


def calculate_supply_factor(gpu_utilization: float) -> float:
    """GPU 공급 상태에 따른 보상 조절.

    gpu_utilization: 네트워크 전체 GPU 사용률 (0~1)
      >0.8: GPU 부족 → 보상 ↑ (참여 유인)
      0.4~0.8: 적정 → 기본
      <0.4: GPU 과잉 → 보상 ↓ (인플레 방지)
    """
    if gpu_utilization > 0.9:
        return 3.0  # 극심한 부족
    elif gpu_utilization > 0.8:
        return 1.5 + (gpu_utilization - 0.8) * 15  # 1.5~3.0
    elif gpu_utilization > 0.4:
        return 1.0  # 적정
    elif gpu_utilization > 0.2:
        return 0.5 + (gpu_utilization - 0.2) * 2.5  # 0.5~1.0
    else:
        return 0.3  # 최소 (완전 중단은 안 함)


def calculate_demand_factor(demand_change: float) -> float:
    """서비스 수요 변화에 따른 보상 조절.

    demand_change: 전주 대비 수요 변화율 (-1 ~ +∞)
      양수: 수요 증가 → 보상 약간 ↑
      음수: 수요 감소 → 보상 ↓
    """
    # 부드러운 곡선 (급격한 변화 방지)
    return max(0.5, min(1.5, 1.0 + demand_change * 0.5))


def calculate_reward(
    gpu_name: str,
    task_type: str,
    gpu_utilization: float,
    demand_change: float,
    total_emitted: int,
    streak_days: int = 0,
) -> dict:
    """최종 보상 계산.

    Returns:
        {
          base_reward: 기본 보상,
          supply_factor: 공급 계수,
          demand_factor: 수요 계수,
          halving_factor: 반감기 계수,
          task_multiplier: 작업 배율,
          streak_bonus: 연속 참여 보너스,
          final_reward: 최종 보상,
          details: 설명
        }
    """
    # 잔여 발행 가능량 체크
    remaining = TOTAL_SUPPLY_CAP - total_emitted
    if remaining <= 0:
        return {
            "base_reward": 0, "supply_factor": 0, "demand_factor": 0,
            "halving_factor": 0, "task_multiplier": 0, "streak_bonus": 0,
            "final_reward": 0, "details": "발행 상한 도달 (10억 HWR)"
        }

    base = BASE_REWARD_PER_HOUR * GPU_PERFORMANCE.get(gpu_name, 0.5)
    supply_f = calculate_supply_factor(gpu_utilization)
    demand_f = calculate_demand_factor(demand_change)
    halving_f = calculate_halving_factor(total_emitted)
    task_m = TASK_MULTIPLIER.get(task_type, 1.0)
    streak_b = 1.0 + min(streak_days * 0.05, 0.5)  # 최대 +50%

    final = base * supply_f * demand_f * halving_f * task_m * streak_b

    # 상한 초과 방지
    final = min(final, remaining)

    return {
        "base_reward": round(base, 2),
        "supply_factor": round(supply_f, 3),
        "demand_factor": round(demand_f, 3),
        "halving_factor": round(halving_f, 4),
        "task_multiplier": task_m,
        "streak_bonus": round(streak_b, 2),
        "final_reward": round(final, 2),
        "hourly_hwr": round(final, 2),
        "daily_hwr": round(final * 24, 2),
        "monthly_hwr": round(final * 24 * 30, 2),
        "details": (
            f"GPU={gpu_name}, task={task_type}, "
            f"supply={supply_f:.2f}, demand={demand_f:.2f}, "
            f"halving={halving_f:.3f}, streak={streak_b:.2f}"
        ),
    }


# ═══════════════════════════════════════════════════════════════
# 소각 계산
# ═══════════════════════════════════════════════════════════════

def calculate_burn(action: str, amount: float) -> dict:
    """소각량 계산.

    Args:
        action: ai_usage, api_call, subscription, purchase, transfer
        amount: 소비/이전 토큰량

    Returns:
        {burned: 소각량, remaining: 실제 사용량, rate: 소각률}
    """
    rate = BURN_RATES.get(action, 0)
    burned = amount * rate
    remaining = amount - burned

    return {
        "action": action,
        "amount": amount,
        "burn_rate": rate,
        "burned": round(burned, 4),
        "remaining": round(remaining, 4),
    }


# ═══════════════════════════════════════════════════════════════
# 5년 시뮬레이션
# ═══════════════════════════════════════════════════════════════

def simulate(years: int = 5):
    """연도별 발행/소각/유통 시뮬레이션."""

    print("\n" + "=" * 80)
    print(" HWARANG 토크노믹스 시뮬레이션")
    print("=" * 80)

    total_emitted = 0
    total_burned = 0
    circulating = 0

    # 연도별 가정
    yearly_scenarios = [
        # (GPU 참여자, 평균 GPU사용률, 수요성장률, 일일 서비스 이용 HWR)
        # 서비스 이용 HWR = 유통량의 일부. 현실적 추정.
        (1_000,   0.85, 0.30, 30_000),        # Y1: 초기, 유저 적음
        (10_000,  0.70, 0.25, 200_000),       # Y2: 성장
        (50_000,  0.60, 0.15, 500_000),       # Y3: 확산
        (200_000, 0.50, 0.08, 1_000_000),     # Y4: 대중화
        (500_000, 0.45, 0.05, 2_000_000),     # Y5: 성숙
    ]

    print(f"\n{'연도':<6} {'참여자':>8} {'일발행':>12} {'일소각':>12} {'순발행':>12} {'누적발행':>14} {'유통량':>14} {'상태':>10}")
    print("-" * 90)

    for year_idx in range(min(years, len(yearly_scenarios))):
        participants, gpu_util, demand_growth, daily_usage = yearly_scenarios[year_idx]

        # 평균 보상 계산 (RTX 4090 기준)
        reward = calculate_reward(
            "RTX 4090", "serving", gpu_util, demand_growth, total_emitted
        )

        # 일일 발행량 = 참여자 × 시간당 보상 × 24시간
        hourly = reward.get("hourly_hwr", reward.get("final_reward", 0))
        daily_emission = participants * hourly * 24
        # 상한 체크
        remaining_cap = TOTAL_SUPPLY_CAP - total_emitted
        yearly_emission = min(daily_emission * 365, remaining_cap)
        actual_daily_emission = yearly_emission / 365

        # 일일 소각량 (유통량 초과 소각 방지)
        daily_burn = daily_usage * BURN_RATES["ai_usage"]
        yearly_burn = daily_burn * 365

        # 순 발행
        net_daily = actual_daily_emission - daily_burn

        total_emitted += yearly_emission
        total_burned += yearly_burn

        # 소각은 유통량을 초과할 수 없음
        circulating = max(0, total_emitted - total_burned)
        if total_burned > total_emitted:
            total_burned = total_emitted  # 소각 상한 = 발행량

        status = "디플레" if net_daily < 0 else "인플레" if net_daily > yearly_emission * 0.01 else "균형"

        print(
            f"  Y{year_idx + 1}   {participants:>8,}  "
            f"{actual_daily_emission:>10,.0f}  {daily_burn:>10,.0f}  "
            f"{net_daily:>10,.0f}  {total_emitted:>12,.0f}  "
            f"{circulating:>12,.0f}  {status:>8}"
        )

    print("-" * 90)
    print(f"\n  총 발행: {total_emitted:,.0f} / {TOTAL_SUPPLY_CAP:,.0f} ({total_emitted/TOTAL_SUPPLY_CAP*100:.1f}%)")
    print(f"  총 소각: {total_burned:,.0f} ({total_burned/max(total_emitted,1)*100:.1f}%)")
    print(f"  유통량:  {circulating:,.0f}")
    print(f"  잔여:    {TOTAL_SUPPLY_CAP - total_emitted:,.0f}")

    # GPU별 예상 수익
    print(f"\n\nGPU별 예상 수익 (현재: 발행 {total_emitted/1e6:.0f}M, GPU사용률 60%):")
    print(f"{'GPU':<15} {'시간당':>10} {'일당':>12} {'월당':>14}")
    print("-" * 55)

    for gpu, perf in sorted(GPU_PERFORMANCE.items(), key=lambda x: x[1]):
        r = calculate_reward(gpu, "serving", 0.6, 0.1, int(total_emitted))
        h = r.get("hourly_hwr", r.get("final_reward", 0))
        print(f"  {gpu:<13} {h:>8.1f}  {h*24:>10.1f}  {h*24*30:>12.1f}")

    print("=" * 80)


# ═══════════════════════════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="HWARANG Adaptive Emission")
    parser.add_argument("mode", choices=["simulate", "calculate", "burn"])
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--gpu", default="RTX 5090")
    parser.add_argument("--task", default="serving")
    parser.add_argument("--gpu-util", type=float, default=0.6)
    parser.add_argument("--demand-growth", type=float, default=0.1)
    parser.add_argument("--emitted", type=int, default=0)
    parser.add_argument("--streak", type=int, default=0)
    parser.add_argument("--action", default="ai_usage")
    parser.add_argument("--amount", type=float, default=100)
    args = parser.parse_args()

    if args.mode == "simulate":
        simulate(args.years)

    elif args.mode == "calculate":
        result = calculate_reward(
            args.gpu, args.task, args.gpu_util,
            args.demand_growth, args.emitted, args.streak
        )
        print(f"\n보상 계산:")
        for k, v in result.items():
            print(f"  {k}: {v}")

    elif args.mode == "burn":
        result = calculate_burn(args.action, args.amount)
        print(f"\n소각 계산:")
        for k, v in result.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
