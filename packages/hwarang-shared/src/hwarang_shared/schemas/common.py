"""Common schemas used across modules."""

from __future__ import annotations

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ErrorDetail(BaseModel):
    message: str
    type: str
    code: str | None = None
    param: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    models_loaded: int = 0
