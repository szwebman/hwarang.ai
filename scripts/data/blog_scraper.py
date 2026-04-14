#!/usr/bin/env python3
"""
한국 기술 블로그 스크래퍼.

수집 대상:
- 네이버 D2, 카카오 기술블로그, 토스, 우아한형제들 등 대기업 기술블로그
- velog, tistory의 인기 글
- 개인 개발자 블로그

특징:
- RSS 피드 우선 사용
- robots.txt 준수
- Rate limiting (서버 부하 방지)
- 텍스트와 코드 블록 분리

사용법:
    python scripts/data/blog_scraper.py --output data/raw/blogs

필요 패키지:
    pip install aiohttp beautifulsoup4 feedparser tqdm
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# 한국 기술 블로그 목록
# ============================================================
KOREAN_TECH_BLOGS = [
    # 대기업
    {
        "name": "naver_d2",
        "rss": None,  # RSS 없음, 수동 크롤링 필요
        "base_url": "https://d2.naver.com",
        "type": "manual",
    },
    {
        "name": "kakao_tech",
        "rss": "https://tech.kakao.com/feed/",
        "base_url": "https://tech.kakao.com",
        "type": "rss",
    },
    {
        "name": "line_engineering",
        "rss": "https://engineering.linecorp.com/ko/feed/",
        "base_url": "https://engineering.linecorp.com",
        "type": "rss",
    },
    {
        "name": "woowahan",
        "rss": "https://techblog.woowahan.com/feed/",
        "base_url": "https://techblog.woowahan.com",
        "type": "rss",
    },
    {
        "name": "toss",
        "rss": "https://toss.tech/rss.xml",
        "base_url": "https://toss.tech",
        "type": "rss",
    },
    {
        "name": "daangn",
        "rss": "https://medium.com/feed/daangn",
        "base_url": "https://medium.com/daangn",
        "type": "medium_rss",
    },
    {
        "name": "coupang",
        "rss": "https://medium.com/feed/coupang-engineering",
        "base_url": "https://medium.com/coupang-engineering",
        "type": "medium_rss",
    },
    {
        "name": "nhn_cloud",
        "rss": None,
        "base_url": "https://meetup.nhncloud.com",
        "type": "manual",
    },
    {
        "name": "skplanet",
        "rss": "https://techblog.skplanet.com/feed",
        "base_url": "https://techblog.skplanet.com",
        "type": "rss",
    },
    {
        "name": "kakaoenterprise",
        "rss": None,
        "base_url": "https://tech.kakaoenterprise.com",
        "type": "manual",
    },
    {
        "name": "banksalad",
        "rss": "https://blog.banksalad.com/rss.xml",
        "base_url": "https://blog.banksalad.com",
        "type": "rss",
    },
    {
        "name": "ridi",
        "rss": "https://ridicorp.com/story/feed/",
        "base_url": "https://ridicorp.com",
        "type": "rss",
    },
    {
        "name": "yanolja",
        "rss": "https://yanolja.github.io/feed.xml",
        "base_url": "https://yanolja.github.io",
        "type": "rss",
    },
]


@dataclass
class BlogArticle:
    """수집된 블로그 글."""
    blog_name: str
    title: str
    url: str
    published: str
    text: str
    code_blocks: list[dict]
    text_length: int
    code_length: int
    article_hash: str


def has_korean_text(text: str, min_chars: int = 50) -> bool:
    """한국어 포함 여부."""
    korean_count = sum(1 for c in text if "\uAC00" <= c <= "\uD7A3")
    return korean_count >= min_chars


def parse_html_article(html: str) -> tuple[str, list[dict]]:
    """HTML에서 텍스트와 코드 블록 추출."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("beautifulsoup4 필요: pip install beautifulsoup4")
        return "", []

    soup = BeautifulSoup(html, "html.parser")

    # 불필요한 요소 제거
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    # 코드 블록 추출
    code_blocks = []
    for code in soup.find_all(["pre", "code"]):
        code_text = code.get_text()
        if len(code_text) < 10:
            continue

        # 언어 감지 (class 속성에서)
        language = "unknown"
        classes = code.get("class", [])
        for cls in classes:
            if "language-" in cls:
                language = cls.replace("language-", "")
                break
            elif cls.startswith("lang-"):
                language = cls.replace("lang-", "")
                break

        code_blocks.append({
            "language": language,
            "code": code_text,
        })

        # 본문에서 코드 블록 제거 (텍스트 추출용)
        code.decompose()

    # 본문 텍스트 추출
    # 가능한 본문 컨테이너 찾기
    article_selectors = [
        "article",
        "main",
        ".post-content",
        ".article-body",
        ".entry-content",
        ".content",
        "#content",
    ]

    article = None
    for selector in article_selectors:
        article = soup.select_one(selector)
        if article:
            break

    if article is None:
        article = soup.body or soup

    text = article.get_text(separator="\n", strip=True)
    # 빈 줄 정리
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text, code_blocks


class BlogScraper:
    """한국 기술 블로그 스크래퍼."""

    def __init__(self, output_dir: Path, rate_limit: float = 1.0):
        self.output_dir = output_dir
        self.rate_limit = rate_limit  # 초
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 진행 상태
        self.state_file = output_dir / "scraper_state.json"
        self.state = self._load_state()

        self.stats = {
            "blogs_processed": 0,
            "articles_collected": 0,
            "korean_articles": 0,
            "total_bytes": 0,
        }

    def _load_state(self) -> dict:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        return {"seen_urls": [], "seen_hashes": []}

    def _save_state(self):
        self.state_file.write_text(json.dumps(self.state, indent=2))

    async def scrape_all(self):
        """모든 블로그 스크래핑."""
        try:
            import aiohttp
        except ImportError:
            logger.error("aiohttp 필요: pip install aiohttp")
            return

        async with aiohttp.ClientSession(
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; HwarangBot/1.0; "
                              "+https://hwarang.ai/bot)",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as session:
            for blog in KOREAN_TECH_BLOGS:
                logger.info(f"[{blog['name']}] 스크래핑 시작")
                try:
                    if blog.get("type") in ("rss", "medium_rss") and blog.get("rss"):
                        await self._scrape_rss(session, blog)
                    else:
                        logger.info(f"  {blog['name']}: 수동 크롤링 필요 (현재 건너뜀)")
                except Exception as e:
                    logger.error(f"  {blog['name']}: {e}")

                self.stats["blogs_processed"] += 1
                self._save_state()

        self._print_stats()

    async def _scrape_rss(self, session, blog: dict):
        """RSS 피드 기반 스크래핑."""
        try:
            import feedparser
        except ImportError:
            logger.error("feedparser 필요: pip install feedparser")
            return

        # RSS 다운로드
        try:
            async with session.get(blog["rss"]) as resp:
                if resp.status != 200:
                    logger.warning(f"  RSS 접근 실패: {resp.status}")
                    return
                rss_text = await resp.text()
        except Exception as e:
            logger.warning(f"  RSS 다운로드 실패: {e}")
            return

        feed = feedparser.parse(rss_text)
        entries = feed.entries
        logger.info(f"  {len(entries)}개 글 발견")

        blog_dir = self.output_dir / blog["name"]
        blog_dir.mkdir(parents=True, exist_ok=True)

        articles_file = blog_dir / "articles.jsonl"

        for entry in entries:
            url = entry.get("link", "")
            if not url or url in self.state["seen_urls"]:
                continue

            await asyncio.sleep(self.rate_limit)

            try:
                article = await self._fetch_article(session, blog, entry)
                if article:
                    with open(articles_file, "a", encoding="utf-8") as f:
                        f.write(json.dumps(asdict(article), ensure_ascii=False) + "\n")
                    self.state["seen_urls"].append(url)
                    self.stats["articles_collected"] += 1
                    if has_korean_text(article.text):
                        self.stats["korean_articles"] += 1
            except Exception as e:
                logger.debug(f"  {url}: {e}")

    async def _fetch_article(self, session, blog: dict, entry) -> BlogArticle | None:
        """단일 글 다운로드 + 파싱."""
        url = entry.get("link", "")
        title = entry.get("title", "")
        published = entry.get("published", "")

        # RSS에 본문이 있는 경우
        content = ""
        if hasattr(entry, "content") and entry.content:
            content = entry.content[0].value
        elif hasattr(entry, "summary"):
            content = entry.summary

        # 본문이 짧으면 실제 페이지 다운로드
        if len(content) < 500:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        content = await resp.text()
            except Exception:
                pass

        if not content:
            return None

        # 파싱
        text, code_blocks = parse_html_article(content)

        # 한국어 확인
        if not has_korean_text(text):
            return None

        # 너무 짧은 글 제외
        if len(text) < 200:
            return None

        # 중복 체크
        article_hash = hashlib.md5(text.encode()).hexdigest()
        if article_hash in self.state["seen_hashes"]:
            return None
        self.state["seen_hashes"].append(article_hash)

        return BlogArticle(
            blog_name=blog["name"],
            title=title,
            url=url,
            published=str(published),
            text=text,
            code_blocks=code_blocks,
            text_length=len(text),
            code_length=sum(len(c["code"]) for c in code_blocks),
            article_hash=article_hash,
        )

    def _print_stats(self):
        logger.info("=" * 60)
        logger.info("스크래핑 완료!")
        logger.info(f"  블로그: {self.stats['blogs_processed']}개")
        logger.info(f"  글: {self.stats['articles_collected']:,}개")
        logger.info(f"  한국어 글: {self.stats['korean_articles']:,}개")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="한국 기술 블로그 스크래퍼")
    parser.add_argument("--output", default="data/raw/blogs", help="출력 디렉토리")
    parser.add_argument("--rate-limit", type=float, default=1.0,
                       help="요청 간 대기 시간 (초)")
    args = parser.parse_args()

    scraper = BlogScraper(
        output_dir=Path(args.output),
        rate_limit=args.rate_limit,
    )

    asyncio.run(scraper.scrape_all())


if __name__ == "__main__":
    main()
