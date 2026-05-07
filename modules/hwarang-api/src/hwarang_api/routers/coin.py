"""HWARANG 코인 — 발행률 조회 API.

스마트 컨트랙트 자체는 변경 불가 (이미 배포된 mint 권한만 서버 보유).
본 라우터는 *오프체인 발행률 계산* 만 노출한다:

    GET /api/coin/emission-rate
        — 현재 supply/demand/halving factor 와 글로벌 multiplier
    POST /api/coin/preview-reward
        — 가상 작업 1건의 예상 보상 미리보기 (mint 안 함)

reward_client 가 이 값을 호출해 라운드 보상 지급량을 계산한다.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from hwarang_api.knowledge.coin_emission import (
    TASK_MULTIPLIER,
    compute_emission_rate,
    compute_reward,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/coin", tags=["Coin/Emission"])


# ────────────────────────────────────────────────────────────────────────
# 네트워크 상태 — 실측치 주입 지점.
# 운영에서는 grid 라우터의 _agents/_round_history 또는 별도 메트릭 서비스에서
# 갱신하고, set_network_state() 호출. 미설정 시 합리적 기본값.
# ────────────────────────────────────────────────────────────────────────

_network_state: dict[str, float] = {
    "gpu_utilization": 0.50,        # 평균 GPU 사용률
    "demand_change_rate": 0.0,      # 전주 대비 수요 변화율
    "cumulative_minted_ratio": 0.0, # 누적 발행량 / 총 상한
}


def set_network_state(
    gpu_utilization: Optional[float] = None,
    demand_change_rate: Optional[float] = None,
    cumulative_minted_ratio: Optional[float] = None,
) -> dict:
    """다른 모듈/스케줄러가 주기적으로 호출 (e.g. grid 모니터)."""
    if gpu_utilization is not None:
        _network_state["gpu_utilization"] = float(gpu_utilization)
    if demand_change_rate is not None:
        _network_state["demand_change_rate"] = float(demand_change_rate)
    if cumulative_minted_ratio is not None:
        _network_state["cumulative_minted_ratio"] = float(cumulative_minted_ratio)
    return dict(_network_state)


def get_network_state() -> dict:
    return dict(_network_state)


# ────────────────────────────────────────────────────────────────────────
# 엔드포인트
# ────────────────────────────────────────────────────────────────────────

@router.get("/emission-rate")
async def emission_rate():
    """현재 발행률 조회 — read-only.

    스마트 컨트랙트 발행 로직은 변경 불가. 본 응답은 reward_client 가
    *오프체인 보상 산정* 에 사용하는 계수.
    """
    return compute_emission_rate(**_network_state)


@router.get("/network-state")
async def network_state():
    """현재 네트워크 상태 (계산 입력값) 조회."""
    return _network_state


class NetworkStatePatch(BaseModel):
    gpu_utilization: Optional[float] = Field(None, ge=0, le=1)
    demand_change_rate: Optional[float] = Field(None, ge=-1, le=10)
    cumulative_minted_ratio: Optional[float] = Field(None, ge=0, le=1)


@router.post("/network-state")
async def update_network_state(payload: NetworkStatePatch):
    """관리자/스케줄러가 네트워크 상태 갱신.

    실제 운영에서는 admin 인증 미들웨어로 보호 권장.
    """
    new_state = set_network_state(
        gpu_utilization=payload.gpu_utilization,
        demand_change_rate=payload.demand_change_rate,
        cumulative_minted_ratio=payload.cumulative_minted_ratio,
    )
    return {"status": "updated", "state": new_state}


class PreviewRewardRequest(BaseModel):
    base_reward: float = Field(100.0, gt=0)
    task_type: str = "inference"
    streak_days: int = Field(0, ge=0)
    # 선택 — 미지정 시 _network_state 사용
    gpu_utilization: Optional[float] = Field(None, ge=0, le=1)
    demand_change_rate: Optional[float] = None
    cumulative_minted_ratio: Optional[float] = Field(None, ge=0, le=1)


@router.post("/preview-reward")
async def preview_reward(req: PreviewRewardRequest):
    """가상 작업 1건의 보상 미리보기. 실제 mint 안 함."""
    breakdown = compute_reward(
        base_reward=req.base_reward,
        gpu_utilization=req.gpu_utilization
            if req.gpu_utilization is not None
            else _network_state["gpu_utilization"],
        demand_change_rate=req.demand_change_rate
            if req.demand_change_rate is not None
            else _network_state["demand_change_rate"],
        cumulative_minted_ratio=req.cumulative_minted_ratio
            if req.cumulative_minted_ratio is not None
            else _network_state["cumulative_minted_ratio"],
        task_type=req.task_type,
        streak_days=req.streak_days,
    )
    return breakdown.to_dict()


@router.get("/task-multipliers")
async def task_multipliers():
    """작업 유형별 배율 목록."""
    return {"multipliers": dict(TASK_MULTIPLIER)}
