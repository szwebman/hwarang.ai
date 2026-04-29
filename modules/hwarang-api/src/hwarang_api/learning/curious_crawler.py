"""HSEE Phase 5 — Curious Crawler.

기존 정기 분산 크롤(``crawl_dispatcher``) 외에, 우선순위 높은 ``KnowledgeGap``
을 채우기 위한 표적 크롤을 실행한다.

흐름:
  1. ``get_priority_gaps()`` 로 상위 N 개 gap 조회
  2. LLM 으로 gap 당 검색 쿼리 5개 생성
  3. 도메인이 매칭되는 ``TrustedSource`` (whitelisted) 에 대해 출처별 검색
     - 정부 OpenAPI (예: 법제처 ``law.go.kr``)
     - 일반 사이트는 stub (TODO: Google Programmable Search 등)
  4. 새 URL 만 ``CrawlJob`` 큐에 push — 분산 크롤러 / 마스터 fallback 가 처리
  5. 처리한 gap 의 status 를 ``crawling`` 으로 업데이트

매 1시간 cron 으로 ``proactive_crawl_cycle()`` 호출.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as _llm_chat
from hwarang_api.learning.gap_detector import get_priority_gaps

logger = logging.getLogger(__name__)


QUERY_GEN_PROMPT = """이 토픽에 대한 신뢰할 만한 정보를 찾기 위한 한국어 검색 쿼리 5개를 생성해라.
형식: JSON 배열 ["쿼리1", "쿼리2", "쿼리3", "쿼리4", "쿼리5"]
토픽: {topic}
도메인: {domain}
JSON 만 출력:"""


# 출처당 큐잉할 쿼리 수 / 쿼리당 URL 수
_MAX_QUERIES_PER_SOURCE = 3
_MAX_URLS_PER_QUERY = 5
_MAX_SOURCES_PER_GAP = 5


def _prisma_ready() -> bool:
    try:
        return bool(prisma.is_connected())
    except Exception:
        return False


def _parse_queries(raw: str) -> list[str]:
    """LLM 출력에서 한국어 쿼리 리스트 파싱."""
    if not raw:
        return []
    try:
        m = re.search(r"\[.*?\]", raw, re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group())
        if not isinstance(data, list):
            return []
        out: list[str] = []
        for q in data:
            if isinstance(q, str) and q.strip():
                cleaned = q.strip()
                if 2 <= len(cleaned) <= 200:
                    out.append(cleaned)
        return out[:5]
    except Exception as exc:  # noqa: BLE001
        logger.debug("query parse failed: %s", exc)
        return []


# ───────────────────────────────────────────────────────────────
# 진입점 : proactive_crawl_cycle
# ───────────────────────────────────────────────────────────────
async def proactive_crawl_cycle(gap_limit: int = 10) -> dict[str, Any]:
    """매 1시간 cron — 우선순위 gap 에 대해 표적 크롤 큐잉."""
    if not _prisma_ready():
        return {"crawls_queued": 0, "reason": "db_unavailable"}

    gaps = await get_priority_gaps(limit=gap_limit)
    if not gaps:
        return {"crawls_queued": 0, "gaps_processed": 0, "reason": "no_gaps"}

    crawls_queued = 0
    gaps_with_results: list[str] = []

    for gap in gaps:
        topic = gap["topic"]
        domain = gap["domain"]
        priority_score = float(gap.get("priority", 1.0))

        # 1) 검색 쿼리 생성
        try:
            raw = await _llm_chat(
                QUERY_GEN_PROMPT.format(topic=topic, domain=domain),
                max_tokens=256,
            )
            queries = _parse_queries(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("query gen failed for %r: %s", topic, exc)
            continue

        if not queries:
            continue

        # 2) 도메인 매칭 출처 조회
        try:
            sources = await prisma.trustedsource.find_many(
                where={
                    "isWhitelisted": True,
                    "isActive": True,
                    "domains": {"hasSome": [domain]},
                },
                take=_MAX_SOURCES_PER_GAP,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("trustedsource query failed: %s", exc)
            sources = []

        if not sources:
            # 도메인 매치가 없으면 type=government 로 fallback
            try:
                sources = await prisma.trustedsource.find_many(
                    where={
                        "isWhitelisted": True,
                        "isActive": True,
                        "type": "government",
                    },
                    take=_MAX_SOURCES_PER_GAP,
                )
            except Exception:  # noqa: BLE001
                sources = []

        # 3) 출처×쿼리 cross-product → URL 후보 수집 → CrawlJob.create
        gap_queued_here = 0
        for src in sources:
            for query in queries[:_MAX_QUERIES_PER_SOURCE]:
                urls = await _search_source(src, query)
                for url in urls[:_MAX_URLS_PER_QUERY]:
                    if not url:
                        continue
                    try:
                        await prisma.crawljob.create(
                            data={
                                "sourceId": src.id,
                                "url": url,
                                "jobType": "page_extract",
                                "metadata": {
                                    "query": query,
                                    "gap_topic": topic,
                                    "trigger": "curious_crawler",
                                },
                                "priority": int(priority_score * 100),
                            }
                        )
                        crawls_queued += 1
                        gap_queued_here += 1
                    except Exception:  # noqa: BLE001
                        # unique 제약 / 이미 큐 — 무시
                        pass

        if gap_queued_here > 0 and gap.get("id"):
            gaps_with_results.append(topic)
            try:
                await prisma.knowledgegap.update(
                    where={"id": gap["id"]},
                    data={
                        "status": "crawling",
                        "searchAttempts": {"increment": 1},
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("gap status update failed: %s", exc)

    return {
        "gaps_processed": len(gaps),
        "gaps_with_crawls": len(gaps_with_results),
        "crawls_queued": crawls_queued,
    }


# ───────────────────────────────────────────────────────────────
# 출처별 검색 (분기)
# ───────────────────────────────────────────────────────────────
async def _search_source(source: Any, query: str) -> list[str]:
    """출처 도메인에 따라 검색 — API 가 있으면 API, 아니면 stub."""
    domain = getattr(source, "domain", "") or ""

    if domain == "law.go.kr":
        return await _search_law_go_kr(query, getattr(source, "apiKey", None))
    if domain == "kostat.go.kr":
        return await _search_kostat(query)

    # 일반 사이트는 site: 검색이나 자체 검색 인덱스가 필요.
    # TODO: Google Programmable Search Engine 또는 자체 search index 통합.
    return []


async def _search_law_go_kr(query: str, api_key: str | None) -> list[str]:
    """법제처 OpenAPI 키워드 검색 — API 키 있을 때만 동작."""
    if not api_key or not query:
        return []
    try:
        import httpx
    except Exception:
        return []

    url = (
        "https://www.law.go.kr/DRF/lawSearch.do"
        f"?OC={api_key}&target=law&query={query}&type=JSON"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.debug("law.go.kr search failed: %s", exc)
        return []

    items = data.get("LawSearch", {}).get("law", []) or []
    out: list[str] = []
    for it in items[:10]:
        law_id = it.get("법령ID") or it.get("법령일련번호")
        if law_id:
            out.append(
                f"https://www.law.go.kr/lsInfoP.do?lsiSeq={law_id}"
            )
    return out


async def _search_kostat(query: str) -> list[str]:
    """통계청 검색 — TODO: 통계청 사이트 검색 / KOSIS API."""
    return []


__all__ = ["proactive_crawl_cycle"]
