"""코딩 출처 통합 크롤러 — GitHub Releases / SO / HN / 한국 tech 블로그.

매 1시간 cron 으로 호출. 4 어댑터를 동시 fetch (asyncio.gather) 한 뒤
HLKM ``ingest_fact`` 로 ``domain="code"`` 사실로 저장.

사용:
    from hwarang_api.research.dev_source_crawler import daily_dev_crawl
    stats = await daily_dev_crawl()  # {"github_releases": ..., ...}
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

try:  # 선택 의존성 — 없으면 RSS 어댑터만 비활성
    import feedparser  # type: ignore
except Exception:  # noqa: BLE001
    feedparser = None  # type: ignore

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 데이터 클래스
# ---------------------------------------------------------------------------
@dataclass
class CodeArticle:
    """크롤된 코딩 글 1건."""

    title: str
    url: str
    content: str  # 본문 (최대 5000자)
    source_domain: str
    source_name: str
    code_blocks: list[str] = field(default_factory=list)  # 추출된 코드 블록
    language: str | None = None
    tags: list[str] = field(default_factory=list)
    published_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# GitHub Releases (인기 라이브러리)
# ---------------------------------------------------------------------------
POPULAR_REPOS: list[str] = [
    # JavaScript/TypeScript
    "facebook/react",
    "vercel/next.js",
    "vuejs/vue",
    "sveltejs/svelte",
    "shadcn-ui/ui",
    "tailwindlabs/tailwindcss",
    "trpc/trpc",
    # Python
    "python/cpython",
    "fastapi/fastapi",
    "pytorch/pytorch",
    "huggingface/transformers",
    "vllm-project/vllm",
    "langchain-ai/langchain",
    # Rust
    "rust-lang/rust",
    "tauri-apps/tauri",
    "tokio-rs/tokio",
    # Go
    "golang/go",
    "kubernetes/kubernetes",
    # AI/ML 도구
    "openai/openai-python",
    "anthropics/anthropic-sdk-python",
    "ollama/ollama",
    "ggerganov/llama.cpp",
]


async def fetch_github_releases(
    token: str | None = None, limit_repos: int = 20
) -> list[CodeArticle]:
    """주요 레포의 최근 releases 가져오기. 토큰 있으면 rate limit 5000/h."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    articles: list[CodeArticle] = []
    async with httpx.AsyncClient(timeout=15) as client:
        for repo in POPULAR_REPOS[:limit_repos]:
            try:
                resp = await client.get(
                    f"https://api.github.com/repos/{repo}/releases",
                    headers=headers,
                    params={"per_page": 3},
                )
                if resp.status_code != 200:
                    logger.debug(
                        "GitHub releases %s status=%d", repo, resp.status_code
                    )
                    continue
                releases = resp.json()
                for r in releases[:3]:
                    body = r.get("body") or ""
                    if not body:
                        continue
                    code_blocks = _extract_code_blocks(body)
                    articles.append(
                        CodeArticle(
                            title=f"{repo} {r.get('tag_name', '')}: {r.get('name') or ''}".strip(),
                            url=r.get("html_url", f"https://github.com/{repo}"),
                            content=body[:5000],
                            source_domain="github.com",
                            source_name=f"GitHub: {repo}",
                            code_blocks=code_blocks[:5],
                            language=_guess_language_from_repo(repo),
                            tags=[repo.split("/")[1], r.get("tag_name", "")],
                            published_at=_parse_iso(r.get("published_at")),
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("GitHub release %s 실패: %s", repo, exc)

    return articles


# ---------------------------------------------------------------------------
# Hacker News (베스트 RSS)
# ---------------------------------------------------------------------------
async def fetch_hackernews_best(top_k: int = 30) -> list[CodeArticle]:
    """HN 베스트 RSS — hnrss.org 가 HN API 를 RSS 로 바꿔줌."""
    if feedparser is None:
        logger.warning("feedparser 미설치 → HN 어댑터 skip")
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://hnrss.org/best?count={top_k}")
        feed = feedparser.parse(resp.text)
        return [
            CodeArticle(
                title=getattr(e, "title", ""),
                url=getattr(e, "link", ""),
                content=_strip_html(getattr(e, "summary", ""))[:3000],
                source_domain="news.ycombinator.com",
                source_name="Hacker News",
                code_blocks=[],
                language=None,
                tags=[],
                published_at=_parse_struct(getattr(e, "published_parsed", None)),
            )
            for e in feed.entries[:top_k]
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("HN fetch 실패: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Stack Overflow (StackExchange API)
# ---------------------------------------------------------------------------
async def fetch_stackoverflow_top(
    tags: list[str] | None = None, top_k: int = 50
) -> list[CodeArticle]:
    """SO 최근 인기 질문 (태그 필터, 본문 포함)."""
    tag_filter = ";".join(
        tags or ["python", "javascript", "react", "typescript"]
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.stackexchange.com/2.3/questions",
                params={
                    "site": "stackoverflow",
                    "tagged": tag_filter,
                    "sort": "votes",
                    "order": "desc",
                    "fromdate": int(
                        (
                            datetime.now(timezone.utc) - timedelta(days=7)
                        ).timestamp()
                    ),
                    "pagesize": min(top_k, 100),
                    "filter": "withbody",
                },
            )
        if resp.status_code != 200:
            logger.debug("SO API status=%d", resp.status_code)
            return []
        data = resp.json()
        articles: list[CodeArticle] = []
        for q in data.get("items", [])[:top_k]:
            body = q.get("body", "")
            articles.append(
                CodeArticle(
                    title=q.get("title", ""),
                    url=q.get("link", ""),
                    content=_strip_html(body)[:3000],
                    source_domain="stackoverflow.com",
                    source_name="Stack Overflow",
                    code_blocks=_extract_code_blocks(body),
                    language=(q.get("tags") or ["unknown"])[0],
                    tags=q.get("tags", []),
                    published_at=datetime.fromtimestamp(
                        q.get("creation_date", 0), tz=timezone.utc
                    ),
                )
            )
        return articles
    except Exception as exc:  # noqa: BLE001
        logger.warning("SO fetch 실패: %s", exc)
        return []


# ---------------------------------------------------------------------------
# 한국 tech 블로그 (RSS 통합)
# ---------------------------------------------------------------------------
KOREAN_TECH_RSS: list[tuple[str, str, str]] = [
    ("tech.kakao.com", "카카오 tech", "https://tech.kakao.com/feed/"),
    ("d2.naver.com", "NAVER D2", "https://d2.naver.com/d2.atom"),
    (
        "techblog.woowahan.com",
        "우아한형제들",
        "https://techblog.woowahan.com/feed/",
    ),
    ("toss.tech", "토스 tech", "https://toss.tech/rss.xml"),
    (
        "engineering.linecorp.com",
        "LINE Engineering",
        "https://engineering.linecorp.com/ko/feed/",
    ),
]


async def fetch_korean_tech_blogs() -> list[CodeArticle]:
    """5개 한국 tech 블로그 RSS 통합 fetch."""
    if feedparser is None:
        logger.warning("feedparser 미설치 → KR RSS 어댑터 skip")
        return []
    articles: list[CodeArticle] = []
    async with httpx.AsyncClient(timeout=15) as client:
        for domain, name, rss_url in KOREAN_TECH_RSS:
            try:
                resp = await client.get(rss_url)
                feed = feedparser.parse(resp.text)
                for e in feed.entries[:10]:
                    body = getattr(e, "summary", "") or ""
                    if not body:
                        content_attr = getattr(e, "content", None)
                        if content_attr and isinstance(content_attr, list):
                            body = content_attr[0].get("value", "") if isinstance(content_attr[0], dict) else ""
                    articles.append(
                        CodeArticle(
                            title=getattr(e, "title", ""),
                            url=getattr(e, "link", ""),
                            content=_strip_html(body)[:3000],
                            source_domain=domain,
                            source_name=name,
                            code_blocks=_extract_code_blocks(body),
                            language=None,
                            tags=[
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
# 통합 사이클 (cron 진입점)
# ---------------------------------------------------------------------------
async def daily_dev_crawl() -> dict:
    """매 1시간 cron — 4 어댑터 동시 fetch + HLKM ingest.

    반환::

        {
          "github_releases": int,
          "hackernews": int,
          "stackoverflow": int,
          "korean_tech": int,
          "fetched_total": int,
          "saved_to_hlkm": int,
          "skipped_unknown_source": int,
          "elapsed_seconds": float,
        }
    """
    started = datetime.now(timezone.utc)
    github_token = os.getenv("HWARANG_GITHUB_TOKEN") or None

    gh, hn, so, kr = await asyncio.gather(
        fetch_github_releases(github_token),
        fetch_hackernews_best(top_k=20),
        fetch_stackoverflow_top(top_k=30),
        fetch_korean_tech_blogs(),
        return_exceptions=True,
    )

    def _safe_len(x) -> int:
        return len(x) if isinstance(x, list) else 0

    all_articles: list[CodeArticle] = []
    for result in (gh, hn, so, kr):
        if isinstance(result, list):
            all_articles.extend(result)
        elif isinstance(result, Exception):
            logger.warning("dev_crawl 어댑터 예외: %s", result)

    saved = 0
    skipped = 0
    for art in all_articles:
        try:
            ok = await _ingest_code_article(art)
            if ok:
                saved += 1
            else:
                skipped += 1
        except Exception as exc:  # noqa: BLE001
            logger.debug("ingest 실패 %s: %s", art.url, exc)

    return {
        "github_releases": _safe_len(gh),
        "hackernews": _safe_len(hn),
        "stackoverflow": _safe_len(so),
        "korean_tech": _safe_len(kr),
        "fetched_total": len(all_articles),
        "saved_to_hlkm": saved,
        "skipped_unknown_source": skipped,
        "elapsed_seconds": (
            datetime.now(timezone.utc) - started
        ).total_seconds(),
    }


async def _ingest_code_article(art: CodeArticle) -> bool:
    """CodeArticle → KnowledgeFact (domain="code") + SourceCitation.

    반환: 등록 성공 True / 출처 미등록(skip) False.
    """
    from hwarang_api.knowledge.pipeline import ingest_fact
    from hwarang_api.knowledge.types import KnowledgeFact, KnowledgeVisibility

    source = await prisma.trustedsource.find_first(
        where={"domain": art.source_domain}
    )
    if not source:
        logger.debug("출처 미등록: %s", art.source_domain)
        return False

    # content: 헤더 + 본문 + 코드 블록 (최대 5000자)
    parts = [f"[{art.source_name}] {art.title}", art.content[:2000]]
    if art.code_blocks:
        parts.append("--- 코드 ---\n" + "\n\n".join(art.code_blocks[:3]))
    content = "\n\n".join(p for p in parts if p)[:5000]

    fact = KnowledgeFact(
        content=content,
        domain="code",
        tags=art.tags[:10],
        language=art.language or "en",
        valid_from=art.published_at,
        confidence_t0=source.trustLevel / 100.0,
        source=art.source_name,
        source_url=art.url,
        source_type="official",  # crawler → KYC 게이트 통과 (bypass_gate=True 이지만 안전망)
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
_CODE_BLOCK_RE = re.compile(r"```(?:\w+\n)?(.*?)```", re.DOTALL)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _extract_code_blocks(text: str) -> list[str]:
    """마크다운 ```fence``` 코드 블록 추출 (20자 이상, 최대 10개)."""
    if not text:
        return []
    blocks = _CODE_BLOCK_RE.findall(text)
    return [b.strip() for b in blocks if len(b.strip()) > 20][:10]


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
    """feedparser time.struct_time → datetime (UTC)."""
    if not t:
        return datetime.now(timezone.utc)
    try:
        return datetime(*t[:6], tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc)


_REPO_LANG_MAP: dict[str, str] = {
    "react": "javascript",
    "next.js": "javascript",
    "vue": "javascript",
    "svelte": "javascript",
    "ui": "javascript",
    "trpc": "typescript",
    "tailwindcss": "css",
    "cpython": "python",
    "fastapi": "python",
    "pytorch": "python",
    "transformers": "python",
    "vllm": "python",
    "langchain": "python",
    "openai-python": "python",
    "anthropic-sdk-python": "python",
    "rust": "rust",
    "tauri": "rust",
    "tokio": "rust",
    "go": "go",
    "kubernetes": "go",
    "ollama": "go",
    "llama.cpp": "cpp",
}


def _guess_language_from_repo(repo: str) -> str | None:
    name = repo.split("/")[1] if "/" in repo else repo
    name_lower = name.lower()
    for k, v in _REPO_LANG_MAP.items():
        if k in name_lower:
            return v
    return None


__all__ = [
    "CodeArticle",
    "POPULAR_REPOS",
    "KOREAN_TECH_RSS",
    "fetch_github_releases",
    "fetch_hackernews_best",
    "fetch_stackoverflow_top",
    "fetch_korean_tech_blogs",
    "daily_dev_crawl",
]
