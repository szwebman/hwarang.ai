"""HSEE Phase 4 — Self-Evolving Engine.

자기 약점 인식 → 자동 데이터 생성 → 자율 진화 (단, RSI 의도적 차단).

루프 (orchestrator.run_evolution_round):
    1. WeaknessDetector — gap_detector + self_questioner + RLHF negative 통합
    2. SyntheticGenerator — 약점 패턴 → 학습 페어 자동 생성
    3. cross_verifier 검증 — Trusted Source 와 모순 시 폐기
    4. SafetyGate — Draft PR 만 생성 (자동 머지 X)
    5. queue_for_phase2_training — 주간 cron 픽업 대기 큐

원칙:
    * 명시 피드백 (👍/👎) 사용 X — 암묵 신호만 (rating, isSatisfied, followupMsg)
    * system prompt 우회 X — 모든 약점 데이터에 동일 system prompt 강제
    * RSI (Recursive Self-Improvement) 차단 — orchestrator 가 자기 자신 변경 X
    * Self-Modify Draft PR only — human approval 없이 머지 절대 금지
"""

from __future__ import annotations

__all__ = [
    "weakness_detector",
    "synthetic_generator",
    "orchestrator",
    "safety_gate",
]
