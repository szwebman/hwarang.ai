"""LLM provider abstraction."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hwarang_cli.providers.base import LLMProvider, LLMResponse

if TYPE_CHECKING:
    from hwarang_cli.config import CLIConfig


def create_provider(config: CLIConfig) -> LLMProvider:
    """Create an LLM provider based on config."""
    provider_name = config.default_provider.lower()

    if provider_name == "hwarang":
        from hwarang_cli.providers.hwarang import HwarangProvider
        return HwarangProvider(
            api_url=config.hwarang_api_url,
            default_model=config.default_model,
        )
    elif provider_name == "openai":
        from hwarang_cli.providers.openai import OpenAIProvider
        return OpenAIProvider(api_key=config.openai_api_key)
    elif provider_name == "anthropic":
        from hwarang_cli.providers.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=config.anthropic_api_key)
    else:
        raise ValueError(f"Unknown provider: {provider_name}")


__all__ = ["LLMProvider", "LLMResponse", "create_provider"]
