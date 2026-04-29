"""World Model — Phase 8 (시나리오 시뮬레이터).

한국 정책/경제/법률 시나리오를 LLM 으로 다단계 시뮬레이션.

모듈 구성
---------
* ``scenarios.py``  — 시나리오 라이브러리 (부동산/환율/실업/법안/IPO)
* ``simulator.py``  — LLM 기반 다단계 상태 진화 (WorldSimulator)
* ``comparator.py`` — 대안 액션 비교 + 최선안 추천
"""

from .scenarios import Scenario, get_scenario, list_scenarios
from .simulator import SimulationResult, WorldSimulator
from .comparator import compare_actions, recommend_best

__all__ = [
    "Scenario",
    "list_scenarios",
    "get_scenario",
    "WorldSimulator",
    "SimulationResult",
    "compare_actions",
    "recommend_best",
]
