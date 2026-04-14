"""API server configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://hwarang:password@localhost:5432/hwarang"
    redis_url: str = "redis://localhost:6379"

    # Model
    model_path: str = "./checkpoints/hwarang-small"
    default_model: str = "hwarang-small"
    device: str = "auto"
    dtype: str = "bfloat16"

    # Distributed mode
    distributed: bool = False  # Set True to enable multi-server mode
    # When True: API server does NOT load models. It delegates to Worker nodes via Redis.
    # Workers connect to the same Redis and pull requests from the queue.

    # Auth
    api_secret_key: str = "change-me-in-production"
    require_auth: bool = False  # Set True in production

    # Rate limiting
    default_rate_limit: int = 60  # requests per minute
    default_token_limit: int = 100000  # tokens per minute

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = {"env_prefix": "HWARANG_", "env_file": ".env"}
