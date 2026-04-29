"""에이전트 평판 — 작업 수행 능력 신뢰.

주의: 출처(URL/도메인) 신뢰는 ``hwarang_api.knowledge.reputation`` 에 별도 시스템.
통합 조회는 ``hwarang_api.cognitive.trust.unified_trust.UnifiedTrust`` 사용.

에이전트 평판 추적 — Prisma ``AgentReputation`` 영속화.

신뢰점수 공식
-------------
``trust = 0.6 * success_ratio + 0.3 * avg_quality + 0.1 * dispute_win_ratio``

Prisma 모델이 아직 마이그레이트되지 않은 환경(개발 초기)에서는
경고 로그만 남기고 메모리 폴백 (프로세스 수명 동안만 유효).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 메모리 폴백 — DB 미가용 시
_MEM: dict[str, dict[str, Any]] = {}


def _compute_trust(
    success: int,
    failure: int,
    avg_quality: float,
    won: int,
    lost: int,
) -> float:
    """공식: 0.6 * success_ratio + 0.3 * quality + 0.1 * dispute_ratio."""
    success_ratio = success / (success + failure + 1)
    dispute_ratio = won / max(won + lost, 1)
    quality = max(0.0, min(1.0, float(avg_quality)))
    score = success_ratio * 0.6 + quality * 0.3 + dispute_ratio * 0.1
    return round(max(0.0, min(1.0, score)), 4)


async def _get_or_create(agent_id: str) -> Optional[Any]:
    """DB 에서 평판 행을 가져오거나 새로 만든다. DB 실패 시 ``None``."""
    try:
        from hwarang_api.db import prisma
    except Exception as exc:  # noqa: BLE001
        logger.warning("reputation: prisma import 실패: %s", exc)
        return None

    try:
        row = await prisma.agentreputation.find_unique(where={"agentId": agent_id})
        if row is not None:
            return row
        row = await prisma.agentreputation.create(data={"agentId": agent_id})
        return row
    except Exception as exc:  # noqa: BLE001
        logger.warning("reputation: DB 조회/생성 실패(%s): %s", agent_id, exc)
        return None


def _mem_get(agent_id: str) -> dict[str, Any]:
    return _MEM.setdefault(
        agent_id,
        {
            "agentId": agent_id,
            "successCount": 0,
            "failureCount": 0,
            "avgQuality": 0.5,
            "trustScore": 0.5,
            "disputesWon": 0,
            "disputesLost": 0,
            "lastUpdated": datetime.now(timezone.utc),
        },
    )


async def record_success(agent_id: str, quality_score: float = 1.0) -> float:
    """성공 1 건 + 품질점수 누적 평균 업데이트.

    Returns
    -------
    float
        업데이트된 trust score.
    """
    quality_score = max(0.0, min(1.0, float(quality_score)))
    row = await _get_or_create(agent_id)

    if row is None:
        rec = _mem_get(agent_id)
        n = rec["successCount"] + 1
        new_q = (rec["avgQuality"] * rec["successCount"] + quality_score) / n
        rec["successCount"] = n
        rec["avgQuality"] = new_q
        rec["trustScore"] = _compute_trust(
            n,
            rec["failureCount"],
            new_q,
            rec["disputesWon"],
            rec["disputesLost"],
        )
        rec["lastUpdated"] = datetime.now(timezone.utc)
        return rec["trustScore"]

    new_success = int(getattr(row, "successCount", 0)) + 1
    prev_q = float(getattr(row, "avgQuality", 0.5))
    prev_n = int(getattr(row, "successCount", 0))
    new_q = (prev_q * prev_n + quality_score) / new_success
    trust = _compute_trust(
        new_success,
        int(getattr(row, "failureCount", 0)),
        new_q,
        int(getattr(row, "disputesWon", 0)),
        int(getattr(row, "disputesLost", 0)),
    )
    try:
        from hwarang_api.db import prisma

        await prisma.agentreputation.update(
            where={"agentId": agent_id},
            data={
                "successCount": new_success,
                "avgQuality": new_q,
                "trustScore": trust,
                "lastUpdated": datetime.now(timezone.utc),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("reputation: success 업데이트 실패(%s): %s", agent_id, exc)
    return trust


async def record_failure(agent_id: str) -> float:
    """실패 1 건 누적 — quality 는 변경 없음."""
    row = await _get_or_create(agent_id)
    if row is None:
        rec = _mem_get(agent_id)
        rec["failureCount"] += 1
        rec["trustScore"] = _compute_trust(
            rec["successCount"],
            rec["failureCount"],
            rec["avgQuality"],
            rec["disputesWon"],
            rec["disputesLost"],
        )
        rec["lastUpdated"] = datetime.now(timezone.utc)
        return rec["trustScore"]

    new_fail = int(getattr(row, "failureCount", 0)) + 1
    trust = _compute_trust(
        int(getattr(row, "successCount", 0)),
        new_fail,
        float(getattr(row, "avgQuality", 0.5)),
        int(getattr(row, "disputesWon", 0)),
        int(getattr(row, "disputesLost", 0)),
    )
    try:
        from hwarang_api.db import prisma

        await prisma.agentreputation.update(
            where={"agentId": agent_id},
            data={
                "failureCount": new_fail,
                "trustScore": trust,
                "lastUpdated": datetime.now(timezone.utc),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("reputation: failure 업데이트 실패(%s): %s", agent_id, exc)
    return trust


async def record_dispute(agent_id: str, won: bool) -> float:
    """분쟁 결과 누적."""
    row = await _get_or_create(agent_id)
    if row is None:
        rec = _mem_get(agent_id)
        if won:
            rec["disputesWon"] += 1
        else:
            rec["disputesLost"] += 1
        rec["trustScore"] = _compute_trust(
            rec["successCount"],
            rec["failureCount"],
            rec["avgQuality"],
            rec["disputesWon"],
            rec["disputesLost"],
        )
        rec["lastUpdated"] = datetime.now(timezone.utc)
        return rec["trustScore"]

    won_n = int(getattr(row, "disputesWon", 0)) + (1 if won else 0)
    lost_n = int(getattr(row, "disputesLost", 0)) + (0 if won else 1)
    trust = _compute_trust(
        int(getattr(row, "successCount", 0)),
        int(getattr(row, "failureCount", 0)),
        float(getattr(row, "avgQuality", 0.5)),
        won_n,
        lost_n,
    )
    try:
        from hwarang_api.db import prisma

        await prisma.agentreputation.update(
            where={"agentId": agent_id},
            data={
                "disputesWon": won_n,
                "disputesLost": lost_n,
                "trustScore": trust,
                "lastUpdated": datetime.now(timezone.utc),
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("reputation: dispute 업데이트 실패(%s): %s", agent_id, exc)
    return trust


async def get_trust_score(agent_id: str) -> float:
    """현재 신뢰점수. 미존재면 기본 0.5."""
    row = await _get_or_create(agent_id)
    if row is None:
        return float(_mem_get(agent_id)["trustScore"])
    return float(getattr(row, "trustScore", 0.5))


async def top_agents(n: int = 10) -> list[dict]:
    """신뢰점수 상위 N 명 (관리자 UI 리더보드)."""
    n = max(1, min(int(n), 100))
    try:
        from hwarang_api.db import prisma

        rows = await prisma.agentreputation.find_many(
            order={"trustScore": "desc"},
            take=n,
        )
        return [
            {
                "agentId": r.agentId,
                "successCount": r.successCount,
                "failureCount": r.failureCount,
                "avgQuality": float(r.avgQuality),
                "trustScore": float(r.trustScore),
                "disputesWon": r.disputesWon,
                "disputesLost": r.disputesLost,
                "lastUpdated": r.lastUpdated.isoformat() if r.lastUpdated else None,
            }
            for r in rows
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("reputation: top_agents DB 실패, 메모리 폴백: %s", exc)
        sorted_mem = sorted(
            _MEM.values(),
            key=lambda r: float(r.get("trustScore", 0)),
            reverse=True,
        )[:n]
        out: list[dict] = []
        for r in sorted_mem:
            d = dict(r)
            ts = d.get("lastUpdated")
            if isinstance(ts, datetime):
                d["lastUpdated"] = ts.isoformat()
            out.append(d)
        return out


async def get_reputation(agent_id: str) -> dict:
    """단일 에이전트 평판 전체 dict (라우터용)."""
    row = await _get_or_create(agent_id)
    if row is None:
        rec = _mem_get(agent_id)
        d = dict(rec)
        ts = d.get("lastUpdated")
        if isinstance(ts, datetime):
            d["lastUpdated"] = ts.isoformat()
        return d
    return {
        "agentId": row.agentId,
        "successCount": row.successCount,
        "failureCount": row.failureCount,
        "avgQuality": float(row.avgQuality),
        "trustScore": float(row.trustScore),
        "disputesWon": row.disputesWon,
        "disputesLost": row.disputesLost,
        "lastUpdated": row.lastUpdated.isoformat() if row.lastUpdated else None,
    }


__all__ = [
    "record_success",
    "record_failure",
    "record_dispute",
    "get_trust_score",
    "top_agents",
    "get_reputation",
]
