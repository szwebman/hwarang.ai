"""Health check endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from hwarang_shared.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request):
    """Health check endpoint."""
    model_manager = request.app.state.model_manager
    return HealthResponse(
        status="ok",
        version="0.1.0",
        models_loaded=model_manager.num_loaded,
    )


@router.get("/ready")
async def readiness_check(request: Request):
    """Readiness check - returns 200 only if at least one model is loaded."""
    model_manager = request.app.state.model_manager
    if model_manager.num_loaded == 0:
        return {"status": "not_ready", "reason": "no models loaded"}
    return {"status": "ready", "models_loaded": model_manager.num_loaded}
