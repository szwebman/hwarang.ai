"""화랑 에이전트 인지(Cognitive) 모듈.

LLM/규칙 기반 자율 결정:
- state_collector: 자기 상태 수집 (GPU/시스템/시간/이력/전문성)
- decision_engine: 라운드 제안에 대한 accept/decline/negotiate 판정
- self_assessor: 학습 라운드 종료 후 자기 평가 + lesson 누적

기존 round_subscription 의 단순 규칙(VRAM/티어/마감) 위에
"사용자 활동 / 배터리 / 야간 / 도메인 적성 / 최근 품질" 같은
컨텍스트 신호를 더해 더 사람-친화적인 참여 결정을 내린다.

LLM 미설치 환경에서는 자동으로 rule_based_decide 폴백.
"""

from .state_collector import AgentState, collect_state
from .decision_engine import (
    Decision,
    RoundOffer,
    decide_about_round,
    llm_decide,
    rule_based_decide,
)
from .self_assessor import SelfAssessment, assess_round_outcome

# OS별 사용자 활동 감지 (macOS/Linux/Windows)
try:
    from .user_activity import (
        get_idle_seconds,
        get_idle_state,
        is_user_active,
    )
except Exception:  # pragma: no cover
    get_idle_seconds = None  # type: ignore
    get_idle_state = None  # type: ignore
    is_user_active = None  # type: ignore

__all__ = [
    "AgentState",
    "collect_state",
    "Decision",
    "RoundOffer",
    "decide_about_round",
    "llm_decide",
    "rule_based_decide",
    "SelfAssessment",
    "assess_round_outcome",
    "get_idle_seconds",
    "get_idle_state",
    "is_user_active",
]
