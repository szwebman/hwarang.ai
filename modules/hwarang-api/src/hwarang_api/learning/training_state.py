"""TrainingJob / FisherSnapshot / ReplaySample 영속 헬퍼 — Phase 2.

라우터 / 워커 / 학습 함수에서 공통으로 쓰는 DB 어댑터.
prisma 직접 호출 패턴을 한 곳에 모아서 재사용.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _prisma_ready() -> bool:
    try:
        return bool(prisma.is_connected())
    except Exception:
        return False


# ────────────────────────────────────────────────────────────
# TrainingJob
# ────────────────────────────────────────────────────────────
async def create_training_job(
    domain: str,
    lora_name: str,
    base_model: str,
    *,
    sample_count: int = 0,
    triggered_by: str = "auto",
    ewc_lambda: float = 1000.0,
    replay_ratio: float = 0.3,
) -> dict:
    """잡 큐에 새 TrainingJob (status=queued) 추가."""
    if not _prisma_ready():
        return {"created": False, "reason": "db_unavailable"}
    try:
        row = await prisma.trainingjob.create(
            data={
                "domain": domain,
                "loraName": lora_name,
                "baseModel": base_model,
                "sampleCount": sample_count,
                "ewcLambda": ewc_lambda,
                "replayRatio": replay_ratio,
                "status": "queued",
                "triggeredBy": triggered_by,
            }
        )
        return {"created": True, "id": row.id, "domain": domain}
    except Exception as e:  # pragma: no cover
        logger.warning(f"TrainingJob create 실패: {e}")
        return {"created": False, "error": str(e)}


async def mark_running(job_id: str) -> None:
    if not _prisma_ready():
        return
    try:
        await prisma.trainingjob.update(
            where={"id": job_id},
            data={"status": "running", "startedAt": _utcnow()},
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"mark_running 실패: {e}")


async def mark_done(
    job_id: str,
    *,
    new_adapter_path: Optional[str] = None,
    forgetting_score: Optional[float] = None,
    quality_score: Optional[float] = None,
    sample_count: Optional[int] = None,
) -> None:
    if not _prisma_ready():
        return
    data: dict[str, Any] = {"status": "done", "completedAt": _utcnow()}
    if new_adapter_path is not None:
        data["newAdapterPath"] = new_adapter_path
    if forgetting_score is not None:
        data["forgettingScore"] = float(forgetting_score)
    if quality_score is not None:
        data["qualityScore"] = float(quality_score)
    if sample_count is not None:
        data["sampleCount"] = int(sample_count)
    try:
        await prisma.trainingjob.update(where={"id": job_id}, data=data)
    except Exception as e:  # pragma: no cover
        logger.warning(f"mark_done 실패: {e}")


async def mark_failed(job_id: str, error_message: str) -> None:
    if not _prisma_ready():
        return
    try:
        await prisma.trainingjob.update(
            where={"id": job_id},
            data={
                "status": "failed",
                "completedAt": _utcnow(),
                "errorMessage": (error_message or "")[:1000],
            },
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"mark_failed 실패: {e}")


async def cancel_job(job_id: str) -> dict:
    """queued 상태에서만 취소. running 은 cancel 표시만 (워커가 체크)."""
    if not _prisma_ready():
        return {"cancelled": False, "reason": "db_unavailable"}
    try:
        job = await prisma.trainingjob.find_unique(where={"id": job_id})
        if not job:
            return {"cancelled": False, "reason": "not_found"}
        if job.status not in ("queued", "running"):
            return {"cancelled": False, "reason": f"status_{job.status}"}
        await prisma.trainingjob.update(
            where={"id": job_id},
            data={
                "status": "failed",
                "errorMessage": "cancelled by user",
                "completedAt": _utcnow(),
            },
        )
        return {"cancelled": True, "id": job_id}
    except Exception as e:  # pragma: no cover
        logger.warning(f"cancel_job 실패: {e}")
        return {"cancelled": False, "error": str(e)}


async def list_jobs(
    status: Optional[str] = None,
    domain: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    if not _prisma_ready():
        return []
    where: dict[str, Any] = {}
    if status:
        where["status"] = status
    if domain:
        where["domain"] = domain
    rows = await prisma.trainingjob.find_many(
        where=where,
        order={"createdAt": "desc"},
        take=limit,
    )
    return [_job_to_dict(r) for r in rows]


async def get_job(job_id: str) -> Optional[dict]:
    if not _prisma_ready():
        return None
    row = await prisma.trainingjob.find_unique(where={"id": job_id})
    return _job_to_dict(row) if row else None


def _job_to_dict(r: Any) -> dict:
    return {
        "id": r.id,
        "domain": r.domain,
        "loraName": r.loraName,
        "baseModel": r.baseModel,
        "sampleCount": r.sampleCount,
        "ewcLambda": r.ewcLambda,
        "replayRatio": r.replayRatio,
        "status": r.status,
        "startedAt": r.startedAt.isoformat() if r.startedAt else None,
        "completedAt": r.completedAt.isoformat() if r.completedAt else None,
        "errorMessage": r.errorMessage,
        "newAdapterPath": r.newAdapterPath,
        "forgettingScore": r.forgettingScore,
        "qualityScore": r.qualityScore,
        "triggeredBy": r.triggeredBy,
        "createdAt": r.createdAt.isoformat() if r.createdAt else None,
    }


# ────────────────────────────────────────────────────────────
# FisherSnapshot
# ────────────────────────────────────────────────────────────
async def upsert_fisher_snapshot(
    lora_name: str,
    domain: str,
    fisher_path: str,
    optimal_path: str,
) -> dict:
    """Fisher snapshot 메타 upsert. 실제 텐서는 디스크에 별도 저장됨."""
    if not _prisma_ready():
        return {"upserted": False, "reason": "db_unavailable"}
    try:
        row = await prisma.fishersnapshot.upsert(
            where={"loraName_domain": {"loraName": lora_name, "domain": domain}},
            data={
                "create": {
                    "loraName": lora_name,
                    "domain": domain,
                    "fisherPath": fisher_path,
                    "optimalPath": optimal_path,
                    "taskCount": 1,
                },
                "update": {
                    "fisherPath": fisher_path,
                    "optimalPath": optimal_path,
                    "taskCount": {"increment": 1},
                    "computedAt": _utcnow(),
                },
            },
        )
        return {"upserted": True, "id": row.id, "taskCount": row.taskCount}
    except Exception as e:  # pragma: no cover
        logger.warning(f"FisherSnapshot upsert 실패: {e}")
        return {"upserted": False, "error": str(e)}


async def get_fisher_snapshot(lora_name: str, domain: str) -> Optional[dict]:
    if not _prisma_ready():
        return None
    try:
        row = await prisma.fishersnapshot.find_unique(
            where={"loraName_domain": {"loraName": lora_name, "domain": domain}},
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"FisherSnapshot 조회 실패: {e}")
        return None
    if not row:
        return None
    return {
        "id": row.id,
        "loraName": row.loraName,
        "domain": row.domain,
        "fisherPath": row.fisherPath,
        "optimalPath": row.optimalPath,
        "taskCount": row.taskCount,
        "computedAt": row.computedAt.isoformat() if row.computedAt else None,
    }


__all__ = [
    "create_training_job",
    "mark_running",
    "mark_done",
    "mark_failed",
    "cancel_job",
    "list_jobs",
    "get_job",
    "upsert_fisher_snapshot",
    "get_fisher_snapshot",
]
