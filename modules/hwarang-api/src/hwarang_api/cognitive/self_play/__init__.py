"""화랑 Adversarial Self-Play (Group θ).

Phase 9.θ — Hwarang vs Hwarang 내부 토론.

여러 한국어 특화 페르소나가 같은 답변을 두고
비판/옹호/회의/실용/법률/윤리 관점에서 토론하여
오류 발견 + 견고성 향상.

서브모듈
--------
- adversarial_personas: 6 페르소나 정의 + LLM 호출
- debate_orchestrator: 다회차 토론 실행
- consensus_finder: 합의/이견 추출
- error_discovery: 자기모순/근거없음 탐지
- auto_debate_trigger: 자동 토론 트리거 판단
"""

from .adversarial_personas import PERSONAS, Persona, respond_as
from .auto_debate_trigger import AutoDebateTrigger
from .consensus_finder import ConsensusAnalysis, ConsensusFinder
from .debate_orchestrator import DebateOrchestrator, DebateResult, Turn
from .error_discovery import Contradiction, ErrorDiscoverer

__all__ = [
    "PERSONAS",
    "Persona",
    "respond_as",
    "DebateOrchestrator",
    "DebateResult",
    "Turn",
    "ConsensusFinder",
    "ConsensusAnalysis",
    "ErrorDiscoverer",
    "Contradiction",
    "AutoDebateTrigger",
]
