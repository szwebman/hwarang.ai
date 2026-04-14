"""Middleware Chain - 요청 파이프라인.

모든 요청이 이 체인을 통과합니다:
  요청 → 인증 → 플랜 확인 → 토큰 한도 → 우선순위 → 안전 필터
  → 캐시 확인 → [추론] → 토큰 차감 → 로깅 → 응답

각 미들웨어는 독립적으로 활성화/비활성화 가능.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Any

logger = logging.getLogger(__name__)


class MiddlewareContext:
    """요청 컨텍스트 (미들웨어 간 데이터 공유)."""

    def __init__(self, request_id: str, raw_request: dict):
        self.request_id = request_id
        self.raw_request = raw_request
        self.user_id: str | None = None
        self.plan: str | None = None
        self.api_key: str | None = None
        self.priority: int = 4  # Free
        self.tokens_estimated: int = 0
        self.tokens_used: int = 0
        self.cached: bool = False
        self.blocked: bool = False
        self.block_reason: str = ""
        self.response: dict | None = None
        self.start_time: float = time.time()
        self.metadata: dict = {}


class Middleware:
    """미들웨어 베이스 클래스."""

    async def process_request(self, ctx: MiddlewareContext) -> bool:
        """요청 처리. False 반환하면 체인 중단."""
        return True

    async def process_response(self, ctx: MiddlewareContext):
        """응답 후처리."""
        pass


class MiddlewareChain:
    """미들웨어 체인 실행기."""

    def __init__(self):
        self._middlewares: list[tuple[str, Middleware]] = []

    def add(self, name: str, middleware: Middleware):
        self._middlewares.append((name, middleware))
        logger.info(f"미들웨어 등록: {name}")

    async def execute(self, ctx: MiddlewareContext) -> MiddlewareContext:
        """전체 체인 실행."""
        # 요청 처리 (순서대로)
        for name, mw in self._middlewares:
            try:
                should_continue = await mw.process_request(ctx)
                if not should_continue:
                    logger.debug(f"미들웨어 {name}에서 중단")
                    break
            except Exception as e:
                logger.error(f"미들웨어 {name} 오류: {e}")
                ctx.blocked = True
                ctx.block_reason = f"Internal error in {name}"
                break

        # 응답 후처리 (역순)
        for name, mw in reversed(self._middlewares):
            try:
                await mw.process_response(ctx)
            except Exception as e:
                logger.error(f"미들웨어 {name} 후처리 오류: {e}")

        return ctx


# ============================================================
# 기본 제공 미들웨어
# ============================================================

class AuthMiddleware(Middleware):
    """인증 미들웨어."""
    async def process_request(self, ctx: MiddlewareContext) -> bool:
        api_key = ctx.raw_request.get("api_key") or ctx.metadata.get("api_key")
        if not api_key:
            ctx.blocked = True
            ctx.block_reason = "API 키가 필요합니다"
            return False
        ctx.api_key = api_key
        # TODO: DB에서 API 키 검증
        ctx.user_id = "user_from_key"
        ctx.plan = "pro"
        return True


class TokenLimitMiddleware(Middleware):
    """토큰 한도 미들웨어."""
    async def process_request(self, ctx: MiddlewareContext) -> bool:
        # TODO: DB에서 잔액 확인
        # if balance < estimated_tokens: block
        return True

    async def process_response(self, ctx: MiddlewareContext):
        # TODO: 사용된 토큰 차감
        pass


class SafetyMiddleware(Middleware):
    """안전 필터 미들웨어."""
    async def process_request(self, ctx: MiddlewareContext) -> bool:
        from hwarang_core.patterns.safety import SafetyGuard
        guard = SafetyGuard()
        messages = ctx.raw_request.get("messages", [])
        last_msg = messages[-1]["content"] if messages else ""
        result = guard.check_input(last_msg)
        if result.level.value == "blocked":
            ctx.blocked = True
            ctx.block_reason = result.reason
            return False
        return True


class CacheMiddleware(Middleware):
    """캐시 미들웨어."""
    def __init__(self, cache):
        self.cache = cache

    async def process_request(self, ctx: MiddlewareContext) -> bool:
        req = ctx.raw_request
        cached = self.cache.get(
            req.get("model", ""), req.get("messages", []), req.get("temperature", 0.7)
        )
        if cached:
            ctx.response = cached
            ctx.cached = True
            return False  # 캐시 히트 → 추론 건너뜀
        return True

    async def process_response(self, ctx: MiddlewareContext):
        if not ctx.cached and ctx.response:
            req = ctx.raw_request
            self.cache.set(
                req.get("model", ""), req.get("messages", []),
                req.get("temperature", 0.7), ctx.response, ctx.tokens_used
            )


class LoggingMiddleware(Middleware):
    """요청/응답 로깅."""
    async def process_request(self, ctx: MiddlewareContext) -> bool:
        logger.info(f"[{ctx.request_id[:8]}] 요청: user={ctx.user_id} plan={ctx.plan}")
        return True

    async def process_response(self, ctx: MiddlewareContext):
        elapsed = (time.time() - ctx.start_time) * 1000
        logger.info(
            f"[{ctx.request_id[:8]}] 응답: {elapsed:.0f}ms "
            f"tokens={ctx.tokens_used} cached={ctx.cached}"
        )
