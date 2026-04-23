"""HLKM A3 - HRAG 통합 브리지.

hwarang-web 측 HRAG(Human-Retrieval-Augmented Generation) 가 취합하는
한국 공공 API(law.go.kr, 기상청 등) 결과를 Knowledge Mesh 로 유입시킨다.

- 주기적으로 fetch → KnowledgeFact 빌드 → pipeline.ingest_fact 호출.
- reverse_lookup_hrag() 는 저장된 fact 의 원본 HRAG 메타를 역추적.
- sync_from_custom_source() 는 임의 URL/RSS/JSON 에서 직접 수집.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal

from hwarang_api.db import prisma
from hwarang_api.knowledge.half_life import DEFAULT_HALF_LIFE
from hwarang_api.knowledge.hrag_client import (
    fetch_law_updates,
    fetch_news,
    fetch_source,
    fetch_weather_updates,
)
from hwarang_api.knowledge.types import (
    KnowledgeFact,
    KnowledgeStatus,
    KnowledgeVisibility,
)

logger = logging.getLogger(__name__)


Domain = Literal["law", "weather", "news"]


_DOMAIN_TO_HALFLIFE: dict[str, int | None] = {
    "law": DEFAULT_HALF_LIFE.get("law"),
    "weather": DEFAULT_HALF_LIFE.get("weather"),
    "news": DEFAULT_HALF_LIFE.get("news"),
}


async def _ingest_fact_via_pipeline(fact: KnowledgeFact) -> dict:
    """pipeline.ingest_fact 를 lazy import (순환 방지).

    pipeline 미구현일 경우 직접 Prisma upsert 로 fallback.
    """
    try:
        from hwarang_api.knowledge.pipeline import ingest_fact  # type: ignore

        return await ingest_fact(fact)
    except Exception as exc:
        logger.debug("pipeline.ingest_fact unavailable (%s), falling back", exc)
        return await _direct_upsert(fact)


async def _direct_upsert(fact: KnowledgeFact) -> dict:
    """pipeline 이 없을 때의 최소 upsert.

    contentHash 가 같으면 updated, 아니면 created 로 취급.
    """
    import hashlib

    content_hash = hashlib.sha256(fact.content.encode("utf-8")).hexdigest()
    existing = await prisma.knowledgefact.find_first(
        where={"contentHash": content_hash}
    )
    if existing:
        await prisma.knowledgefact.update(
            where={"id": existing.id},
            data={
                "lastVerifiedAt": datetime.now(timezone.utc),
                "sourceUrl": fact.source_url,
            },
        )
        return {"status": "updated", "id": existing.id}

    created = await prisma.knowledgefact.create(
        data={
            "content": fact.content,
            "contentHash": content_hash,
            "domain": fact.domain,
            "entity": fact.entity,
            "tags": fact.tags or [],
            "language": fact.language,
            "validFrom": fact.valid_from,
            "validTo": fact.valid_to,
            "confidenceT0": fact.confidence_t0,
            "halfLifeDays": fact.half_life_days,
            "status": fact.status.value,
            "source": fact.source,
            "sourceUrl": fact.source_url,
            "sourceType": fact.source_type,
            "visibility": fact.visibility.value,
            "ownerUserId": fact.owner_user_id,
        }
    )
    return {"status": "created", "id": created.id}


def _build_fact(item: dict, domain: str) -> KnowledgeFact:
    """HRAG 아이템 → KnowledgeFact."""
    source_name = item.get("source") or {
        "law": "law.go.kr",
        "weather": "kma",
        "news": "news",
    }.get(domain, "hrag")

    eff = item.get("effective_date") or datetime.now(timezone.utc)
    if isinstance(eff, str):
        try:
            eff = datetime.fromisoformat(eff)
        except ValueError:
            eff = datetime.now(timezone.utc)

    body = item.get("content") or item.get("title") or ""
    title = item.get("title") or ""
    text = f"{title}\n{body}".strip() if title and title not in body else body

    return KnowledgeFact(
        content=text,
        domain=domain,
        entity=title[:128] if title else None,
        tags=[domain, "hrag"],
        language="ko",
        valid_from=eff,
        valid_to=None,
        confidence_t0=0.95,
        half_life_days=_DOMAIN_TO_HALFLIFE.get(domain),
        status=KnowledgeStatus.CONFIRMED,
        source=source_name,
        source_url=item.get("source_url"),
        source_type="official",
        visibility=KnowledgeVisibility.PUBLIC,
    )


async def sync_from_hrag(domain: Domain, limit: int = 100) -> dict:
    """HRAG 소스에서 최근 항목을 가져와 Knowledge Mesh 에 저장.

    반환: {"fetched", "ingested", "updated", "skipped", "errors"}.
    """
    fetched: list[dict] = []
    try:
        if domain == "law":
            fetched = await fetch_law_updates()
        elif domain == "weather":
            fetched = await fetch_weather_updates()
        elif domain == "news":
            fetched = await fetch_news(["정책", "경제", "사회"])
    except Exception as exc:
        logger.exception("sync_from_hrag fetch failed")
        return {
            "fetched": 0,
            "ingested": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [str(exc)],
        }

    fetched = fetched[:limit]
    stats = {"fetched": len(fetched), "ingested": 0, "updated": 0, "skipped": 0}
    errors: list[str] = []

    for item in fetched:
        try:
            fact = _build_fact(item, domain)
            result = await _ingest_fact_via_pipeline(fact)
            status = (result or {}).get("status", "skipped")
            if status == "created":
                stats["ingested"] += 1
            elif status == "updated":
                stats["updated"] += 1
            else:
                stats["skipped"] += 1
        except Exception as exc:
            errors.append(str(exc))
            stats["skipped"] += 1

    if errors:
        stats["errors"] = errors  # type: ignore[assignment]
    return stats


async def schedule_hrag_sync() -> None:
    """단순 asyncio 루프로 주기적 동기화를 돌린다.

    - law : 6h
    - weather : 1h
    - news : 30m
    호출자가 `asyncio.create_task(schedule_hrag_sync())` 로 띄운다.
    """
    intervals = {"law": 6 * 3600, "weather": 3600, "news": 1800}
    tasks = {d: 0.0 for d in intervals}

    while True:
        now = asyncio.get_event_loop().time()
        for d, gap in intervals.items():
            if now - tasks[d] >= gap:
                try:
                    stats = await sync_from_hrag(d, limit=200)  # type: ignore[arg-type]
                    logger.info("HRAG sync %s: %s", d, stats)
                except Exception:
                    logger.exception("HRAG scheduled sync failed (%s)", d)
                tasks[d] = asyncio.get_event_loop().time()
        await asyncio.sleep(60)  # 분 단위로 깨어 스케줄 검사


async def reverse_lookup_hrag(fact_id: str) -> dict | None:
    """저장된 fact 의 원본 HRAG 메타를 돌려준다.

    official 소스에 한해, 최소한 source/url/effective_date 을 반환.
    현재는 source_url 재조회로 fresh snapshot 도 포함.
    """
    row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if row is None:
        return None
    if row.sourceType != "official":
        return None

    fresh: dict[str, Any] | None = None
    if row.sourceUrl:
        try:
            fresh = await fetch_source(row.sourceUrl)
        except Exception:
            fresh = None

    return {
        "fact_id": row.id,
        "source": row.source,
        "source_url": row.sourceUrl,
        "source_type": row.sourceType,
        "domain": row.domain,
        "valid_from": row.validFrom.isoformat() if row.validFrom else None,
        "last_verified_at": row.lastVerifiedAt.isoformat()
        if row.lastVerifiedAt
        else None,
        "fresh_snapshot": {
            "status": (fresh or {}).get("status"),
            "content_type": (fresh or {}).get("content_type"),
            "bytes": len((fresh or {}).get("content", "") or ""),
        }
        if fresh
        else None,
    }


async def sync_from_custom_source(source_url: str, parser: str = "auto") -> list[str]:
    """임의 URL 에서 HTML/JSON/RSS 파싱 → 여러 fact 로 분해해 적재.

    반환: 새로 적재된 fact id 목록.
    """
    doc = await fetch_source(source_url)
    if not doc or doc.get("status", 0) != 200:
        return []
    content = doc.get("content", "")
    ct = (doc.get("content_type") or "").lower()

    items: list[dict] = []
    effective_parser = parser
    if effective_parser == "auto":
        if "json" in ct:
            effective_parser = "json"
        elif "xml" in ct or "rss" in ct or content.strip().startswith("<?xml"):
            effective_parser = "rss"
        else:
            effective_parser = "html"

    if effective_parser == "json":
        try:
            obj = json.loads(content)
            if isinstance(obj, list):
                for i, it in enumerate(obj):
                    items.append(
                        {
                            "title": str(it.get("title") or f"{source_url}#{i}"),
                            "content": str(
                                it.get("content") or it.get("body") or json.dumps(it)
                            ),
                            "source_url": it.get("url") or source_url,
                            "effective_date": datetime.now(timezone.utc),
                            "source": source_url,
                        }
                    )
            elif isinstance(obj, dict):
                items.append(
                    {
                        "title": str(obj.get("title") or source_url),
                        "content": str(
                            obj.get("content") or obj.get("body") or json.dumps(obj)
                        ),
                        "source_url": source_url,
                        "effective_date": datetime.now(timezone.utc),
                        "source": source_url,
                    }
                )
        except Exception as exc:
            logger.warning("json parse failed: %s", exc)

    elif effective_parser == "rss":
        import re as _re

        entries = _re.findall(
            r"<item[^>]*>(.*?)</item>", content, flags=_re.DOTALL | _re.IGNORECASE
        )
        for entry in entries:
            title = _extract_tag(entry, "title")
            link = _extract_tag(entry, "link") or source_url
            body = _extract_tag(entry, "description") or ""
            items.append(
                {
                    "title": title,
                    "content": f"{title}\n{body}",
                    "source_url": link,
                    "effective_date": datetime.now(timezone.utc),
                    "source": source_url,
                }
            )

    else:  # html
        from hwarang_api.knowledge.web import strip_html

        text = strip_html(content)
        if text:
            items.append(
                {
                    "title": source_url,
                    "content": text[:4000],
                    "source_url": source_url,
                    "effective_date": datetime.now(timezone.utc),
                    "source": source_url,
                }
            )

    new_ids: list[str] = []
    for item in items:
        try:
            fact = _build_fact(item, "general")
            fact.source_type = "crawl"
            result = await _ingest_fact_via_pipeline(fact)
            if (result or {}).get("status") == "created" and result.get("id"):
                new_ids.append(result["id"])
        except Exception:
            logger.exception("custom source ingest failed")
    return new_ids


def _extract_tag(xml: str, tag: str) -> str:
    import re as _re

    m = _re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, flags=_re.DOTALL | _re.IGNORECASE)
    if not m:
        return ""
    return _re.sub(r"<[^>]+>", "", m.group(1)).strip()


__all__ = [
    "sync_from_hrag",
    "schedule_hrag_sync",
    "reverse_lookup_hrag",
    "sync_from_custom_source",
]
