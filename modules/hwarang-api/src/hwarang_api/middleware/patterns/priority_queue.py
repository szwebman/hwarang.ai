"""Priority Queue - 플랜별 우선순위 처리.

Business > Pro > Starter > Free 순서로 처리합니다.
서버가 바쁠 때 유료 사용자가 먼저 처리됩니다.
"""

from __future__ import annotations

import asyncio
import heapq
import time
import logging
from dataclasses import dataclass, field
from enum import IntEnum

logger = logging.getLogger(__name__)


class Priority(IntEnum):
    """낮은 숫자 = 높은 우선순위."""
    ENTERPRISE = 0
    BUSINESS = 1
    PRO = 2
    STARTER = 3
    FREE = 4

PLAN_PRIORITY = {
    "enterprise": Priority.ENTERPRISE,
    "business": Priority.BUSINESS,
    "pro": Priority.PRO,
    "starter": Priority.STARTER,
    "free": Priority.FREE,
}


@dataclass(order=True)
class PriorityRequest:
    priority: int
    timestamp: float = field(compare=True)
    request_id: str = field(compare=False)
    data: dict = field(compare=False)
    future: asyncio.Future = field(compare=False, repr=False)


class PriorityQueue:
    """우선순위 기반 요청 큐."""

    def __init__(self, max_size: int = 10_000):
        self._heap: list[PriorityRequest] = []
        self._max_size = max_size
        self._stats = {p.name: 0 for p in Priority}

    async def enqueue(self, request_id: str, plan: str, data: dict) -> asyncio.Future:
        """요청을 우선순위 큐에 추가."""
        if len(self._heap) >= self._max_size:
            raise Exception("큐가 가득 찼습니다. 잠시 후 다시 시도하세요.")

        priority = PLAN_PRIORITY.get(plan, Priority.FREE)
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        item = PriorityRequest(
            priority=priority,
            timestamp=time.time(),
            request_id=request_id,
            data=data,
            future=future,
        )
        heapq.heappush(self._heap, item)
        self._stats[Priority(priority).name] += 1
        return future

    async def dequeue(self) -> PriorityRequest | None:
        """가장 높은 우선순위 요청 꺼내기."""
        if not self._heap:
            return None
        return heapq.heappop(self._heap)

    @property
    def size(self) -> int:
        return len(self._heap)

    @property
    def stats(self) -> dict:
        return {**self._stats, "current_size": self.size}
