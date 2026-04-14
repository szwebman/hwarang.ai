"""Abstract inference protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from hwarang_shared.schemas.chat import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
)


class InferenceProtocol(ABC):
    """Protocol that any inference backend must implement."""

    @abstractmethod
    async def generate(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Generate a complete response."""
        ...

    @abstractmethod
    async def generate_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[ChatCompletionChunk]:
        """Generate a streaming response."""
        ...

    @abstractmethod
    async def is_ready(self) -> bool:
        """Check if the engine is ready to serve."""
        ...
