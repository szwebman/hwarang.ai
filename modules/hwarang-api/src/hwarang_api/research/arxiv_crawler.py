"""arxiv 매일 논문 수집.

매일 06:00 KST cron:
1. cs.AI / cs.CL / cs.LG / stat.ML 카테고리 신규 논문 list
2. 화랑 관련 키워드 필터 (LLM, alignment, RAG, MoE, federated, LoRA, Korean 등)
3. 각 논문 → Paper Prisma upsert (pending 상태로)
4. 중복 (arxivId unique) 자동 dedup

arxiv API: http://export.arxiv.org/api/query (무료, no key)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


ARXIV_API = "http://export.arxiv.org/api/query"


# 화랑 관련 키워드 (LLM/AI 일반 — 26개 기법 스택과 정렬)
HWARANG_KEYWORDS = [
    # 기반 모델
    "large language model", "LLM", "transformer",
    # 학습 / 어댑터
    "fine-tuning", "LoRA", "PEFT", "adapter",
    "federated learning", "distributed training",
    # RAG
    "RAG", "retrieval augmented",
    # MoE
    "MoE", "mixture of experts",
    # 지식 / 메모리
    "knowledge graph", "knowledge distillation",
    # 정렬
    "alignment", "RLHF", "DPO", "RLAIF",
    # 추론
    "reasoning", "chain of thought", "CoT",
    # 추론 최적화
    "speculative decoding", "inference optimization",
    # 한국어
    "Korean", "한국어",
    # 적응
    "domain adaptation", "continual learning",
    # 양자화 / 서빙
    "vLLM", "quantization", "AWQ", "GPTQ",
    # 자기개선
    "active learning", "self-improvement",
]


async def fetch_recent_papers(
    categories: Optional[list[str]] = None,
    days_back: int = 1,
    max_results: int = 200,
) -> list[dict]:
    """최근 N일 논문 list."""
    if categories is None:
        categories = ["cs.AI", "cs.CL", "cs.LG", "stat.ML"]

    cat_query = "+OR+".join(f"cat:{c}" for c in categories)

    # 최근 N 일
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=days_back)
    ).strftime("%Y%m%d%H%M%S")

    params = {
        "search_query": (
            f"({cat_query})+AND+submittedDate:[{cutoff}+TO+999999999999]"
        ),
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    try:
        # feedparser 지연 임포트 — 패키지 부재 시에도 모듈 import 자체는 성공
        import feedparser  # type: ignore

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(ARXIV_API, params=params)
        feed = feedparser.parse(resp.text)
        return [_parse_entry(e) for e in feed.entries]
    except ImportError:
        logger.warning("feedparser 미설치 — arxiv crawl 비활성")
        return []
    except Exception as e:  # noqa: BLE001
        logger.warning("arxiv fetch 실패: %s", e)
        return []


def _parse_entry(entry) -> dict:
    """feedparser entry → dict."""
    # entry.id: "http://arxiv.org/abs/2404.16710v2"
    arxiv_id = entry.id.split("/abs/")[-1].split("v")[0]  # "2404.16710"

    authors = [a.name for a in getattr(entry, "authors", [])]

    pdf_url = None
    code_url = None
    for link in getattr(entry, "links", []):
        if link.get("type") == "application/pdf":
            pdf_url = link["href"]
        elif "github" in link.get("href", "").lower():
            code_url = link["href"]

    categories = []
    for tag in getattr(entry, "tags", []):
        categories.append(tag.term)

    return {
        "arxivId": arxiv_id,
        "title": entry.title.strip().replace("\n", " "),
        "authors": authors,
        "abstract": entry.summary.strip().replace("\n", " "),
        "publishedAt": _parse_arxiv_date(entry.published),
        "pdfUrl": pdf_url or f"https://arxiv.org/pdf/{arxiv_id}.pdf",
        "codeUrl": code_url,
        "categories": categories,
    }


def _parse_arxiv_date(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def is_hwarang_relevant(paper: dict) -> tuple[bool, list[str]]:
    """제목+초록에 화랑 키워드 매칭. (1단계 빠른 필터)"""
    text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
    matched = [k for k in HWARANG_KEYWORDS if k.lower() in text]
    return len(matched) >= 1, matched


async def daily_arxiv_cycle() -> dict:
    """매일 06:00 KST cron — 신규 논문 수집 + Paper upsert."""
    started = datetime.now(timezone.utc)

    raw = await fetch_recent_papers(days_back=1, max_results=300)
    if not raw:
        return {"fetched": 0, "reason": "arxiv_no_results"}

    relevant: list[dict] = []
    for p in raw:
        ok, keywords = is_hwarang_relevant(p)
        if ok:
            p["keywords"] = keywords
            relevant.append(p)

    saved = 0
    skipped = 0
    for p in relevant:
        try:
            await prisma.paper.upsert(
                where={"arxivId": p["arxivId"]},
                data={
                    "create": {
                        "arxivId": p["arxivId"],
                        "source": "arxiv",
                        "title": p["title"][:500],
                        "authors": p["authors"][:30],
                        "abstract": p["abstract"][:5000],
                        "pdfUrl": p["pdfUrl"],
                        "codeUrl": p.get("codeUrl"),
                        "categories": p["categories"][:10],
                        "keywords": p.get("keywords", [])[:20],
                        "publishedAt": p["publishedAt"],
                        "status": "pending",
                    },
                    "update": {
                        "title": p["title"][:500],
                        "abstract": p["abstract"][:5000],
                    },
                },
            )
            saved += 1
        except Exception as e:  # noqa: BLE001
            skipped += 1
            logger.debug("Paper upsert 실패 %s: %s", p.get("arxivId"), e)

    return {
        "fetched": len(raw),
        "relevant": len(relevant),
        "saved": saved,
        "skipped": skipped,
        "elapsed_seconds": (
            datetime.now(timezone.utc) - started
        ).total_seconds(),
    }


# OpenReview 어댑터 (선택 — 동일 인터페이스, 현재는 stub)
async def fetch_openreview_papers(venue: str = "ICLR.cc/2025") -> list[dict]:
    """OpenReview API 로 학회 accepted 논문 수집.

    https://docs.openreview.net/getting-started/using-the-api/notes
    TODO: 키 없이 가능, 단순 구현. 현재는 stub.
    """
    logger.info("openreview fetch stub: venue=%s", venue)
    return []
