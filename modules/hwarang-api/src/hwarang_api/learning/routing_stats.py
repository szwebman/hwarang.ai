"""도메인×모델 라우팅 시간 윈도우 통계.

HNTL 라우터가 도메인별 가중치를 동적으로 조정할 때 입력으로 사용한다.
1 시간 단위 윈도우로 누적, ``RoutingStats`` 테이블에 upsert.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)

WINDOW_HOURS = 1


def _floor_hour(dt: datetime) -> datetime:
    """``dt`` 를 1 시간 단위로 내림 (UTC)."""
    return dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _prisma_ready() -> bool:
    try:
        return bool(prisma.is_connected())
    except Exception:
        return False


async def record_routing(
    domain: str,
    model_name: str,
    latency_ms: int,
    satisfaction: float = 0.0,
) -> dict:
    """현재 시간 윈도우의 ``RoutingStats`` 행에 누적.

    ``satisfaction`` 은 ``-1.0 ~ +1.0`` 사이의 float (없으면 0).
    """
    domain = (domain or "general").strip().lower()
    model_name = (model_name or "unknown").strip()
    latency_ms = max(0, int(latency_ms or 0))

    if not _prisma_ready():
        return {"recorded": False, "reason": "db_unavailable"}

    window_start = _floor_hour(datetime.now(timezone.utc))
    has_satisfaction = satisfaction is not None and satisfaction != 0.0

    create_data: dict[str, Any] = {
        "domain": domain,
        "modelName": model_name,
        "windowStart": window_start,
        "totalRequests": 1,
        "totalLatencyMs": latency_ms,
        "satisfactionSum": float(satisfaction or 0.0),
        "satisfactionCount": 1 if has_satisfaction else 0,
    }

    update_data: dict[str, Any] = {
        "totalRequests": {"increment": 1},
        "totalLatencyMs": {"increment": latency_ms},
        "satisfactionSum": {"increment": float(satisfaction or 0.0)},
    }
    if has_satisfaction:
        update_data["satisfactionCount"] = {"increment": 1}

    try:
        row = await prisma.routingstats.upsert(
            where={
                "domain_modelName_windowStart": {
                    "domain": domain,
                    "modelName": model_name,
                    "windowStart": window_start,
                }
            },
            data={
                "create": create_data,
                "update": update_data,
            },
        )
        return {"recorded": True, "stats_id": getattr(row, "id", None)}
    except Exception as e:  # pragma: no cover
        logger.warning(f"RoutingStats upsert 실패: {e}")
        return {"recorded": False, "error": str(e)}


async def get_domain_quality(domain: str, hours: int = 24) -> dict:
    """최근 ``hours`` 시간 동안의 ``domain`` 평균 만족도/지연.

    반환: ``{domain, model_breakdown: [...], total_requests, avg_satisfaction, avg_latency_ms}``.
    """
    domain = (domain or "general").strip().lower()

    if not _prisma_ready():
        return {
            "domain": domain,
            "model_breakdown": [],
            "total_requests": 0,
            "avg_satisfaction": 0.0,
            "avg_latency_ms": 0.0,
        }

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    try:
        rows = await prisma.routingstats.find_many(
            where={"domain": domain, "windowStart": {"gte": cutoff}},
            order={"windowStart": "desc"},
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"RoutingStats find_many 실패: {e}")
        return {
            "domain": domain,
            "model_breakdown": [],
            "total_requests": 0,
            "avg_satisfaction": 0.0,
            "avg_latency_ms": 0.0,
        }

    by_model: dict[str, dict[str, float]] = {}
    total_req = 0
    total_lat = 0
    sat_sum = 0.0
    sat_count = 0

    for r in rows:
        m = r.modelName
        bucket = by_model.setdefault(
            m,
            {"requests": 0, "latency_ms": 0, "sat_sum": 0.0, "sat_count": 0},
        )
        bucket["requests"] += int(r.totalRequests or 0)
        bucket["latency_ms"] += int(r.totalLatencyMs or 0)
        bucket["sat_sum"] += float(r.satisfactionSum or 0.0)
        bucket["sat_count"] += int(r.satisfactionCount or 0)

        total_req += int(r.totalRequests or 0)
        total_lat += int(r.totalLatencyMs or 0)
        sat_sum += float(r.satisfactionSum or 0.0)
        sat_count += int(r.satisfactionCount or 0)

    breakdown = []
    for m, b in by_model.items():
        breakdown.append(
            {
                "model": m,
                "requests": b["requests"],
                "avg_latency_ms": b["latency_ms"] / b["requests"] if b["requests"] else 0.0,
                "avg_satisfaction": b["sat_sum"] / b["sat_count"] if b["sat_count"] else 0.0,
            }
        )
    breakdown.sort(key=lambda x: x["requests"], reverse=True)

    return {
        "domain": domain,
        "hours": hours,
        "total_requests": total_req,
        "avg_satisfaction": sat_sum / sat_count if sat_count else 0.0,
        "avg_latency_ms": total_lat / total_req if total_req else 0.0,
        "model_breakdown": breakdown,
    }


async def list_all_domain_quality(hours: int = 24, limit: int = 50) -> list[dict]:
    """모든 도메인의 최근 만족도 — 관리자 대시보드용."""
    if not _prisma_ready():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    try:
        rows = await prisma.routingstats.find_many(
            where={"windowStart": {"gte": cutoff}},
            order={"windowStart": "desc"},
            take=limit * 50,
        )
    except Exception:  # pragma: no cover
        return []

    domains: dict[str, dict[str, float]] = {}
    for r in rows:
        d = r.domain
        bucket = domains.setdefault(
            d, {"requests": 0, "sat_sum": 0.0, "sat_count": 0, "latency_ms": 0}
        )
        bucket["requests"] += int(r.totalRequests or 0)
        bucket["sat_sum"] += float(r.satisfactionSum or 0.0)
        bucket["sat_count"] += int(r.satisfactionCount or 0)
        bucket["latency_ms"] += int(r.totalLatencyMs or 0)

    out = []
    for d, b in domains.items():
        out.append(
            {
                "domain": d,
                "requests": b["requests"],
                "avg_satisfaction": b["sat_sum"] / b["sat_count"] if b["sat_count"] else 0.0,
                "avg_latency_ms": b["latency_ms"] / b["requests"] if b["requests"] else 0.0,
            }
        )
    out.sort(key=lambda x: x["requests"], reverse=True)
    return out[:limit]


__all__ = ["record_routing", "get_domain_quality", "list_all_domain_quality"]
