"""CLI configuration management."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import tomli
import tomli_w


@dataclass
class CLIConfig:
    """CLI configuration loaded from ~/.hwarang/config.toml."""

    # Provider settings
    default_provider: str = "hwarang"
    default_model: str = "hwarang-small"

    # API endpoints
    hwarang_api_url: str = "http://localhost:8000"
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Generation defaults
    temperature: float = 0.7
    max_tokens: int = 2048

    # UI settings
    theme: str = "default"
    show_token_count: bool = False

    # History
    history_enabled: bool = True
    history_db_path: str = ""

    @classmethod
    def config_dir(cls) -> Path:
        return Path.home() / ".hwarang"

    @classmethod
    def config_path(cls) -> Path:
        return cls.config_dir() / "config.toml"

    @classmethod
    def load(cls) -> CLIConfig:
        """Load config from file, falling back to defaults."""
        config = cls()

        # Override from file
        path = cls.config_path()
        if path.exists():
            with open(path, "rb") as f:
                data = tomli.load(f)
            for key, value in data.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        # Override from environment
        if env_key := os.environ.get("OPENAI_API_KEY"):
            config.openai_api_key = env_key
        if env_key := os.environ.get("ANTHROPIC_API_KEY"):
            config.anthropic_api_key = env_key
        if env_url := os.environ.get("HWARANG_API_URL"):
            config.hwarang_api_url = env_url

        # Set defaults for computed paths
        if not config.history_db_path:
            config.history_db_path = str(cls.config_dir() / "history.db")

        return config

    def save(self) -> None:
        """Save config to file."""
        self.config_dir().mkdir(parents=True, exist_ok=True)
        from dataclasses import asdict

        with open(self.config_path(), "wb") as f:
            tomli_w.dump(asdict(self), f)
