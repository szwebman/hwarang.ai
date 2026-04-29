"""분산 크롤 작업 분배 API.

마스터 ↔ 에이전트 인터페이스. 에이전트 (Hwarang Grid 데스크탑/노드) 는 다음
4 개 엔드포인트로 마스터와 통신:

  * ``POST /api/crawl/lease``           — N 개 작업을 임대 (5 분 lease)
  * ``POST /api/crawl/submit/{id}``     — 추출 결과 제출 → HLKM ingest
  * ``POST /api/crawl/release/{id}``    — 처리 실패 시 임대 반환
  * ``POST /api/crawl/heartbeat/{id}``  — 긴 작업 시 lease 연장

마스터/관리자용:

  * ``GET  /api/crawl/status``          — 큐 상태 + 활성 에이전트
  * ``GET  /api/crawl/jobs``            — 작업 목록 (status 필터)
  * ``POST /api/crawl/dispatch``        — 디스패처 수동 트리거

핵심 보장:
  * **중복 없음** — ``update_many(where=status="pending")`` 의 atomic
    return.count 으로 같은 잡이 두 에이전트에 동시 임대되지 않도록 한다.
  * **장애 복원** — lease 가 만료된 (``leaseExpiresAt < now``) 작업은
    /lease 호출 시 자동 회수되어 다른 에이전트에게 재할당된다.
  * **whitelist only** — CrawlJob 은 디스패처가 TrustedSource 화이트리스트
    에서만 생성되므로, 에이전트가 임의 URL 을 가져갈 수 없다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from hwarang_api.db import prisma
from hwarang_api.knowledge.crawl_dispatcher import dispatch_pending_crawls
from hwarang_api.knowledge.pipeline import ingest_fact
from hwarang_api.knowledge.types import KnowledgeFact, KnowledgeVisibility

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crawl", tags=["DistributedCrawl"])

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
LEASE_DURATION_MIN = 5
MAX_LEASE_BATCH = 20


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 인증 헬퍼
# ---------------------------------------------------------------------------
def _check_agent(authorization: str | None) -> str:
    """에이전트 Bearer 토큰 검증 → ``agent_id`` 반환.

    실제 검증 로직은 ``hwarang_api.routers.grid`` 의 에이전트 인증 (또는
    ApiKey 모듈) 과 통합. 현재는 단순화 — 토큰 자체를 agent_id 로 취급.
    실서비스에서는 ApiKey/AgentRegistry 에서 lookup 후 활성 에이전트인지 확인.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer 토큰 필요")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(401, "빈 토큰")
    return token


# ---------------------------------------------------------------------------
# 모델
# ---------------------------------------------------------------------------
class LeaseRequest(BaseModel):
    agent_id: str = Field(..., description="에이전트 식별자")
    max_jobs: int = Field(5, ge=1, le=MAX_LEASE_BATCH)
    domain_filter: list[str] | None = Field(
        None,
        description="에이전트가 처리 가능한 도메인 (TrustedSource.domains hasSome)",
    )


class LeasedJob(BaseModel):
    id: str
    url: str
    jobType: str
    metadata: dict
    sourceTrustLevel: int
    sourceDomain: str  # TrustedSource.domains[0] (없으면 'general')
    sourceDisplayName: str
    leaseExpiresAt: str


class LeaseResponse(BaseModel):
    jobs: list[LeasedJob]
    leaseExpiresAt: str


class SubmitRequest(BaseModel):
    agent_id: str
    title: str | None = None
    content: str = Field(..., min_length=1)
    publishedAt: str | None = None
    contentHash: str | None = None


class ReleaseRequest(BaseModel):
    agent_id: str
    reason: str | None = None


# ---------------------------------------------------------------------------
# 에이전트 측 엔드포인트
# ---------------------------------------------------------------------------
@router.post("/lease", response_model=LeaseResponse)
async def lease_jobs(
    req: LeaseRequest, authorization: str | None = Header(None)
) -> LeaseResponse:
    """N 개 작업을 atomic 하게 임대.

    1. 만료된 lease 회수 (다른 에이전트가 죽은 경우)
    2. priority desc + createdAt asc 로 candidate 선정
    3. update_many(where=status="pending") atomic 으로 lease 잡기
    4. 통계 업데이트
    """
    agent_id = _check_agent(authorization)

    # 차단 에이전트 체크
    stats = await prisma.crawlagentstats.find_unique(where={"agentId": agent_id})
    if stats and stats.isBlocked:
        raise HTTPException(403, "에이전트 차단됨")

    now = _utcnow()
    expires = now + timedelta(minutes=LEASE_DURATION_MIN)

    # ── 1. 만료된 lease 회수 (장애 복원) ──
    try:
        await prisma.crawljob.update_many(
            where={"status": "leased", "leaseExpiresAt": {"lt": now}},
            data={
                "status": "pending",
                "leasedBy": None,
                "leasedAt": None,
                "leaseExpiresAt": None,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("expired-lease sweep fail: %s", exc)

    # ── 2. candidate 선정 ──
    where: dict[str, Any] = {"status": "pending"}
    if req.domain_filter:
        where["source"] = {"is": {"domains": {"hasSome": req.domain_filter}}}

    candidates = await prisma.crawljob.find_many(
        where=where,
        include={"source": True},
        order=[{"priority": "desc"}, {"createdAt": "asc"}],
        take=min(req.max_jobs, MAX_LEASE_BATCH),
    )

    # ── 3. atomic lease (update_many → count > 0 인 것만 실제 leased) ──
    leased: list[LeasedJob] = []
    for j in candidates:
        try:
            result = await prisma.crawljob.update_many(
                where={"id": j.id, "status": "pending"},
                data={
                    "status": "leased",
                    "leasedBy": agent_id,
                    "leasedAt": now,
                    "leaseExpiresAt": expires,
                    "attemptCount": {"increment": 1},
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("lease update fail (%s): %s", j.id, exc)
            continue

        if getattr(result, "count", 0) > 0:
            src = j.source
            domains = list(getattr(src, "domains", []) or []) if src else []
            leased.append(
                LeasedJob(
                    id=j.id,
                    url=j.url,
                    jobType=j.jobType,
                    metadata=j.metadata or {},
                    sourceTrustLevel=int(getattr(src, "trustLevel", 0) or 0),
                    sourceDomain=domains[0] if domains else "general",
                    sourceDisplayName=getattr(src, "displayName", "") or "",
                    leaseExpiresAt=expires.isoformat(),
                )
            )

    # ── 4. 통계 ──
    if leased:
        try:
            await prisma.crawlagentstats.upsert(
                where={"agentId": agent_id},
                data={
                    "create": {
                        "agentId": agent_id,
                        "totalLeased": len(leased),
                        "lastLeasedAt": now,
                    },
                    "update": {
                        "totalLeased": {"increment": len(leased)},
                        "lastLeasedAt": now,
                    },
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("agent stats upsert fail (%s): %s", agent_id, exc)

    return LeaseResponse(jobs=leased, leaseExpiresAt=expires.isoformat())


@router.post("/submit/{job_id}")
async def submit_result(
    job_id: str, req: SubmitRequest, authorization: str | None = Header(None)
) -> dict:
    """에이전트가 크롤 결과 제출 → HLKM ingest + CrawlJob 완료."""
    agent_id = _check_agent(authorization)

    job = await prisma.crawljob.find_unique(
        where={"id": job_id}, include={"source": True}
    )
    if not job:
        raise HTTPException(404, f"job not found: {job_id}")
    if job.leasedBy != agent_id:
        raise HTTPException(403, "다른 에이전트가 임대한 작업")
    if job.status != "leased":
        raise HTTPException(400, f"잘못된 상태: {job.status}")

    src = job.source
    domains = list(getattr(src, "domains", []) or []) if src else []
    domain = domains[0] if domains else "general"
    confidence = max(0.0, min(1.0, float(getattr(src, "trustLevel", 50) or 50) / 100.0))

    fact = KnowledgeFact(
        content=f"{(req.title or '').strip()}. {req.content}".strip()[:5000],
        domain=domain,
        source=getattr(src, "displayName", "") or job.url,
        source_url=job.url,
        source_type="official",  # bypass_gate 와 함께 KYC 우회 신호
        confidence_t0=confidence,
        visibility=KnowledgeVisibility.PUBLIC,
        valid_from=_parse_date(req.publishedAt) or _utcnow(),
    )

    try:
        result = await ingest_fact(fact, bypass_gate=True)
    except Exception as exc:  # noqa: BLE001
        logger.exception("ingest_fact fail (%s): %s", job.url, exc)
        raise HTTPException(500, f"ingest 실패: {exc}") from exc

    fact_id = result.get("fact_id") if isinstance(result, dict) else None

    # SourceCitation
    if fact_id:
        try:
            await prisma.sourcecitation.create(
                data={
                    "factId": fact_id,
                    "sourceId": job.sourceId,
                    "url": job.url,
                    "title": (req.title or "")[:500] or None,
                    "excerpt": (req.content or "")[:500],
                    "publishedAt": _parse_date(req.publishedAt),
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("sourcecitation create fail: %s", exc)

    # 완료 처리
    completed_at = _utcnow()
    try:
        await prisma.crawljob.update(
            where={"id": job_id},
            data={
                "status": "completed",
                "factId": fact_id,
                "completedAt": completed_at,
                "resultJson": req.model_dump(),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("crawljob complete update fail: %s", exc)

    # 에이전트 통계 + latency
    try:
        latency_ms = 0.0
        if job.leasedAt:
            latency_ms = max(0.0, (completed_at - job.leasedAt).total_seconds() * 1000.0)
        existing = await prisma.crawlagentstats.find_unique(where={"agentId": agent_id})
        new_avg = latency_ms
        if existing and existing.totalCompleted > 0:
            # incremental EMA — 0.7 * old + 0.3 * new
            new_avg = round(
                0.7 * float(existing.avgLatencyMs or 0) + 0.3 * latency_ms, 2
            )
        await prisma.crawlagentstats.upsert(
            where={"agentId": agent_id},
            data={
                "create": {
                    "agentId": agent_id,
                    "totalCompleted": 1,
                    "lastCompletedAt": completed_at,
                    "avgLatencyMs": new_avg,
                },
                "update": {
                    "totalCompleted": {"increment": 1},
                    "lastCompletedAt": completed_at,
                    "avgLatencyMs": new_avg,
                },
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("agent completed-stats fail: %s", exc)

    # 출처 성공률 갱신
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

    return {"ok": True, "factId": fact_id, "status": "completed"}


@router.post("/release/{job_id}")
async def release_job(
    job_id: str,
    req: ReleaseRequest,
    authorization: str | None = Header(None),
) -> dict:
    """에이전트가 처리 못함 → pending 으로 되돌림 (또는 max attempts 초과 시 failed)."""
    agent_id = _check_agent(authorization)

    job = await prisma.crawljob.find_unique(where={"id": job_id})
    if not job:
        raise HTTPException(404)
    if job.leasedBy != agent_id:
        raise HTTPException(403, "다른 에이전트가 임대한 작업")

    new_status = "failed" if job.attemptCount >= job.maxAttempts else "pending"

    await prisma.crawljob.update(
        where={"id": job_id},
        data={
            "status": new_status,
            "leasedBy": None,
            "leasedAt": None,
            "leaseExpiresAt": None,
            "lastError": (req.reason or "")[:1000] or None,
        },
    )

    if new_status == "failed":
        try:
            await prisma.crawlagentstats.upsert(
                where={"agentId": agent_id},
                data={
                    "create": {"agentId": agent_id, "totalFailed": 1},
                    "update": {"totalFailed": {"increment": 1}},
                },
            )
        except Exception:  # noqa: BLE001
            pass

    return {"ok": True, "status": new_status}


@router.post("/heartbeat/{job_id}")
async def heartbeat(
    job_id: str, authorization: str | None = Header(None)
) -> dict:
    """긴 작업 시 lease 연장. 이 에이전트가 leased 한 잡만 가능."""
    agent_id = _check_agent(authorization)
    job = await prisma.crawljob.find_unique(where={"id": job_id})
    if not job:
        raise HTTPException(404)
    if job.leasedBy != agent_id:
        raise HTTPException(403)
    if job.status != "leased":
        raise HTTPException(400, f"잘못된 상태: {job.status}")

    new_expires = _utcnow() + timedelta(minutes=LEASE_DURATION_MIN)
    await prisma.crawljob.update(
        where={"id": job_id}, data={"leaseExpiresAt": new_expires}
    )
    return {"leaseExpiresAt": new_expires.isoformat()}


# ---------------------------------------------------------------------------
# 마스터/관리자용
# ---------------------------------------------------------------------------
@router.get("/status")
async def crawl_status() -> dict:
    """관리자 대시보드용 큐 상태 + top 에이전트 요약."""
    queue: dict[str, int] = {}
    for status in ("pending", "leased", "completed", "failed", "expired"):
        try:
            queue[status] = await prisma.crawljob.count(where={"status": status})
        except Exception:  # noqa: BLE001
            queue[status] = -1

    try:
        agents = await prisma.crawlagentstats.find_many(
            where={"isBlocked": False},
            order={"totalCompleted": "desc"},
            take=20,
        )
    except Exception:  # noqa: BLE001
        agents = []

    return {
        "queue": queue,
        "active_agents": len(agents),
        "top_agents": [
            {
                "agentId": a.agentId,
                "completed": a.totalCompleted,
                "failed": a.totalFailed,
                "trustWeight": a.trustWeight,
                "avgLatencyMs": a.avgLatencyMs,
            }
            for a in agents[:10]
        ],
        "lease_duration_minutes": LEASE_DURATION_MIN,
    }


@router.get("/jobs")
async def list_jobs(
    status: str | None = Query(None),
    source_id: str | None = Query(None),
    take: int = Query(50, ge=1, le=500),
) -> dict:
    """작업 목록 (관리자용)."""
    where: dict[str, Any] = {}
    if status:
        where["status"] = status
    if source_id:
        where["sourceId"] = source_id

    try:
        jobs = await prisma.crawljob.find_many(
            where=where or None,
            order={"createdAt": "desc"},
            take=take,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"조회 실패: {exc}") from exc

    return {
        "count": len(jobs),
        "jobs": [
            {
                "id": j.id,
                "url": j.url,
                "status": j.status,
                "jobType": j.jobType,
                "leasedBy": j.leasedBy,
                "attemptCount": j.attemptCount,
                "priority": j.priority,
                "factId": j.factId,
                "lastError": j.lastError,
                "createdAt": j.createdAt.isoformat() if j.createdAt else None,
                "completedAt": j.completedAt.isoformat() if j.completedAt else None,
            }
            for j in jobs
        ],
    }


@router.post("/dispatch")
async def manual_dispatch() -> dict:
    """관리자가 즉시 디스패처 트리거 (스케줄과 무관하게 강제 실행)."""
    return await dispatch_pending_crawls()


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _parse_date(iso_str: str | None) -> datetime | None:
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except Exception:
        return None


__all__ = ["router"]
