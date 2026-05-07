"""화이트리스트 출처 크롤러 — RSS / API / sitemap / 사용자 정의 셀렉터.

화랑은 무차별 크롤링을 하지 않는다. 관리자 승인 ``TrustedSource`` 만
주기적으로 순회하면서 새 콘텐츠를 수집하고, HLKM ``ingest_fact`` 로
저장하면서 ``SourceCitation`` 도 함께 생성한다.

매 6 시간마다 (cron) 활성 화이트리스트 출처를 순회 — ``crawl_all_sources()``.
스케줄러는 ``hwarang_api.workers.hlkm_scheduler`` 가 호출.

기존 스크래퍼 통합:
  ``press_correction_scraper`` 와 ``external_retraction`` 모듈은
  별도 모듈로 두지 않고, ``SourceCrawler._crawl_custom`` 에서 출처 도메인을
  보고 dispatch 한다 (기존 함수 그대로 재사용).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

from hwarang_api.db import prisma
from hwarang_api.knowledge.pipeline import ingest_fact
from hwarang_api.knowledge.types import KnowledgeFact, KnowledgeVisibility

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
    from bs4 import BeautifulSoup  # type: ignore

    HAS_BS4 = True
except Exception:  # noqa: BLE001
    BeautifulSoup = None  # type: ignore[assignment]
    HAS_BS4 = False


USER_AGENT = (
    "Mozilla/5.0 (compatible; HwarangHLKM-Crawler/1.0; +https://hwarang.ai/bots)"
)
DEFAULT_TIMEOUT = 15
MAX_ITEMS_PER_FEED = 30
MAX_SITEMAP_URLS = 50


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 단일 출처 크롤러
# ---------------------------------------------------------------------------
class SourceCrawler:
    """단일 ``TrustedSource`` 의 크롤링 로직.

    ``source.crawlMethod`` 에 따라 4 가지 메서드로 분기:
      * ``rss``     — feedparser 로 RSS/Atom 피드 파싱
      * ``api``     — 출처별 API 핸들러 (도메인 dispatch)
      * ``sitemap`` — sitemap.xml URL 목록 → 각 URL 메타데이터 추출
      * ``scraper`` — selectorJson 또는 도메인별 커스텀 핸들러
    """

    def __init__(self, source: Any) -> None:
        self.source = source

    # ─────── 공개 진입점 ─────── ─────── ─────── ─────── ───────
    async def crawl(self) -> dict:
        """``crawlMethod`` 에 따라 분기, 결과 통계 반환."""
        method = getattr(self.source, "crawlMethod", "rss")
        try:
            if method == "rss":
                items = await self._crawl_rss()
            elif method == "api":
                items = await self._crawl_api()
            elif method == "sitemap":
                items = await self._crawl_sitemap()
            elif method == "scraper":
                items = await self._crawl_custom()
            elif method == "none":
                return {"crawled": 0, "skipped": True, "reason": "method=none"}
            else:
                return {"crawled": 0, "skipped": True, "reason": f"unknown method {method}"}

            ingested = 0
            for item in items:
                if await self._ingest_one(item):
                    ingested += 1

            await self._update_stats(ingested, len(items))
            return {"crawled": len(items), "ingested": ingested}
        except Exception as exc:  # noqa: BLE001
            logger.exception("crawl failed for %s", self.source.domain)
            await self._update_stats(0, 0, error=str(exc))
            return {"error": str(exc)}

    # ─────── 메서드별 구현 ─────── ─────── ─────── ───────
    async def _crawl_rss(self) -> list[dict]:
        """RSS / Atom 피드 → 최근 N 개 항목."""
        if not getattr(self.source, "rssUrl", None):
            return []
        if not HAS_HTTPX or not HAS_FEEDPARSER:
            logger.warning("httpx/feedparser 미설치, RSS 크롤 건너뜀: %s", self.source.domain)
            return []
        try:
            async with httpx.AsyncClient(
                timeout=DEFAULT_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            ) as client:
                resp = await client.get(self.source.rssUrl)
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.warning("RSS fetch fail (%s): %s", self.source.domain, exc)
            return []

        feed = feedparser.parse(resp.text)
        items: list[dict] = []
        for entry in feed.entries[:MAX_ITEMS_PER_FEED]:
            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue
            summary = (
                entry.get("summary")
                or entry.get("description")
                or ""
            )
            items.append(
                {
                    "title": title,
                    "url": link,
                    "summary": summary[:1000],
                    "published": entry.get("published_parsed"),
                }
            )
        return items

    async def _crawl_api(self) -> list[dict]:
        """공공데이터포털 / 법제처 / 통계청 OpenAPI 등 출처별 핸들러.

        현재는 stub. 실제 구현 시 ``self.source.domain`` 으로 dispatch:
            law.go.kr      → 법제처 OpenAPI (자료 검색)
            kostat.go.kr   → KOSIS API
            kma.go.kr      → 기상청 단기예보 API
        """
        # 도메인별 dispatch — 향후 핸들러 추가 시 여기에 분기 추가
        domain = self.source.domain
        if domain == "law.go.kr":
            return await self._api_law_go_kr()
        # 미구현 출처는 RSS 가 있으면 RSS fallback
        if getattr(self.source, "rssUrl", None):
            return await self._crawl_rss()
        return []

    async def _api_law_go_kr(self) -> list[dict]:
        """법제처 OpenAPI 최신 법령 — apiKey 가 있을 때만 동작."""
        if not getattr(self.source, "apiKey", None) or not HAS_HTTPX:
            return []
        endpoint = self.source.apiEndpoint or "https://www.law.go.kr/DRF/lawSearch.do"
        params = {
            "OC": self.source.apiKey,
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
            items.append(
                {
                    "title": title,
                    "url": urljoin("https://www.law.go.kr", link)
                    if link.startswith("/")
                    else link,
                    "summary": r.get("법령구분명", ""),
                    "published": None,
                }
            )
        return items

    async def _crawl_sitemap(self) -> list[dict]:
        """sitemap.xml → 새 URL 만 메타데이터 수집.

        URL 의 lastmod 가 lastCrawledAt 이후인 것만 처리.
        """
        if not HAS_HTTPX:
            return []
        sitemap_url = getattr(self.source, "apiEndpoint", None) or (
            f"https://{self.source.domain}/sitemap.xml"
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
            logger.warning("sitemap fetch fail (%s): %s", self.source.domain, exc)
            return []

        items: list[dict] = []
        try:
            root = ET.fromstring(resp.text)
        except Exception:
            return []

        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        last_crawled = getattr(self.source, "lastCrawledAt", None)

        for url_el in root.findall(".//sm:url", ns)[:MAX_SITEMAP_URLS]:
            loc = url_el.findtext("sm:loc", default="", namespaces=ns).strip()
            lastmod_raw = url_el.findtext("sm:lastmod", default="", namespaces=ns).strip()
            if not loc:
                continue
            published = _parse_iso_date(lastmod_raw)
            # lastCrawledAt 이후만
            if last_crawled and published and published <= last_crawled:
                continue
            items.append(
                {
                    "title": loc.rsplit("/", 1)[-1] or loc,
                    "url": loc,
                    "summary": "",
                    "published": _to_time_struct(published),
                }
            )
        return items

    async def _crawl_custom(self) -> list[dict]:
        """``selectorJson`` 또는 도메인별 dispatch 로 커스텀 스크래핑.

        기존 ``press_correction_scraper`` / ``external_retraction`` 어댑터:
          - chosun.com / joongang.co.kr / donga.com / hani.co.kr / khan.co.kr / yna.co.kr
            → 정정/반론 페이지 스크래퍼 (press_correction_scraper.scrape_correction_page)
          - factcheck.snu.ac.kr → external_retraction.query_factcheck_snu (DB 시드는
            sync_provider 가 담당, 여기선 최근 스캔만 트리거)
        """
        domain = self.source.domain
        # 한국 언론사 정정 페이지 dispatch
        from hwarang_api.knowledge.press_correction_scraper import (
            KOREAN_PRESS_CORRECTION_PAGES,
            scrape_correction_page,
        )

        outlet_map = {
            "chosun.com": "chosun",
            "joongang.co.kr": "joongang",
            "donga.com": "donga",
            "hani.co.kr": "hani",
            "khan.co.kr": "khan",
            "yna.co.kr": "yonhap",
        }
        if domain in outlet_map and outlet_map[domain] in KOREAN_PRESS_CORRECTION_PAGES:
            try:
                rows = await scrape_correction_page(outlet_map[domain])
                return [
                    {
                        "title": r.get("title", "")[:300],
                        "url": r.get("url", ""),
                        "summary": r.get("title", ""),
                        "published": None,
                    }
                    for r in rows
                    if r.get("url")
                ]
            except Exception as exc:  # noqa: BLE001
                logger.warning("press correction scrape fail (%s): %s", domain, exc)
                return []

        # 팩트체커 dispatch — 기존 sync_provider 호출
        if domain in {"factcheck.snu.ac.kr", "ftn.factchecker.or.kr"}:
            try:
                from hwarang_api.knowledge.external_retraction import sync_provider

                provider = "factcheck_kr" if domain == "factcheck.snu.ac.kr" else None
                if provider:
                    await sync_provider(provider, batch_size=20)
            except Exception as exc:  # noqa: BLE001
                logger.warning("factcheck sync fail (%s): %s", domain, exc)
            # sync_provider 가 직접 KnowledgeFact 를 찾기 때문에, 우리는 0 개 리포트.
            return []

        # 일반 BS4 셀렉터 기반 (selectorJson 사용)
        selector = getattr(self.source, "selectorJson", None)
        if not selector or not HAS_HTTPX or not HAS_BS4:
            return []
        list_url = selector.get("list_url") if isinstance(selector, dict) else None
        css = selector.get("item") if isinstance(selector, dict) else None
        if not list_url or not css:
            return []
        try:
            async with httpx.AsyncClient(
                timeout=DEFAULT_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            ) as client:
                resp = await client.get(list_url)
                resp.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        items: list[dict] = []
        for el in soup.select(css)[:MAX_ITEMS_PER_FEED]:
            a = el.find("a")
            if not a:
                continue
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not href or not title:
                continue
            url = urljoin(f"https://{self.source.domain}", href)
            items.append({"title": title, "url": url, "summary": "", "published": None})
        return items

    # ─────── 후처리 ─────── ─────── ─────── ───────
    async def _ingest_one(self, item: dict) -> bool:
        """item → KnowledgeFact + SourceCitation. 중복이면 False."""
        title = item.get("title")
        url = item.get("url")
        if not title or not url:
            return False

        # 중복 체크 (URL 기준)
        try:
            existing = await prisma.sourcecitation.find_first(where={"url": url})
        except Exception:
            existing = None
        if existing:
            return False

        # KnowledgeFact 생성 — 출처 신뢰도 → 사실 신뢰도
        summary = item.get("summary") or ""
        content = f"{title}. {summary}".strip()[:2000]
        domains = list(getattr(self.source, "domains", []) or [])
        domain = domains[0] if domains else "general"
        confidence = max(0.0, min(1.0, self.source.trustLevel / 100.0))

        fact = KnowledgeFact(
            content=content,
            domain=domain,
            source=self.source.displayName,
            source_url=url,
            source_type="official",  # bypass_gate 와 함께 KYC 우회 신호
            confidence_t0=confidence,
            visibility=KnowledgeVisibility.PUBLIC,
            valid_from=_to_datetime(item.get("published")) or _utcnow(),
        )
        try:
            result = await ingest_fact(fact, bypass_gate=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ingest_fact fail (%s): %s", url, exc)
            return False

        # SourceCitation 기록
        try:
            await prisma.sourcecitation.create(
                data={
                    "factId": result.get("fact_id"),
                    "sourceId": self.source.id,
                    "url": url,
                    "title": title[:500],
                    "excerpt": (summary or "")[:500],
                    "publishedAt": _to_datetime(item.get("published")),
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("sourcecitation create fail (%s): %s", url, exc)

        return True

    async def _update_stats(
        self, ingested: int, total: int, error: str | None = None
    ) -> None:
        """크롤 결과를 TrustedSource 행에 누적."""
        # successRate 는 EMA 로 살짝 부드럽게 — 단순화: 성공 1.0, 에러 0.5
        new_success = 1.0 if not error else 0.5
        try:
            current = float(getattr(self.source, "successRate", 1.0) or 1.0)
        except Exception:
            current = 1.0
        smoothed = round(0.7 * current + 0.3 * new_success, 4)

        try:
            await prisma.trustedsource.update(
                where={"id": self.source.id},
                data={
                    "totalCrawled": {"increment": total},
                    "totalFacts": {"increment": ingested},
                    "lastCrawledAt": _utcnow(),
                    "successRate": smoothed,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("update stats fail (%s): %s", self.source.domain, exc)


# ---------------------------------------------------------------------------
# 일괄 실행 — 스케줄러에서 호출
# ---------------------------------------------------------------------------
async def crawl_all_sources() -> dict:
    """[DEPRECATED] Phase 4.1 부터 분산 크롤로 대체.

    이제는 ``crawl_dispatcher.dispatch_pending_crawls()`` (마스터=디스패처) +
    에이전트 워커 (``/api/crawl/lease``) 가 같은 일을 분담해서 한다.
    이 함수는 backward-compat 용으로만 유지. 새 코드는 호출하지 말 것.
    """
    try:
        sources = await prisma.trustedsource.find_many(
            where={"isWhitelisted": True, "isActive": True},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("trustedsource.find_many failed: %s", exc)
        return {"error": str(exc)}

    results: dict[str, Any] = {}
    total_ingested = 0
    total_crawled = 0
    for s in sources:
        res = await SourceCrawler(s).crawl()
        results[s.domain] = res
        total_ingested += int(res.get("ingested", 0) or 0)
        total_crawled += int(res.get("crawled", 0) or 0)

    return {
        "total_sources": len(sources),
        "total_crawled": total_crawled,
        "total_ingested": total_ingested,
        "by_source": results,
    }


async def crawl_one_source(source_id: str) -> dict:
    """단일 출처 즉시 크롤 (테스트/관리자 트리거용)."""
    src = await prisma.trustedsource.find_unique(where={"id": source_id})
    if not src:
        return {"error": f"source not found: {source_id}"}
    return await SourceCrawler(src).crawl()


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _to_datetime(time_struct: Any) -> datetime | None:
    """feedparser time_struct 또는 datetime → tz-aware datetime."""
    if not time_struct:
        return None
    if isinstance(time_struct, datetime):
        if time_struct.tzinfo is None:
            return time_struct.replace(tzinfo=timezone.utc)
        return time_struct
    try:
        return datetime(*time_struct[:6], tzinfo=timezone.utc)
    except Exception:
        return None


def _to_time_struct(dt: datetime | None) -> tuple | None:
    if not dt:
        return None
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, 0, 0, 0)


def _parse_iso_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        # sitemap lastmod 는 보통 ISO 8601
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except Exception:
        try:
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None


# ---------------------------------------------------------------------------
# HSEE Phase 4 — Trusted Source 자동 갱신
# ---------------------------------------------------------------------------
async def crawl_trusted_sources(
    top_k: int = 8,
    queries: tuple[str, ...] = (
        "최신 공시", "주요 변경", "신규 통계", "최저시급", "환율", "법령 개정",
    ),
) -> dict:
    """1차 출처 API (법제처/KOSIS/국세청/MFDS/ECOS/KMA) 주기 호출.

    HSEE Phase 4 Trusted Source Network 의 신뢰도 자동 갱신용:
      1. 도메인 별 대표 쿼리로 ``primary_source_apis.search_primary_sources`` 호출
      2. 결과를 ``self_questioner._ingest_api_results`` 패턴으로 HLKM 에 사실 ingest
      3. ``TrustedSource.lastCrawledAt`` / ``successRate`` 갱신 (이미 매칭되는 row 가
         있을 때만 — 새로 만들지 않음, 관리자 승인 정책 보존)

    스케줄러: 매일 04:00 KST.
    """
    started = _utcnow()
    try:
        from hwarang_api.knowledge.primary_source_apis import (
            search_primary_sources,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("primary_source_apis 임포트 실패: %s", exc)
        return {"error": "primary_source_apis_unavailable"}

    # 도메인 키는 primary_source_apis.DOMAIN_TO_APIS 와 정확히 일치해야 매칭됨.
    # 키워드는 매일 04:00 KST 호출되므로 도메인당 ~12개 상한 (rate limit 보호).
    domain_map = {
        "legal": [
            "법령 개정", "최저시급", "최저임금", "근로기준법", "개인정보보호법",
            "주택임대차보호법", "부동산 거래법", "도로교통법", "형법 개정",
            "상법 개정", "공정거래법", "소비자보호법",
        ],
        "tax": [
            "연말정산", "부가세 신고", "종합소득세", "양도소득세", "상속세",
            "증여세", "법인세", "원천세", "간이과세", "종합부동산세",
            "세액공제", "세무조사",
        ],
        "statistics": [
            "주요 통계", "신규 통계", "인구 통계", "가계동향", "고용동향",
            "소비자물가지수", "생산자물가지수", "주택가격동향", "사업체조사",
            "수출입동향", "산업생산지수", "경제활동인구",
        ],
        "medical": [
            "의약품 허가", "의약품 회수", "의료기기 허가", "부작용 보고",
            "임상시험 승인", "신약 허가", "백신 안전성", "의료기기 회수",
        ],
        "drug": [
            "의약품 허가", "마약류 관리", "전문의약품", "일반의약품", "복약지도",
        ],
        "food": [
            "식품 회수", "식중독 발생", "건강기능식품", "식품첨가물",
            "화장품 회수", "수입식품 검사", "유전자변형식품",
        ],
        "finance": [
            "환율", "기준금리", "외환보유액", "무역수지", "경상수지",
            "통화량", "GDP 성장률", "수출입 통계", "생산자물가",
            "산업생산", "소비자심리지수", "기업경기실사지수",
        ],
        "economy": [
            "GDP 성장률", "경제성장률", "산업생산", "수출입동향",
            "고용동향", "물가상승률", "통화정책",
        ],
        "weather": [
            "서울 날씨", "부산 날씨", "대구 날씨", "광주 날씨", "제주 날씨",
            "기상특보", "태풍 정보", "폭염특보", "한파특보", "미세먼지",
            "황사특보", "호우특보", "강수량 예보",
        ],
        "general": list(queries),
    }

    total_results = 0
    ingested = 0
    by_domain: dict[str, dict] = {}

    for dom, qs in domain_map.items():
        dom_total = 0
        dom_ingested = 0
        for q in qs:
            try:
                results = await search_primary_sources(q, dom, top_k=top_k)
            except Exception as exc:  # noqa: BLE001
                logger.debug("primary search fail [%s/%s]: %s", dom, q, exc)
                continue
            dom_total += len(results)

            # ingest helper 재사용
            try:
                from hwarang_api.learning.self_questioner import (
                    _ingest_api_results,
                )

                saved = await _ingest_api_results(results, dom)
                dom_ingested += saved
            except Exception as exc:  # noqa: BLE001
                logger.debug("ingest helper unavailable: %s", exc)

        total_results += dom_total
        ingested += dom_ingested
        by_domain[dom] = {"queries": dom_total, "ingested": dom_ingested}

    # TrustedSource lastCrawledAt 도 함께 bump (활성 신뢰도 신호로)
    try:
        active = await prisma.trustedsource.find_many(
            where={"isWhitelisted": True, "isActive": True},
            take=200,
        )
        for s in active:
            try:
                await prisma.trustedsource.update(
                    where={"id": s.id},
                    data={"lastCrawledAt": _utcnow()},
                )
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        logger.debug("TrustedSource lastCrawledAt bump fail: %s", exc)

    return {
        "started_at": started.isoformat(),
        "elapsed_seconds": (_utcnow() - started).total_seconds(),
        "total_results": total_results,
        "ingested": ingested,
        "by_domain": by_domain,
    }


__all__ = [
    "SourceCrawler",
    "crawl_all_sources",
    "crawl_one_source",
    "crawl_trusted_sources",
]
