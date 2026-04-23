"""HLKM - 한국 언론사 정정/반론 보도 스크래퍼.

조선·중앙·동아·한겨레·경향·연합 등 주요 언론사의 정정/반론 코너와
언론중재위원회(PAC) 시정권고/반론보도 결정문을 주기적으로 수집해,
HLKM ``KnowledgeFact`` 중 원본 기사와 매칭되는 항목을 자동 무효화한다.

설계 원칙:
  * BeautifulSoup4 가 있으면 사용, 없으면 정규식 fallback.
  * 페이지 구조 변경에 그레이스풀 — 실패 = 빈 리스트.
  * User-Agent 명시 + 과도한 병렬 요청 피하기 위해 asyncio.Semaphore 사용.
  * 매칭 기준: (1) 원본 기사 URL 일치, (2) 제목 유사도 ≥ threshold.

스케줄러에서 ``run_full_press_scan`` 을 일 1회 호출하는 것을 가정한다.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urljoin

import httpx

from hwarang_api.db import prisma

from .retraction import record_retraction

logger = logging.getLogger(__name__)

try:  # pragma: no cover — 선택 의존성
    from bs4 import BeautifulSoup  # type: ignore

    HAS_BS4 = True
except Exception:  # noqa: BLE001
    BeautifulSoup = None  # type: ignore[assignment]
    HAS_BS4 = False


USER_AGENT = (
    "Mozilla/5.0 (compatible; HwarangHLKM-Correction-Bot/1.0; "
    "+https://hwarang.ai/bots)"
)
DEFAULT_TIMEOUT = 15
_SCRAPE_SEM = asyncio.Semaphore(4)


#: 언론사별 정정 페이지. ``selector`` 는 BS4 CSS 셀렉터, 없으면 정규식 fallback.
KOREAN_PRESS_CORRECTION_PAGES: dict[str, dict[str, Any]] = {
    "chosun": {
        "url": "https://www.chosun.com/correction/",
        "selector": ".correction-item",
        "base": "https://www.chosun.com",
    },
    "joongang": {
        "url": "https://www.joongang.co.kr/correction",
        "selector": ".list_basic li",
        "base": "https://www.joongang.co.kr",
    },
    "donga": {
        "url": "https://www.donga.com/correction",
        "selector": ".articleList li",
        "base": "https://www.donga.com",
    },
    "hani": {
        "url": "https://www.hani.co.kr/arti/correction/",
        "selector": ".article-list-item",
        "base": "https://www.hani.co.kr",
    },
    "khan": {
        "url": "https://www.khan.co.kr/correction/",
        "selector": ".phArtc",
        "base": "https://www.khan.co.kr",
    },
    "yonhap": {
        "url": "https://www.yna.co.kr/correction/index",
        "selector": ".list-type038 li",
        "base": "https://www.yna.co.kr",
    },
    "press_arbitration": {
        "url": "https://www.pac.or.kr/kor/notice/",
        "selector": ".board-list tbody tr",
        "base": "https://www.pac.or.kr",
        "note": "언론중재위원회 시정권고/반론보도",
    },
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────
# HTTP
# ─────────────────────────────────────────────
async def _fetch_html(url: str) -> str | None:
    """httpx GET — 2xx 아니면 ``None``."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "ko,en-US;q=0.8,en;q=0.7",
    }
    try:
        async with _SCRAPE_SEM:
            async with httpx.AsyncClient(
                timeout=DEFAULT_TIMEOUT, follow_redirects=True
            ) as client:
                r = await client.get(url, headers=headers)
        if r.status_code >= 400:
            logger.debug("fetch_html %s → %d", url, r.status_code)
            return None
        return r.text
    except Exception as exc:  # noqa: BLE001
        logger.debug("fetch_html error %s: %s", url, exc)
        return None


# ─────────────────────────────────────────────
# URL / 텍스트 유틸
# ─────────────────────────────────────────────
def normalize_outlet_url(outlet: str, relative_url: str) -> str:
    """상대 경로를 절대 URL 로."""
    if not relative_url:
        return ""
    if relative_url.startswith("http://") or relative_url.startswith("https://"):
        return relative_url
    base = KOREAN_PRESS_CORRECTION_PAGES.get(outlet, {}).get("base", "")
    if not base:
        return relative_url
    return urljoin(base + "/", relative_url)


_URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>]+")


def extract_article_url_from_correction(correction_text: str) -> str | None:
    """정정 본문 텍스트에서 원본 기사 URL 추출 (첫 번째 http 링크)."""
    if not correction_text:
        return None
    m = _URL_IN_TEXT.search(correction_text)
    if not m:
        return None
    url = m.group(0).rstrip(".,);]\"'")
    return url or None


def _similarity(a: str, b: str) -> float:
    """제목/클레임 유사도 (0~1)."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.strip(), b.strip()).ratio()


# ─────────────────────────────────────────────
# 파싱
# ─────────────────────────────────────────────
_DATE_PAT = re.compile(
    r"(20\d{2}[./-]\s?\d{1,2}[./-]\s?\d{1,2}|20\d{2}년\s?\d{1,2}월\s?\d{1,2}일)"
)
_A_TAG = re.compile(
    r'<a[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<text>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_STRIP_TAGS = re.compile(r"<[^>]+>")


def _parse_with_bs4(html: str, selector: str, outlet: str) -> list[dict]:
    """BeautifulSoup 파서."""
    items: list[dict] = []
    try:
        soup = BeautifulSoup(html, "html.parser")  # type: ignore[misc]
    except Exception as exc:  # noqa: BLE001
        logger.debug("bs4 parse failed %s: %s", outlet, exc)
        return items

    nodes = soup.select(selector) if selector else []
    for node in nodes[:50]:
        a = node.find("a")
        if not a:
            continue
        href = a.get("href") or ""
        title = a.get_text(strip=True)
        # 날짜
        text_block = node.get_text(" ", strip=True)
        dm = _DATE_PAT.search(text_block)
        date_str = dm.group(1) if dm else ""
        items.append(
            {
                "title": title[:300],
                "date": date_str,
                "original_article_url": extract_article_url_from_correction(text_block)
                or "",
                "correction_text": text_block[:800],
                "correction_url": normalize_outlet_url(outlet, href),
                "outlet": outlet,
            }
        )
    return items


def _parse_with_regex(html: str, outlet: str) -> list[dict]:
    """BS4 부재 시 정규식 fallback — <a> 태그 스캔 후 '정정/반론/바로잡' 키워드로 필터."""
    items: list[dict] = []
    keyword_re = re.compile(r"정정|반론|바로잡|오보|시정권고|사과", re.IGNORECASE)
    for m in _A_TAG.finditer(html):
        href = m.group("href")
        raw = _STRIP_TAGS.sub("", m.group("text")).strip()
        if not raw or not keyword_re.search(raw):
            continue
        # 주변 ±200자 문맥에서 날짜 추출 시도
        start = max(0, m.start() - 200)
        end = min(len(html), m.end() + 200)
        ctx = _STRIP_TAGS.sub(" ", html[start:end])
        dm = _DATE_PAT.search(ctx)
        items.append(
            {
                "title": raw[:300],
                "date": dm.group(1) if dm else "",
                "original_article_url": extract_article_url_from_correction(ctx) or "",
                "correction_text": ctx[:800],
                "correction_url": normalize_outlet_url(outlet, href),
                "outlet": outlet,
            }
        )
        if len(items) >= 50:
            break
    return items


async def scrape_correction_page(outlet: str) -> list[dict]:
    """단일 언론사 정정 페이지 스크래핑.

    각 항목: ``{title, date, original_article_url, correction_text, correction_url, outlet}``.
    실패 = 빈 리스트.
    """
    cfg = KOREAN_PRESS_CORRECTION_PAGES.get(outlet)
    if not cfg:
        logger.warning("unknown outlet %s", outlet)
        return []

    html = await _fetch_html(cfg["url"])
    if not html:
        return []

    if HAS_BS4 and cfg.get("selector"):
        items = _parse_with_bs4(html, cfg["selector"], outlet)
        if items:
            return items
    return _parse_with_regex(html, outlet)


async def scrape_press_arbitration() -> list[dict]:
    """언론중재위원회 시정권고/반론보도 결정문 — 공지사항 리스트.

    PDF 첨부가 많아 제목과 URL 수준만 수집하고, 본문 연계는 추후 보강.
    """
    cfg = KOREAN_PRESS_CORRECTION_PAGES["press_arbitration"]
    html = await _fetch_html(cfg["url"])
    if not html:
        return []

    items: list[dict] = []
    if HAS_BS4:
        try:
            soup = BeautifulSoup(html, "html.parser")  # type: ignore[misc]
            for tr in soup.select(cfg["selector"])[:40]:
                a = tr.find("a")
                if not a:
                    continue
                title = a.get_text(strip=True)
                if not title:
                    continue
                href = a.get("href") or ""
                row_text = tr.get_text(" ", strip=True)
                dm = _DATE_PAT.search(row_text)
                items.append(
                    {
                        "title": title[:300],
                        "date": dm.group(1) if dm else "",
                        "correction_url": normalize_outlet_url(
                            "press_arbitration", href
                        ),
                        "correction_text": row_text[:500],
                        "original_article_url": "",
                        "outlet": "press_arbitration",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("press_arbitration bs4 parse failed: %s", exc)

    if not items:
        items = _parse_with_regex(html, "press_arbitration")

    # 시정권고/반론보도 관련 키워드만 남기기
    kw = re.compile(r"시정권고|반론보도|정정보도|직권조정|심의결정")
    items = [it for it in items if kw.search(it.get("title", "") + it.get("correction_text", ""))]
    return items


async def scrape_kpcc_official() -> list[dict]:
    """한국언론진흥재단(KPF) / 언론중재위 공식 발표 — 강제력 있는 공식 정정.

    현재는 PAC 결정문을 재사용. KPF 별도 DB 공개 시 본 함수 내부에서 교체.
    """
    items = await scrape_press_arbitration()
    for it in items:
        it["authority"] = "official"
    return items


# ─────────────────────────────────────────────
# 매칭 & 반영
# ─────────────────────────────────────────────
async def match_corrections_to_facts(
    corrections: list[dict], similarity_threshold: float = 0.7
) -> list[tuple[str, dict]]:
    """정정 항목을 HLKM fact 와 매칭.

    매칭 전략:
      1. ``original_article_url`` 과 fact.source_url 정확 일치 → 즉시 매칭.
      2. 없으면 동일 outlet 도메인 하의 최근 fact 중 제목 유사도 ≥ threshold.

    Returns: ``[(fact_id, correction_dict), ...]``.
    """
    matches: list[tuple[str, dict]] = []
    if not corrections:
        return matches

    for corr in corrections:
        orig_url = (corr.get("original_article_url") or "").strip()
        title = (corr.get("title") or "").strip()

        # (1) URL 정확 매칭
        if orig_url:
            try:
                row = await prisma.knowledgefact.find_first(
                    where={"sourceUrl": orig_url, "retracted": False}
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("find_first by url failed: %s", exc)
                row = None
            if row:
                matches.append((row.id, corr))
                continue

        # (2) 유사도 매칭 — outlet base 도메인으로 후보 축소
        if not title:
            continue
        outlet = corr.get("outlet", "")
        base = KOREAN_PRESS_CORRECTION_PAGES.get(outlet, {}).get("base", "")
        where: dict[str, Any] = {"retracted": False}
        if base:
            where["sourceUrl"] = {"contains": base.replace("https://", "").replace("http://", "")}
        try:
            candidates = await prisma.knowledgefact.find_many(
                where=where, take=200, order={"createdAt": "desc"}
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("candidate load failed: %s", exc)
            continue

        best: tuple[float, Any] | None = None
        for row in candidates:
            score = _similarity(title, row.content[:200])
            if best is None or score > best[0]:
                best = (score, row)
        if best and best[0] >= similarity_threshold:
            matches.append((best[1].id, corr))

    return matches


async def process_matched_corrections(matches: list[tuple[str, dict]]) -> dict:
    """매칭된 ``(fact_id, correction)`` 쌍에 대해 ``record_retraction`` 호출."""
    stats = {"recorded": 0, "errors": 0}
    for fact_id, corr in matches:
        reason = (
            f"[{corr.get('outlet', '?')}] {corr.get('title', '')} "
            f"({corr.get('date', '?')})\n"
            f"{corr.get('correction_text', '')[:1500]}"
        )
        try:
            await record_retraction(
                fact_id=fact_id,
                retracted_by=f"press:{corr.get('outlet', 'unknown')}",
                retraction_url=corr.get("correction_url") or None,
                retraction_type="correction_notice",
                reason=reason[:3800],
                detected_by=f"press_scraper:{corr.get('outlet', 'unknown')}",
            )
            stats["recorded"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("record_retraction failed fact=%s: %s", fact_id, exc)
            stats["errors"] += 1
    return stats


# ─────────────────────────────────────────────
# 전체 스캔
# ─────────────────────────────────────────────
async def run_full_press_scan(similarity_threshold: float = 0.7) -> dict:
    """모든 언론사 + PAC 병렬 스크래핑 → 매칭 → 정정 기록.

    Returns::

        {"outlets_scanned": N, "corrections_found": M,
         "matched": K, "recorded": J, "started_at": ..., "finished_at": ...}
    """
    started = _utcnow()
    outlets = list(KOREAN_PRESS_CORRECTION_PAGES.keys())

    tasks = []
    for o in outlets:
        if o == "press_arbitration":
            tasks.append(asyncio.create_task(scrape_press_arbitration()))
        else:
            tasks.append(asyncio.create_task(scrape_correction_page(o)))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    all_corrections: list[dict] = []
    for o, res in zip(outlets, results):
        if isinstance(res, Exception):
            logger.warning("scrape %s raised: %s", o, res)
            continue
        if not res:
            continue
        all_corrections.extend(res)

    matches = await match_corrections_to_facts(
        all_corrections, similarity_threshold=similarity_threshold
    )
    record_stats = await process_matched_corrections(matches)

    finished = _utcnow()
    out = {
        "outlets_scanned": len(outlets),
        "corrections_found": len(all_corrections),
        "matched": len(matches),
        "recorded": record_stats.get("recorded", 0),
        "errors": record_stats.get("errors", 0),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_sec": (finished - started).total_seconds(),
    }
    logger.info("[press_correction_scraper] run_full_press_scan → %s", out)
    return out


__all__ = [
    "KOREAN_PRESS_CORRECTION_PAGES",
    "HAS_BS4",
    "scrape_correction_page",
    "scrape_press_arbitration",
    "scrape_kpcc_official",
    "match_corrections_to_facts",
    "process_matched_corrections",
    "run_full_press_scan",
    "extract_article_url_from_correction",
    "normalize_outlet_url",
]
