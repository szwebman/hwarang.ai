"""코드/디자인 도메인 HFL 라운드 자동 오케스트레이션.

* :mod:`code_round_orchestrator` — 코드 LoRA 라운드 트리거 + 시작
* :mod:`design_round_orchestrator` — 디자인 LoRA 라운드 트리거 + 시작
* :mod:`code_round_quality` — 라운드 종료 후 품질 검증 + 자동 롤백

scheduler (``workers/hlkm_scheduler.py``) 가 매 6 시간 트리거 평가,
매 1 시간 미검증 라운드 검증을 수행한다.
"""

from .code_round_orchestrator import (
    CodeRoundDecision,
    evaluate_code_round_trigger,
    start_code_round,
)
from .code_round_quality import validate_completed_round
from .design_round_orchestrator import (
    DesignRoundDecision,
    evaluate_design_round_trigger,
    start_design_round,
)
from .eval_set_builder import build_or_load_eval_set, rebuild_eval_set
from .lora_evaluator import EvalResult, evaluate_lora

__all__ = [
    "CodeRoundDecision",
    "evaluate_code_round_trigger",
    "start_code_round",
    "DesignRoundDecision",
    "evaluate_design_round_trigger",
    "start_design_round",
    "validate_completed_round",
    "build_or_load_eval_set",
    "rebuild_eval_set",
    "evaluate_lora",
    "EvalResult",
]
