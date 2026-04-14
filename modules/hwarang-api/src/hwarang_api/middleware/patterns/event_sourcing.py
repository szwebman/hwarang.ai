"""Event Sourcing - 모든 이벤트를 기록.

토큰 거래, API 호출, 모델 배포, 에러 등
모든 이벤트를 시간순으로 기록합니다.
감사(audit), 디버깅, 분석에 활용.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    # 토큰
    TOKEN_CHARGED = "token.charged"
    TOKEN_USED = "token.used"
    TOKEN_PURCHASED = "token.purchased"
    TOKEN_GRID_REWARD = "token.grid_reward"

    # API
    API_REQUEST = "api.request"
    API_RESPONSE = "api.response"
    API_ERROR = "api.error"

    # 인증
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_KEY_CREATED = "auth.key_created"

    # 모델
    MODEL_DEPLOYED = "model.deployed"
    MODEL_ROLLBACK = "model.rollback"

    # 서버
    WORKER_REGISTERED = "worker.registered"
    WORKER_DIED = "worker.died"

    # 플랜
    PLAN_UPGRADED = "plan.upgraded"
    PLAN_DOWNGRADED = "plan.downgraded"


@dataclass
class Event:
    id: str
    type: EventType
    timestamp: float
    user_id: str | None
    data: dict
    metadata: dict = None


class EventStore:
    """이벤트 저장소."""

    def __init__(self, max_memory: int = 100_000):
        self._events: list[Event] = []
        self._max_memory = max_memory
        self._redis = None

    async def connect_redis(self, redis_url: str):
        import redis.asyncio as aioredis
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def emit(self, event_type: EventType, user_id: str = None, data: dict = None):
        """이벤트 발행."""
        event = Event(
            id=str(uuid.uuid4()),
            type=event_type,
            timestamp=time.time(),
            user_id=user_id,
            data=data or {},
        )

        # 메모리 저장
        self._events.append(event)
        if len(self._events) > self._max_memory:
            self._events.pop(0)

        # Redis 저장 (영구)
        if self._redis:
            await self._redis.rpush(
                f"hwarang:events:{event_type.value}",
                json.dumps(asdict(event)),
            )
            await self._redis.ltrim(f"hwarang:events:{event_type.value}", -10000, -1)

        logger.debug(f"Event: {event_type.value} user={user_id} data={data}")

    async def query(
        self, event_type: EventType = None, user_id: str = None,
        since: float = 0, limit: int = 100,
    ) -> list[Event]:
        """이벤트 조회."""
        results = self._events
        if event_type:
            results = [e for e in results if e.type == event_type]
        if user_id:
            results = [e for e in results if e.user_id == user_id]
        if since:
            results = [e for e in results if e.timestamp >= since]
        return results[-limit:]


# 싱글턴
_store: EventStore | None = None

def get_event_store() -> EventStore:
    global _store
    if _store is None:
        _store = EventStore()
    return _store
