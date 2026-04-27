"""에이전트 공통 HTTP 유틸 — Bearer 인증 + 지수 백오프 재시도.

`urllib.request` 만 사용 (외부 의존성 없음 → 부트스트랩 단계에서도 동작).
모든 마스터 API 호출은 이 모듈을 통하도록 통일한다.

환경변수:
    HWARANG_AGENT_KEY  — 에이전트 API 키 (1순위)
    HWARANG_API_KEY    — 일반 API 키 (2순위)
    HWARANG_AGENT_ID   — 헤더 X-Agent-Id 값 (옵션)
"""

from __future__ import annotations

import logging
import os
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


_USER_AGENT = "hwarang-agent/0.1"
_DEFAULT_RETRIES = 3


def _api_key() -> str:
    return os.getenv("HWARANG_AGENT_KEY") or os.getenv("HWARANG_API_KEY") or ""


def _build_headers(extra: dict | None = None) -> dict:
    headers: dict[str, str] = {"User-Agent": _USER_AGENT}
    key = _api_key()
    if key:
        headers["Authorization"] = f"Bearer {key}"
        # 일부 엔드포인트는 X-Agent-Key 를 요구 → 둘 다 보냄
        headers["X-Agent-Key"] = key
    aid = os.getenv("HWARANG_AGENT_ID")
    if aid:
        headers["X-Agent-Id"] = aid
    if extra:
        headers.update(extra)
    return headers


def make_request(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    timeout: float = 10.0,
    headers: dict | None = None,
    retries: int = _DEFAULT_RETRIES,
):
    """Bearer 헤더 자동 추가 + 지수 백오프(1s, 2s, 4s) 재시도.

    네트워크/5xx 에러는 재시도, 4xx 는 즉시 raise.
    Returns urllib HTTPResponse — 호출자가 .read() 책임.
    """
    last_exc: Exception | None = None
    final_headers = _build_headers(headers)
    for attempt in range(max(1, retries)):
        try:
            req = urllib.request.Request(
                url, data=data, headers=final_headers, method=method
            )
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            last_exc = e
            # 4xx 는 클라이언트 잘못 — 재시도 의미 없음
            if 400 <= e.code < 500 and e.code != 429:
                raise
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            last_exc = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("make_request: 알 수 없는 실패")


__all__ = ["make_request"]
