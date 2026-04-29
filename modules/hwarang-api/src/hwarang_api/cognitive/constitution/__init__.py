"""화랑 Constitutional AI 모듈.

- constitution: 명시적 헌법 16 원칙
- self_critique: 응답 후 자기 비판 + 자동 수정
- value_conflict: 두 원칙 충돌 시 priority 기반 해결
- moral_reasoning: 회색 영역 도덕 추론
"""

from .constitution import (
    CONSTITUTION,
    Principle,
    constitution_summary_for_prompt,
    get_by_category,
    get_by_priority,
    get_constitution,
    get_principle,
)
from .moral_reasoning import MoralJudgment, judge_moral_gray_area
from .self_critique import CritiqueResult, auto_revise_if_violation, self_critique
from .value_conflict import ConflictResolution, resolve_conflict

__all__ = [
    "CONSTITUTION",
    "Principle",
    "get_constitution",
    "get_principle",
    "get_by_category",
    "get_by_priority",
    "constitution_summary_for_prompt",
    "CritiqueResult",
    "self_critique",
    "auto_revise_if_violation",
    "ConflictResolution",
    "resolve_conflict",
    "MoralJudgment",
    "judge_moral_gray_area",
]
