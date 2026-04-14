"""API key authentication middleware."""

from __future__ import annotations

import hashlib
import logging

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_api_key(
    request: Request,
    api_key: str | None = Security(api_key_header),
) -> str | None:
    """Verify the API key from the Authorization header.

    Expects: 'Bearer hk-...'
    Returns the API key string if valid, None if auth is disabled.
    """
    settings = request.app.state.settings

    if not settings.require_auth:
        return None

    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    # Strip 'Bearer ' prefix
    if api_key.startswith("Bearer "):
        api_key = api_key[7:]

    # Validate key format
    if not api_key.startswith("hk-"):
        raise HTTPException(status_code=401, detail="Invalid API key format")

    # TODO: Validate against database when DB is set up
    # For now, accept any well-formed key
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    logger.debug(f"API key validated: {api_key[:8]}...")

    return api_key
