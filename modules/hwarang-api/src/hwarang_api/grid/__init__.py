"""Hwarang Grid — 분산 학습 라운드 분배 알고리즘.

서브모듈:

* :mod:`.matcher` — :class:`AgentMatcher`: 라운드 후보 점수화/선정
* :mod:`.sharder` — :class:`DataShardingService`: 데이터 샤딩 + validation 분리
* :mod:`.straggler` — :class:`StragglerHandler`: 느린 에이전트 탐지/재할당
* :mod:`.round_orchestrator` — :class:`RoundOrchestrator`: 라이프사이클 통합

``hwarang_api.routers.grid`` 가 이 패키지를 lazy import 한다.
순환 참조 방지를 위해 :class:`RoundOrchestrator` 는 ``broadcast_round_event``
를 callback 으로 주입받는다 (직접 import 금지).
"""

from __future__ import annotations

from .matcher import AgentMatcher
from .sharder import DataShardingService
from .straggler import StragglerHandler
from .round_orchestrator import RoundOrchestrator

__all__ = [
    "AgentMatcher",
    "DataShardingService",
    "StragglerHandler",
    "RoundOrchestrator",
]
