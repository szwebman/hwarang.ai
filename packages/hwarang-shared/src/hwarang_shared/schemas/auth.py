"""Authentication schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class APIKeyCreate(BaseModel):
    name: str
    owner: str | None = None
    rate_limit: int = 60
    permissions: dict = {"models": ["*"]}


class APIKeyInfo(BaseModel):
    id: str
    name: str
    owner: str | None
    key_prefix: str  # First 8 chars of the key for identification
    rate_limit: int
    is_active: bool
    created_at: datetime
    expires_at: datetime | None
