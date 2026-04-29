"""Hwarang Cognitive Layer — Phase 9.ζ (Group ζ).

Meta-cognition + Theory of Mind.

서브모듈
--------
* ``self_reflection``        — 자기 답변 비판 분석 (논리 공백/가정 검증/출처/반례)
* ``confidence_calibration`` — 답변 사실가능성 + 도메인 과거 정확도로 재보정
* ``theory_of_mind``         — 사용자 멘탈 모델 (전문성/관심/스타일/오개념) 추적/예측
* ``knowledge_gap_detector`` — 자기지식 공백 식별 + 외부탐색 힌트

모든 LLM 호출은 ``hwarang_api.knowledge.llm._chat`` 사용.
DB / JSON 파싱 실패는 절대 raise 하지 않고 안전 기본값으로 폴백한다.
"""

from __future__ import annotations

from .confidence_calibration import ConfidenceCalibrator
from .knowledge_gap_detector import Gap, KnowledgeGapDetector
from .self_reflection import ReflectionResult, SelfReflection
from .theory_of_mind import TheoryOfMind

__all__ = [
    "SelfReflection",
    "ReflectionResult",
    "ConfidenceCalibrator",
    "TheoryOfMind",
    "KnowledgeGapDetector",
    "Gap",
]
