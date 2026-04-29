"""Cognitive 결정의 감사 로그 (Compliance / 디버깅 / 사후 분석).

매 사이클의 결정마다 다음을 기록:
* 환각 점수 (``hallucinationScore``)
* 일관성 점수 (``consistencyScore``)
* 스키마 준수 (``schemaValid``)
* 위험 키워드 (``riskyKeywords``)
* 차단된 액션 (``blockedActions``)
* 사람 승인 필요 여부 (``requiresApproval``)

DB
--
``CognitiveAudit`` Prisma 모델 (schema.prisma 끝 참조).
모델이 아직 마이그레이션되지 않은 환경에서도 안전하게 동작하도록
모든 DB 호출을 try/except 로 감싼다.

사용처
------
* ``master_loop.cognitive_cycle`` — 매 사이클 결정 후 ``log_audit`` 호출
* 관리자 UI ``GET /api/cognitive/audit/summary`` — 주간 요약
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


async def log_audit(
    memory_id: str,
    cycle_type: str,
    hallucination_report: dict | None = None,
    risky_actions_blocked: list | None = None,
    user_approval_required: bool = False,
) -> bool:
    """감사 로그 1 건 기록.

    Args:
        memory_id: 연결된 ``CognitiveMemory.id``
        cycle_type: ``"scheduled"`` / ``"free_will"`` / ``"interrupt"``
        hallucination_report: ``HallucinationReport`` 의 dict 화 (선택)
        risky_actions_blocked: 차단된 액션 이름 목록 (선택)
        user_approval_required: 사람 승인 필요 여부

    Returns:
        성공 여부.
    """
    try:
        report = hallucination_report or {}
        await prisma.cognitiveaudit.create(
            data={
                "memoryId": memory_id or "",
                "cycleType": cycle_type,
                "hallucinationScore": report.get("confidence"),
                "consistencyScore": report.get("consistency_score"),
                "schemaValid": (
                    report.get("schema_valid")
                    if "schema_valid" in report
                    else True
                ),
                "riskyKeywords": list(report.get("risky_keywords", []) or []),
                "blockedActions": list(risky_actions_blocked or []),
                "requiresApproval": bool(user_approval_required),
                "auditedAt": datetime.now(timezone.utc),
            }
        )
        return True
    except Exception as exc:  # noqa: BLE001
        # 모델 미존재 / DB 미연결 등 — 무시 (사이클은 계속 진행)
        logger.debug("audit 로그 실패: %s", exc)
        return False


async def get_audit_summary(days: int = 7) -> dict[str, Any]:
    """주간 감사 요약 — 관리자 UI 가 호출.

    Returns:
        ``{
            days, total, blocked_count, halluc_count, schema_violations,
            avg_consistency, avg_hallucination, approval_required
        }``
    """
    days = max(1, int(days))
    since = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        audits = await prisma.cognitiveaudit.find_many(
            where={"auditedAt": {"gte": since}},
            take=1000,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit summary 조회 실패: %s", exc)
        return {"days": days, "total": 0, "error": str(exc)}

    if not audits:
        return {"days": days, "total": 0}

    total = len(audits)

    def _safe(val: float | None) -> float:
        return float(val) if val is not None else 0.0

    return {
        "days": days,
        "total": total,
        "blocked_count": sum(
            1 for a in audits if getattr(a, "blockedActions", None)
        ),
        "halluc_count": sum(
            1
            for a in audits
            if (getattr(a, "hallucinationScore", None) or 0.0) > 0.5
        ),
        "schema_violations": sum(
            1 for a in audits if not getattr(a, "schemaValid", True)
        ),
        "avg_consistency": round(
            sum(_safe(getattr(a, "consistencyScore", None)) for a in audits)
            / total,
            3,
        ),
        "avg_hallucination": round(
            sum(_safe(getattr(a, "hallucinationScore", None)) for a in audits)
            / total,
            3,
        ),
        "approval_required": sum(
            1 for a in audits if getattr(a, "requiresApproval", False)
        ),
    }


__all__ = ["log_audit", "get_audit_summary"]
