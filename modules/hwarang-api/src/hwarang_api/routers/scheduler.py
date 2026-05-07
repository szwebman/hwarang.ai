"""Scheduler 관리 엔드포인트 (관리자 전용).

운영자가 다중 인스턴스 cron 락 / 잡 상태를 모니터링/제어할 수 있게 한다.

엔드포인트:
  * GET  /api/scheduler/status                 — leader 여부 + 잡별 last_run/last_error
  * GET  /api/scheduler/locks                  — 현재 살아있는 분산 락 목록
  * POST /api/scheduler/locks/{job_name}/release — 강제 해제 (TTL 만료 안 기다리고)

인증: ``HWARANG_INTERNAL_KEY`` Bearer (cognitive/learning 패턴 동일).
"""

from __future__ import annotations

import logging
import os
import socket
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from hwarang_api.routers.learning import _check_internal_key
from hwarang_api.workers import scheduler_lock

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scheduler", tags=["Scheduler"])


async def _require_internal(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> None:
    """admin Next.js 가 부착하는 ``HWARANG_INTERNAL_KEY`` 검증."""
    _check_internal_key(authorization)


def _is_leader_env() -> bool:
    raw = os.environ.get("HWARANG_SCHEDULER_LEADER")
    if raw is None:
        return True
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


@router.get("/status", dependencies=[Depends(_require_internal)])
async def get_status() -> dict:
    """이 인스턴스의 scheduler 상태 + 잡별 마지막 실행 정보.

    응답:
        {
          "host": "api-pod-1",
          "is_leader_env": true,         # HWARANG_SCHEDULER_LEADER 환경변수
          "running": true,               # scheduler.start() 진입 여부
          "jobs": [
            {"name": "weekly_lora_train", "last_run": "...", "last_result": {...}, "last_error": null},
            ...
          ]
        }
    """
    from hwarang_api.workers.hlkm_scheduler import get_scheduler

    sched = get_scheduler()
    job_names = sorted(
        set(sched.last_run.keys())
        | set(sched.last_result.keys())
        | set(sched.last_error.keys())
    )
    jobs = []
    for name in job_names:
        last_run = sched.last_run.get(name)
        jobs.append(
            {
                "name": name,
                "last_run": last_run.isoformat() if last_run else None,
                "last_result": sched.last_result.get(name),
                "last_error": sched.last_error.get(name),
            }
        )
    return {
        "host": socket.gethostname(),
        "is_leader_env": _is_leader_env(),
        "running": bool(sched.running),
        "task_count": len(sched.tasks),
        "jobs": jobs,
    }


@router.get("/locks", dependencies=[Depends(_require_internal)])
async def list_locks() -> dict:
    """현재 살아있는 분산 락 목록 (DB 기반).

    응답:
        {
          "host": "api-pod-1",
          "locks": [
            {"job_name": "weekly_lora_train", "host": "api-pod-2",
             "acquired_at": "...", "expires_at": "...", "ttl_seconds": 21450},
            ...
          ]
        }
    """
    locks = await scheduler_lock.list_active()
    return {
        "host": socket.gethostname(),
        "locks": locks,
        "count": len(locks),
    }


@router.post(
    "/locks/{job_name}/release",
    dependencies=[Depends(_require_internal)],
)
async def force_release(job_name: str) -> dict:
    """잡 락을 강제 해제 — TTL 만료 안 기다리고 즉시.

    크래시한 인스턴스가 락을 점유하고 있어 다른 인스턴스가 픽업 못 할 때,
    또는 운영자가 잡을 수동으로 다시 돌리고 싶을 때 사용.
    """
    if not job_name or len(job_name) > 200:
        raise HTTPException(400, "invalid job_name")

    try:
        from hwarang_api.db import prisma  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"DB unavailable: {exc}")

    # host 와 무관하게 이 잡의 lock 행 삭제 (운영자 권한)
    try:
        await prisma.execute_raw(
            "DELETE FROM scheduler_lock WHERE job_name = $1",
            job_name,
        )
    except Exception as exc:  # noqa: BLE001
        # 테이블 없음 / DB 오류
        raise HTTPException(500, f"release failed: {exc}")

    logger.warning(
        "scheduler_lock force-released by admin: job=%s host=%s",
        job_name,
        socket.gethostname(),
    )
    return {"ok": True, "job_name": job_name, "released_by": socket.gethostname()}


__all__ = ["router"]
