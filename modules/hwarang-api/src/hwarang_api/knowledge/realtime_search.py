"""실시간 웹 검색 — Naver 검색 API + Wikipedia + TrustedSource.

우선순위:
1. Naver 검색 API (한국 콘텐츠, 무료 25k/일) — news + encyc
2. 위키백과 한국어 (구조화된 사실, 키 불필요)
3. (확장) TrustedSource 정부 사이트 직접 검색

환경변수:
    HWARANG_NAVER_CLIENT_ID, HWARANG_NAVER_CLIENT_SECRET
    (없으면 Naver 어댑터는 빈 결과 반환, Wikipedia 만으로 동작)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str
    source: str       # "naver", "wikipedia", "primary"
    trust_score: int  # 0~100


# ─── Naver 검색 ─────────────────────────────────

NAVER_CLIENT_ID = (
    os.getenv("HWARANG_NAVER_CLIENT_ID", "")
    or os.getenv("NAVER_CLIENT_ID", "")
)
NAVER_CLIENT_SECRET = (
    os.getenv("HWARANG_NAVER_CLIENT_SECRET", "")
    or os.getenv("NAVER_CLIENT_SECRET", "")
)


_HTML_TAG = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _HTML_TAG.sub("", text or "").strip()


def _naver_trust(url: str) -> int:
    """URL 도메인 기반 신뢰도 추정 — TrustedSource 와 매칭."""
    if not url:
        return 30
    domain_to_score = {
        # 통신사·공영방송
        "yna.co.kr": 75, "kbs.co.kr": 70, "mbc.co.kr": 70, "sbs.co.kr": 70,
        # 종합지
        "chosun.com": 60, "joongang.co.kr": 60, "donga.com": 60,
        "hani.co.kr": 60, "khan.co.kr": 60,
        # 정부 1차 출처
        "korea.kr": 95, "law.go.kr": 100, "go.kr": 90,
        # 위키
        "namu.wiki": 50,
    }
    for d, s in domain_to_score.items():
        if d in url:
            return s
    return 40  # 기본


async def search_naver(
    query: str, top_k: int = 5, kind: str = "news"
) -> list[SearchHit]:
    """Naver Search API.

    kind: news (뉴스), encyc (지식백과), webkr (웹), kin (지식인)
    """
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return []

    url = f"https://openapi.naver.com/v1/search/{kind}.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": top_k, "sort": "sim"}  # 또는 date

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            logger.debug(f"Naver {kind} non-200: {resp.status_code}")
            return []
        data = resp.json()
        items = data.get("items", [])
        return [
            SearchHit(
                title=_strip_html(item.get("title", "")),
                url=item.get("link") or item.get("originallink", ""),
                snippet=_strip_html(item.get("description", "")),
                source="naver",
                trust_score=_naver_trust(item.get("link", "")),
            )
            for item in items[:top_k]
        ]
    except Exception as e:
        logger.warning(f"Naver search 실패: {e}")
        return []


# ─── Wikipedia 한국어 ──────────────────────────

async def search_wikipedia_ko(query: str, top_k: int = 3) -> list[SearchHit]:
    """위키백과 한국어 API. 무료, 키 불필요."""
    url = "https://ko.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": query,
        "srlimit": top_k,
        "srprop": "snippet|titlesnippet",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                url,
                params=params,
                headers={"User-Agent": "HwarangBot/1.0 (realtime-search)"},
            )
        if resp.status_code != 200:
            return []
        data = resp.json()
        items = data.get("query", {}).get("search", [])
        return [
            SearchHit(
                title=item.get("title", ""),
                url=f"https://ko.wikipedia.org/wiki/{item.get('title', '').replace(' ', '_')}",
                snippet=_strip_html(item.get("snippet", "")),
                source="wikipedia",
                trust_score=80,
            )
            for item in items[:top_k]
        ]
    except Exception as e:
        logger.debug(f"Wikipedia search 실패: {e}")
        return []


# ─── 통합 검색 ──────────────────────────────────

async def realtime_search(query: str, top_k: int = 8) -> list[SearchHit]:
    """Naver(news+encyc) + Wikipedia 동시 검색 → 신뢰도 정렬."""
    naver_news, naver_encyc, wiki = await asyncio.gather(
        search_naver(query, top_k=4, kind="news"),
        search_naver(query, top_k=2, kind="encyc"),
        search_wikipedia_ko(query, top_k=2),
        return_exceptions=True,
    )

    all_hits: list[SearchHit] = []
    for results in (naver_news, naver_encyc, wiki):
        if isinstance(results, Exception):
            logger.debug(f"realtime_search sub-task failed: {results}")
            continue
        all_hits.extend(results)

    # 중복 제거 + 신뢰도 정렬
    seen_urls: set[str] = set()
    unique: list[SearchHit] = []
    for h in sorted(all_hits, key=lambda x: -x.trust_score):
        if not h.url or h.url in seen_urls:
            continue
        seen_urls.add(h.url)
        unique.append(h)

    return unique[:top_k]


# ─── 본문 fetch (선택, 깊은 답변 필요할 때) ────

async def fetch_full_content(url: str, max_chars: int = 3000) -> Optional[str]:
    """검색 결과의 실제 본문 가져오기 (BeautifulSoup 가용 시)."""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(
                url, headers={"User-Agent": "HwarangBot/1.0"}
            )
        if resp.status_code != 200:
            return None
        try:
            from bs4 import BeautifulSoup  # type: ignore
        except Exception:
            # bs4 미설치 환경 — 단순 태그 제거 fallback
            return _strip_html(resp.text)[:max_chars]
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        article = soup.find("article") or soup.find("main") or soup.body
        if article:
            return article.get_text(separator="\n", strip=True)[:max_chars]
    except Exception as e:
        logger.debug(f"fetch_full_content 실패 ({url}): {e}")
        return None
    return None
