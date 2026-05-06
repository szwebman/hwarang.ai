"""화랑 AI 공식 Python SDK.

OpenAI Chat Completions 100% 호환 + ``@hwarang`` 확장 (HP v1.0).

빠른 시작::

    from hwarang import Hwarang

    hwarang = Hwarang(api_key="hk-...")

    # OpenAI 스타일
    r = hwarang.chat.completions.create(
        messages=[{"role": "user", "content": "안녕"}],
    )
    print(r.text)

    # HP 단순 엔트리 (DSL only)
    r = hwarang.do(
        intent="add",
        scope="src/api/",
        input="POST /api/orders 라우터",
        workflow=["plan", "code", "test"],
    )
    print(r.get("summary"))

    # Markup 자동 파싱
    r = hwarang.chat.completions.create(
        messages=[{"role": "user", "content": "react 18.3 으로 업그레이드"}],
        hwarang={"format": "markup", "include": ["plan", "diff"]},
    )
    if r.markup:
        for step in r.markup.plan:
            print(step["title"], step["status"])
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ._client import AsyncHwarangClient, HwarangClient
from ._dsl import build_do_request, do_to_chat_extension
from ._errors import (
    HwarangAuthError,
    HwarangError,
    HwarangRateLimitError,
    HwarangTimeoutError,
)
from ._markup import has_markup, parse_markup
from ._types import (
    ChatMessage,
    ChatResponse,
    DoRequest,
    DoResponse,
    HwarangExtension,
    MarkupSection,
    ToolCall,
    ToolDefinition,
)

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "Hwarang",
    "AsyncHwarang",
    "HwarangClient",
    "AsyncHwarangClient",
    "HwarangError",
    "HwarangAuthError",
    "HwarangRateLimitError",
    "HwarangTimeoutError",
    "MarkupSection",
    "HwarangExtension",
    "ChatResponse",
    "ChatMessage",
    "ToolCall",
    "ToolDefinition",
    "DoRequest",
    "DoResponse",
    "parse_markup",
    "has_markup",
    "build_do_request",
    "do_to_chat_extension",
]


# ─────────────────────────────────────────────────────────
# 메인 클래스 (sync)
# ─────────────────────────────────────────────────────────


class _CompletionsNamespace:
    """``hwarang.chat.completions`` — OpenAI 호환 진입점."""

    def __init__(self, client: HwarangClient) -> None:
        self._client = client

    def create(
        self,
        messages: List[ChatMessage],
        *,
        model: Optional[str] = None,
        tools: Optional[List[ToolDefinition]] = None,
        tool_choice: Any = "auto",
        temperature: Optional[float] = None,
        max_tokens: int = 16384,
        stream: bool = False,
        hwarang: Optional[HwarangExtension] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> ChatResponse:
        return self._client.chat_completion(
            messages=messages,
            model=model,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            hwarang=hwarang,
            extra=extra,
        )


class _ChatNamespace:
    def __init__(self, client: HwarangClient) -> None:
        self.completions = _CompletionsNamespace(client)


class Hwarang:
    """화랑 AI 공식 SDK 메인 클래스 (sync).

    OpenAI SDK 와 비슷한 인터페이스:

    - ``hwarang.chat.completions.create(...)`` — OpenAI 호환 호출
    - ``hwarang.do(...)``                       — HP DSL 단순 엔트리
    - ``hwarang.ask(text)``                     — 한 줄 헬퍼

    환경변수:
        - ``HWARANG_API_KEY``   — API 키 (없으면 ``api_key`` 인자 필수)
        - ``HWARANG_API_URL``   — API 베이스 URL (기본 ``https://hwarang.ai``)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        default_model: str = "hwarang",
        timeout: float = 120.0,
    ) -> None:
        self._client = HwarangClient(
            api_key=api_key,
            api_url=api_url,
            default_model=default_model,
            timeout=timeout,
        )
        self.chat = _ChatNamespace(self._client)

    # ── HP 단순 엔트리 ────────────────────────────────────

    def do(self, **req: Any) -> Dict[str, Any]:
        """``/v1/hwarang/do`` — DSL 만으로 호출.

        예::

            r = hwarang.do(
                intent="add",
                scope="src/api/",
                input="POST /api/orders 결제 후 주문 생성",
                workflow=["plan", "code", "test"],
                language="ko",
            )
        """
        return self._client.do(**req)

    # ── 한 줄 헬퍼 ────────────────────────────────────────

    def ask(
        self,
        text: str,
        *,
        language: str = "ko",
        format: str = "plain",
        identity: str = "strict",
    ) -> ChatResponse:
        """가장 단순한 헬퍼 — 한 번 묻고 답 받기."""
        ext: HwarangExtension = {
            "language": language,  # type: ignore[typeddict-item]
            "format": format,  # type: ignore[typeddict-item]
            "identity": identity,  # type: ignore[typeddict-item]
        }
        return self._client.chat_completion(
            messages=[{"role": "user", "content": text}],
            hwarang=ext,
        )

    # ── 자원 관리 ─────────────────────────────────────────

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Hwarang":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


# ─────────────────────────────────────────────────────────
# 메인 클래스 (async)
# ─────────────────────────────────────────────────────────


class _AsyncCompletionsNamespace:
    def __init__(self, client: AsyncHwarangClient) -> None:
        self._client = client

    async def create(
        self,
        messages: List[ChatMessage],
        *,
        model: Optional[str] = None,
        tools: Optional[List[ToolDefinition]] = None,
        tool_choice: Any = "auto",
        temperature: Optional[float] = None,
        max_tokens: int = 16384,
        stream: bool = False,
        hwarang: Optional[HwarangExtension] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> ChatResponse:
        return await self._client.chat_completion(
            messages=messages,
            model=model,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            hwarang=hwarang,
            extra=extra,
        )


class _AsyncChatNamespace:
    def __init__(self, client: AsyncHwarangClient) -> None:
        self.completions = _AsyncCompletionsNamespace(client)


class AsyncHwarang:
    """화랑 AI 공식 SDK 메인 클래스 (async). ``Hwarang`` 와 동일 API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        default_model: str = "hwarang",
        timeout: float = 120.0,
    ) -> None:
        self._client = AsyncHwarangClient(
            api_key=api_key,
            api_url=api_url,
            default_model=default_model,
            timeout=timeout,
        )
        self.chat = _AsyncChatNamespace(self._client)

    async def do(self, **req: Any) -> Dict[str, Any]:
        return await self._client.do(**req)

    async def ask(
        self,
        text: str,
        *,
        language: str = "ko",
        format: str = "plain",
        identity: str = "strict",
    ) -> ChatResponse:
        ext: HwarangExtension = {
            "language": language,  # type: ignore[typeddict-item]
            "format": format,  # type: ignore[typeddict-item]
            "identity": identity,  # type: ignore[typeddict-item]
        }
        return await self._client.chat_completion(
            messages=[{"role": "user", "content": text}],
            hwarang=ext,
        )

    async def close(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> "AsyncHwarang":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()
