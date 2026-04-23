"""HRAG 어댑터 - 한국 공공 API/웹 자원을 공통 dict 포맷으로 변환.

반환 아이템 스키마(권장):
    {
        "title": str,
        "content": str,
        "effective_date": datetime,
        "source_url": str,
        "source": str,  # API 명 ("law.go.kr" 등)
        "meta": dict,   # 원본 응답 일부
    }

환경변수:
  LAW_GO_KR_API_KEY   - 국가법령정보센터 OpenAPI 키
  KMA_API_KEY         - 기상청 API 키
  NEWS_API_KEY        - 뉴스 API 키 (선택)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

_LAW_KEY = os.getenv("LAW_GO_KR_API_KEY", "")
_KMA_KEY = os.getenv("KMA_API_KEY", "")
_NEWS_KEY = os.getenv("NEWS_API_KEY", "")
_HTTP_TIMEOUT = float(os.getenv("HRAG_HTTP_TIMEOUT", "10.0"))


async def fetch_source(url: str) -> dict:
    """범용 URL fetcher.

    반환: {"content": str, "headers": dict, "status": int, "content_type": str}.
    네트워크/파싱 실패 시 status=0 + content="".
    """
    try:
        import httpx

        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT, follow_redirects=True
        ) as client:
            r = await client.get(url, headers={"User-Agent": "hwarang-hlkm/1.0"})
            ct = r.headers.get("content-type", "")
            return {
                "content": r.text,
                "headers": dict(r.headers),
                "status": r.status_code,
                "content_type": ct,
                "url": str(r.url),
            }
    except Exception as exc:
        logger.warning("fetch_source failed for %s: %s", url, exc)
        return {
            "content": "",
            "headers": {},
            "status": 0,
            "content_type": "",
            "url": url,
            "error": str(exc),
        }


async def fetch_law_updates(since: datetime | None = None) -> list[dict]:
    """국가법령정보센터(law.go.kr) 최근 개정 법령 목록.

    API 키가 없으면 빈 리스트 반환. `since` 는 개정일 필터.
    """
    if not _LAW_KEY:
        logger.info("LAW_GO_KR_API_KEY not set; skipping fetch_law_updates")
        return []

    try:
        import httpx
    except Exception:
        return []

    # law.go.kr 의 현행법령 목록 API.
    # 실제 파라미터는 운영환경에서 확정하되 기본값으로 최근 100건을 가져온다.
    url = "https://www.law.go.kr/DRF/lawSearch.do"
    params = {
        "OC": _LAW_KEY,
        "target": "law",
        "type": "JSON",
        "display": "100",
    }
    if since:
        params["ancYd"] = since.strftime("%Y%m%d") + "~" + datetime.now(
            timezone.utc
        ).strftime("%Y%m%d")

    out: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                return []
            data: Any = r.json()
            laws = (
                data.get("LawSearch", {}).get("law", [])
                if isinstance(data, dict)
                else []
            )
            if isinstance(laws, dict):
                laws = [laws]
            for item in laws:
                eff_s = item.get("시행일자") or item.get("공포일자") or ""
                eff = _parse_yyyymmdd(eff_s)
                out.append(
                    {
                        "title": item.get("법령명한글", ""),
                        "content": item.get("법령명한글", "")
                        + " — "
                        + (item.get("소관부처명", "") or ""),
                        "effective_date": eff or datetime.now(timezone.utc),
                        "source_url": item.get("법령상세링크", "")
                        or "https://www.law.go.kr",
                        "source": "law.go.kr",
                        "meta": item,
                    }
                )
    except Exception as exc:
        logger.warning("fetch_law_updates failed: %s", exc)
    return out


async def fetch_weather_updates() -> list[dict]:
    """기상청 최근 특보/예보 목록.

    실서비스에서는 기상청_단기예보 API 등을 호출. 여기서는 일반 구조만 제공.
    API 키 없거나 실패 시 빈 리스트.
    """
    if not _KMA_KEY:
        return []

    try:
        import httpx
    except Exception:
        return []

    url = (
        "http://apis.data.go.kr/1360000/WthrWrnInfoService/getWthrWrnList"
    )
    params = {
        "serviceKey": _KMA_KEY,
        "dataType": "JSON",
        "numOfRows": "50",
        "pageNo": "1",
    }
    out: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                return []
            data: Any = r.json()
            items = (
                data.get("response", {})
                .get("body", {})
                .get("items", {})
                .get("item", [])
            )
            if isinstance(items, dict):
                items = [items]
            for item in items:
                eff = (
                    _parse_yyyymmdd(str(item.get("tmFc", "")))
                    or datetime.now(timezone.utc)
                )
                out.append(
                    {
                        "title": item.get("t1", "기상특보"),
                        "content": item.get("t6") or item.get("other") or "",
                        "effective_date": eff,
                        "source_url": "https://www.weather.go.kr",
                        "source": "kma",
                        "meta": item,
                    }
                )
    except Exception as exc:
        logger.warning("fetch_weather_updates failed: %s", exc)
    return out


async def fetch_news(keywords: list[str]) -> list[dict]:
    """뉴스 수집 스텁.

    현재 공식 API 연동 전이므로 fixture-style placeholder 를 돌려준다.
    운영에 붙일 때 Naver News / Kakao / NewsAPI 등으로 교체.
    """
    if not keywords:
        return []
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    for kw in keywords[:5]:
        out.append(
            {
                "title": f"[fixture] {kw} 관련 속보",
                "content": f"{kw} 관련 최근 이슈 요약 (테스트 픽스처).",
                "effective_date": now - timedelta(hours=1),
                "source_url": f"https://news.example.com/search?q={kw}",
                "source": "news-fixture",
                "meta": {"keyword": kw, "fixture": True},
            }
        )
    return out


def _parse_yyyymmdd(s: str) -> datetime | None:
    """YYYYMMDD 또는 YYYY-MM-DD 문자열을 UTC datetime 으로 변환."""
    if not s:
        return None
    s = s.strip().replace("-", "").replace(".", "")
    if len(s) < 8 or not s[:8].isdigit():
        return None
    try:
        return datetime(
            int(s[:4]), int(s[4:6]), int(s[6:8]), tzinfo=timezone.utc
        )
    except Exception:
        return None


__all__ = [
    "fetch_source",
    "fetch_law_updates",
    "fetch_weather_updates",
    "fetch_news",
]
