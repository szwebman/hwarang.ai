"""다중 에이전트 작업 협상 — 입찰/낙찰.

# TODO: Redis — 현재는 in-memory dict. 프로세스 재시작 시 입찰 휘발됨.
프로덕션에서는 Redis pub/sub + sorted set 으로 교체하고
broadcast 는 ``/api/grid/rounds/ws`` 채널 재사용.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from hwarang_api.grid.social.reputation import get_trust_score

logger = logging.getLogger(__name__)


@dataclass
class Bid:
    """단일 입찰."""

    agent_id: str
    estimated_time_sec: float
    confidence: float
    price_tokens: float
    submitted_at: float = field(default_factory=time.time)


@dataclass
class _TaskState:
    task_id: str
    candidate_agents: list[str]
    budget_tokens: int
    bids: dict[str, Bid] = field(default_factory=dict)
    proposed_at: float = field(default_factory=time.time)


class TaskNegotiation:
    """간단한 입찰/낙찰 매니저.

    프로세스 단일 인스턴스에서 여러 task 를 관리. 각 task 는 ``task_id`` 로 식별.
    입찰 수신은 외부에서 ``submit_bid`` 호출 (HTTP 콜백 또는 grid WS) 가정.
    """

    def __init__(self) -> None:
        # TODO: Redis — 다중 worker 환경에서 공유 필요.
        self._tasks: dict[str, _TaskState] = {}
        self._lock = asyncio.Lock()

    async def propose_task(
        self,
        task_id: str,
        candidate_agents: list[str],
        budget_tokens: int,
    ) -> dict:
        """task 등록 + (production: 후보들에게 broadcast).

        현재는 storage 등록만. 실제 broadcast 는 grid 라우터 WS 와 통합 예정.
        """
        async with self._lock:
            self._tasks[task_id] = _TaskState(
                task_id=task_id,
                candidate_agents=list(candidate_agents),
                budget_tokens=int(budget_tokens),
            )
        logger.info(
            "negotiate.propose: task=%s candidates=%d budget=%d",
            task_id,
            len(candidate_agents),
            budget_tokens,
        )
        return {
            "task_id": task_id,
            "candidates": list(candidate_agents),
            "budget_tokens": int(budget_tokens),
            "broadcast": "in-memory (TODO Redis)",
        }

    async def submit_bid(
        self,
        task_id: str,
        agent_id: str,
        estimated_time_sec: float,
        confidence: float,
        price_tokens: float,
    ) -> bool:
        """단일 에이전트 입찰 등록. task 가 없거나 후보가 아니면 ``False``."""
        async with self._lock:
            state = self._tasks.get(task_id)
            if state is None:
                logger.warning("negotiate.bid: 알 수 없는 task=%s", task_id)
                return False
            if state.candidate_agents and agent_id not in state.candidate_agents:
                logger.warning(
                    "negotiate.bid: %s 는 task=%s 후보 아님",
                    agent_id,
                    task_id,
                )
                return False
            state.bids[agent_id] = Bid(
                agent_id=agent_id,
                estimated_time_sec=max(0.0, float(estimated_time_sec)),
                confidence=max(0.0, min(1.0, float(confidence))),
                price_tokens=max(0.0, float(price_tokens)),
            )
        return True

    async def collect_bids(self, task_id: str, timeout_s: int = 10) -> list[Bid]:
        """``timeout_s`` 동안 입찰 수집 후 리스트 반환.

        실제 환경에서는 외부 콜백이 그 사이에 ``submit_bid`` 를 호출.
        타임아웃 후 모든 입찰 반환 (조기 종료 조건은 production 에서 추가).
        """
        timeout_s = max(1, min(int(timeout_s), 120))
        await asyncio.sleep(timeout_s)
        async with self._lock:
            state = self._tasks.get(task_id)
            if state is None:
                return []
            return list(state.bids.values())

    async def select_winner(
        self,
        task_id: str,
        criteria: str = "trust_weighted",
    ) -> Optional[dict]:
        """낙찰자 선정.

        Criteria
        --------
        ``trust_weighted`` (기본)
            ``score = (1 / max(price, 1)) * trust * confidence``.
        ``cheapest``
            가장 낮은 ``price_tokens``.
        ``fastest``
            가장 짧은 ``estimated_time_sec``.

        Returns
        -------
        dict | None
            ``{agent_id, score, bid: {...}, criteria}`` 또는 입찰 없을 시 None.
        """
        async with self._lock:
            state = self._tasks.get(task_id)
            if state is None or not state.bids:
                return None
            bids = list(state.bids.values())
            budget = state.budget_tokens

        # 예산 초과 입찰 제외
        eligible = [b for b in bids if b.price_tokens <= budget or budget <= 0]
        if not eligible:
            eligible = bids

        if criteria == "cheapest":
            winner = min(eligible, key=lambda b: b.price_tokens)
            score = -winner.price_tokens
        elif criteria == "fastest":
            winner = min(eligible, key=lambda b: b.estimated_time_sec)
            score = -winner.estimated_time_sec
        else:
            # trust_weighted 기본
            scored: list[tuple[float, Bid]] = []
            for b in eligible:
                trust = await get_trust_score(b.agent_id)
                price_div = max(1.0, b.price_tokens)
                score_val = (1.0 / price_div) * trust * b.confidence
                scored.append((score_val, b))
            scored.sort(key=lambda x: x[0], reverse=True)
            score, winner = scored[0]

        return {
            "task_id": task_id,
            "agent_id": winner.agent_id,
            "score": round(float(score), 6),
            "criteria": criteria,
            "bid": {
                "estimated_time_sec": winner.estimated_time_sec,
                "confidence": winner.confidence,
                "price_tokens": winner.price_tokens,
            },
        }

    async def get_task(self, task_id: str) -> Optional[dict]:
        async with self._lock:
            state = self._tasks.get(task_id)
            if state is None:
                return None
            return {
                "task_id": state.task_id,
                "candidates": list(state.candidate_agents),
                "budget_tokens": state.budget_tokens,
                "bid_count": len(state.bids),
                "proposed_at": state.proposed_at,
            }


# 싱글톤 — 프로세스 전역 — TODO: Redis 로 교체 시 인터페이스 유지
_negotiator: Optional[TaskNegotiation] = None


def get_negotiator() -> TaskNegotiation:
    global _negotiator
    if _negotiator is None:
        _negotiator = TaskNegotiation()
    return _negotiator


__all__ = ["TaskNegotiation", "Bid", "get_negotiator"]
