"""Social Agent Network 라우터 — Phase 8.

엔드포인트
----------
* POST /api/social/negotiate            — 작업 입찰 제안 + 수집 + 낙찰
* POST /api/social/dispute              — 답변 충돌 LLM 심판
* POST /api/social/federated-query      — 신뢰 가중 분산 추론
* GET  /api/social/reputation/{agent_id}
* GET  /api/social/leaderboard
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from hwarang_api.routers.learning import _check_internal_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/social", tags=["Social"])


def _require_internal(authorization: Optional[str] = Header(None)) -> None:
    _check_internal_key(authorization)


# ────────────────────────────────────────────────────────────
# 1. Negotiate — propose + collect + select_winner 통합 호출
# ────────────────────────────────────────────────────────────
class NegotiatePayload(BaseModel):
    task_id: str
    candidate_agents: list[str] = Field(default_factory=list)
    budget_tokens: int = 100
    timeout_s: int = 10
    criteria: str = "trust_weighted"


@router.post("/negotiate")
async def negotiate(
    payload: NegotiatePayload,
    _: None = Depends(_require_internal),
) -> dict:
    """task 제안 → 입찰 수집 → 낙찰자 선택을 한 번에 수행.

    실제 입찰은 외부에서 ``submit_bid`` 콜백으로 들어와야 한다 (현재 in-memory
    저장소). 입찰이 없으면 ``winner=None`` 반환.
    """
    from hwarang_api.grid.social.negotiation import get_negotiator

    n = get_negotiator()
    proposal = await n.propose_task(
        task_id=payload.task_id,
        candidate_agents=payload.candidate_agents,
        budget_tokens=payload.budget_tokens,
    )
    bids = await n.collect_bids(payload.task_id, timeout_s=payload.timeout_s)
    winner = await n.select_winner(payload.task_id, criteria=payload.criteria)

    return {
        "proposal": proposal,
        "bid_count": len(bids),
        "bids": [
            {
                "agent_id": b.agent_id,
                "estimated_time_sec": b.estimated_time_sec,
                "confidence": b.confidence,
                "price_tokens": b.price_tokens,
            }
            for b in bids
        ],
        "winner": winner,
    }


class BidPayload(BaseModel):
    task_id: str
    agent_id: str
    estimated_time_sec: float
    confidence: float
    price_tokens: float


@router.post("/negotiate/bid")
async def submit_bid(payload: BidPayload) -> dict:
    """에이전트가 입찰을 제출 (인증은 주체측에서 별도 — 내부키 미사용)."""
    from hwarang_api.grid.social.negotiation import get_negotiator

    ok = await get_negotiator().submit_bid(
        task_id=payload.task_id,
        agent_id=payload.agent_id,
        estimated_time_sec=payload.estimated_time_sec,
        confidence=payload.confidence,
        price_tokens=payload.price_tokens,
    )
    return {"accepted": ok}


# ────────────────────────────────────────────────────────────
# 2. Dispute — 충돌 답변 LLM 심판
# ────────────────────────────────────────────────────────────
class DisputeAnswer(BaseModel):
    agent_id: str
    content: str
    sources: list[str] = Field(default_factory=list)


class DisputePayload(BaseModel):
    answers: list[DisputeAnswer] = Field(default_factory=list)
    update_reputation: bool = True


@router.post("/dispute")
async def dispute_endpoint(
    payload: DisputePayload,
    _: None = Depends(_require_internal),
) -> dict:
    from hwarang_api.grid.social.dispute import resolve_dispute

    answers = [a.model_dump() for a in payload.answers]
    result = await resolve_dispute(answers, update_reputation=payload.update_reputation)
    return result


# ────────────────────────────────────────────────────────────
# 3. Federated query — 분산 추론
# ────────────────────────────────────────────────────────────
class FederatedQueryPayload(BaseModel):
    question: str
    num_agents: int = 3


@router.post("/federated-query")
async def federated_query_endpoint(
    payload: FederatedQueryPayload,
    _: None = Depends(_require_internal),
) -> dict:
    from hwarang_api.grid.social.federated_reason import federated_query

    return await federated_query(payload.question, num_agents=payload.num_agents)


# ────────────────────────────────────────────────────────────
# 4. Reputation 조회 / 리더보드
# ────────────────────────────────────────────────────────────
@router.get("/reputation/{agent_id}")
async def reputation_endpoint(agent_id: str) -> dict:
    from hwarang_api.grid.social.reputation import get_reputation

    return await get_reputation(agent_id)


@router.get("/leaderboard")
async def leaderboard_endpoint(n: int = 10) -> dict:
    from hwarang_api.grid.social.reputation import top_agents

    rows = await top_agents(n=n)
    return {"count": len(rows), "agents": rows}


__all__ = ["router"]
