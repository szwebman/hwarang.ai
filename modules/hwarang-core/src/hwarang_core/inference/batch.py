"""Continuous batching scheduler for inference.

Groups incoming requests into batches for efficient GPU utilization.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from hwarang_shared.schemas.chat import ChatCompletionRequest, ChatCompletionResponse

logger = logging.getLogger(__name__)


@dataclass
class PendingRequest:
    """A request waiting to be batched."""

    request: ChatCompletionRequest
    future: asyncio.Future
    arrived_at: float = field(default_factory=time.monotonic)


class BatchScheduler:
    """Continuous batching scheduler.

    Collects incoming requests and dispatches them in batches
    for more efficient GPU utilization.
    """

    def __init__(
        self,
        engine,
        max_batch_size: int = 8,
        max_wait_ms: float = 50.0,
    ):
        self.engine = engine
        self.max_batch_size = max_batch_size
        self.max_wait_ms = max_wait_ms
        self._queue: asyncio.Queue[PendingRequest] = asyncio.Queue()
        self._running = False

    async def submit(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Submit a request for batched processing."""
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        pending = PendingRequest(request=request, future=future)
        await self._queue.put(pending)
        return await future

    async def start(self) -> None:
        """Start the batch processing loop."""
        self._running = True
        logger.info(f"BatchScheduler started (max_batch={self.max_batch_size}, "
                     f"max_wait={self.max_wait_ms}ms)")

        while self._running:
            batch = await self._collect_batch()
            if batch:
                await self._process_batch(batch)

    async def stop(self) -> None:
        """Stop the batch processing loop."""
        self._running = False

    async def _collect_batch(self) -> list[PendingRequest]:
        """Collect requests into a batch."""
        batch: list[PendingRequest] = []

        # Wait for at least one request
        try:
            first = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            batch.append(first)
        except asyncio.TimeoutError:
            return []

        # Collect more requests up to batch size or timeout
        deadline = time.monotonic() + self.max_wait_ms / 1000
        while len(batch) < self.max_batch_size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=remaining)
                batch.append(item)
            except asyncio.TimeoutError:
                break

        return batch

    async def _process_batch(self, batch: list[PendingRequest]) -> None:
        """Process a batch of requests."""
        logger.debug(f"Processing batch of {len(batch)} requests")

        # For now, process each request individually
        # A more advanced implementation would batch the forward passes
        for pending in batch:
            try:
                response = await self.engine.generate(pending.request)
                pending.future.set_result(response)
            except Exception as e:
                pending.future.set_exception(e)
