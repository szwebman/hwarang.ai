"""Ebbinghaus Forgetting Curve — 사용되지 않는 기억의 retention 감쇠.

공식
----
    retention(t) = exp(-t / strength)
    strength = log(1 + frequency * emotional_weight)

* t : 마지막 접근 후 경과 일수
* strength : 자주/감정적으로 강한 기억일수록 오래 유지

Hwarang 정책
-----------
"삭제 없이 누적" (HLKM). 망각은 hard-delete 가 아니라 soft-archive
(``archived=True`` 마킹). 학습 데이터/감사 추적이 보장됨.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from hwarang_api.db import prisma

from .replay_buffer import Memory

logger = logging.getLogger(__name__)


class ForgettingCurve:
    """retention 계산 + 망각 후보 선별 + soft-archive 적용."""

    DEFAULT_THRESHOLD = 0.05
    # strength 가 0 이 되지 않게 최소 floor
    _MIN_STRENGTH = 0.5

    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        self.threshold = max(0.0, min(1.0, float(threshold)))

    @staticmethod
    def _strength(memory: Memory) -> float:
        freq = max(0, int(memory.frequency))
        emo = max(0.0, min(1.0, float(memory.emotional_weight)))
        s = math.log1p(freq * emo)
        return max(ForgettingCurve._MIN_STRENGTH, s)

    @staticmethod
    def _days_since(ts: datetime, now: datetime) -> float:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return max(0.0, (now - ts).total_seconds() / 86400.0)

    def compute_retention(
        self, memory: Memory, current_time: datetime | None = None
    ) -> float:
        """0~1 retention 점수. 1 = 완전 기억, 0 = 거의 잊음."""
        now = current_time or datetime.now(timezone.utc)
        t = self._days_since(memory.last_accessed, now)
        s = self._strength(memory)
        try:
            return float(math.exp(-t / s))
        except OverflowError:
            return 0.0

    def should_forget(
        self,
        memory: Memory,
        threshold: float | None = None,
        recent_window_days: float = 3.0,
    ) -> bool:
        """retention < threshold AND 최근 recent_window_days 일 안에 접근 X 일 때만."""
        thr = self.threshold if threshold is None else max(0.0, min(1.0, threshold))
        now = datetime.now(timezone.utc)
        if self._days_since(memory.last_accessed, now) <= recent_window_days:
            return False
        return self.compute_retention(memory, now) < thr

    async def apply_forgetting(self, memories: list[Memory]) -> list[str]:
        """망각 후보 id 리스트 반환 + DB 에 archived=True soft-mark.

        DB 컬럼이 없거나 호출 실패해도 id 리스트는 반환 (fallback).
        절대 hard-delete 금지.
        """
        if not memories:
            return []
        to_archive: list[str] = [m.id for m in memories if self.should_forget(m)]
        if not to_archive:
            return []

        # CognitiveMemory 에는 archived 컬럼이 없을 수 있음 — try/except 로 안전.
        # 마이그레이션 이전 환경에서는 id 만 반환 (in-memory archive 책임은 호출측).
        for mid in to_archive:
            try:
                await prisma.cognitivememory.update(
                    where={"id": mid},
                    data={"archived": True},
                )
            except Exception as exc:  # noqa: BLE001
                # 컬럼 미존재 / 모델 미마이그레이션 — 디버그 로그만
                logger.debug("archive 마킹 스킵 (%s): %s", mid, exc)
                continue
        return to_archive


__all__ = ["ForgettingCurve"]
