"""Sleep Scheduler — 한 번의 수면 사이클 오케스트레이션.

3 단계
------
* Phase 1 (NREM)    — top-50 salient 메모리 재생 + 의미 규칙 통합
* Phase 2 (REM)     — 무작위 10 개 seed 로 dream 생성 + 교훈 추출
* Phase 3 (Cleanup) — 망각곡선 적용 + soft-archive

Cron 권장
---------
``0 3 * * *`` — 매일 새벽 3 시. 다만 본 모듈은 함수만 제공하고
글로벌 cron 등록은 하지 않는다 (호출 측 결정).
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import asdict, dataclass, field

from .consolidator import ConsolidationResult, MemoryConsolidator
from .dream_generator import Dream, DreamGenerator
from .forgetting_curve import ForgettingCurve
from .replay_buffer import Memory, ReplayBuffer

logger = logging.getLogger(__name__)


@dataclass
class SleepCycleResult:
    """한 사이클의 종합 결과 — JSON 직렬화 안전."""

    replayed: int = 0
    consolidated_rules: int = 0
    dreams_generated: int = 0
    lessons_extracted: int = 0
    archived_count: int = 0
    duration_s: float = 0.0
    errors: list[str] = field(default_factory=list)
    consolidation: dict | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# 마지막 사이클 결과 캐시 (라우터 GET /last-cycle 용)
_LAST_RESULT: SleepCycleResult | None = None


class SleepScheduler:
    """한 사이클 실행 — 외부에서 cron 으로 깨움."""

    def __init__(
        self,
        actor: str = "master",
        replay_top_n: int = 50,
        dream_seed_count: int = 10,
        dream_variations: int = 3,
        forgetting_threshold: float = 0.05,
    ):
        self.actor = actor
        self.replay_top_n = replay_top_n
        self.dream_seed_count = dream_seed_count
        self.dream_variations = dream_variations
        self.forgetting_threshold = forgetting_threshold

    async def _phase1_nrem(
        self,
    ) -> tuple[list[Memory], ConsolidationResult]:
        """Replay + Consolidate."""
        buf = ReplayBuffer(actor=self.actor)
        memories = await buf.select_for_replay(n=self.replay_top_n)
        consolidator = MemoryConsolidator()
        cresult = await consolidator.consolidate_batch(memories)
        return memories, cresult

    async def _phase2_rem(
        self, replayed: list[Memory]
    ) -> tuple[list[Dream], list[str]]:
        """Dream + extract lessons."""
        if not replayed:
            return [], []
        seed_n = min(self.dream_seed_count, len(replayed))
        seeds = random.sample(replayed, seed_n)
        gen = DreamGenerator(num_variations=self.dream_variations)
        dreams = await gen.dream(seeds)
        lessons = await gen.extract_lessons(dreams)
        if lessons:
            await gen.feed_back_to_semantic_rules(lessons)
        return dreams, lessons

    async def _phase3_cleanup(self, replayed: list[Memory]) -> int:
        """Forgetting curve → archive."""
        curve = ForgettingCurve(threshold=self.forgetting_threshold)
        archived = await curve.apply_forgetting(replayed)
        return len(archived)

    async def _audit_log(self, result: SleepCycleResult) -> None:
        """가능하면 cognitive/audit.py 에 한 줄 남김 — 실패해도 무시."""
        try:
            from hwarang_api.cognitive.audit import log_audit

            await log_audit(
                memory_id="",
                cycle_type="sleep_cycle",
                hallucination_report={
                    "confidence": 0.0,
                    "consistency_score": 1.0,
                    "schema_valid": True,
                    "risky_keywords": [],
                },
                risky_actions_blocked=[],
                user_approval_required=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("sleep audit 기록 스킵: %s", exc)

    async def run_sleep_cycle(self) -> SleepCycleResult:
        """전체 사이클 1 회 실행."""
        global _LAST_RESULT
        t0 = time.time()
        result = SleepCycleResult()
        try:
            replayed, cresult = await self._phase1_nrem()
            result.replayed = len(replayed)
            result.consolidated_rules = (
                cresult.rules_created + cresult.rules_updated
            )
            result.consolidation = {
                "clusters_processed": cresult.clusters_processed,
                "rules_created": cresult.rules_created,
                "rules_updated": cresult.rules_updated,
                "total_memories_consolidated": cresult.total_memories_consolidated,
                "errors": cresult.errors,
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("Phase 1 (NREM) 실패")
            result.errors.append(f"phase1: {exc}")
            replayed = []

        try:
            dreams, lessons = await self._phase2_rem(replayed)
            result.dreams_generated = len(dreams)
            result.lessons_extracted = len(lessons)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Phase 2 (REM) 실패")
            result.errors.append(f"phase2: {exc}")

        try:
            result.archived_count = await self._phase3_cleanup(replayed)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Phase 3 (cleanup) 실패")
            result.errors.append(f"phase3: {exc}")

        result.duration_s = round(time.time() - t0, 3)
        await self._audit_log(result)
        _LAST_RESULT = result
        return result


def get_last_cycle_result() -> SleepCycleResult | None:
    """라우터 GET /api/sleep/last-cycle 이 호출."""
    return _LAST_RESULT


async def run_default_cycle() -> SleepCycleResult:
    """기본 옵션 한 사이클. CLI / 라우터 공용."""
    return await SleepScheduler().run_sleep_cycle()


# 권장 cron 표현식 — 문서/관리자 UI 가 참조 (자동 등록 X)
RECOMMENDED_CRON = "0 3 * * *"  # 매일 새벽 3시


__all__ = [
    "SleepScheduler",
    "SleepCycleResult",
    "get_last_cycle_result",
    "run_default_cycle",
    "RECOMMENDED_CRON",
]


if __name__ == "__main__":
    # 직접 실행 시 한 사이클
    res = asyncio.run(run_default_cycle())
    print(res.to_dict())
