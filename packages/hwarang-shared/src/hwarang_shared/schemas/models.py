"""Model information schemas."""

from __future__ import annotations

import time

from pydantic import BaseModel, Field


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "hwarang"
    max_context_length: int = 4096
    capabilities: list[str] = Field(default_factory=lambda: ["chat", "completion"])


class ModelList(BaseModel):
    object: str = "list"
    data: list[ModelInfo]
