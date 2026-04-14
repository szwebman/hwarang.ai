"""Token bucket rate limiter."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    """Simple in-memory token bucket for rate limiting."""

    capacity: float
    refill_rate: float  # tokens per second
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.monotonic)

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if allowed."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    @property
    def retry_after(self) -> float:
        """Seconds until the next token is available."""
        if self.tokens >= 1:
            return 0.0
        return (1 - self.tokens) / self.refill_rate


class RateLimiter:
    """In-memory rate limiter using token bucket algorithm.

    For production, replace with Redis-backed implementation.
    """

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self._buckets: dict[str, TokenBucket] = defaultdict(
            lambda: TokenBucket(
                capacity=float(requests_per_minute),
                refill_rate=requests_per_minute / 60.0,
                tokens=float(requests_per_minute),
            )
        )

    def check(self, key: str) -> tuple[bool, float]:
        """Check if a request is allowed.

        Args:
            key: Rate limit key (e.g., API key or IP address).

        Returns:
            Tuple of (allowed, retry_after_seconds).
        """
        bucket = self._buckets[key]
        allowed = bucket.consume()
        return allowed, bucket.retry_after
