"""HWARANG 코인 — 적응형 발행률 (Adaptive Emission) 계산.

특허 (HWARANG_coin_patent_draft_KR.md) 의 발행 공식을 서버에서 *계산만* 한다.

  보상 = baseReward × supplyFactor × demandFactor × halvingFactor
              × taskMultiplier × streakBonus

주의 — 스마트 컨트랙트는 절대 변경하지 않는다:
  · 본 모듈은 발행률을 *조회/추정* 하는 read-only 계산기.
  · 실제 mint 는 `coin.mint_for_user()` 가 수행 (이미 배포된 컨트랙트).
  · 에이전트는 작업 + 증명만, 발행은 서버 (지정된 minter 키) 만.

사용:
    from hwarang_api.knowledge.coin_emission import (
        compute_emission_rate, compute_reward,
    )
    info = compute_emission_rate(
        gpu_utilization=0.85,
        demand_change_rate=0.10,
        cumulative_minted_ratio=0.12,
    )
    reward = compute_reward(
        base_reward=100.0,
        gpu_utilization=0.85,
        demand_change_rate=0.10,
        cumulative_minted_ratio=0.12,
        task_type="sft_train",
        streak_days=7,
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ────────────────────────────────────────────────────────────────────────
# 작업 유형별 배율 (특허 (e) taskMultiplier)
# ────────────────────────────────────────────────────────────────────────

TaskType = Literal[
    "inference",       # 추론 서빙
    "sft_train",       # SFT 학습
    "dpo_train",       # DPO 학습
    "feedback_verify", # 피드백 검증
    "data_gen",        # 데이터 생성
    "hfl_round",       # HFL 라운드 기여 (학습 카테고리로 분류)
]

TASK_MULTIPLIER: dict[str, float] = {
    "inference": 1.0,
    "sft_train": 2.0,
    "dpo_train": 2.5,
    "feedback_verify": 0.5,
    "data_gen": 1.5,
    "hfl_round": 2.0,  # HFL 라운드 = SFT 학습으로 분류
}


# ────────────────────────────────────────────────────────────────────────
# (b) supplyFactor — GPU 가용률에 따른 보상 자동 조절
#   가용률 = (1 - 평균 사용률). 즉 가용률 90%↑ = 자원 남음 → 0.3 으로 축소.
#   (특허 line 82~88 정의 그대로)
# ────────────────────────────────────────────────────────────────────────

def supply_factor(gpu_utilization: float) -> float:
    """gpu_utilization: 네트워크 평균 사용률 (0.0 ~ 1.0).

    특허 정의: GPU 가용률 (= 미사용률 = 1 - utilization) 에 따른 보상.
    """
    util = max(0.0, min(1.0, gpu_utilization))
    availability = 1.0 - util  # 가용률

    if availability > 0.90:
        return 3.0
    if availability >= 0.80:
        # 0.80~0.90 선형 보간 1.5 → 3.0
        t = (availability - 0.80) / 0.10
        return 1.5 + t * (3.0 - 1.5)
    if availability >= 0.40:
        return 1.0
    if availability >= 0.20:
        # 0.20~0.40 선형 보간 0.5 → 1.0
        t = (availability - 0.20) / 0.20
        return 0.5 + t * (1.0 - 0.5)
    return 0.3


# ────────────────────────────────────────────────────────────────────────
# (c) demandFactor — AI 서비스 이용량 변화율
#   demandFactor = clamp(0.5, 1.5, 1.0 + 변화율 × 0.5)
# ────────────────────────────────────────────────────────────────────────

def demand_factor(demand_change_rate: float) -> float:
    """demand_change_rate: 전주 대비 변화율 (예 +0.20 = +20%)."""
    raw = 1.0 + demand_change_rate * 0.5
    return max(0.5, min(1.5, raw))


# ────────────────────────────────────────────────────────────────────────
# (d) halvingFactor — 누적 발행량 마일스톤 기반
# ────────────────────────────────────────────────────────────────────────

def halving_factor(cumulative_minted_ratio: float) -> float:
    """cumulative_minted_ratio: 누적 발행량 / 총 상한 (0.0~1.0)."""
    r = max(0.0, cumulative_minted_ratio)
    if r >= 0.40:
        return 0.0625
    if r >= 0.30:
        return 0.125
    if r >= 0.20:
        return 0.25
    if r >= 0.10:
        return 0.5
    return 1.0


# ────────────────────────────────────────────────────────────────────────
# (f) streakBonus — 연속 참여 보너스 (최대 +50%)
# ────────────────────────────────────────────────────────────────────────

def streak_bonus(streak_days: int, max_bonus: float = 0.5) -> float:
    """연속 참여일에 비례. 30일 이상 → 최대 보너스."""
    if streak_days <= 0:
        return 1.0
    saturation = min(1.0, streak_days / 30.0)
    return 1.0 + max_bonus * saturation


# ────────────────────────────────────────────────────────────────────────
# 통합 계산
# ────────────────────────────────────────────────────────────────────────

@dataclass
class EmissionBreakdown:
    base_reward: float
    supply_factor: float
    demand_factor: float
    halving_factor: float
    task_multiplier: float
    streak_bonus: float
    final_reward: float

    def to_dict(self) -> dict:
        return {
            "base_reward": self.base_reward,
            "supply_factor": round(self.supply_factor, 4),
            "demand_factor": round(self.demand_factor, 4),
            "halving_factor": round(self.halving_factor, 6),
            "task_multiplier": round(self.task_multiplier, 4),
            "streak_bonus": round(self.streak_bonus, 4),
            "final_reward": round(self.final_reward, 6),
        }


def compute_reward(
    base_reward: float,
    gpu_utilization: float = 0.5,
    demand_change_rate: float = 0.0,
    cumulative_minted_ratio: float = 0.0,
    task_type: str = "inference",
    streak_days: int = 0,
) -> EmissionBreakdown:
    """공식 그대로 계산:
        보상 = baseReward × supplyFactor × demandFactor × halvingFactor
                  × taskMultiplier × streakBonus
    """
    sf = supply_factor(gpu_utilization)
    df = demand_factor(demand_change_rate)
    hf = halving_factor(cumulative_minted_ratio)
    tm = TASK_MULTIPLIER.get(task_type, 1.0)
    sb = streak_bonus(streak_days)

    final = base_reward * sf * df * hf * tm * sb
    return EmissionBreakdown(
        base_reward=base_reward,
        supply_factor=sf,
        demand_factor=df,
        halving_factor=hf,
        task_multiplier=tm,
        streak_bonus=sb,
        final_reward=final,
    )


def compute_emission_rate(
    gpu_utilization: float = 0.5,
    demand_change_rate: float = 0.0,
    cumulative_minted_ratio: float = 0.0,
) -> dict:
    """현재 *전역* 발행률 (task/streak 무관 부분만) 반환.

    GET /api/coin/emission-rate 가 그대로 직렬화.
    """
    sf = supply_factor(gpu_utilization)
    df = demand_factor(demand_change_rate)
    hf = halving_factor(cumulative_minted_ratio)
    return {
        "supply_factor": round(sf, 4),
        "demand_factor": round(df, 4),
        "halving_factor": round(hf, 6),
        "global_multiplier": round(sf * df * hf, 6),
        "inputs": {
            "gpu_utilization": gpu_utilization,
            "demand_change_rate": demand_change_rate,
            "cumulative_minted_ratio": cumulative_minted_ratio,
        },
        "task_multipliers": dict(TASK_MULTIPLIER),
        "note": "스마트 컨트랙트의 mint 권한은 서버만 보유. 본 값은 read-only 계산.",
    }


__all__ = [
    "TASK_MULTIPLIER",
    "supply_factor",
    "demand_factor",
    "halving_factor",
    "streak_bonus",
    "compute_reward",
    "compute_emission_rate",
    "EmissionBreakdown",
]
