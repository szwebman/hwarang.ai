"""한국 신뢰 출처 22개 초기 시드.

분류 (괄호 안은 trustLevel):
  - 정부 1차 출처 (95~100): law.go.kr, kostat.go.kr, nts.go.kr, mfds.go.kr,
    fsc.go.kr, courts.go.kr, kma.go.kr, korea.kr  (8 개)
  - 학술 (85): riss.kr, kiss.kstudy.com, dbpia.co.kr  (3 개)
  - 메이저 언론 (60~75): yna.co.kr (75), kbs/mbc/sbs (70),
    chosun/joongang/donga/hani/khan (60)  (9 개)
  - 팩트체커 (90~95): factcheck.snu.ac.kr, ftn.factchecker.or.kr  (2 개)
  - 의료 (85~90): kma.org, amc.seoul.kr, snuh.org  (3 개)

사용:
    python -m scripts.seed_trusted_sources

기존 행이 있으면 덮어쓴다 (upsert). 화이트리스트/trustLevel 만 변경하고
싶으면 관리자 UI 의 PUT /api/sources/{id} 를 사용하라.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# .env 자동 로드 — DATABASE_URL 을 prisma 가 읽도록
try:
    from dotenv import load_dotenv

    _here = Path(__file__).resolve().parent.parent  # modules/hwarang-api/
    for candidate in [_here / ".env", _here.parent / "hwarang-web" / ".env"]:
        if candidate.exists():
            load_dotenv(candidate, override=False)
except ImportError:
    pass

if not os.getenv("DATABASE_URL"):
    print(
        "❌ DATABASE_URL 이 설정되지 않았습니다. .env 파일 또는 환경변수로 지정하세요.",
        file=sys.stderr,
    )
    sys.exit(1)

from prisma import Prisma  # type: ignore


SOURCES: list[dict] = [
    # ── 정부 1차 출처 ─────────────────────────────────────────
    {
        "domain": "law.go.kr",
        "displayName": "국가법령정보센터",
        "type": "government",
        "trustLevel": 100,
        "isPrimarySource": True,
        "domains": ["legal"],
        "crawlMethod": "api",
        "apiEndpoint": "https://www.law.go.kr/DRF/lawSearch.do",
    },
    {
        "domain": "kostat.go.kr",
        "displayName": "통계청",
        "type": "government",
        "trustLevel": 100,
        "isPrimarySource": True,
        "domains": ["statistics", "economy"],
        "crawlMethod": "api",
    },
    {
        "domain": "nts.go.kr",
        "displayName": "국세청",
        "type": "government",
        "trustLevel": 100,
        "isPrimarySource": True,
        "domains": ["tax", "finance"],
        "crawlMethod": "rss",
    },
    {
        "domain": "mfds.go.kr",
        "displayName": "식약처",
        "type": "government",
        "trustLevel": 100,
        "isPrimarySource": True,
        "domains": ["medical", "food", "drug"],
        "crawlMethod": "rss",
    },
    {
        "domain": "fsc.go.kr",
        "displayName": "금융위원회",
        "type": "government",
        "trustLevel": 95,
        "isPrimarySource": True,
        "domains": ["finance"],
        "crawlMethod": "rss",
    },
    {
        "domain": "courts.go.kr",
        "displayName": "대법원 종합법률정보",
        "type": "government",
        "trustLevel": 100,
        "isPrimarySource": True,
        "domains": ["legal"],
        "crawlMethod": "api",
    },
    {
        "domain": "kma.go.kr",
        "displayName": "기상청",
        "type": "government",
        "trustLevel": 100,
        "isPrimarySource": True,
        "domains": ["weather"],
        "crawlMethod": "api",
    },
    {
        "domain": "korea.kr",
        "displayName": "정책브리핑",
        "type": "government",
        "trustLevel": 95,
        "isPrimarySource": True,
        "domains": ["policy", "government"],
        "crawlMethod": "rss",
        "rssUrl": "https://www.korea.kr/rss/policy.xml",
    },
    # ── 학술 ──────────────────────────────────────────────────
    {
        "domain": "riss.kr",
        "displayName": "RISS 학술연구정보",
        "type": "academic",
        "trustLevel": 85,
        "domains": ["academic"],
        "crawlMethod": "api",
    },
    {
        "domain": "kiss.kstudy.com",
        "displayName": "KISS 한국학술",
        "type": "academic",
        "trustLevel": 85,
        "domains": ["academic"],
        "crawlMethod": "api",
    },
    {
        "domain": "dbpia.co.kr",
        "displayName": "DBpia",
        "type": "academic",
        "trustLevel": 85,
        "domains": ["academic"],
        "crawlMethod": "api",
    },
    # ── 메이저 언론 ───────────────────────────────────────────
    {
        "domain": "yna.co.kr",
        "displayName": "연합뉴스",
        "type": "news_major",
        "trustLevel": 75,
        "domains": ["news"],
        "crawlMethod": "rss",
        "rssUrl": "https://www.yna.co.kr/rss/news.xml",
    },
    {
        "domain": "kbs.co.kr",
        "displayName": "KBS 뉴스",
        "type": "news_major",
        "trustLevel": 70,
        "domains": ["news"],
        "crawlMethod": "rss",
        "rssUrl": "http://world.kbs.co.kr/rss/rss_news.htm?lang=k",
    },
    {
        "domain": "imnews.imbc.com",
        "displayName": "MBC 뉴스",
        "type": "news_major",
        "trustLevel": 70,
        "domains": ["news"],
        "crawlMethod": "rss",
    },
    {
        "domain": "news.sbs.co.kr",
        "displayName": "SBS 뉴스",
        "type": "news_major",
        "trustLevel": 70,
        "domains": ["news"],
        "crawlMethod": "rss",
    },
    {
        "domain": "chosun.com",
        "displayName": "조선일보",
        "type": "news_major",
        "trustLevel": 60,
        "domains": ["news"],
        "crawlMethod": "rss",
    },
    {
        "domain": "joongang.co.kr",
        "displayName": "중앙일보",
        "type": "news_major",
        "trustLevel": 60,
        "domains": ["news"],
        "crawlMethod": "rss",
    },
    {
        "domain": "donga.com",
        "displayName": "동아일보",
        "type": "news_major",
        "trustLevel": 60,
        "domains": ["news"],
        "crawlMethod": "rss",
    },
    {
        "domain": "hani.co.kr",
        "displayName": "한겨레",
        "type": "news_major",
        "trustLevel": 60,
        "domains": ["news"],
        "crawlMethod": "rss",
    },
    {
        "domain": "khan.co.kr",
        "displayName": "경향신문",
        "type": "news_major",
        "trustLevel": 60,
        "domains": ["news"],
        "crawlMethod": "rss",
    },
    # ── 팩트체커 ─────────────────────────────────────────────
    {
        "domain": "factcheck.snu.ac.kr",
        "displayName": "SNU 팩트체크",
        "type": "fact_checker",
        "trustLevel": 95,
        "domains": ["fact_check"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "ftn.factchecker.or.kr",
        "displayName": "팩트체크넷",
        "type": "fact_checker",
        "trustLevel": 90,
        "domains": ["fact_check"],
        "crawlMethod": "scraper",
    },
    # ── 의료 ─────────────────────────────────────────────────
    {
        "domain": "kma.org",
        "displayName": "대한의사협회",
        "type": "medical",
        "trustLevel": 90,
        "domains": ["medical"],
        "crawlMethod": "rss",
    },
    {
        "domain": "amc.seoul.kr",
        "displayName": "서울아산병원",
        "type": "medical",
        "trustLevel": 85,
        "domains": ["medical"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "snuh.org",
        "displayName": "서울대병원",
        "type": "medical",
        "trustLevel": 85,
        "domains": ["medical"],
        "crawlMethod": "scraper",
    },
    # ── 연구/학술 (Research Engine — Group A) ────────────────
    {
        "domain": "arxiv.org",
        "displayName": "arXiv",
        "type": "academic",
        "trustLevel": 90,
        "isPrimarySource": True,
        "domains": ["research", "ai"],
        "crawlMethod": "api",
        "apiEndpoint": "http://export.arxiv.org/api/query",
    },
    {
        "domain": "openreview.net",
        "displayName": "OpenReview",
        "type": "academic",
        "trustLevel": 85,
        "domains": ["research", "ai"],
        "crawlMethod": "api",
    },
    {
        "domain": "aclanthology.org",
        "displayName": "ACL Anthology",
        "type": "academic",
        "trustLevel": 90,
        "domains": ["research", "nlp"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "huggingface.co",
        "displayName": "Hugging Face Papers",
        "type": "academic",
        "trustLevel": 80,
        "domains": ["research", "ai"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "papers.cool",
        "displayName": "Papers.cool",
        "type": "academic",
        "trustLevel": 70,
        "domains": ["research", "ai"],
        "crawlMethod": "scraper",
    },
]


# ── Code Engine — 코딩 출처 22개 (한국 5 + 글로벌 17) ─────────────────
# 분류:
#   - 1차 출처(85~100): GitHub, 공식 docs (Python/MDN/React/Next/Rust), PyPI, npm
#   - 한국 tech 블로그(80~85): kakao/naver/woowahan/toss/line, kakaopay/ridi (낮은쪽)
#   - 글로벌 커뮤니티(60~80): HN, SO, Lobsters, dev.to, Reddit, Velog
CODING_SOURCES: list[dict] = [
    # GitHub (1차 출처)
    {
        "domain": "github.com",
        "displayName": "GitHub",
        "type": "code_platform",
        "trustLevel": 90,
        "isPrimarySource": True,
        "domains": ["coding"],
        "crawlMethod": "api",
    },
    {
        "domain": "api.github.com",
        "displayName": "GitHub API",
        "type": "code_platform",
        "trustLevel": 95,
        "isPrimarySource": True,
        "domains": ["coding"],
        "crawlMethod": "api",
    },
    # 공식 문서 (1차 출처)
    {
        "domain": "docs.python.org",
        "displayName": "Python Docs",
        "type": "official_docs",
        "trustLevel": 100,
        "isPrimarySource": True,
        "domains": ["coding"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "developer.mozilla.org",
        "displayName": "MDN Web Docs",
        "type": "official_docs",
        "trustLevel": 100,
        "isPrimarySource": True,
        "domains": ["coding"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "react.dev",
        "displayName": "React Docs",
        "type": "official_docs",
        "trustLevel": 95,
        "isPrimarySource": True,
        "domains": ["coding"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "nextjs.org",
        "displayName": "Next.js Docs",
        "type": "official_docs",
        "trustLevel": 95,
        "isPrimarySource": True,
        "domains": ["coding"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "doc.rust-lang.org",
        "displayName": "Rust Docs",
        "type": "official_docs",
        "trustLevel": 100,
        "isPrimarySource": True,
        "domains": ["coding"],
        "crawlMethod": "scraper",
    },
    # 한국 tech 블로그 (높은 신뢰도, RSS 통합)
    {
        "domain": "tech.kakao.com",
        "displayName": "카카오 tech",
        "type": "tech_blog",
        "trustLevel": 85,
        "domains": ["coding"],
        "crawlMethod": "rss",
        "rssUrl": "https://tech.kakao.com/feed/",
    },
    {
        "domain": "d2.naver.com",
        "displayName": "NAVER D2",
        "type": "tech_blog",
        "trustLevel": 85,
        "domains": ["coding"],
        "crawlMethod": "rss",
        "rssUrl": "https://d2.naver.com/d2.atom",
    },
    {
        "domain": "techblog.woowahan.com",
        "displayName": "우아한형제들 tech",
        "type": "tech_blog",
        "trustLevel": 85,
        "domains": ["coding"],
        "crawlMethod": "rss",
        "rssUrl": "https://techblog.woowahan.com/feed/",
    },
    {
        "domain": "toss.tech",
        "displayName": "토스 tech",
        "type": "tech_blog",
        "trustLevel": 85,
        "domains": ["coding"],
        "crawlMethod": "rss",
        "rssUrl": "https://toss.tech/rss.xml",
    },
    {
        "domain": "kakaopay.tech",
        "displayName": "카카오페이 tech",
        "type": "tech_blog",
        "trustLevel": 80,
        "domains": ["coding"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "ridicorp.com",
        "displayName": "리디 tech",
        "type": "tech_blog",
        "trustLevel": 80,
        "domains": ["coding"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "engineering.linecorp.com",
        "displayName": "LINE 엔지니어링",
        "type": "tech_blog",
        "trustLevel": 85,
        "domains": ["coding"],
        "crawlMethod": "rss",
        "rssUrl": "https://engineering.linecorp.com/ko/feed/",
    },
    {
        "domain": "v3.velog.io",
        "displayName": "Velog 트렌딩",
        "type": "tech_blog",
        "trustLevel": 65,
        "domains": ["coding"],
        "crawlMethod": "scraper",
    },
    # 글로벌 커뮤니티
    {
        "domain": "news.ycombinator.com",
        "displayName": "Hacker News",
        "type": "tech_community",
        "trustLevel": 75,
        "domains": ["coding"],
        "crawlMethod": "rss",
        "rssUrl": "https://hnrss.org/best",
    },
    {
        "domain": "stackoverflow.com",
        "displayName": "Stack Overflow",
        "type": "tech_community",
        "trustLevel": 80,
        "domains": ["coding"],
        "crawlMethod": "api",
        "apiEndpoint": "https://api.stackexchange.com/2.3/questions",
    },
    {
        "domain": "lobste.rs",
        "displayName": "Lobsters",
        "type": "tech_community",
        "trustLevel": 70,
        "domains": ["coding"],
        "crawlMethod": "rss",
        "rssUrl": "https://lobste.rs/rss",
    },
    {
        "domain": "dev.to",
        "displayName": "DEV Community",
        "type": "tech_community",
        "trustLevel": 65,
        "domains": ["coding"],
        "crawlMethod": "rss",
        "rssUrl": "https://dev.to/feed",
    },
    {
        "domain": "reddit.com",
        "displayName": "Reddit r/programming",
        "type": "tech_community",
        "trustLevel": 60,
        "domains": ["coding"],
        "crawlMethod": "rss",
        "rssUrl": "https://www.reddit.com/r/programming/.rss",
    },
    # 패키지 레지스트리 (1차 출처)
    {
        "domain": "pypi.org",
        "displayName": "PyPI",
        "type": "package_registry",
        "trustLevel": 95,
        "isPrimarySource": True,
        "domains": ["coding"],
        "crawlMethod": "api",
    },
    {
        "domain": "npmjs.com",
        "displayName": "npm",
        "type": "package_registry",
        "trustLevel": 90,
        "isPrimarySource": True,
        "domains": ["coding"],
        "crawlMethod": "api",
    },
]


# ── Design Engine — 디자인 출처 19개 (한국 4 + 글로벌 15) ─────────────
# 분류:
#   - 갤러리/트렌드 (75~90): Awwwards, SiteInspire, Dribbble, Behance, Land-book
#   - 디자인 시스템 (1차, 90~100): shadcn/ui, Tailwind UI, Material, Apple HIG
#   - 디자인 블로그 글로벌 (85): Smashing, CSS-Tricks, Vercel, Linear
#   - 한국 디자인 (70~75): Brunch, 요즘IT, 퍼블리, UX Daily
#   - 컴포넌트 GitHub (코딩과 겹침, 90): shadcn-ui, radix-ui
DESIGN_SOURCES: list[dict] = [
    # ── 갤러리 / 트렌드 (1차) ─────────────────────────────────
    {
        "domain": "awwwards.com",
        "displayName": "Awwwards",
        "type": "design_gallery",
        "trustLevel": 90,
        "domains": ["design"],
        "crawlMethod": "rss",
        "rssUrl": "https://www.awwwards.com/sites_of_the_day/feed",
    },
    {
        "domain": "siteinspire.com",
        "displayName": "SiteInspire",
        "type": "design_gallery",
        "trustLevel": 80,
        "domains": ["design"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "dribbble.com",
        "displayName": "Dribbble Popular",
        "type": "design_gallery",
        "trustLevel": 75,
        "domains": ["design"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "behance.net",
        "displayName": "Behance",
        "type": "design_gallery",
        "trustLevel": 75,
        "domains": ["design"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "land-book.com",
        "displayName": "Land-book",
        "type": "design_gallery",
        "trustLevel": 80,
        "domains": ["design"],
        "crawlMethod": "scraper",
    },
    # ── UI/UX 디자인 시스템 (1차) ─────────────────────────────
    {
        "domain": "ui.shadcn.com",
        "displayName": "shadcn/ui",
        "type": "design_system",
        "trustLevel": 95,
        "isPrimarySource": True,
        "domains": ["design", "coding"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "tailwindui.com",
        "displayName": "Tailwind UI",
        "type": "design_system",
        "trustLevel": 90,
        "domains": ["design", "coding"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "material.io",
        "displayName": "Material Design",
        "type": "design_system",
        "trustLevel": 100,
        "isPrimarySource": True,
        "domains": ["design"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "developer.apple.com",
        "displayName": "Apple HIG",
        "type": "design_system",
        "trustLevel": 100,
        "isPrimarySource": True,
        "domains": ["design"],
        "crawlMethod": "scraper",
    },
    # ── 글로벌 디자인 블로그 ──────────────────────────────────
    {
        "domain": "smashingmagazine.com",
        "displayName": "Smashing Magazine",
        "type": "design_blog",
        "trustLevel": 85,
        "domains": ["design"],
        "crawlMethod": "rss",
        "rssUrl": "https://www.smashingmagazine.com/feed/",
    },
    {
        "domain": "css-tricks.com",
        "displayName": "CSS-Tricks",
        "type": "design_blog",
        "trustLevel": 85,
        "domains": ["design", "coding"],
        "crawlMethod": "rss",
        "rssUrl": "https://css-tricks.com/feed/",
    },
    {
        "domain": "vercel.com",
        "displayName": "Vercel Design",
        "type": "design_blog",
        "trustLevel": 85,
        "domains": ["design"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "linear.app",
        "displayName": "Linear Engineering",
        "type": "design_blog",
        "trustLevel": 85,
        "domains": ["design"],
        "crawlMethod": "scraper",
    },
    # ── 한국 디자인 ───────────────────────────────────────────
    {
        "domain": "brunch.co.kr",
        "displayName": "Brunch (디자인)",
        "type": "design_blog",
        "trustLevel": 70,
        "domains": ["design"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "yozm.wishket.com",
        "displayName": "요즘IT",
        "type": "design_blog",
        "trustLevel": 75,
        "domains": ["design", "coding"],
        "crawlMethod": "rss",
        "rssUrl": "https://yozm.wishket.com/magazine/rss/",
    },
    {
        "domain": "publy.co",
        "displayName": "퍼블리",
        "type": "design_blog",
        "trustLevel": 75,
        "domains": ["design"],
        "crawlMethod": "scraper",
    },
    {
        "domain": "uxdaily.kr",
        "displayName": "UX Daily",
        "type": "design_blog",
        "trustLevel": 70,
        "domains": ["design"],
        "crawlMethod": "scraper",
    },
    # ── 컴포넌트/프레임워크 GitHub (코딩과 겹침) ───────────────
    {
        "domain": "shadcn-ui",
        "displayName": "shadcn/ui Releases",
        "type": "design_system",
        "trustLevel": 90,
        "domains": ["design", "coding"],
        "crawlMethod": "api",
    },
    {
        "domain": "radix-ui",
        "displayName": "Radix UI",
        "type": "design_system",
        "trustLevel": 90,
        "domains": ["design", "coding"],
        "crawlMethod": "api",
    },
]


# 기존 SOURCES 와 합쳐서 한 번에 시드.
SOURCES = SOURCES + CODING_SOURCES + DESIGN_SOURCES


async def main() -> None:
    db = Prisma()
    await db.connect()
    try:
        seeded = 0
        for src in SOURCES:
            payload = {
                "displayName": src["displayName"],
                "type": src["type"],
                "trustLevel": src["trustLevel"],
                "isPrimarySource": src.get("isPrimarySource", False),
                "isWhitelisted": src.get("isWhitelisted", True),
                "isActive": src.get("isActive", True),
                "domains": src.get("domains", []),
                "crawlMethod": src.get("crawlMethod", "rss"),
                "rssUrl": src.get("rssUrl"),
                "apiEndpoint": src.get("apiEndpoint"),
                "apiKey": src.get("apiKey"),
                "selectorJson": src.get("selectorJson"),
                "notes": src.get("notes"),
            }
            await db.trustedsource.upsert(
                where={"domain": src["domain"]},
                data={
                    "create": {"domain": src["domain"], **payload},
                    "update": payload,
                },
            )
            seeded += 1
        print(f"✓ Seeded {seeded} trusted sources")

        # 카테고리별 분포 출력
        for t in [
            "government",
            "academic",
            "news_major",
            "fact_checker",
            "medical",
            "code_platform",
            "official_docs",
            "tech_blog",
            "tech_community",
            "package_registry",
            "design_gallery",
            "design_system",
            "design_blog",
        ]:
            n = await db.trustedsource.count(where={"type": t})
            print(f"  {t}: {n}")
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
