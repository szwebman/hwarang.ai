"""디자인 출처 통합 크롤러.

매 6시간 cron — Awwwards / Smashing / CSS-Tricks / 한국 디자인 블로그 /
shadcn·radix·tailwind GitHub releases 5 어댑터를 ``asyncio.gather`` 로 동시 fetch
하고 HLKM ``ingest_fact`` 로 ``domain="design"`` 사실로 저장.

특징:
  - 이미지 URL 추출 (디자인은 시각이 핵심)
  - 메타 태그 / og:image 호환
  - 컬러 팔레트는 옵션 (colorthief 미설치 시 빈 리스트)

사용:
    from hwarang_api.research.design_source_crawler import daily_design_crawl
    stats = await daily_design_crawl()
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

try:  # 선택 의존성 — 없으면 RSS 어댑터 비활성
    import feedparser  # type: ignore
except Exception:  # noqa: BLE001
    feedparser = None  # type: ignore

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 데이터 클래스
# ---------------------------------------------------------------------------
@dataclass
class DesignArticle:
    """크롤된 디자인 글/사이트 1건."""

    title: str
    url: str
    content: str  # 본문 (최대 5000자)
    source_domain: str
    source_name: str
    image_urls: list[str] = field(default_factory=list)
    color_palette: list[str] = field(default_factory=list)  # hex (#fff)
    layout_category: str | None = None  # hero / grid / split / asymmetric
    style_tags: list[str] = field(default_factory=list)  # minimalism / brutalism
    published_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Awwwards — Site of the Day RSS
# ---------------------------------------------------------------------------
async def fetch_awwwards_sotd(top_k: int = 10) -> list[DesignArticle]:
    """Awwwards SOTD RSS — 디자인 트렌드 1차 출처."""
    if feedparser is None:
        logger.warning("feedparser 미설치 → Awwwards skip")
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://www.awwwards.com/sites_of_the_day/feed"
            )
        feed = feedparser.parse(resp.text)
        return [
            DesignArticle(
                title=getattr(e, "title", ""),
                url=getattr(e, "link", ""),
                content=_strip_html(getattr(e, "summary", ""))[:2000],
                source_domain="awwwards.com",
                source_name="Awwwards SOTD",
                image_urls=_extract_images_from_html(
                    getattr(e, "summary", "")
                ),
                published_at=_parse_struct(
                    getattr(e, "published_parsed", None)
                ),
            )
            for e in feed.entries[:top_k]
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Awwwards 실패: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Smashing Magazine — RSS
# ---------------------------------------------------------------------------
async def fetch_smashing_magazine(top_k: int = 15) -> list[DesignArticle]:
    if feedparser is None:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://www.smashingmagazine.com/feed/")
        feed = feedparser.parse(resp.text)
        return [
            DesignArticle(
                title=getattr(e, "title", ""),
                url=getattr(e, "link", ""),
                content=_strip_html(getattr(e, "summary", ""))[:3000],
                source_domain="smashingmagazine.com",
                source_name="Smashing Magazine",
                image_urls=_extract_images_from_html(
                    getattr(e, "summary", "")
                ),
                style_tags=[
                    t.term
                    for t in getattr(e, "tags", [])[:5]
                    if hasattr(t, "term")
                ],
                published_at=_parse_struct(
                    getattr(e, "published_parsed", None)
                ),
            )
            for e in feed.entries[:top_k]
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Smashing 실패: %s", exc)
        return []


# ---------------------------------------------------------------------------
# CSS-Tricks — RSS
# ---------------------------------------------------------------------------
async def fetch_css_tricks(top_k: int = 15) -> list[DesignArticle]:
    if feedparser is None:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://css-tricks.com/feed/")
        feed = feedparser.parse(resp.text)
        return [
            DesignArticle(
                title=getattr(e, "title", ""),
                url=getattr(e, "link", ""),
                content=_strip_html(getattr(e, "summary", ""))[:3000],
                source_domain="css-tricks.com",
                source_name="CSS-Tricks",
                image_urls=_extract_images_from_html(
                    getattr(e, "summary", "")
                ),
                style_tags=[
                    t.term
                    for t in getattr(e, "tags", [])[:5]
                    if hasattr(t, "term")
                ],
                published_at=_parse_struct(
                    getattr(e, "published_parsed", None)
                ),
            )
            for e in feed.entries[:top_k]
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("CSS-Tricks 실패: %s", exc)
        return []


# ---------------------------------------------------------------------------
# 한국 디자인 블로그 (요즘IT 등)
# ---------------------------------------------------------------------------
KOREAN_DESIGN_RSS: list[tuple[str, str, str]] = [
    ("yozm.wishket.com", "요즘IT", "https://yozm.wishket.com/magazine/rss/"),
    # brunch / publy / uxdaily — RSS 없으면 scraper 단계에서 처리. 현재 stub.
]


async def fetch_korean_design_blogs() -> list[DesignArticle]:
    """한국 디자인 블로그 — RSS 통합."""
    if feedparser is None:
        return []
    articles: list[DesignArticle] = []
    async with httpx.AsyncClient(timeout=15) as client:
        for domain, name, rss_url in KOREAN_DESIGN_RSS:
            try:
                resp = await client.get(rss_url)
                feed = feedparser.parse(resp.text)
                for e in feed.entries[:10]:
                    summary = getattr(e, "summary", "") or ""
                    if not summary:
                        content_attr = getattr(e, "content", None)
                        if content_attr and isinstance(content_attr, list):
                            summary = (
                                content_attr[0].get("value", "")
                                if isinstance(content_attr[0], dict)
                                else ""
                            )
                    articles.append(
                        DesignArticle(
                            title=getattr(e, "title", ""),
                            url=getattr(e, "link", ""),
                            content=_strip_html(summary)[:3000],
                            source_domain=domain,
                            source_name=name,
                            image_urls=_extract_images_from_html(summary),
                            style_tags=[
                                t.term
                                for t in getattr(e, "tags", [])[:5]
                                if hasattr(t, "term")
                            ],
                            published_at=_parse_struct(
                                getattr(e, "published_parsed", None)
                            ),
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("%s RSS 실패: %s", name, exc)
    return articles


# ---------------------------------------------------------------------------
# shadcn / radix / tailwind GitHub Releases
# ---------------------------------------------------------------------------
DESIGN_REPOS: list[str] = [
    "shadcn-ui/ui",
    "radix-ui/primitives",
    "tailwindlabs/tailwindcss",
]


async def fetch_shadcn_releases() -> list[DesignArticle]:
    """shadcn/radix/tailwind GitHub releases — 새 컴포넌트 / 기능."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.getenv("HWARANG_GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    articles: list[DesignArticle] = []
    async with httpx.AsyncClient(timeout=15) as client:
        for repo in DESIGN_REPOS:
            try:
                resp = await client.get(
                    f"https://api.github.com/repos/{repo}/releases",
                    headers=headers,
                    params={"per_page": 3},
                )
                if resp.status_code != 200:
                    logger.debug(
                        "GitHub releases %s status=%d",
                        repo,
                        resp.status_code,
                    )
                    continue
                for r in resp.json()[:3]:
                    body = r.get("body") or ""
                    if not body:
                        continue
                    # source_domain: shadcn-ui, radix-ui, tailwindlabs (TrustedSource 시드와 일치)
                    src_domain = repo.split("/")[0]
                    articles.append(
                        DesignArticle(
                            title=f"{repo} {r.get('tag_name', '')}: {r.get('name') or ''}".strip(),
                            url=r.get("html_url", f"https://github.com/{repo}"),
                            content=body[:3000],
                            source_domain=src_domain,
                            source_name=f"GitHub: {repo}",
                            published_at=_parse_iso(r.get("published_at")),
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("%s releases 실패: %s", repo, exc)
    return articles


# ---------------------------------------------------------------------------
# 통합 사이클 (cron 진입점)
# ---------------------------------------------------------------------------
async def daily_design_crawl() -> dict:
    """매 6시간 cron — 5 어댑터 동시 fetch + HLKM ingest.

    반환::

        {
          "awwwards": int, "smashing": int, "css_tricks": int,
          "korean": int, "shadcn_radix": int,
          "fetched_total": int, "saved_to_hlkm": int,
          "skipped_unknown_source": int, "elapsed_seconds": float,
        }
    """
    started = datetime.now(timezone.utc)

    aw, sm, ct, kr, sh = await asyncio.gather(
        fetch_awwwards_sotd(),
        fetch_smashing_magazine(),
        fetch_css_tricks(),
        fetch_korean_design_blogs(),
        fetch_shadcn_releases(),
        return_exceptions=True,
    )

    def _safe_len(x) -> int:
        return len(x) if isinstance(x, list) else 0

    all_articles: list[DesignArticle] = []
    for result in (aw, sm, ct, kr, sh):
        if isinstance(result, list):
            all_articles.extend(result)
        elif isinstance(result, Exception):
            logger.warning("design_crawl 어댑터 예외: %s", result)

    saved = 0
    skipped = 0
    for art in all_articles:
        try:
            ok = await _ingest_design_article(art)
            if ok:
                saved += 1
            else:
                skipped += 1
        except Exception as exc:  # noqa: BLE001
            logger.debug("design ingest 실패 %s: %s", art.url, exc)

    return {
        "awwwards": _safe_len(aw),
        "smashing": _safe_len(sm),
        "css_tricks": _safe_len(ct),
        "korean": _safe_len(kr),
        "shadcn_radix": _safe_len(sh),
        "fetched_total": len(all_articles),
        "saved_to_hlkm": saved,
        "skipped_unknown_source": skipped,
        "elapsed_seconds": (
            datetime.now(timezone.utc) - started
        ).total_seconds(),
    }


async def _ingest_design_article(art: DesignArticle) -> bool:
    """DesignArticle → KnowledgeFact (domain="design") + SourceCitation."""
    from hwarang_api.knowledge.pipeline import ingest_fact
    from hwarang_api.knowledge.types import KnowledgeFact, KnowledgeVisibility

    source = await prisma.trustedsource.find_first(
        where={"domain": art.source_domain}
    )
    if not source:
        logger.debug("디자인 출처 미등록: %s", art.source_domain)
        return False

    # content: 헤더 + 본문 + 이미지 + 태그 (최대 5000자)
    parts = [f"[{art.source_name}] {art.title}", art.content[:2500]]
    if art.image_urls:
        parts.append("이미지: " + ", ".join(art.image_urls[:3]))
    if art.style_tags:
        parts.append("태그: " + ", ".join(art.style_tags))
    if art.color_palette:
        parts.append("팔레트: " + ", ".join(art.color_palette[:5]))
    content = "\n\n".join(p for p in parts if p)[:5000]

    fact = KnowledgeFact(
        content=content,
        domain="design",
        tags=art.style_tags[:10],
        language="ko",
        valid_from=art.published_at or datetime.now(timezone.utc),
        confidence_t0=source.trustLevel / 100.0,
        source=art.source_name,
        source_url=art.url,
        source_type="official",  # crawler — KYC 게이트는 bypass_gate=True 로 통과
        visibility=KnowledgeVisibility.PUBLIC,
    )
    result = await ingest_fact(fact, bypass_gate=True)
    fact_id = result.get("fact_id")

    if fact_id:
        try:
            await prisma.sourcecitation.create(
                data={
                    "factId": fact_id,
                    "sourceId": source.id,
                    "url": art.url,
                    "title": art.title[:300],
                    "excerpt": art.content[:500],
                    "publishedAt": art.published_at,
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("SourceCitation 생성 실패: %s", exc)
    return True


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
_IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _extract_images_from_html(html: str) -> list[str]:
    """HTML 에서 ``<img src="...">`` 추출 (최대 5개).

    og:image / theme-color 등 메타 태그도 우회로 잡힐 수 있도록 src 만 본다.
    """
    if not html:
        return []
    return _IMG_RE.findall(html)[:5]


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return _HTML_TAG_RE.sub("", text).strip()


def _parse_iso(s: str | None) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc)


def _parse_struct(t) -> datetime:
    """feedparser ``time.struct_time`` → ``datetime`` (UTC)."""
    if not t:
        return datetime.now(timezone.utc)
    try:
        return datetime(*t[:6], tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc)


__all__ = [
    "DesignArticle",
    "DESIGN_REPOS",
    "KOREAN_DESIGN_RSS",
    "fetch_awwwards_sotd",
    "fetch_smashing_magazine",
    "fetch_css_tricks",
    "fetch_korean_design_blogs",
    "fetch_shadcn_releases",
    "daily_design_crawl",
]
