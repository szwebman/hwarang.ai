"""Response Cache - 같은 질문에 GPU 안 쓰고 즉시 응답.

같은 (또는 매우 유사한) 질문이 반복되면 캐시된 답변을 반환합니다.
GPU 자원을 아끼고 응답 속도를 <10ms로 단축.

방식:
1. Exact Match: 해시 기반 정확 일치
2. Semantic Match: 임베딩 유사도 기반 (선택)

설정:
  - TTL: 캐시 유효 시간 (기본 1시간)
  - 최대 크기: 10,000개 (LRU 방식)
  - temperature > 0이면 캐시 안 함 (매번 다른 결과)
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    response: dict
    created_at: float
    hit_count: int = 0
    tokens_saved: int = 0


class ResponseCache:
    """LRU 기반 응답 캐시."""

    def __init__(self, max_size: int = 10_000, ttl_seconds: float = 3600):
        self.max_size = max_size
        self.ttl = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._stats = {"hits": 0, "misses": 0, "tokens_saved": 0}

    def _make_key(self, model: str, messages: list[dict], temperature: float) -> str | None:
        """캐시 키 생성. temperature > 0이면 None (캐시 안 함)."""
        if temperature > 0:
            return None
        content = json.dumps({"model": model, "messages": messages}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    def get(self, model: str, messages: list[dict], temperature: float) -> dict | None:
        """캐시에서 응답 조회."""
        key = self._make_key(model, messages, temperature)
        if key is None:
            return None

        entry = self._cache.get(key)
        if entry is None:
            self._stats["misses"] += 1
            return None

        if time.time() - entry.created_at > self.ttl:
            del self._cache[key]
            self._stats["misses"] += 1
            return None

        entry.hit_count += 1
        self._cache.move_to_end(key)
        self._stats["hits"] += 1
        self._stats["tokens_saved"] += entry.tokens_saved
        return entry.response

    def set(self, model: str, messages: list[dict], temperature: float,
            response: dict, tokens_used: int = 0):
        """응답을 캐시에 저장."""
        key = self._make_key(model, messages, temperature)
        if key is None:
            return

        if len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)

        self._cache[key] = CacheEntry(
            response=response, created_at=time.time(), tokens_saved=tokens_used,
        )

    def clear(self):
        self._cache.clear()

    @property
    def stats(self) -> dict:
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / max(total, 1) * 100
        return {
            **self._stats,
            "size": len(self._cache),
            "hit_rate": f"{hit_rate:.1f}%",
        }
