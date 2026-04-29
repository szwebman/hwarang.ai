"""Phase 9.ι — 수면 사이클 (Sleep Cycle / Memory Consolidation).

뇌의 수면-각성 사이클을 모방: NREM 단계는 episodic memory 를 의미 규칙으로 통합,
REM 단계는 "꿈"으로 변형 시나리오를 생성·비평하며, 마지막 정리 단계에서
망각곡선(Ebbinghaus)을 적용해 사용되지 않은 기억을 archived 로 표시한다.
"""

from .consolidator import ConsolidationResult, MemoryConsolidator
from .dream_generator import Dream, DreamGenerator
from .forgetting_curve import ForgettingCurve
from .replay_buffer import Memory, ReplayBuffer
from .sleep_scheduler import SleepCycleResult, SleepScheduler

__all__ = [
    "Memory",
    "ReplayBuffer",
    "MemoryConsolidator",
    "ConsolidationResult",
    "ForgettingCurve",
    "Dream",
    "DreamGenerator",
    "SleepScheduler",
    "SleepCycleResult",
]
