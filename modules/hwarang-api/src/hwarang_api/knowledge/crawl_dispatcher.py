"""분산 크롤 디스패처 — 마스터 측.

TrustedSource 의 ``crawlSchedule`` (cron) 와 ``lastCrawledAt`` 을 비교해
due 한 출처에 대해서만 URL 목록을 enumerate, ``CrawlJob`` 큐에 push.

push 된 잡은 에이전트가 ``/api/crawl/lease`` 로 가져가서 실제 페이지 본문을
추출/제출 (``/api/crawl/submit/{id}``) 한다.

핵심 보장:
  * **중복 없음** — ``CrawlJob.@@unique([sourceId, url])`` 제약으로 같은 URL 은
    두 번 큐잉되지 않음.
  * **whitelist only** — ``isWhitelisted=true && isActive=true`` 만 대상.
  * **공평 분배** — ``priority = trustLevel`` 로 신뢰도 높은 출처 우선.

스케줄러 (``hlkm_scheduler``) 가 매 5 분마다 ``dispatch_pending_crawls()``
를 호출. 기존 ``source_crawler.crawl_all_sources()`` 의 직접 ingest 로직은
deprecated (분산 크롤로 대체).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)

# 선택 의존성 — 없으면 graceful skip
try:
    import httpx  # type: ignore

    HAS_HTTPX = True
except Exception:  # noqa: BLE001
    HAS_HTTPX = False

try:
    import feedparser  # type: ignore

    HAS_FEEDPARSER = True
except Exception:  # noqa: BLE001
    HAS_FEEDPARSER = False

try:
    from croniter import croniter  # type: ignore

    HAS_CRONITER = True
except Exception:  # noqa: BLE001
    croniter = None  # type: ignore[assignment]
    HAS_CRONITER = False


USER_AGENT = (
    "Mozilla/5.0 (compatible; HwarangHLKM-Dispatcher/1.0; +https://hwarang.ai/bots)"
)
DEFAULT_TIMEOUT = 15
MAX_ITEMS_PER_FEED = 30
MAX_SITEMAP_URLS = 50
DEFAULT_INTERVAL_HOURS = 6


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 공개 진입점
# ---------------------------------------------------------------------------
async def dispatch_pending_crawls() -> dict:
    """due 인 모든 TrustedSource 에 대해 CrawlJob 을 생성.

    스케줄러에서 매 5 분 주기로 호출.
    """
    try:
        sources = await prisma.trustedsource.find_many(
            where={"isWhitelisted": True, "isActive": True},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("trustedsource.find_many failed: %s", exc)
        return {"error": str(exc)}

    results: dict[str, Any] = {}
    total_jobs = 0
    total_candidates = 0
    now = _utcnow()

    for src in sources:
        if not _is_due(src, now):
            continue

        try:
            urls = await _enumerate_urls(src)
        except Exception as exc:  # noqa: BLE001
            logger.warning("enumerate fail (%s): %s", src.domain, exc)
            results[src.domain] = {"error": str(exc)}
            continue

        jobs_created = 0
        for url_data in urls:
            url = url_data.get("url")
            if not url:
                continue
            try:
                await prisma.crawljob.create(
                    data={
                        "sourceId": src.id,
                        "url": url,
                        "jobType": url_data.get("type", "page_extract"),
                        "metadata": url_data.get("metadata", {}),
                        "priority": int(getattr(src, "trustLevel", 0) or 0),
                    }
                )
                jobs_created += 1
            except Exception:
                # unique violation = 이미 큐에 있음 → skip
                continue

        # lastCrawledAt 갱신 (다음 cron 비교 기준)
        try:
            await prisma.trustedsource.update(
                where={"id": src.id},
                data={"lastCrawledAt": now},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("trustedsource update fail (%s): %s", src.domain, exc)

        total_jobs += jobs_created
        total_candidates += len(urls)
        results[src.domain] = {
            "jobs_created": jobs_created,
            "candidates": len(urls),
        }

    return {
        "total_sources_due": len(results),
        "total_jobs_created": total_jobs,
        "total_candidates": total_candidates,
        "by_source": results,
    }


# ---------------------------------------------------------------------------
# due 판정
# ---------------------------------------------------------------------------
def _is_due(src: Any, now: datetime) -> bool:
    """``crawlSchedule`` (cron) 와 ``lastCrawledAt`` 으로 due 여부 판단."""
    last = getattr(src, "lastCrawledAt", None)
    if not last:
        return True  # 한 번도 안 크롤됐으면 즉시

    schedule = getattr(src, "crawlSchedule", None) or "0 */6 * * *"

    if HAS_CRONITER:
        try:
            cron = croniter(schedule, last)
            next_run = cron.get_next(datetime)
            # croniter 는 naive datetime 을 반환할 수 있음 → tz 보정
            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=timezone.utc)
            return now >= next_run
        except Exception:  # noqa: BLE001
            pass

    # cron 파싱 실패 또는 미설치 → 기본 인터벌
    return (now - last) >= timedelta(hours=DEFAULT_INTERVAL_HOURS)


# ---------------------------------------------------------------------------
# URL enumerate (4 가지 메서드)
# ---------------------------------------------------------------------------
async def _enumerate_urls(src: Any) -> list[dict]:
    """source 별 URL 목록 추출 — RSS / sitemap / API / custom 분기."""
    method = getattr(src, "crawlMethod", "rss")

    if method == "rss" and getattr(src, "rssUrl", None):
        return await _enum_rss(src)
    if method == "sitemap":
        return await _enum_sitemap(src)
    if method == "api":
        return await _enum_api(src)
    # ``scraper`` / ``custom`` / ``none`` 은 enumerate 단계에서는 패스 —
    # press_correction_scraper 등은 별도 (legacy) 경로를 그대로 사용한다.
    return []


async def _enum_rss(src: Any) -> list[dict]:
    """RSS / Atom 피드 → 항목 URL 목록."""
    if not HAS_HTTPX or not HAS_FEEDPARSER:
        logger.warning(
            "httpx/feedparser 미설치, RSS enumerate skip: %s", src.domain
        )
        return []
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            resp = await client.get(src.rssUrl)
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("RSS fetch fail (%s): %s", src.domain, exc)
        return []

    feed = feedparser.parse(resp.text)
    items: list[dict] = []
    for e in feed.entries[:MAX_ITEMS_PER_FEED]:
        link = (e.get("link") or "").strip()
        if not link:
            continue
        items.append(
            {
                "url": link,
                "type": "rss_item",
                "metadata": {
                    "title": (e.get("title") or "").strip()[:500],
                    "summary": (e.get("summary") or e.get("description") or "")[
                        :1000
                    ],
                    "published": e.get("published", ""),
                },
            }
        )
    return items


async def _enum_sitemap(src: Any) -> list[dict]:
    """sitemap.xml → ``loc`` URL 목록 (``lastCrawledAt`` 이후 lastmod 만)."""
    if not HAS_HTTPX:
        return []
    sitemap_url = getattr(src, "apiEndpoint", None) or (
        f"https://{src.domain}/sitemap.xml"
    )
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            resp = await client.get(sitemap_url)
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("sitemap fetch fail (%s): %s", src.domain, exc)
        return []

    try:
        root = ET.fromstring(resp.text)
    except Exception:
        return []

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    last_crawled = getattr(src, "lastCrawledAt", None)
    items: list[dict] = []
    for url_el in root.findall(".//sm:url", ns)[:MAX_SITEMAP_URLS]:
        loc = (url_el.findtext("sm:loc", default="", namespaces=ns) or "").strip()
        lastmod_raw = (
            url_el.findtext("sm:lastmod", default="", namespaces=ns) or ""
        ).strip()
        if not loc:
            continue
        published = _parse_iso_date(lastmod_raw)
        if last_crawled and published and published <= last_crawled:
            continue
        items.append(
            {
                "url": loc,
                "type": "sitemap_url",
                "metadata": {"lastmod": lastmod_raw},
            }
        )
    return items


async def _enum_api(src: Any) -> list[dict]:
    """공공 OpenAPI — 도메인별 dispatch.

    현재는 law.go.kr (법제처) 만 구현. 다른 OpenAPI 추가 시 분기 추가.
    """
    domain = getattr(src, "domain", "")
    if domain == "law.go.kr":
        return await _api_law_go_kr(src)

    # 미구현 출처는 RSS fallback (rssUrl 이 등록돼 있으면)
    if getattr(src, "rssUrl", None):
        return await _enum_rss(src)
    return []


async def _api_law_go_kr(src: Any) -> list[dict]:
    """법제처 OpenAPI 최신 법령 — apiKey 가 있을 때만 동작."""
    if not getattr(src, "apiKey", None) or not HAS_HTTPX:
        return []
    endpoint = src.apiEndpoint or "https://www.law.go.kr/DRF/lawSearch.do"
    params = {
        "OC": src.apiKey,
        "target": "law",
        "type": "JSON",
        "display": "30",
        "sort": "ddes",
    }
    try:
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = await client.get(endpoint, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("law.go.kr API fail: %s", exc)
        return []

    results = data.get("LawSearch", {}).get("law", []) or []
    items: list[dict] = []
    for r in results[:MAX_ITEMS_PER_FEED]:
        title = r.get("법령명한글") or ""
        link = r.get("법령상세링크") or r.get("법령링크") or ""
        if not title or not link:
            continue
        url = urljoin("https://www.law.go.kr", link) if link.startswith("/") else link
        items.append(
            {
                "url": url,
                "type": "api_query",
                "metadata": {
                    "title": title,
                    "category": r.get("법령구분명", ""),
                },
            }
        )
    return items


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _parse_iso_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except Exception:
        try:
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None


__all__ = ["dispatch_pending_crawls"]
