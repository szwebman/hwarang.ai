"""Active Inference 엔드포인트 (Phase 9.η).

Free Energy Principle 기반 예측/행동/감시 API.

엔드포인트
----------
* ``POST /api/active-inference/predict``        — 다음 관찰 예측
* ``POST /api/active-inference/record-actual``  — 실제 관찰 기록 + error 산출
* ``POST /api/active-inference/select-action``  — 후보 중 expected free energy 최저 선택
* ``GET  /api/active-inference/free-energy``    — 현재 자유에너지 상태
* ``GET  /api/active-inference/recent-surprise``— 최근 surprise 평균

상태는 process-local 싱글턴(``_state``)으로 보관한다. 영속화 TODO: Prisma.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from hwarang_api.cognitive.active_inference import (
    FreeEnergyMonitor,
    GenerativeModel,
    PolicySelector,
    PredictionErrorTracker,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/active-inference", tags=["ActiveInference"])


# ────────────────────────────────────────────────────────────
# Process-local singletons
# TODO: 영속화 — Prisma 모델로 마이그레이션
# ────────────────────────────────────────────────────────────
class _ActiveInferenceState:
    def __init__(self) -> None:
        self.generative = GenerativeModel()
        self.error_tracker = PredictionErrorTracker()
        self.monitor = FreeEnergyMonitor(error_tracker=self.error_tracker)
        self.policy = PolicySelector(generative_model=self.generative)


_state = _ActiveInferenceState()


# ────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────
class PredictPayload(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)


class RecordActualPayload(BaseModel):
    prediction_id: str
    actual: str


class SelectActionPayload(BaseModel):
    situation: dict[str, Any] = Field(default_factory=dict)
    candidate_actions: list[str]
    goal: str


# ────────────────────────────────────────────────────────────
# 1. predict
# ────────────────────────────────────────────────────────────
@router.post("/predict")
async def predict(payload: PredictPayload) -> dict[str, Any]:
    """현재 컨텍스트 다음 관찰을 LLM 으로 예측."""
    pred = await _state.generative.predict_next_observation(payload.context)
    return {"prediction": pred.to_dict()}


# ────────────────────────────────────────────────────────────
# 2. record-actual
# ────────────────────────────────────────────────────────────
@router.post("/record-actual")
async def record_actual(payload: RecordActualPayload) -> dict[str, Any]:
    """예측 ID 에 실제 관찰을 매핑하고 LLM judge 로 error 산출."""
    pred = _state.generative.get(payload.prediction_id)
    if pred is None:
        raise HTTPException(
            status_code=404,
            detail=f"prediction_id 를 찾을 수 없음: {payload.prediction_id}",
        )
    _state.error_tracker.record_actual(payload.prediction_id, payload.actual)
    metrics = await _state.error_tracker.compute_error(pred, payload.actual)
    return {
        "prediction_id": payload.prediction_id,
        "metrics": metrics.to_dict(),
        "surprise_threshold_breached": _state.error_tracker.surprise_threshold_breached(),
    }


# ────────────────────────────────────────────────────────────
# 3. select-action
# ────────────────────────────────────────────────────────────
@router.post("/select-action")
async def select_action(payload: SelectActionPayload) -> dict[str, Any]:
    """후보 행동 중 expected free energy 최저 선택."""
    if not payload.candidate_actions:
        raise HTTPException(
            status_code=400, detail="candidate_actions 는 비어 있을 수 없다."
        )
    choice = await _state.policy.select_action(
        situation=payload.situation,
        candidate_actions=payload.candidate_actions,
        goal=payload.goal,
    )
    return {"choice": choice.to_dict()}


# ────────────────────────────────────────────────────────────
# 4. free-energy
# ────────────────────────────────────────────────────────────
@router.get("/free-energy")
async def free_energy() -> dict[str, Any]:
    """현재 자유에너지 metric + 권고 행동 모드."""
    fe = await _state.monitor.current_free_energy()
    fe["should_act"] = await _state.monitor.should_act_to_reduce()
    fe["recommended_action_type"] = await _state.monitor.recommended_action_type()
    return fe


# ────────────────────────────────────────────────────────────
# 5. recent-surprise
# ────────────────────────────────────────────────────────────
@router.get("/recent-surprise")
async def recent_surprise(window: int = 20) -> dict[str, Any]:
    """최근 N 개 surprise 평균 + 임계 초과 여부."""
    if window < 1:
        raise HTTPException(status_code=400, detail="window 는 1 이상이어야 한다.")
    avg = _state.error_tracker.aggregate_recent_surprise(window=window)
    return {
        "window": window,
        "mean_surprise": round(avg, 4),
        "threshold": _state.error_tracker.SURPRISE_THRESHOLD,
        "breached": avg > _state.error_tracker.SURPRISE_THRESHOLD,
        "history_size": len(_state.error_tracker.history_snapshot()),
    }


__all__ = ["router"]
