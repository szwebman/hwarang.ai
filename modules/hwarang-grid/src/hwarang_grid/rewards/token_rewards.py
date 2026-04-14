"""토큰 보상 시스템.

보상 원칙:
1. "처리한 만큼" 보상 (시간이 아니라 실제 작업량 기반)
2. Hwarang이 손해보지 않는 구조 (보상 < 수익)
3. 유저에게도 의미 있는 보상 (전기세 이상)

보상 공식:
  보상 토큰 = 처리한 토큰 × 보상률 × GPU 효율 보너스 × 연속 참여 보너스

보상률:
  = 유저가 소비하는 토큰 가격의 10~20%를 Grid 기여자에게 돌려줌
  = 추론: 처리 1K 토큰당 5~15 토큰 보상 (모델 크기에 따라)
  = 유저가 30B 모델로 300토큰 요청 → Grid 기여자에게 ~3토큰 보상 (1%)

경제 구조:
  유저가 API 호출: 300 토큰 소비 (Pro 플랜에서 차감)
  Grid 기여자가 처리: 3 토큰 보상 (보상률 1%)
  Hwarang 마진: 297 토큰 (99%)

  → Hwarang이 충분히 이익
  → 기여자도 쌓이면 의미 있는 양
  → 기여자 1,000명이면 서버 비용 0원
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ============================================================
# 보상 설정 (관리자가 조정 가능)
# ============================================================

# 처리한 토큰 1K당 보상 (모델별)
REWARD_PER_1K_TOKENS = {
    "7b":  8,     # 7B 모델: 1K 토큰 처리당 8 토큰 보상
    "13b": 12,    # 13B: 12 토큰
    "30b": 20,    # 30B: 20 토큰 (더 무거운 작업 = 더 많은 보상)
}

# 작업 유형별 배수
WORK_TYPE_MULTIPLIER = {
    "inference":       1.0,   # 추론 (기본)
    "finetune_batch":  2.0,   # 파인튜닝 배치 (GPU 풀로드, 가치 높음)
    "embedding":       0.5,   # 임베딩 생성 (가벼움)
    "data_process":    0.3,   # 데이터 전처리 (CPU 위주)
}

# GPU 효율 보너스 (빠른 GPU는 같은 시간에 더 많이 처리 → 자연스럽게 더 많이 벌림)
# → 별도 배수 불필요! 빠른 GPU = 같은 시간에 더 많은 토큰 처리 = 더 많은 보상
# → 처리량 기반이라 자동으로 공정

# 연속 참여 보너스
STREAK_BONUS = {
    7:  1.05,    # 7일 연속 → 5% 보너스
    30: 1.10,    # 30일 연속 → 10% 보너스
    90: 1.15,    # 90일 연속 → 15% 보너스
}

# 특별 보상
REFERRAL_BONUS = 5_000       # 친구 초대 시 5천 토큰
WELCOME_BONUS = 3_000        # 첫 가입 시 3천 토큰
MILESTONE_BONUSES = {
    100_000:  5_000,          # 누적 10만 토큰 처리 → 5천 보너스
    1_000_000: 20_000,        # 누적 100만 → 2만 보너스
    10_000_000: 100_000,      # 누적 1000만 → 10만 보너스
}

# 최소 보상 (너무 작은 작업은 1토큰이라도 보상)
MIN_REWARD = 1


# ============================================================
# 보상 계산
# ============================================================

@dataclass
class RewardCalculation:
    """보상 계산 결과."""
    tokens_processed: int       # 처리한 토큰 수
    model_size: str             # "7b", "30b" 등
    work_type: str              # 작업 유형
    base_reward: int            # 기본 보상
    work_multiplier: float      # 작업 유형 배수
    streak_multiplier: float    # 연속 참여 배수
    total_reward: int           # 최종 보상
    breakdown: str              # 계산 과정 (로그용)


def calculate_reward(
    tokens_processed: int,
    model_size: str = "7b",
    work_type: str = "inference",
    streak_days: int = 0,
) -> RewardCalculation:
    """토큰 보상 계산.

    Args:
        tokens_processed: 이 작업에서 처리한 토큰 수 (prompt + completion)
        model_size: 모델 크기 ("7b", "13b", "30b")
        work_type: 작업 유형
        streak_days: 연속 참여 일수

    Returns:
        보상 계산 결과
    """
    # 1. 기본 보상 (처리량 기반)
    rate = REWARD_PER_1K_TOKENS.get(model_size, 8)
    base = max(MIN_REWARD, int((tokens_processed / 1000) * rate))

    # 2. 작업 유형 배수
    work_mult = WORK_TYPE_MULTIPLIER.get(work_type, 1.0)

    # 3. 연속 참여 보너스
    streak_mult = 1.0
    for days, mult in sorted(STREAK_BONUS.items()):
        if streak_days >= days:
            streak_mult = mult

    # 4. 최종 계산
    total = max(MIN_REWARD, int(base * work_mult * streak_mult))

    breakdown = (
        f"{tokens_processed} tokens × {rate}/1K({model_size}) = {base} "
        f"× {work_mult:.1f}({work_type}) "
        f"× {streak_mult:.2f}(연속{streak_days}일) "
        f"= {total} 토큰"
    )

    return RewardCalculation(
        tokens_processed=tokens_processed,
        model_size=model_size,
        work_type=work_type,
        base_reward=base,
        work_multiplier=work_mult,
        streak_multiplier=streak_mult,
        total_reward=total,
        breakdown=breakdown,
    )


# ============================================================
# 예상 수익 계산
# ============================================================

# GPU별 초당 처리량 (tokens/sec, 추론 기준)
GPU_THROUGHPUT = {
    "RTX 3060":     30,     # 30 tok/s (7B INT4)
    "RTX 3060 Ti":  35,
    "RTX 3070":     45,
    "RTX 3070 Ti":  50,
    "RTX 3080":     65,
    "RTX 3080 Ti":  70,
    "RTX 3090":     80,
    "RTX 4060":     40,
    "RTX 4060 Ti":  50,
    "RTX 4070":     60,
    "RTX 4070 Ti":  75,
    "RTX 4080":     90,
    "RTX 4090":     120,
    "RTX 5060":     45,
    "RTX 5070":     70,
    "RTX 5070 Ti":  85,
    "RTX 5080":     100,
    "RTX 5090":     150,
}

# GPU TDP (와트)
GPU_TDP = {
    "RTX 3060": 170, "RTX 3070": 220, "RTX 3080": 320, "RTX 3090": 350,
    "RTX 4060": 115, "RTX 4070": 200, "RTX 4080": 320, "RTX 4090": 450,
    "RTX 5060": 145, "RTX 5070": 250, "RTX 5080": 360, "RTX 5090": 575,
}


def estimate_monthly_earnings(
    gpu_name: str,
    daily_hours: float = 16,
    model_size: str = "7b",
    utilization: float = 0.6,   # 실제 작업률 60% (대기 시간 포함)
) -> dict:
    """GPU별 월간 예상 토큰 적립량.

    Args:
        gpu_name: GPU 이름
        daily_hours: 하루 평균 기여 시간
        model_size: 주로 처리할 모델
        utilization: 실제 작업이 들어오는 비율 (0~1)
    """
    # GPU 처리량
    tok_per_sec = GPU_THROUGHPUT.get(gpu_name, 30)
    rate = REWARD_PER_1K_TOKENS.get(model_size, 8)

    # 시간당 처리 토큰 (실제 작업률 반영)
    tokens_per_hour = tok_per_sec * 3600 * utilization
    reward_per_hour = int((tokens_per_hour / 1000) * rate)

    daily_reward = int(reward_per_hour * daily_hours)
    monthly_reward = int(daily_reward * 30)

    # 토큰 가치 환산 (Pro 29,000원 / 500K)
    token_value_krw = 29000 / 500000  # = 0.058원/토큰
    monthly_value = int(monthly_reward * token_value_krw)

    # 전기세
    tdp = GPU_TDP.get(gpu_name, 200)
    actual_watts = tdp * 0.7  # 실사용 70%
    kwh_month = (actual_watts / 1000) * daily_hours * 30
    electricity = int(kwh_month * 120)  # 120원/kWh

    return {
        "gpu": gpu_name,
        "model": model_size,
        "tokens_per_sec": tok_per_sec,
        "reward_per_hour": reward_per_hour,
        "daily_reward": daily_reward,
        "monthly_reward": monthly_reward,
        "monthly_value_krw": monthly_value,
        "electricity_krw": electricity,
        "net_profit_krw": monthly_value - electricity,
        "equivalent_plan": _equivalent_plan(monthly_reward),
        "utilization": f"{utilization*100:.0f}%",
    }


def _equivalent_plan(monthly_tokens: int) -> str:
    if monthly_tokens >= 2_000_000:
        return "Business (99,000원 상당)"
    elif monthly_tokens >= 500_000:
        return "Pro (29,000원 상당)"
    elif monthly_tokens >= 100_000:
        return "Starter (9,900원 상당)"
    elif monthly_tokens >= 10_000:
        return "Free 이상"
    return "Free 미만"


# ============================================================
# 경제 시뮬레이션 (Hwarang 관점)
# ============================================================

def simulate_economics(
    grid_users: int = 1000,
    avg_gpu: str = "RTX 4070",
    paying_users: int = 500,
    avg_tokens_per_user: int = 300_000,
) -> dict:
    """Grid 경제 시뮬레이션.

    Args:
        grid_users: Grid 참여자 수
        avg_gpu: 평균 GPU
        paying_users: 유료 사용자 수
        avg_tokens_per_user: 유료 사용자 월 평균 사용 토큰
    """
    # Grid 비용 (보상으로 나가는 토큰)
    gpu_earning = estimate_monthly_earnings(avg_gpu)
    total_grid_reward = gpu_earning["monthly_reward"] * grid_users
    total_grid_value = gpu_earning["monthly_value_krw"] * grid_users

    # 수익 (유료 사용자가 소비하는 토큰)
    total_consumption = paying_users * avg_tokens_per_user
    token_price = 29000 / 500000  # 원/토큰
    total_revenue = int(total_consumption * token_price)

    # Grid 보상 비율
    reward_ratio = total_grid_reward / max(total_consumption, 1)

    # 클라우드 대비 절약
    cloud_cost = grid_users * 16 * 30 * 150  # GPU시간 × 시간당 150원 (RunPod 환산)

    return {
        "grid_users": grid_users,
        "paying_users": paying_users,
        "total_consumption_tokens": total_consumption,
        "total_grid_reward_tokens": total_grid_reward,
        "reward_ratio": f"{reward_ratio*100:.1f}%",
        "monthly_revenue_krw": total_revenue,
        "monthly_grid_cost_krw": total_grid_value,
        "monthly_profit_krw": total_revenue - total_grid_value,
        "cloud_equivalent_cost_krw": cloud_cost,
        "savings_vs_cloud_krw": cloud_cost - total_grid_value,
        "sustainable": total_revenue > total_grid_value,
    }
