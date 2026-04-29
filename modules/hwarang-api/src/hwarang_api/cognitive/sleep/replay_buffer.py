"""Replay Buffer — 가장 "현저한(salient)" 기억을 골라 재생.

뇌의 hippocampus 가 수면 중 중요한 episode 를 반복 재생하며 cortex 로
이전하는 과정을 모방.

Saliency 공식
-------------
    saliency = 0.4 * recency
             + 0.3 * emotional_weight
             + 0.2 * surprise
             + 0.1 * frequency

* recency: 마지막 접근 후 경과 일수에 대한 지수 감쇠 (exp(-days/14))
* emotional_weight: LLM 또는 outcome_score 로부터 0~1 신호
* surprise: prediction error (없으면 0.5 default)
* frequency: 누적 접근 횟수 (log scale)

DB
--
``CognitiveMemory`` 테이블을 episodic memory 로 사용.
``timestamp`` 를 created_at 으로, ``outcomeScore`` 를 emotional_weight proxy 로.
``last_accessed`` / ``frequency`` / ``surprise`` 컬럼이 없으므로 in-memory
ReplayStat 캐시로 누적 (프로세스 재시작 시 초기화 — TODO: 별도 모델).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


@dataclass
class Memory:
    """재생 후보 한 건."""

    id: str
    content: str
    created_at: datetime
    last_accessed: datetime
    frequency: int = 0
    emotional_weight: float = 0.5
    surprise: float = 0.5
    actor: str = "master"
    saliency: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


# 프로세스 라이프타임 통계 — id → (frequency, last_accessed)
# TODO: 영구화하려면 ReplayStat Prisma 모델 추가.
_REPLAY_STATS: dict[str, dict[str, Any]] = {}


def _record_access(mem_id: str) -> None:
    """재생 시 frequency 증가 + last_accessed 갱신."""
    now = datetime.now(timezone.utc)
    cur = _REPLAY_STATS.get(mem_id) or {"frequency": 0, "last_accessed": now}
    cur["frequency"] = int(cur.get("frequency", 0)) + 1
    cur["last_accessed"] = now
    _REPLAY_STATS[mem_id] = cur


def _recency_score(last_accessed: datetime) -> float:
    """0~1, 최근일수록 1. 14일 이상이면 거의 0."""
    now = datetime.now(timezone.utc)
    if last_accessed.tzinfo is None:
        last_accessed = last_accessed.replace(tzinfo=timezone.utc)
    days = max(0.0, (now - last_accessed).total_seconds() / 86400.0)
    return math.exp(-days / 14.0)


def _frequency_score(freq: int) -> float:
    """log 정규화 — 자주 본 기억일수록 높지만 무한 증가 방지."""
    return min(1.0, math.log1p(max(0, freq)) / 5.0)


def compute_saliency(m: Memory) -> float:
    """공식대로 0~1 점수 계산. 입력 음수/이상치는 안전 클램프."""
    rec = max(0.0, min(1.0, _recency_score(m.last_accessed)))
    emo = max(0.0, min(1.0, float(m.emotional_weight)))
    sur = max(0.0, min(1.0, float(m.surprise)))
    freq = _frequency_score(int(m.frequency))
    score = 0.4 * rec + 0.3 * emo + 0.2 * sur + 0.1 * freq
    return max(0.0, min(1.0, score))


class ReplayBuffer:
    """CognitiveMemory 에서 saliency top-N 선택."""

    def __init__(self, actor: str = "master", lookback_days: int = 30):
        self.actor = actor
        self.lookback_days = lookback_days

    async def _load_recent(self, take: int = 500) -> list[Memory]:
        """최근 lookback_days 일치 episodic memory 로드. 실패 시 [] 반환."""
        try:
            rows = await prisma.cognitivememory.find_many(
                where={"actor": self.actor},
                order={"timestamp": "desc"},
                take=take,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("replay buffer DB 조회 실패: %s", exc)
            return []

        out: list[Memory] = []
        for r in rows or []:
            mid = getattr(r, "id", None)
            if not mid:
                continue
            stat = _REPLAY_STATS.get(mid, {})
            ts = getattr(r, "timestamp", None) or datetime.now(timezone.utc)
            last = stat.get("last_accessed") or ts
            freq = int(stat.get("frequency", 0))
            score = getattr(r, "outcomeScore", None)
            emo = float(score) if score is not None else 0.5
            # outcomeScore 가 -1~1 범위일 수 있어 abs → 0~1
            emo = max(0.0, min(1.0, abs(emo)))

            content_parts = []
            reasoning = getattr(r, "reasoning", None)
            decision = getattr(r, "decision", None)
            outcome = getattr(r, "outcome", None)
            if decision:
                content_parts.append(f"결정: {decision}")
            if reasoning:
                content_parts.append(f"추론: {reasoning[:300]}")
            if outcome:
                content_parts.append(f"결과: {outcome[:200]}")
            content = "\n".join(content_parts) or "(empty)"

            mem = Memory(
                id=str(mid),
                content=content,
                created_at=ts,
                last_accessed=last,
                frequency=freq,
                emotional_weight=emo,
                surprise=0.5,
                actor=self.actor,
                metadata={"lesson": getattr(r, "lesson", None)},
            )
            mem.saliency = compute_saliency(mem)
            out.append(mem)
        return out

    async def select_for_replay(self, n: int = 50) -> list[Memory]:
        """Top-N saliency. n<=0 이면 빈 리스트."""
        if n <= 0:
            return []
        pool = await self._load_recent(take=max(n * 5, 200))
        if not pool:
            return []
        pool.sort(key=lambda m: m.saliency, reverse=True)
        chosen = pool[:n]
        for m in chosen:
            _record_access(m.id)
        return chosen


__all__ = ["Memory", "ReplayBuffer", "compute_saliency"]
