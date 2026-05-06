"""HTTP 클라이언트 (sync + async).

저수준 ``HwarangClient`` / ``AsyncHwarangClient`` 는 단순 함수를 노출.
보통은 :class:`hwarang.Hwarang` / :class:`hwarang.AsyncHwarang` 사용 권장.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import httpx

from ._errors import (
    HwarangAuthError,
    HwarangError,
    HwarangRateLimitError,
    HwarangTimeoutError,
)
from ._markup import parse_markup
from ._types import (
    ChatMessage,
    ChatResponse,
    HwarangExtension,
    MarkupSection,
    ToolCall,
    ToolDefinition,
)

_SDK_VERSION = "1.0.0"
_USER_AGENT = f"hwarang-sdk-py/{_SDK_VERSION}"


def _extract_err(text: str, fallback: str) -> str:
    """응답 본문에서 에러 메시지를 추출. JSON 이 아니면 fallback."""
    if not text:
        return fallback
    try:
        j = json.loads(text)
        if isinstance(j, dict):
            for k in ("error", "message", "detail"):
                v = j.get(k)
                if isinstance(v, str) and v:
                    return v
                if isinstance(v, dict) and isinstance(v.get("message"), str):
                    return v["message"]
        return fallback
    except (ValueError, TypeError):
        return text[:200] or fallback


def _raise_for_status(resp: httpx.Response) -> None:
    """HTTP 에러를 화랑 에러로 변환."""
    if resp.is_success:
        return
    msg = _extract_err(resp.text, f"HTTP {resp.status_code}")
    if resp.status_code in (401, 403):
        raise HwarangAuthError(msg, resp.status_code)
    if resp.status_code == 429:
        raise HwarangRateLimitError(msg, resp.status_code, "rate_limited")
    raise HwarangError(msg, resp.status_code)


def _build_body(
    messages: List[ChatMessage],
    *,
    model: str,
    tools: Optional[List[ToolDefinition]],
    tool_choice: Any,
    temperature: Optional[float],
    max_tokens: int,
    stream: bool,
    hwarang: Optional[HwarangExtension],
    extra: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "model": model,
        "messages": list(messages),
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if tools:
        body["tools"] = list(tools)
        body["tool_choice"] = tool_choice
    if temperature is not None:
        body["temperature"] = temperature
    if hwarang:
        body["@hwarang"] = dict(hwarang)
    if extra:
        for k, v in extra.items():
            if k not in body:
                body[k] = v
    return body


def _wrap_response(
    raw: Dict[str, Any],
    ext: Optional[HwarangExtension],
) -> ChatResponse:
    """vLLM/OpenAI 스타일 응답을 :class:`ChatResponse` 로 감싼다.

    - ``hwarang.format == "markup"`` 이면 ``content`` 본문을 직접 파싱
    - 서버가 이미 ``@hwarang.markup`` 을 채워줬으면 그것을 우선 사용
    """
    choices = raw.get("choices") or []
    msg = (choices[0].get("message") if choices else {}) or {}
    content = msg.get("content") or ""
    raw_tool_calls = msg.get("tool_calls") or []
    tool_calls: List[ToolCall] = list(raw_tool_calls)

    markup: Optional[MarkupSection] = None

    server_meta = raw.get("@hwarang") or raw.get("hwarang") or {}
    server_markup = server_meta.get("markup") if isinstance(server_meta, dict) else None
    want_markup = bool(ext and ext.get("format") == "markup")

    if isinstance(server_markup, dict):
        markup = MarkupSection(
            plan=list(server_markup.get("plan") or []),
            diffs=list(server_markup.get("diffs") or []),
            suggestions=list(server_markup.get("suggestions") or []),
            warnings=list(server_markup.get("warnings") or []),
            errors=list(server_markup.get("errors") or []),
            tools=list(server_markup.get("tools") or []),
            results=list(server_markup.get("results") or []),
            summary=server_markup.get("summary"),
        )
    elif want_markup and content:
        parsed = parse_markup(content)
        markup = MarkupSection(**parsed)

    return ChatResponse(
        raw=raw,
        text=content,
        tool_calls=tool_calls,
        markup=markup,
    )


# ─────────────────────────────────────────────────────────
# Sync 클라이언트
# ─────────────────────────────────────────────────────────


class HwarangClient:
    """저수준 sync HTTP 클라이언트.

    보통은 ``Hwarang(api_key=...)`` 가 더 편하다. 이 클래스는 SDK 외부
    프레임워크와 결합할 때 직접 사용한다.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        default_model: str = "hwarang",
        timeout: float = 120.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("HWARANG_API_KEY", "")
        url = api_url or os.getenv("HWARANG_API_URL", "https://hwarang.ai")
        self.api_url = url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self._owned_client = client is None
        self._client = client

    # ── public ────────────────────────────────────────────

    def chat_completion(
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
        """``POST /v1/chat/completions`` (OpenAI 호환 + ``@hwarang``)."""
        body = _build_body(
            messages,
            model=model or self.default_model,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            hwarang=hwarang,
            extra=extra,
        )
        raw = self._post_json("/v1/chat/completions", body)
        return _wrap_response(raw, hwarang)

    def do(self, **req: Any) -> Dict[str, Any]:
        """``POST /v1/hwarang/do`` 단순 엔트리."""
        return self._post_json("/v1/hwarang/do", req)

    def close(self) -> None:
        if self._owned_client and self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "HwarangClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ── internal ──────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
            "X-Hwarang-SDK": f"py/{_SDK_VERSION}",
        }
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def _post_json(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        client = self._get_client()
        try:
            resp = client.post(
                f"{self.api_url}{path}",
                json=body,
                headers=self._headers(),
            )
        except httpx.TimeoutException as e:
            raise HwarangTimeoutError(f"요청 타임아웃: {e}") from e
        except httpx.HTTPError as e:
            raise HwarangError(f"네트워크 오류: {e}") from e

        _raise_for_status(resp)
        try:
            return resp.json()
        except ValueError as e:
            raise HwarangError(f"응답이 JSON 이 아님: {resp.text[:200]}") from e


# ─────────────────────────────────────────────────────────
# Async 클라이언트
# ─────────────────────────────────────────────────────────


class AsyncHwarangClient:
    """저수준 async HTTP 클라이언트. ``HwarangClient`` 와 동일 API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        default_model: str = "hwarang",
        timeout: float = 120.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("HWARANG_API_KEY", "")
        url = api_url or os.getenv("HWARANG_API_URL", "https://hwarang.ai")
        self.api_url = url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self._owned_client = client is None
        self._client = client

    async def chat_completion(
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
        body = _build_body(
            messages,
            model=model or self.default_model,
            tools=tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            hwarang=hwarang,
            extra=extra,
        )
        raw = await self._post_json("/v1/chat/completions", body)
        return _wrap_response(raw, hwarang)

    async def do(self, **req: Any) -> Dict[str, Any]:
        return await self._post_json("/v1/hwarang/do", req)

    async def close(self) -> None:
        if self._owned_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "AsyncHwarangClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # ── internal ──────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
            "X-Hwarang-SDK": f"py/{_SDK_VERSION}",
        }
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def _post_json(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        client = self._get_client()
        try:
            resp = await client.post(
                f"{self.api_url}{path}",
                json=body,
                headers=self._headers(),
            )
        except httpx.TimeoutException as e:
            raise HwarangTimeoutError(f"요청 타임아웃: {e}") from e
        except httpx.HTTPError as e:
            raise HwarangError(f"네트워크 오류: {e}") from e

        _raise_for_status(resp)
        try:
            return resp.json()
        except ValueError as e:
            raise HwarangError(f"응답이 JSON 이 아님: {resp.text[:200]}") from e
