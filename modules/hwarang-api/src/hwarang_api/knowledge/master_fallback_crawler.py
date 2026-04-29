"""에이전트가 부족할 때 마스터가 직접 크롤하는 fallback.

작동:
  * 매 10 분 cron 으로 실행 (``HLKMScheduler.master_fallback_crawl``)
  * 30 분 이상 ``pending`` 상태로 leased 안 된 ``CrawlJob`` 검색
  * 최대 N 개 (기본 5) 만 직접 처리 — 마스터 부하 제한
  * 에이전트의 ``submit`` 와 동일한 ingest 경로 (``ingest_fact`` + ``SourceCitation``)

목적:
  * 에이전트 0 명 → 시스템 멈춤 방지 (boot-strap)
  * 에이전트 폭증 시 자동으로 fallback 비활성 (작업이 빨리 leased 됨)
  * 처리량은 작아도, 분산 크롤이 망가져도 큐가 영원히 쌓이는 일은 없게

동시성:
  * ``update_many(where=status="pending")`` atomic 으로 lease 잡음 — 동시
    실행되더라도 같은 잡을 두 번 처리하지 않음.
  * lease 만료(10 분) 가 짧아 fallback 가 죽어도 다른 워커/에이전트가 회수.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from hwarang_api.db import prisma
from hwarang_api.knowledge.pipeline import ingest_fact
from hwarang_api.knowledge.types import KnowledgeFact, KnowledgeVisibility

logger = logging.getLogger(__name__)


# 가상 agent id — CrawlAgentStats / leasedBy 식별자로 사용
MASTER_FALLBACK_AGENT_ID = "master-fallback"

DEFAULT_STALE_MINUTES = 30
DEFAULT_MAX_JOBS = 5
DEFAULT_TIMEOUT_SEC = 15
LEASE_DURATION_MIN = 10  # 마스터 fallback 의 lease 보유 시간

# 선택 의존성 — 없으면 graceful skip
try:
    import httpx  # type: ignore

    HAS_HTTPX = True
except Exception:  # noqa: BLE001
    HAS_HTTPX = False

try:
    from bs4 import BeautifulSoup  # type: ignore

    HAS_BS4 = True
except Exception:  # noqa: BLE001
    BeautifulSoup = None  # type: ignore[assignment]
    HAS_BS4 = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 공개 진입점
# ---------------------------------------------------------------------------
async def run_fallback_cycle(
    stale_minutes: int = DEFAULT_STALE_MINUTES,
    max_jobs: int = DEFAULT_MAX_JOBS,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict:
    """오래된 pending 작업을 마스터가 직접 처리.

    Returns:
        ``{"processed": N, "failed": M, "candidates": K}`` 또는
        ``{"processed": 0, "skipped": "..."}``
    """
    if not HAS_HTTPX:
        logger.warning("httpx 미설치 — 마스터 fallback 비활성")
        return {"processed": 0, "skipped": "httpx_missing"}

    cutoff = _utcnow() - timedelta(minutes=stale_minutes)

    # ── 1. 30 분 이상 pending 인 작업 후보 ──
    try:
        stale = await prisma.crawljob.find_many(
            where={
                "status": "pending",
                "createdAt": {"lt": cutoff},
            },
            include={"source": True},
            order=[{"priority": "desc"}, {"createdAt": "asc"}],
            take=max_jobs,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("fallback find_many 실패: %s", exc)
        return {"processed": 0, "skipped": f"db_error: {exc}"}

    if not stale:
        return {"processed": 0, "skipped": "no_stale_jobs"}

    logger.info("마스터 fallback 크롤 시작 — %d건 후보", len(stale))

    processed = 0
    failed = 0
    for job in stale:
        # ── 2. atomic lease (동시성 보호) ──
        now = _utcnow()
        expires = now + timedelta(minutes=LEASE_DURATION_MIN)
        try:
            result = await prisma.crawljob.update_many(
                where={"id": job.id, "status": "pending"},
                data={
                    "status": "leased",
                    "leasedBy": MASTER_FALLBACK_AGENT_ID,
                    "leasedAt": now,
                    "leaseExpiresAt": expires,
                    "attemptCount": {"increment": 1},
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("fallback lease update 실패 (%s): %s", job.id, exc)
            continue

        if getattr(result, "count", 0) == 0:
            # 다른 워커/에이전트가 이미 가져감
            continue

        # ── 3. fetch + extract ──
        try:
            content = await _fetch_and_extract(
                job.url, job.metadata or {}, timeout_sec
            )
            if not content or not (content.get("content") or "").strip():
                await _release(job.id, "no_content")
                failed += 1
                continue

            # ── 4. ingest_fact ──
            src = job.source
            domains = list(getattr(src, "domains", []) or []) if src else []
            domain = domains[0] if domains else "general"
            confidence = max(
                0.0,
                min(
                    1.0,
                    float(getattr(src, "trustLevel", 50) or 50) / 100.0,
                ),
            )

            fact_content = (
                f"{(content.get('title') or '').strip()}. {content['content']}"
            ).strip()[:5000]
            fact = KnowledgeFact(
                content=fact_content,
                domain=domain,
                source=getattr(src, "displayName", "") or job.url,
                source_url=job.url,
                source_type="official",  # bypass_gate 와 함께 KYC 우회 신호
                confidence_t0=confidence,
                visibility=KnowledgeVisibility.PUBLIC,
            )
            ingest_result = await ingest_fact(fact, bypass_gate=True)
            fact_id = (
                ingest_result.get("fact_id")
                if isinstance(ingest_result, dict)
                else None
            )

            # ── 5. SourceCitation ──
            if fact_id:
                try:
                    await prisma.sourcecitation.create(
                        data={
                            "factId": fact_id,
                            "sourceId": job.sourceId,
                            "url": job.url,
                            "title": (content.get("title") or "")[:500] or None,
                            "excerpt": (content.get("content") or "")[:500],
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("fallback sourcecitation 실패: %s", exc)

            # ── 6. 완료 처리 ──
            try:
                await prisma.crawljob.update(
                    where={"id": job.id},
                    data={
                        "status": "completed",
                        "factId": fact_id,
                        "completedAt": _utcnow(),
                        "resultJson": content,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("fallback complete 업데이트 실패: %s", exc)

            # 출처 통계
            try:
                await prisma.trustedsource.update(
                    where={"id": job.sourceId},
                    data={
                        "totalCrawled": {"increment": 1},
                        "totalFacts": {"increment": 1 if fact_id else 0},
                    },
                )
            except Exception:  # noqa: BLE001
                pass

            # CrawlAgentStats 도 업데이트 (master-fallback 가상 에이전트)
            try:
                await prisma.crawlagentstats.upsert(
                    where={"agentId": MASTER_FALLBACK_AGENT_ID},
                    data={
                        "create": {
                            "agentId": MASTER_FALLBACK_AGENT_ID,
                            "totalLeased": 1,
                            "totalCompleted": 1,
                            "lastLeasedAt": now,
                            "lastCompletedAt": _utcnow(),
                        },
                        "update": {
                            "totalLeased": {"increment": 1},
                            "totalCompleted": {"increment": 1},
                            "lastLeasedAt": now,
                            "lastCompletedAt": _utcnow(),
                        },
                    },
                )
            except Exception:  # noqa: BLE001
                pass

            processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("fallback 작업 %s 실패: %s", job.id, exc)
            await _release(job.id, str(exc)[:200])
            failed += 1

    return {
        "processed": processed,
        "failed": failed,
        "candidates": len(stale),
        "stale_minutes": stale_minutes,
    }


# ---------------------------------------------------------------------------
# fetch + 본문 추출 (간단 버전)
# ---------------------------------------------------------------------------
async def _fetch_and_extract(
    url: str, metadata: dict, timeout: int
) -> Optional[dict]:
    """URL fetch + HTML 본문 추출 (간단 버전).

    BeautifulSoup 가 없으면 raw text 의 앞 5000 자만 사용.
    """
    if not HAS_HTTPX:
        return None
    try:
        async with httpx.AsyncClient(  # type: ignore[name-defined]
            timeout=timeout,
            headers={"User-Agent": "HwarangBot/1.0 (master-fallback)"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                logger.debug(
                    "fallback fetch %s status=%d", url, resp.status_code
                )
                return None

            ctype = (resp.headers.get("content-type") or "").lower()
            text = resp.text

            # HTML 이 아니면 raw 사용
            if "html" not in ctype:
                return {
                    "title": (metadata.get("title") or "")[:300],
                    "content": text[:5000],
                    "contentHash": hashlib.sha256(text.encode()).hexdigest(),
                }

            # HTML → BS4 본문 추출
            if HAS_BS4:
                try:
                    soup = BeautifulSoup(text, "html.parser")  # type: ignore[misc]
                    for tag in soup(
                        ["script", "style", "nav", "header", "footer", "aside"]
                    ):
                        tag.decompose()
                    title_tag = soup.title.string if soup.title else None
                    title = (title_tag or metadata.get("title") or "").strip()[
                        :300
                    ]
                    main = (
                        soup.find("article")
                        or soup.find("main")
                        or soup.body
                    )
                    body_text = (
                        main.get_text(separator="\n", strip=True) if main else ""
                    )
                    return {
                        "title": title,
                        "content": body_text[:5000],
                        "contentHash": hashlib.sha256(
                            body_text.encode()
                        ).hexdigest(),
                    }
                except Exception as exc:  # noqa: BLE001
                    logger.debug("BS4 파싱 실패 (%s): %s", url, exc)

            # BS4 없거나 파싱 실패 → raw fallback
            return {
                "title": (metadata.get("title") or "")[:300],
                "content": text[:5000],
                "contentHash": hashlib.sha256(text.encode()).hexdigest(),
            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("마스터 fetch 실패 %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# 잡 release
# ---------------------------------------------------------------------------
async def _release(job_id: str, reason: str) -> None:
    """처리 실패 시 lease 반환 (또는 max attempts 초과면 failed)."""
    try:
        job = await prisma.crawljob.find_unique(where={"id": job_id})
    except Exception:  # noqa: BLE001
        return
    if not job:
        return

    new_status = (
        "failed"
        if (job.attemptCount or 0) >= (job.maxAttempts or 3)
        else "pending"
    )
    try:
        await prisma.crawljob.update(
            where={"id": job_id},
            data={
                "status": new_status,
                "leasedBy": None,
                "leasedAt": None,
                "leaseExpiresAt": None,
                "lastError": (reason or "")[:1000] or None,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("fallback _release 실패 (%s): %s", job_id, exc)


__all__ = [
    "MASTER_FALLBACK_AGENT_ID",
    "run_fallback_cycle",
]
