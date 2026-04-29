"""Hwarang 진짜 인과 추론 모듈.

기존 causal_extractor.py 가 텍스트→edge 추출 (상관성 가까움) 이라면,
이 패키지는 그 위에 진짜 인과 추론 레이어를 얹는다:

* causal_graph    — CausalEdge + 매개/혼란 변수 탐지
* do_calculus     — Pearl's do(X) 단순화 (backdoor adjustment 휴리스틱)
* counterfactual  — 반사실 추론 ("만약 X 가 다르게 일어났으면?")
* causal_chain    — 다단계 인과 (A→B→C→D) BFS + 누적 확률
"""

from .causal_chain import CausalChain, trace_chain
from .causal_graph import (
    CausalEdge,
    find_confounders,
    find_mediators,
    get_causal_edge,
)
from .counterfactual import (
    CounterfactualResult,
    explain_what_if,
    reason_counterfactual,
)
from .do_calculus import InterventionResult, estimate_intervention

__all__ = [
    "CausalEdge",
    "CausalChain",
    "CounterfactualResult",
    "InterventionResult",
    "estimate_intervention",
    "explain_what_if",
    "find_confounders",
    "find_mediators",
    "get_causal_edge",
    "reason_counterfactual",
    "trace_chain",
]
