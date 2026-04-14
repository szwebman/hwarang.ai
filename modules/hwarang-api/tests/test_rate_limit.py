"""Tests for rate limiting."""

from hwarang_api.middleware.rate_limit import RateLimiter


class TestRateLimiter:
    def test_allows_within_limit(self):
        limiter = RateLimiter(requests_per_minute=60)
        allowed, retry_after = limiter.check("test-key")
        assert allowed is True
        assert retry_after == 0.0

    def test_blocks_over_limit(self):
        limiter = RateLimiter(requests_per_minute=2)
        limiter.check("test-key")
        limiter.check("test-key")
        allowed, retry_after = limiter.check("test-key")
        assert allowed is False
        assert retry_after > 0

    def test_separate_keys(self):
        limiter = RateLimiter(requests_per_minute=1)
        limiter.check("key-a")
        # Key B should still be allowed
        allowed, _ = limiter.check("key-b")
        assert allowed is True
