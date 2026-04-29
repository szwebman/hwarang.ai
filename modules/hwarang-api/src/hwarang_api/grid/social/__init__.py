"""Social Agent Network — Phase 8.

에이전트 평판 / 협상 / 분쟁 / 분산 추론.

서브모듈
--------
* ``reputation.py``       — Agent 신뢰점수 (DB 영속화)
* ``negotiation.py``      — 작업 입찰/낙찰 (in-memory, TODO Redis)
* ``dispute.py``          — LLM 심판으로 답변 충돌 해결
* ``federated_reason.py`` — 신뢰 가중 분산 추론
"""

from __future__ import annotations

from .reputation import (
    get_trust_score,
    record_dispute,
    record_failure,
    record_success,
    top_agents,
)
from .negotiation import TaskNegotiation
from .dispute import resolve_dispute
from .federated_reason import federated_query

__all__ = [
    "get_trust_score",
    "record_success",
    "record_failure",
    "record_dispute",
    "top_agents",
    "TaskNegotiation",
    "resolve_dispute",
    "federated_query",
]
