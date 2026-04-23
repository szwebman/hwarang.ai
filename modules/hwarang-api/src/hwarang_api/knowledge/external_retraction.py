"""HLKM - 외부 정정/철회 DB 연동 (External Retraction Sources).

Retraction Watch / Crossref Labs / Snopes / SNU팩트체크 등 공개 외부
정정·팩트체크 데이터베이스를 주기적으로 조회해, 우리 HLKM 의
``KnowledgeFact`` 와 매칭되는 항목을 자동 무효화하는 모듈.

주요 책임:
  1. ``ExternalRetractionSource`` Prisma 테이블로 제공자 관리
     (providerName / baseUrl / apiKey / syncIntervalHours / lastSyncAt …).
  2. DOI / 클레임 텍스트 기반으로 외부 소스 병렬 조회.
  3. 매칭 결과를 ``record_retraction`` 으로 반영 + ``lastSyncAt`` 갱신.

네트워크/파싱 오류는 ``None`` 반환 + 로그만 남기고 예외를 올리지 않는다
(그레이스풀 디그레이드). 이 모듈은 스케줄러(Celery / cron) 에서
``sync_all_providers`` 로 주기 실행되는 것을 가정한다.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from hwarang_api.db import prisma

from .retraction import record_retraction
from .types import KnowledgeFact

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
USER_AGENT = "HwarangHLKM/1.0 (+https://hwarang.ai)"
DEFAULT_TIMEOUT = 10
DOI_REGEX = re.compile(r"10\.\d{4,}/[^\s\"'<>)]+")


#: 기본 제공자 목록 — ``seed_providers`` 로 DB upsert.
DEFAULT_PROVIDERS: list[dict[str, Any]] = [
    {
        "providerName": "retraction_watch",
        "baseUrl": "http://api.labs.crossref.org/works",
        "domain": "medical",
        "syncIntervalHours": 24,
    },
    {
        "providerName": "snopes",
        "baseUrl": "https://www.snopes.com",
        "domain": "general",
        "syncIntervalHours": 12,
    },
    {
        "providerName": "factcheck_kr",
        "baseUrl": "https://factcheck.snu.ac.kr",
        "domain": "news",
        "syncIntervalHours": 24,
    },
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def extract_doi(source: str) -> str | None:
    """임의 문자열(source / source_url / citation)에서 DOI 추출.

    예: "https://doi.org/10.1038/s41586-021-03819-2" → "10.1038/s41586-021-03819-2".
    발견 실패 시 ``None``.
    """
    if not source:
        return None
    m = DOI_REGEX.search(source)
    if not m:
        return None
    doi = m.group(0).rstrip(".,);]")
    return doi or None


# ─────────────────────────────────────────────
# 공용 HTTP 헬퍼
# ─────────────────────────────────────────────
async def _fetch_json(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    params: dict[str, Any] | None = None,
) -> dict | None:
    """httpx 공용 JSON GET — 실패 시 ``None``.

    2xx 가 아니거나 JSON 파싱 실패도 조용히 ``None``.
    """
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url, headers=hdrs, params=params)
        if r.status_code >= 400:
            logger.debug("fetch_json %s → %d", url, r.status_code)
            return None
        ct = r.headers.get("content-type", "")
        if "json" not in ct.lower():
            # 일부 서버가 text/plain 으로 JSON 반환 — 시도만 해본다
            try:
                return r.json()
            except Exception:  # noqa: BLE001
                return None
        return r.json()
    except Exception as exc:  # noqa: BLE001
        logger.debug("fetch_json error %s: %s", url, exc)
        return None


async def _fetch_text(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    params: dict[str, Any] | None = None,
) -> str | None:
    """httpx 공용 텍스트 GET — 실패 시 ``None``."""
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url, headers=hdrs, params=params)
        if r.status_code >= 400:
            return None
        return r.text
    except Exception as exc:  # noqa: BLE001
        logger.debug("fetch_text error %s: %s", url, exc)
        return None


# ─────────────────────────────────────────────
# Provider 관리
# ─────────────────────────────────────────────
async def seed_providers() -> int:
    """``DEFAULT_PROVIDERS`` 를 DB 에 upsert.

    이미 존재하는 providerName 은 baseUrl / domain / syncIntervalHours 를
    보존(덮어쓰지 않음). 신규 삽입 건수만 반환.
    """
    inserted = 0
    for p in DEFAULT_PROVIDERS:
        try:
            exists = await prisma.externalretractionsource.find_unique(
                where={"providerName": p["providerName"]}
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("seed_providers find failed %s: %s", p["providerName"], exc)
            continue
        if exists:
            continue
        try:
            await prisma.externalretractionsource.create(
                data={
                    "providerName": p["providerName"],
                    "baseUrl": p["baseUrl"],
                    "domain": p.get("domain", "general"),
                    "syncIntervalHours": int(p.get("syncIntervalHours", 24)),
                    "active": True,
                }
            )
            inserted += 1
            logger.info("[external_retraction] seeded provider %s", p["providerName"])
        except Exception as exc:  # noqa: BLE001
            logger.error("seed_providers create failed %s: %s", p["providerName"], exc)
    return inserted


async def list_providers(active_only: bool = True) -> list[dict]:
    """등록된 provider 목록 반환."""
    where: dict[str, Any] = {"active": True} if active_only else {}
    try:
        rows = await prisma.externalretractionsource.find_many(where=where)
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_providers failed: %s", exc)
        return []
    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "provider_name": r.providerName,
                "base_url": r.baseUrl,
                "domain": r.domain,
                "active": r.active,
                "sync_interval_hours": r.syncIntervalHours,
                "last_sync_at": getattr(r, "lastSyncAt", None),
            }
        )
    return out


async def update_provider(provider_name: str, **kwargs: Any) -> None:
    """Provider 필드 업데이트 (baseUrl / apiKey / syncIntervalHours / active / domain)."""
    allowed = {"baseUrl", "apiKey", "syncIntervalHours", "active", "domain"}
    data = {k: v for k, v in kwargs.items() if k in allowed}
    if not data:
        return
    try:
        await prisma.externalretractionsource.update(
            where={"providerName": provider_name}, data=data
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("update_provider %s failed: %s", provider_name, exc)


async def deactivate_provider(provider_name: str) -> None:
    """Provider 비활성화 (active=False)."""
    await update_provider(provider_name, active=False)


# ─────────────────────────────────────────────
# 개별 Provider 쿼리
# ─────────────────────────────────────────────
async def query_retraction_watch(doi: str) -> dict | None:
    """Crossref Labs / Crossref Works API 로 ``update-to`` / ``retraction-of`` 확인.

    Crossref 의 ``update-policy`` 또는 ``update-to`` 필드에 retraction 신호가 있으면
    정정으로 간주한다. Retraction Watch 데이터베이스가 Crossref 와 통합되어 있어
    사실상 동일한 데이터 소스.

    반환 포맷::

        {"retracted": True, "retraction_date": "2022-01-15", "reason": "...",
         "source_doi": "10.xxxx/...", "source": "crossref"}
    """
    if not doi:
        return None

    url = f"https://api.crossref.org/works/{doi}"
    data = await _fetch_json(url)
    if not isinstance(data, dict):
        return None

    msg = data.get("message") if isinstance(data.get("message"), dict) else None
    if not msg:
        return None

    update_policy = (msg.get("update-policy") or "").lower()
    updates_to = msg.get("update-to") or []
    is_retracted = "retraction" in update_policy or "withdrawal" in update_policy

    # update-to 배열 내 type == "retraction" 검사
    retraction_entry: dict | None = None
    if isinstance(updates_to, list):
        for u in updates_to:
            if isinstance(u, dict) and "retract" in (u.get("type") or "").lower():
                is_retracted = True
                retraction_entry = u
                break

    if not is_retracted:
        return None

    retraction_date = ""
    reason = update_policy or "crossref: retraction signal"
    source_doi = doi
    if retraction_entry:
        dp = retraction_entry.get("updated") or {}
        if isinstance(dp, dict):
            parts = dp.get("date-parts") or [[]]
            if parts and parts[0]:
                try:
                    retraction_date = "-".join(f"{int(x):02d}" for x in parts[0])
                except Exception:  # noqa: BLE001
                    retraction_date = ""
        reason = retraction_entry.get("label") or reason
        source_doi = retraction_entry.get("DOI") or doi

    return {
        "retracted": True,
        "retraction_date": retraction_date,
        "reason": reason,
        "source_doi": source_doi,
        "source": "crossref",
    }


async def query_snopes(claim_text: str) -> dict | None:
    """Snopes 팩트체크 검색 — 공개 검색 URL fallback.

    Snopes 는 공식 퍼블릭 JSON API 를 제공하지 않으므로, ``/?s=<query>`` 검색
    결과에서 첫 번째 팩트체크 URL 과 등급을 추출한다. 파싱 실패 = ``None``.
    """
    if not claim_text:
        return None

    q = claim_text.strip()[:200]
    url = "https://www.snopes.com/"
    text = await _fetch_text(url, params={"s": q})
    if not text:
        return None

    # 결과 카드: <a href="https://www.snopes.com/fact-check/..." class="outer_article_link...">
    link_m = re.search(
        r'href="(https?://www\.snopes\.com/fact-check/[^"]+)"', text
    )
    if not link_m:
        return None
    article_url = link_m.group(1)

    # 제목
    title = ""
    title_m = re.search(
        r'href="' + re.escape(article_url) + r'"[^>]*>\s*<[^>]+>([^<]{5,200})',
        text,
    )
    if title_m:
        title = title_m.group(1).strip()

    # 등급 추정 (false / mostly false / mixed / true) — 검색 결과 페이지 제한적이라
    # 본문 페이지를 한 번 더 방문해 rating 박스 파싱.
    rating = "unknown"
    body = await _fetch_text(article_url)
    if body:
        r_m = re.search(
            r'rating[-_ ]?(?:title|name|label)[^<>]*>\s*([A-Za-z ]{3,40})',
            body,
            re.IGNORECASE,
        )
        if r_m:
            rating = r_m.group(1).strip().lower().replace(" ", "_")

    return {"rating": rating, "url": article_url, "title": title or q}


async def query_factcheck_snu(claim_text: str) -> dict | None:
    """서울대 SNU팩트체크 공개 검색.

    ``https://factcheck.snu.ac.kr/v2/search?query=...`` 형태의 공개 검색 엔드포인트
    HTML 을 정규식으로 파싱한다. 구조 변경 시 ``None``.
    """
    if not claim_text:
        return None

    q = claim_text.strip()[:200]
    text = await _fetch_text(
        "https://factcheck.snu.ac.kr/v2/search", params={"query": q}
    )
    if not text:
        return None

    # 첫 번째 결과 링크
    link_m = re.search(
        r'href="(/v2/facts/[^"]+)"', text
    )
    if not link_m:
        return None
    url = "https://factcheck.snu.ac.kr" + link_m.group(1)

    rating_m = re.search(
        r'(?:class|data-rating)="[^"]*?(전혀 사실 아님|대체로 사실 아님|절반의 사실|대체로 사실|사실)[^"]*"',
        text,
    )
    rating = rating_m.group(1) if rating_m else "unknown"

    outlet_m = re.search(r'언론사[^<>]*>\s*([^<\n]{2,40})', text)
    media_outlet = outlet_m.group(1).strip() if outlet_m else ""

    return {"rating": rating, "url": url, "media_outlet": media_outlet}


# ─────────────────────────────────────────────
# 통합 쿼리
# ─────────────────────────────────────────────
async def query_all_providers(fact: KnowledgeFact) -> list[dict]:
    """fact 하나를 모든 활성 provider 에 병렬 조회.

    - ``fact.source`` / ``fact.source_url`` 에서 DOI 추출 시도 → 의학 provider.
    - DOI 가 없으면 ``fact.content`` 로 일반 검색 (snopes, SNU팩트체크 등).
    """
    providers = await list_providers(active_only=True)
    if not providers:
        return []

    doi = extract_doi(fact.source or "") or extract_doi(fact.source_url or "")
    tasks: list[asyncio.Task] = []
    labels: list[str] = []

    for p in providers:
        name = p["provider_name"]
        if name == "retraction_watch":
            if not doi:
                continue
            tasks.append(asyncio.create_task(query_retraction_watch(doi)))
            labels.append(name)
        elif name == "snopes":
            tasks.append(asyncio.create_task(query_snopes(fact.content)))
            labels.append(name)
        elif name == "factcheck_kr":
            tasks.append(asyncio.create_task(query_factcheck_snu(fact.content)))
            labels.append(name)
        else:
            # 알 수 없는 provider — 스킵
            continue

    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[dict] = []
    for label, r in zip(labels, results):
        if isinstance(r, Exception) or not r:
            continue
        entry = dict(r)
        entry["provider"] = label
        out.append(entry)
    return out


# ─────────────────────────────────────────────
# Provider sync (주기 배치)
# ─────────────────────────────────────────────
async def _candidate_facts(domain: str, batch_size: int) -> list[Any]:
    """해당 domain 의 최근 CONFIRMED 사실 중 미정정 샘플."""
    where: dict[str, Any] = {"retracted": False}
    if domain and domain != "general":
        where["domain"] = domain
    try:
        rows = await prisma.knowledgefact.find_many(
            where=where,
            take=batch_size,
            order={"createdAt": "desc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("_candidate_facts failed domain=%s: %s", domain, exc)
        return []
    return list(rows)


def _snopes_rating_is_false(rating: str) -> bool:
    r = (rating or "").lower()
    return any(
        tag in r for tag in ("false", "mostly_false", "pants_on_fire", "misattributed", "scam")
    )


def _snu_rating_is_false(rating: str) -> bool:
    return rating in {"전혀 사실 아님", "대체로 사실 아님"}


async def sync_provider(provider_name: str, batch_size: int = 50) -> dict:
    """특정 provider 의 최근 정정 데이터를 수집·반영.

    1. 활성/비활성 확인.
    2. 해당 domain 의 후보 fact 로드.
    3. provider 별 쿼리 + 매칭되면 ``record_retraction``.
    4. ``lastSyncAt`` 갱신.
    """
    stats: dict[str, Any] = {
        "provider": provider_name,
        "scanned": 0,
        "matched": 0,
        "recorded": 0,
        "errors": 0,
    }
    try:
        prov = await prisma.externalretractionsource.find_unique(
            where={"providerName": provider_name}
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("sync_provider lookup failed %s: %s", provider_name, exc)
        stats["errors"] += 1
        return stats
    if not prov or not prov.active:
        stats["skipped"] = "inactive"
        return stats

    facts = await _candidate_facts(prov.domain, batch_size)
    stats["scanned"] = len(facts)

    for row in facts:
        try:
            fact = KnowledgeFact(
                id=row.id,
                content=row.content,
                domain=row.domain,
                valid_from=row.validFrom,
                source=row.source,
                source_url=row.sourceUrl,
            )
        except Exception:  # noqa: BLE001
            continue

        result: dict | None = None
        retraction_url: str | None = None
        reason: str = ""
        is_match = False

        try:
            if provider_name == "retraction_watch":
                doi = extract_doi(fact.source or "") or extract_doi(fact.source_url or "")
                if not doi:
                    continue
                result = await query_retraction_watch(doi)
                if result and result.get("retracted"):
                    is_match = True
                    retraction_url = f"https://doi.org/{result.get('source_doi', doi)}"
                    reason = (
                        f"Retraction Watch/Crossref: {result.get('reason', '')} "
                        f"(date={result.get('retraction_date', '?')})"
                    )
            elif provider_name == "snopes":
                result = await query_snopes(fact.content)
                if result and _snopes_rating_is_false(result.get("rating", "")):
                    is_match = True
                    retraction_url = result.get("url")
                    reason = f"Snopes: {result.get('rating')} — {result.get('title', '')}"
            elif provider_name == "factcheck_kr":
                result = await query_factcheck_snu(fact.content)
                if result and _snu_rating_is_false(result.get("rating", "")):
                    is_match = True
                    retraction_url = result.get("url")
                    reason = (
                        f"SNU팩트체크: {result.get('rating')} "
                        f"— {result.get('media_outlet', '')}"
                    )
            else:
                logger.debug("unknown provider %s", provider_name)
                continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("query failed provider=%s fact=%s: %s", provider_name, row.id, exc)
            stats["errors"] += 1
            continue

        if not is_match:
            continue
        stats["matched"] += 1
        try:
            await record_retraction(
                fact_id=row.id,
                retracted_by=f"external:{provider_name}",
                retraction_url=retraction_url,
                retraction_type="external_db",
                reason=reason[:3800],
                detected_by=f"external:{provider_name}",
            )
            stats["recorded"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("record_retraction failed fact=%s: %s", row.id, exc)
            stats["errors"] += 1

    try:
        await prisma.externalretractionsource.update(
            where={"providerName": provider_name},
            data={"lastSyncAt": _utcnow()},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("lastSyncAt update failed %s: %s", provider_name, exc)

    logger.info("[external_retraction] sync_provider %s → %s", provider_name, stats)
    return stats


async def sync_all_providers() -> dict:
    """모든 활성 provider 를 ``syncIntervalHours`` 기준으로 순회."""
    out: dict[str, Any] = {"providers": [], "total_recorded": 0}
    now = _utcnow()
    try:
        provs = await prisma.externalretractionsource.find_many(where={"active": True})
    except Exception as exc:  # noqa: BLE001
        logger.error("sync_all_providers list failed: %s", exc)
        return out

    for p in provs:
        last = getattr(p, "lastSyncAt", None)
        interval = timedelta(hours=int(getattr(p, "syncIntervalHours", 24) or 24))
        if last and (now - last) < interval:
            out["providers"].append({"name": p.providerName, "skipped": "interval"})
            continue
        stats = await sync_provider(p.providerName)
        out["providers"].append(stats)
        out["total_recorded"] += int(stats.get("recorded", 0))
    return out


__all__ = [
    "DEFAULT_PROVIDERS",
    "seed_providers",
    "list_providers",
    "update_provider",
    "deactivate_provider",
    "query_retraction_watch",
    "query_snopes",
    "query_factcheck_snu",
    "query_all_providers",
    "sync_provider",
    "sync_all_providers",
    "extract_doi",
]
