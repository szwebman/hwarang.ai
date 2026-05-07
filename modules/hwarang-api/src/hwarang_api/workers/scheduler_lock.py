"""다중 인스턴스 cron job 분산 락 (PostgreSQL UPSERT 기반).

``HWARANG_SCHEDULER_LEADER`` 환경변수 가드의 **백업 안전망**.
LEADER=1 이 두 인스턴스에 동시에 설정된 사고에서도 같은 잡이 동시에 실행되지
않도록 ``scheduler_lock`` 테이블에 UPSERT 한다.

테이블 스키마 (prisma model: SchedulerLock):
    job_name    TEXT PRIMARY KEY
    host        TEXT
    acquired_at TIMESTAMPTZ
    expires_at  TIMESTAMPTZ  (TTL 만료 시 다른 인스턴스가 takeover 가능)

동작:
  * ``try_acquire(name, ttl)`` → INSERT ... ON CONFLICT DO UPDATE
    WHERE expires_at < NOW() RETURNING host. 본인 host 면 True.
  * ``release(name)`` → DELETE WHERE host = me. 즉시 해제.
  * DB 미가용/테이블 없음 → True (fail-open: env LEADER 가드만으로 동작).
"""

from __future__ import annotations

import logging
import socket
from typing import Any

logger = logging.getLogger(__name__)

# TTL 미지정 시 기본값 (초). 학습 같은 무거운 잡은 호출자가 길게 지정.
_DEFAULT_TTL_SECONDS = 1800  # 30 분


def _hostname() -> str:
    return socket.gethostname()


async def try_acquire(job_name: str, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> bool:
    """잡 락 획득 시도.

    Args:
        job_name: 잡 이름 (scheduler 등록 이름과 일치).
        ttl_seconds: 락 만료 (강제 종료/크래시 대비). 잡이 이보다 오래 걸리면
            다른 인스턴스가 takeover 할 수 있음 — 무거운 잡은 넉넉히.

    Returns:
        True: 락 획득 (잡 실행 진행).
        False: 다른 인스턴스가 보유 중 (skip).

    Notes:
        DB 미가용 / 테이블 없음 / 기타 예외 → True (fail-open).
        env LEADER 가드가 1차 방어이므로 락 실패 시 환경변수만 신뢰.
    """
    try:
        from hwarang_api.db import prisma  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.debug("scheduler_lock: prisma import 실패 (%s) — fail-open", exc)
        return True

    host = _hostname()
    ttl_str = str(int(ttl_seconds))

    try:
        rows: list[Any] = await prisma.query_raw(
            """
            INSERT INTO scheduler_lock (job_name, host, acquired_at, expires_at)
            VALUES ($1, $2, NOW(), NOW() + ($3 || ' seconds')::INTERVAL)
            ON CONFLICT (job_name) DO UPDATE
            SET host        = EXCLUDED.host,
                acquired_at = EXCLUDED.acquired_at,
                expires_at  = EXCLUDED.expires_at
            WHERE scheduler_lock.expires_at < NOW()
            RETURNING host
            """,
            job_name,
            host,
            ttl_str,
        )
    except Exception as exc:  # noqa: BLE001
        # 테이블 미존재 (마이그레이션 전), 권한 부족, DB 다운 등.
        logger.warning(
            "scheduler_lock: query 실패 (%s: %s) — fall back to env-only guard",
            type(exc).__name__,
            exc,
        )
        return True

    if not rows:
        # ON CONFLICT DO UPDATE WHERE expires_at < NOW() 조건 미충족 →
        # 같은 row 가 이미 다른 host 에 있고 아직 만료되지 않음.
        return False

    # RETURNING host 결과
    row0 = rows[0]
    holder = row0.get("host") if isinstance(row0, dict) else None
    return holder == host


async def release(job_name: str) -> None:
    """잡 종료 시 락 해제. TTL 만료 전 다음 인스턴스가 즉시 가져갈 수 있도록."""
    try:
        from hwarang_api.db import prisma  # type: ignore
    except Exception:
        return

    host = _hostname()
    try:
        await prisma.execute_raw(
            "DELETE FROM scheduler_lock WHERE job_name = $1 AND host = $2",
            job_name,
            host,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("scheduler_lock: release 실패 [%s]: %s", job_name, exc)


async def list_active() -> list[dict]:
    """현재 살아있는 락 목록 — 관리자/운영자 디버깅용."""
    try:
        from hwarang_api.db import prisma  # type: ignore
    except Exception:
        return []
    try:
        rows = await prisma.query_raw(
            """
            SELECT job_name, host, acquired_at, expires_at,
                   EXTRACT(EPOCH FROM (expires_at - NOW()))::INT AS ttl_seconds
            FROM scheduler_lock
            WHERE expires_at > NOW()
            ORDER BY job_name
            """
        )
        return [dict(r) for r in (rows or [])]
    except Exception:
        return []


__all__ = ["try_acquire", "release", "list_active"]
