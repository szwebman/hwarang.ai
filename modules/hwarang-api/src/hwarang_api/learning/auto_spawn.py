"""HSEE Phase 3 — 새 LoRA / 도메인 spawn 결정.

CapabilityMonitor 가 측정한 메트릭을 분석해 ``GrowthDecision`` 을 제안한다.
실제 실행은 관리자 승인 후 (또는 낮은 위험 결정에 한해 자동 승인 후) 수행.

트리거 규칙:

1. ``factualAccuracy < 0.6`` → ``spawn_lora`` (해당 도메인 LoRA 재학습)
2. ``unmatchedRate > 0.3``    → ``split_domain`` (도메인이 너무 광범위, sub-domain 으로 분리)
3. ``EmergentDomain.sampleCount >= 1000`` → ``spawn_lora`` (새 도메인 LoRA spawn)
4. ``failureRate > 0.2``      → ``expand_lora_rank`` (현 LoRA capacity 부족)

각 트리거는 7 일 윈도우 평균을 사용하며, 동일 도메인+동일 trigger 의 ``proposed``
상태 결정이 이미 있으면 중복 제안하지 않는다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from hwarang_api.db import prisma
from hwarang_api.learning.capability_monitor import (
    THRESHOLD_HIGH_FAILURE,
    THRESHOLD_HIGH_UNMATCHED,
    THRESHOLD_LOW_FACTUAL,
)
from hwarang_api.learning.training_state import create_training_job

logger = logging.getLogger(__name__)


# 새 도메인 승격 임계치 (EmergentDomain.sampleCount)
EMERGENT_PROMOTE_THRESHOLD = 1000


def _prisma_ready() -> bool:
    try:
        return bool(prisma.is_connected())
    except Exception:
        return False


def _days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


# ────────────────────────────────────────────────────────────
# 평가 + 제안
# ────────────────────────────────────────────────────────────
async def evaluate_and_propose(window_days: int = 7) -> list[dict[str, Any]]:
    """능력 메트릭 + EmergentDomain 분석 후 ``GrowthDecision`` 제안.

    각 결정은 ``status="proposed"`` 로 기록. 자동 승인은 ``growth_planner`` 에서.
    """
    if not _prisma_ready():
        return []

    proposals: list[dict[str, Any]] = []

    # 1) 도메인별 최신 메트릭
    metrics = await prisma.capabilitymetric.find_many(
        where={"measuredAt": {"gte": _days_ago(window_days)}},
        order={"measuredAt": "desc"},
    )

    by_domain: dict[str, Any] = {}
    for m in metrics:
        if m.domain not in by_domain:
            by_domain[m.domain] = m

    for domain, m in by_domain.items():
        # (a) 사실 정확도 낮음 → LoRA 재학습
        if m.factualAccuracy is not None and m.factualAccuracy < THRESHOLD_LOW_FACTUAL:
            p = await _propose_decision(
                "spawn_lora",
                trigger_domain=domain,
                trigger_metric="low_factual_accuracy",
                trigger_value=float(m.factualAccuracy),
                proposal={
                    "domain": domain,
                    "min_samples": 5000,
                    "reason": "factual accuracy below threshold",
                    "threshold": THRESHOLD_LOW_FACTUAL,
                },
            )
            if p:
                proposals.append(p)

        # (b) 미매칭 비율 높음 → 도메인 split
        if m.unmatchedRate is not None and m.unmatchedRate > THRESHOLD_HIGH_UNMATCHED:
            p = await _propose_decision(
                "split_domain",
                trigger_domain=domain,
                trigger_metric="high_unmatched",
                trigger_value=float(m.unmatchedRate),
                proposal={
                    "parent_domain": domain,
                    "reason": "domain too broad — fallback to general too often",
                    "threshold": THRESHOLD_HIGH_UNMATCHED,
                },
            )
            if p:
                proposals.append(p)

        # (c) 답변 거부율 높음 → LoRA rank 확장
        if m.failureRate is not None and m.failureRate > THRESHOLD_HIGH_FAILURE:
            p = await _propose_decision(
                "expand_lora_rank",
                trigger_domain=domain,
                trigger_metric="high_failure_rate",
                trigger_value=float(m.failureRate),
                proposal={
                    "domain": domain,
                    "current_rank": 16,
                    "target_rank": 32,
                    "reason": "high refusal/failure rate suggests insufficient LoRA capacity",
                },
            )
            if p:
                proposals.append(p)

    # 2) EmergentDomain 의 충분히 큰 클러스터 → 새 LoRA spawn
    try:
        emergent = await prisma.emergentdomain.find_many(
            where={
                "isPromoted": False,
                "sampleCount": {"gte": EMERGENT_PROMOTE_THRESHOLD},
            },
        )
    except Exception:  # pragma: no cover
        emergent = []

    for e in emergent:
        p = await _propose_decision(
            "spawn_lora",
            trigger_domain=e.candidateName,
            trigger_metric="emergent_domain",
            trigger_value=float(e.sampleCount),
            proposal={
                "new_domain": e.candidateName,
                "description": e.description,
                "example_queries": list(e.exampleQueries or []),
                "min_samples": EMERGENT_PROMOTE_THRESHOLD,
                "emergent_id": e.id,
            },
        )
        if p:
            proposals.append(p)

    return proposals


async def _propose_decision(
    decision_type: str,
    *,
    trigger_domain: Optional[str],
    trigger_metric: str,
    trigger_value: Optional[float],
    proposal: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """중복 회피 + GrowthDecision 생성."""
    # 동일 도메인+동일 trigger 의 미처리 결정이 있으면 skip
    try:
        existing = await prisma.growthdecision.find_first(
            where={
                "decisionType": decision_type,
                "triggerDomain": trigger_domain,
                "triggerMetric": trigger_metric,
                "status": {"in": ["proposed", "approved", "executing"]},
            },
        )
    except Exception:  # pragma: no cover
        existing = None

    if existing:
        return None

    try:
        row = await prisma.growthdecision.create(
            data={
                "decisionType": decision_type,
                "triggerDomain": trigger_domain,
                "triggerMetric": trigger_metric,
                "triggerValue": trigger_value,
                "proposalJson": proposal,
                "status": "proposed",
            }
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"GrowthDecision create 실패: {e}")
        return None

    logger.info(
        f"[auto_spawn] proposed {decision_type} domain={trigger_domain} "
        f"metric={trigger_metric}={trigger_value}"
    )
    return _decision_to_dict(row)


# ────────────────────────────────────────────────────────────
# 승인 / 거절 / 실행
# ────────────────────────────────────────────────────────────
async def approve_decision(
    decision_id: str, reviewed_by: Optional[str] = None
) -> dict[str, Any]:
    if not _prisma_ready():
        return {"approved": False, "reason": "db_unavailable"}
    try:
        row = await prisma.growthdecision.update(
            where={"id": decision_id},
            data={
                "status": "approved",
                "reviewedBy": reviewed_by,
                "reviewedAt": datetime.now(timezone.utc),
            },
        )
        return {"approved": True, "id": row.id, "type": row.decisionType}
    except Exception as e:  # pragma: no cover
        logger.warning(f"approve_decision 실패: {e}")
        return {"approved": False, "error": str(e)}


async def reject_decision(
    decision_id: str,
    reason: str,
    reviewed_by: Optional[str] = None,
) -> dict[str, Any]:
    if not _prisma_ready():
        return {"rejected": False, "reason": "db_unavailable"}
    try:
        await prisma.growthdecision.update(
            where={"id": decision_id},
            data={
                "status": "rejected",
                "rejectReason": (reason or "")[:500],
                "reviewedBy": reviewed_by,
                "reviewedAt": datetime.now(timezone.utc),
            },
        )
        return {"rejected": True, "id": decision_id}
    except Exception as e:  # pragma: no cover
        logger.warning(f"reject_decision 실패: {e}")
        return {"rejected": False, "error": str(e)}


async def execute_decision(decision_id: str) -> dict[str, Any]:
    """승인된 결정 실행. 결정 타입별 핸들러 분기."""
    if not _prisma_ready():
        return {"executed": False, "reason": "db_unavailable"}

    try:
        decision = await prisma.growthdecision.find_unique(
            where={"id": decision_id}
        )
    except Exception as e:  # pragma: no cover
        return {"executed": False, "error": str(e)}

    if not decision:
        return {"executed": False, "reason": "not_found"}
    if decision.status != "approved":
        return {"executed": False, "reason": f"status_{decision.status}"}

    # executing 표시
    try:
        await prisma.growthdecision.update(
            where={"id": decision_id},
            data={"status": "executing"},
        )
    except Exception:  # pragma: no cover
        pass

    handler = {
        "spawn_lora": _spawn_lora,
        "split_domain": _split_domain,
        "scale_base": _scale_base,
        "expand_lora_rank": _expand_lora_rank,
    }.get(decision.decisionType)

    if not handler:
        result = {"error": f"unknown decision type: {decision.decisionType}"}
        await _mark_done(decision_id, result, success=False)
        return {"executed": False, **result}

    try:
        result = await handler(decision)
    except Exception as e:  # pragma: no cover
        logger.warning(f"execute_decision 실행 실패: {e}")
        result = {"error": str(e)}
        await _mark_done(decision_id, result, success=False)
        return {"executed": False, **result}

    success = "error" not in result
    await _mark_done(decision_id, result, success=success)
    return {"executed": success, **result}


async def _mark_done(
    decision_id: str, result: dict[str, Any], success: bool
) -> None:
    try:
        await prisma.growthdecision.update(
            where={"id": decision_id},
            data={
                "status": "done" if success else "rejected",
                "resultJson": result,
                "executedAt": datetime.now(timezone.utc),
            },
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"_mark_done 실패: {e}")


# ────────────────────────────────────────────────────────────
# 결정 핸들러
# ────────────────────────────────────────────────────────────
async def _spawn_lora(decision: Any) -> dict[str, Any]:
    """새 LoRA TrainingJob 생성 + EmergentDomain 이면 promotion."""
    p: dict[str, Any] = decision.proposalJson or {}
    domain = p.get("new_domain") or p.get("domain") or decision.triggerDomain
    if not domain:
        return {"error": "no domain"}

    # 베이스 모델 — AIModel 에서 동일 카테고리 우선, 없으면 default
    base_model = "hwarang-v5-awq"
    try:
        existing = await prisma.aimodel.find_first(
            where={"category": domain, "isActive": True, "loraName": {"not": None}},
        )
        if existing:
            base_model = existing.backendId
    except Exception:  # pragma: no cover
        pass

    lora_name = f"hwarang-{domain}-v1"

    job = await create_training_job(
        domain=domain,
        lora_name=lora_name,
        base_model=base_model,
        sample_count=int(p.get("min_samples") or 0),
        triggered_by="auto_spawn",
    )

    # EmergentDomain 이면 promoted=true
    if p.get("emergent_id"):
        try:
            await prisma.emergentdomain.update(
                where={"id": p["emergent_id"]},
                data={
                    "isPromoted": True,
                    "promotedAt": datetime.now(timezone.utc),
                },
            )
        except Exception:  # pragma: no cover
            pass

    return {
        "type": "spawn_lora",
        "domain": domain,
        "loraName": lora_name,
        "baseModel": base_model,
        "trainingJob": job,
    }


async def _split_domain(decision: Any) -> dict[str, Any]:
    """도메인 split — 클러스터링 결과 활용 필요. 자동화 제한적.

    현재는 ``EmergentDomain`` 후보를 트리거 도메인으로 부착하고 사람 검토 표시.
    """
    return {
        "type": "split_domain",
        "todo": "manual_review_required",
        "note": "use domain_clustering.discover_emergent_domains for sub-clusters",
        "parent_domain": decision.triggerDomain,
    }


async def _scale_base(decision: Any) -> dict[str, Any]:
    """Depth Up-Scaling / 베이스 모델 교체 — 외부 ``mergekit`` 잡 필요."""
    return {
        "type": "scale_base",
        "todo": "manual_execution_required",
        "note": "trigger external mergekit / model merge pipeline",
        "proposal": decision.proposalJson,
    }


async def _expand_lora_rank(decision: Any) -> dict[str, Any]:
    """LoRA rank 확장 — 새 TrainingJob 을 더 높은 rank 메타로 enqueue."""
    p: dict[str, Any] = decision.proposalJson or {}
    domain = p.get("domain") or decision.triggerDomain
    if not domain:
        return {"error": "no domain"}

    base_model = "hwarang-v5-awq"
    try:
        ai = await prisma.aimodel.find_first(
            where={"category": domain, "isActive": True, "loraName": {"not": None}},
        )
        if ai:
            base_model = ai.backendId
            lora_name = ai.loraName + "-r" + str(p.get("target_rank") or 32)
        else:
            lora_name = f"hwarang-{domain}-r{p.get('target_rank') or 32}"
    except Exception:  # pragma: no cover
        lora_name = f"hwarang-{domain}-r32"

    job = await create_training_job(
        domain=domain,
        lora_name=lora_name,
        base_model=base_model,
        triggered_by="auto_spawn_rank",
    )
    return {
        "type": "expand_lora_rank",
        "domain": domain,
        "loraName": lora_name,
        "trainingJob": job,
    }


# ────────────────────────────────────────────────────────────
# 조회
# ────────────────────────────────────────────────────────────
async def list_decisions(
    status: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if not _prisma_ready():
        return []
    where: dict[str, Any] = {}
    if status:
        where["status"] = status
    rows = await prisma.growthdecision.find_many(
        where=where,
        order={"createdAt": "desc"},
        take=limit,
    )
    return [_decision_to_dict(r) for r in rows]


async def get_decision(decision_id: str) -> Optional[dict[str, Any]]:
    if not _prisma_ready():
        return None
    row = await prisma.growthdecision.find_unique(where={"id": decision_id})
    return _decision_to_dict(row) if row else None


def _decision_to_dict(r: Any) -> dict[str, Any]:
    return {
        "id": r.id,
        "decisionType": r.decisionType,
        "triggerDomain": r.triggerDomain,
        "triggerMetric": r.triggerMetric,
        "triggerValue": r.triggerValue,
        "status": r.status,
        "proposalJson": r.proposalJson,
        "reviewedBy": r.reviewedBy,
        "reviewedAt": r.reviewedAt.isoformat() if r.reviewedAt else None,
        "rejectReason": r.rejectReason,
        "executedAt": r.executedAt.isoformat() if r.executedAt else None,
        "resultJson": r.resultJson,
        "createdAt": r.createdAt.isoformat() if r.createdAt else None,
    }


__all__ = [
    "evaluate_and_propose",
    "approve_decision",
    "reject_decision",
    "execute_decision",
    "list_decisions",
    "get_decision",
]
