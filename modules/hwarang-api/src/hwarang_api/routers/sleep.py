"""Phase 9.ι Sleep Cycle 라우터.

엔드포인트
----------
* ``POST /api/sleep/run``            — 사이클 1 회 실행 (관리자)
* ``GET  /api/sleep/last-cycle``     — 마지막 사이클 결과
* ``GET  /api/sleep/semantic-rules`` — SemanticRule 조회 (topic 필터)
* ``POST /api/sleep/dream``          — 수동 dream (선택 seed_memory_ids)

권한
----
``run`` / ``dream`` 는 ``X-Admin-Token`` 헤더가 ``HWARANG_ADMIN_TOKEN`` 과
일치해야 한다.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from hwarang_api.cognitive.sleep import (
    DreamGenerator,
    Memory,
    ReplayBuffer,
    SleepScheduler,
)
from hwarang_api.cognitive.sleep.sleep_scheduler import get_last_cycle_result
from hwarang_api.db import prisma

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sleep", tags=["Sleep"])


def _verify_admin(x_admin_token: Optional[str]) -> None:
    expected = os.getenv("HWARANG_ADMIN_TOKEN")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="HWARANG_ADMIN_TOKEN 미설정 — Sleep API 비활성",
        )
    if not x_admin_token or x_admin_token != expected:
        raise HTTPException(status_code=401, detail="관리자 인증 실패")


class RunRequest(BaseModel):
    actor: str = Field("master", description="대상 actor")
    replay_top_n: int = Field(50, ge=1, le=500)
    dream_seed_count: int = Field(10, ge=0, le=50)
    dream_variations: int = Field(3, ge=1, le=10)
    forgetting_threshold: float = Field(0.05, ge=0.0, le=1.0)


@router.post("/run")
async def run_sleep(
    body: RunRequest | None = None,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> dict:
    """수면 사이클 1 회 트리거."""
    _verify_admin(x_admin_token)
    body = body or RunRequest()
    sched = SleepScheduler(
        actor=body.actor,
        replay_top_n=body.replay_top_n,
        dream_seed_count=body.dream_seed_count,
        dream_variations=body.dream_variations,
        forgetting_threshold=body.forgetting_threshold,
    )
    result = await sched.run_sleep_cycle()
    return result.to_dict()


@router.get("/last-cycle")
async def last_cycle() -> dict:
    """마지막 실행 결과. 아직 실행 전이면 null 필드들."""
    res = get_last_cycle_result()
    if res is None:
        return {"available": False}
    return {"available": True, **res.to_dict()}


@router.get("/semantic-rules")
async def list_rules(
    topic: Optional[str] = None,
    limit: int = 50,
    from_dream: Optional[bool] = None,
) -> dict:
    """SemanticRule 조회 (topic substring + from_dream 필터)."""
    limit = max(1, min(int(limit), 200))
    where: dict = {}
    if topic:
        where["topic"] = {"contains": topic}
    if from_dream is not None:
        where["fromDream"] = bool(from_dream)
    try:
        rows = await prisma.semanticrule.find_many(
            where=where or None,
            take=limit,
            order={"lastReinforced": "desc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("SemanticRule 조회 실패: %s", exc)
        return {"items": [], "error": str(exc), "migration_pending": True}

    items = []
    for r in rows or []:
        items.append(
            {
                "id": getattr(r, "id", None),
                "topic": getattr(r, "topic", None),
                "rule": getattr(r, "rule", None),
                "confidence": getattr(r, "confidence", None),
                "exceptions": getattr(r, "exceptions", []),
                "sourceCount": getattr(r, "sourceCount", 0),
                "lastReinforced": getattr(r, "lastReinforced", None),
                "fromDream": getattr(r, "fromDream", False),
            }
        )
    return {"items": items, "count": len(items)}


class DreamRequest(BaseModel):
    seed_memory_ids: Optional[list[str]] = Field(
        None, description="비우면 saliency top 으로 자동 선택"
    )
    count: int = Field(5, ge=1, le=30, description="총 dream 수 (seed 별 1)")
    variations: int = Field(1, ge=1, le=5)
    actor: str = "master"


@router.post("/dream")
async def manual_dream(
    body: DreamRequest,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> dict:
    """수동 dream — 디버깅 / 콘텐츠 생성용."""
    _verify_admin(x_admin_token)

    seeds: list[Memory] = []
    if body.seed_memory_ids:
        # 명시 id 들로 메모리 hydrate
        for mid in body.seed_memory_ids[: body.count]:
            try:
                row = await prisma.cognitivememory.find_unique(
                    where={"id": mid}
                )
            except Exception:
                row = None
            if not row:
                continue
            seeds.append(
                Memory(
                    id=str(getattr(row, "id")),
                    content=(
                        f"{getattr(row, 'decision', '')}\n"
                        f"{(getattr(row, 'reasoning', '') or '')[:300]}"
                    ),
                    created_at=getattr(row, "timestamp", None)
                    or __import__("datetime").datetime.utcnow(),
                    last_accessed=getattr(row, "timestamp", None)
                    or __import__("datetime").datetime.utcnow(),
                    actor=body.actor,
                )
            )
    if not seeds:
        # 자동 선택
        buf = ReplayBuffer(actor=body.actor)
        seeds = await buf.select_for_replay(n=body.count)

    if not seeds:
        return {"dreams": [], "lessons": [], "note": "no seeds available"}

    gen = DreamGenerator(num_variations=body.variations)
    dreams = await gen.dream(seeds[: body.count])
    lessons = await gen.extract_lessons(dreams)

    return {
        "dreams": [
            {
                "seed_memory_id": d.seed_memory_id,
                "variation": d.variation,
                "plausibility": d.plausibility,
                "ideal_response": d.ideal_response,
                "lessons_learned": d.lessons_learned,
            }
            for d in dreams
        ],
        "lessons": lessons,
    }


__all__ = ["router"]
