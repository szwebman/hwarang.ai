"""Models endpoint - list available models."""

from __future__ import annotations

from fastapi import APIRouter, Request

from hwarang_shared.schemas.models import ModelList

router = APIRouter()


@router.get("/models", response_model=ModelList)
async def list_models(request: Request):
    """List all loaded models."""
    model_manager = request.app.state.model_manager
    models = model_manager.list_models()
    return ModelList(data=models)
