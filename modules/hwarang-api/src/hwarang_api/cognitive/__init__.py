"""Master Cognitive Loop — Phase 6 / Free Will — Phase 7.

Phase 6 — 마스터가 자율적으로 관찰 → 추론 → 계획 → 실행 → 반성 사이클을
매 15 분 실행한다. ``hlkm_scheduler`` 가 ``cognitive_cycle()`` 을 cron 으로 호출.

Phase 7 — 자유의사 (Free Will). cron 없이 적응적 간격 + 자기 목표 + 자발 질문 + 의도.

모듈 구성
---------
* ``memory.py``               — CognitiveMemory CRUD (record/update/lessons)
* ``reasoning.py``            — LLM JSON 추론 + 폴백 (의도 주입 포함)
* ``guardrails.py``           — 단일 결정 디스패치 + 승인 큐잉
* ``guardrails_advanced.py``  — 무한루프/비용/자가종료 메타 안전 (Phase 6 보강)
* ``inter_agent.py``          — 다회차 토론 + 의견 변경 추적 (Phase 6 보강)
* ``orchestrator.py``         — 라운드 시작 전 에이전트 의향 조사 (Phase 6 보강)
* ``master_loop.py``          — observe + reason + execute + reflect 메인 사이클
* ``free_will.py``            — Phase 7 적응적 간격 + 인터럽트 무한 루프
* ``goal_generator.py``       — Phase 7 LLM 자유 목표 생성 → GrowthDecision
* ``spontaneous.py``          — Phase 7 자발적 호기심 사이클 (seed + 자동 메타 질문)
* ``intent.py``               — Phase 7 매주 의도 선언 (SystemSetting)
"""

from .guardrails import check_and_execute
from .guardrails_advanced import (
    check_cost_budget,
    check_health,
    clear_disable_flag,
    detect_infinite_loop,
    emergency_disable,
    is_cognitive_enabled,
    should_self_disable,
)
from .inter_agent import AgentOpinion, DebateState, multi_round_debate
from .master_loop import (
    AVAILABLE_ACTIONS,
    COGNITIVE_ENABLED,
    MAX_ACTIONS_PER_DAY,
    REQUIRES_APPROVAL,
    cognitive_cycle,
    observe,
    reflect_on_recent,
)
from .memory import (
    find_similar_past_decisions,
    get_recent_lessons,
    record_decision,
    update_outcome,
)
from .orchestrator import consult_agents_for_round
from .reasoning import reason_about_state

# Phase 7 — Free Will
from .free_will import (
    DEFAULT_INTERVAL_SEC,
    MAX_INTERVAL_SEC,
    MIN_INTERVAL_SEC,
    current_interval,
    decide_next_interval,
    free_will_goal_cycle,
    free_will_loop,
    is_running,
    stop_free_will,
    trigger_immediate_cycle,
)
from .goal_generator import generate_creative_goals, queue_goal_as_decision
from .intent import (
    FOCUS_AREAS,
    declare_weekly_intent,
    get_current_intent,
)
from .spontaneous import SEED_CURIOSITIES, spontaneous_curiosity_cycle

__all__ = [
    # 메인 사이클
    "cognitive_cycle",
    "observe",
    "reflect_on_recent",
    # 메모리
    "record_decision",
    "update_outcome",
    "get_recent_lessons",
    "find_similar_past_decisions",
    # 추론
    "reason_about_state",
    # 가드레일 (기본)
    "check_and_execute",
    # 가드레일 (고급)
    "detect_infinite_loop",
    "check_cost_budget",
    "check_health",
    "should_self_disable",
    "emergency_disable",
    "is_cognitive_enabled",
    "clear_disable_flag",
    # 토론
    "multi_round_debate",
    "AgentOpinion",
    "DebateState",
    # 오케스트레이터
    "consult_agents_for_round",
    # 카탈로그
    "AVAILABLE_ACTIONS",
    "REQUIRES_APPROVAL",
    "COGNITIVE_ENABLED",
    "MAX_ACTIONS_PER_DAY",
    # Phase 7 — Free Will
    "free_will_loop",
    "decide_next_interval",
    "trigger_immediate_cycle",
    "stop_free_will",
    "is_running",
    "current_interval",
    "free_will_goal_cycle",
    "MIN_INTERVAL_SEC",
    "MAX_INTERVAL_SEC",
    "DEFAULT_INTERVAL_SEC",
    "generate_creative_goals",
    "queue_goal_as_decision",
    "spontaneous_curiosity_cycle",
    "SEED_CURIOSITIES",
    "declare_weekly_intent",
    "get_current_intent",
    "FOCUS_AREAS",
]
