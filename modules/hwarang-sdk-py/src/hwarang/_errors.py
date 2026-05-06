"""화랑 SDK 에러 클래스."""

from __future__ import annotations

from typing import Optional


class HwarangError(Exception):
    """모든 SDK 에러의 기본 클래스.

    Attributes:
        message: 사람이 읽는 에러 메시지.
        status: HTTP 상태 코드 (네트워크 호출 실패 시).
        code: 화랑 API 가 반환한 에러 코드 (예: ``rate_limited``).
    """

    def __init__(
        self,
        message: str,
        status: Optional[int] = None,
        code: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code

    def __repr__(self) -> str:
        parts = [f"message={self.message!r}"]
        if self.status is not None:
            parts.append(f"status={self.status}")
        if self.code is not None:
            parts.append(f"code={self.code!r}")
        return f"HwarangError({', '.join(parts)})"


class HwarangAuthError(HwarangError):
    """API 키 누락/만료/거부."""


class HwarangRateLimitError(HwarangError):
    """요청 제한 초과 (HTTP 429)."""


class HwarangTimeoutError(HwarangError):
    """요청 타임아웃."""
