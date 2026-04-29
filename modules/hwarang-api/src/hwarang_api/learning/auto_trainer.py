"""자동 학습 트리거 — Phase 2.

Phase 1 의 ``auto_trigger`` 가 HFL 라운드 (Federated 다중 에이전트) 를 시작했다면,
Phase 2 의 ``auto_trainer`` 는 **단일 노드 LoRA 점진 학습 잡** 을 큐에 푸시한다.

흐름:
1. ``maybe_enqueue_training(domain)`` — 마지막 done 잡 이후 RLHFFeedback 누적 ≥ 1000 → 큐 push
2. ``process_queue()`` — 워커가 주기적으로 호출, queued 잡 1 개 pop 해서 ``train_online_lora`` 실행
3. ``training_jobs_status()`` — 관리자 UI 용 요약
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from hwarang_api.db import prisma
from hwarang_api.learning.training_state import (
    create_training_job,
    get_job,
    list_jobs,
)

logger = logging.getLogger(__name__)


# 환경변수
TRAINING_THRESHOLD = int(os.getenv("HSEE_TRAINING_THRESHOLD", "1000"))
LORA_BASE_DIR = os.getenv(
    "HSEE_LORA_BASE_DIR", "/mnt/nvme2/hwarang/lora_adapters"
)
DEFAULT_EWC_LAMBDA = float(os.getenv("HSEE_EWC_LAMBDA", "1000.0"))
DEFAULT_REPLAY_RATIO = float(os.getenv("HSEE_REPLAY_RATIO", "0.3"))


def _prisma_ready() -> bool:
    try:
        return bool(prisma.is_connected())
    except Exception:
        return False


# ────────────────────────────────────────────────────────────
# Enqueue
# ────────────────────────────────────────────────────────────
async def maybe_enqueue_training(
    domain: str,
    threshold: int = TRAINING_THRESHOLD,
    *,
    triggered_by: str = "auto",
) -> dict:
    """RLHFFeedback 가 임계치 넘으면 TrainingJob queued 로 추가.

    임계치 기준 = "마지막 done 잡 이후" RLHFFeedback 신규 건수.
    """
    if not _prisma_ready():
        return {"triggered": False, "reason": "db_unavailable"}

    domain = (domain or "general").strip().lower()

    # 1) 이미 queued/running 잡이 있으면 push 안 함 (도메인별 단일 잡 정책)
    try:
        existing = await prisma.trainingjob.find_first(
            where={"domain": domain, "status": {"in": ["queued", "running"]}},
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"TrainingJob 조회 실패: {e}")
        existing = None
    if existing:
        return {
            "triggered": False,
            "reason": "already_queued_or_running",
            "jobId": existing.id,
            "status": existing.status,
        }

    # 2) 마지막 done 잡 이후 누적 데이터
    last_done = await prisma.trainingjob.find_first(
        where={"domain": domain, "status": "done"},
        order={"completedAt": "desc"},
    )
    cutoff = (
        last_done.completedAt
        if last_done and last_done.completedAt
        else datetime(2020, 1, 1, tzinfo=timezone.utc)
    )

    try:
        count = await prisma.rlhffeedback.count(
            where={"domain": domain, "createdAt": {"gt": cutoff}},
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"RLHFFeedback count 실패: {e}")
        return {"triggered": False, "reason": f"db_error:{e}"}

    if count < threshold:
        return {
            "triggered": False,
            "reason": "insufficient_samples",
            "count": count,
            "threshold": threshold,
            "domain": domain,
        }

    # 3) 도메인 매칭 LoRA 찾기
    try:
        aimodel = await prisma.aimodel.find_first(
            where={
                "category": domain,
                "isActive": True,
                "loraName": {"not": None},
            },
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"AIModel 조회 실패: {e}")
        aimodel = None

    if not aimodel or not aimodel.loraName:
        return {
            "triggered": False,
            "reason": "no_lora_for_domain",
            "domain": domain,
            "count": count,
        }

    # 4) 잡 생성
    res = await create_training_job(
        domain=domain,
        lora_name=aimodel.loraName,
        base_model=aimodel.backendId,
        sample_count=count,
        triggered_by=triggered_by,
        ewc_lambda=DEFAULT_EWC_LAMBDA,
        replay_ratio=DEFAULT_REPLAY_RATIO,
    )
    if not res.get("created"):
        return {"triggered": False, "reason": "create_failed", **res}

    logger.info(
        f"[auto_trainer] enqueue domain={domain} count={count} "
        f"lora={aimodel.loraName} job={res['id']}"
    )
    return {
        "triggered": True,
        "jobId": res["id"],
        "domain": domain,
        "count": count,
        "loraName": aimodel.loraName,
        "baseModel": aimodel.backendId,
    }


# ────────────────────────────────────────────────────────────
# Worker — queued 잡 1 개 처리
# ────────────────────────────────────────────────────────────
async def process_queue() -> dict:
    """워커 루프 — queued 잡 1 개 골라서 train_online_lora 실행.

    호출 주체: 별도 학습 워커 컨테이너 (cron 또는 long-running loop).
    동시성: ``status="queued"`` → ``running`` 전환을 atomic 하게 하지 않으므로
    두 워커가 같은 잡을 잡을 수 있음. 단일 워커 가정 또는 SELECT FOR UPDATE
    필요시 raw SQL 로 보강.
    """
    if not _prisma_ready():
        return {"processed": 0, "reason": "db_unavailable"}

    try:
        job = await prisma.trainingjob.find_first(
            where={"status": "queued"},
            order={"createdAt": "asc"},
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"queue pop 실패: {e}")
        return {"processed": 0, "error": str(e)}

    if not job:
        return {"processed": 0}

    # train_online_lora 는 torch 의존성이라 lazy import
    from hwarang_api.learning.online_lora import train_online_lora

    target_lora_path = os.path.join(LORA_BASE_DIR, job.loraName)
    logger.info(
        f"[auto_trainer] processing job={job.id} domain={job.domain} "
        f"lora={job.loraName} target={target_lora_path}"
    )

    result = await train_online_lora(
        job_id=job.id,
        domain=job.domain,
        base_model=job.baseModel,
        target_lora_path=target_lora_path,
        ewc_lambda=job.ewcLambda,
        new_data_ratio=1.0 - job.replayRatio,
    )
    return {"processed": 1, "jobId": job.id, "result": result}


# ────────────────────────────────────────────────────────────
# Status
# ────────────────────────────────────────────────────────────
async def training_jobs_status() -> dict[str, Any]:
    """현재 큐 상태 요약."""
    if not _prisma_ready():
        return {"db": "unavailable"}

    summary: dict[str, int] = {}
    for status in ("queued", "running", "done", "failed"):
        try:
            summary[status] = await prisma.trainingjob.count(
                where={"status": status}
            )
        except Exception:  # pragma: no cover
            summary[status] = -1

    recent = await list_jobs(limit=10)
    return {
        "threshold": TRAINING_THRESHOLD,
        "ewc_lambda": DEFAULT_EWC_LAMBDA,
        "replay_ratio": DEFAULT_REPLAY_RATIO,
        "summary": summary,
        "recent": recent,
    }


__all__ = [
    "maybe_enqueue_training",
    "process_queue",
    "training_jobs_status",
    "get_job",
    "list_jobs",
]
