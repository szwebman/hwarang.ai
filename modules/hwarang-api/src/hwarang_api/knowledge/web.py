"""HLKM 일반 웹 수집 유틸.

hrag_client 가 한국 공공 API 전용이라면, web.py 는
임의 URL 의 HTML/JSON/RSS 를 끌어오기 위한 경량 래퍼 + 검색 placeholder 를 둔다.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from hwarang_api.knowledge.hrag_client import fetch_source as _hrag_fetch_source

logger = logging.getLogger(__name__)

_SEARCH_URL = os.getenv("WEB_SEARCH_URL", "")  # 내부 meta-search endpoint (옵션)
_SEARCH_KEY = os.getenv("WEB_SEARCH_API_KEY", "")
_HTTP_TIMEOUT = float(os.getenv("WEB_HTTP_TIMEOUT", "10.0"))


async def fetch_source(url: str) -> dict:
    """임의 URL 의 내용을 당겨온다 (hrag_client 와 동일 계약).

    반환: {"content": str, "headers": dict, "status": int, "content_type": str, "url": str}.
    """
    return await _hrag_fetch_source(url)


async def web_search(query: str, top_k: int = 5) -> list[dict]:
    """일반 웹 검색.

    - WEB_SEARCH_URL 이 설정돼 있으면 meta-search (예: SearxNG, Brave) 호출.
    - 없으면 간단한 placeholder (쿼리로 만든 가상 결과) 반환.
    반환 스키마: [{"title", "url", "snippet"}]
    """
    if not query:
        return []

    if _SEARCH_URL:
        try:
            import httpx

            params: dict[str, Any] = {"q": query, "format": "json"}
            headers: dict[str, str] = {}
            if _SEARCH_KEY:
                headers["Authorization"] = f"Bearer {_SEARCH_KEY}"
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                r = await client.get(_SEARCH_URL, params=params, headers=headers)
                if r.status_code == 200:
                    data: Any = r.json()
                    raw = data.get("results") or data.get("items") or []
                    out: list[dict] = []
                    for item in raw[:top_k]:
                        out.append(
                            {
                                "title": item.get("title") or item.get("name") or "",
                                "url": item.get("url")
                                or item.get("link")
                                or item.get("href")
                                or "",
                                "snippet": item.get("snippet")
                                or item.get("content")
                                or item.get("description")
                                or "",
                            }
                        )
                    return out
        except Exception as exc:
            logger.warning("web_search meta-search failed: %s", exc)

    # Fallback placeholder
    return [
        {
            "title": f"[placeholder] {query} - result {i + 1}",
            "url": f"https://example.com/search?q={query}&n={i + 1}",
            "snippet": f"No real search backend configured. Query: {query}",
        }
        for i in range(min(top_k, 3))
    ]


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(html: str) -> str:
    """경량 HTML → 텍스트. <script>/<style> 제거 후 태그 스트립."""
    if not html:
        return ""
    clean = re.sub(
        r"<script.*?</script>|<style.*?</style>",
        " ",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    clean = _TAG_RE.sub(" ", clean)
    clean = _WS_RE.sub(" ", clean).strip()
    return clean


async def fetch_and_extract_text(url: str) -> str:
    """URL 을 fetch 한 뒤 텍스트만 추출해 반환."""
    doc = await fetch_source(url)
    ct = (doc.get("content_type") or "").lower()
    content = doc.get("content") or ""
    if "html" in ct:
        return strip_html(content)
    return content


__all__ = ["fetch_source", "web_search", "strip_html", "fetch_and_extract_text"]
