"""Online RLHF — 매 피드백마다 즉시 1 step gradient + LoRA hot-swap.

Phase 2 의 batch 학습 (1000건 모이면 라운드) 과 달리, 여기는:
- 피드백 1건 → 즉시 큐 → 백그라운드 워커 1 step
- 누적 N step → vLLM hot-reload (다음 응답에 즉시 반영)
- 평가 셋 baseline 대비 떨어지면 자동 롤백

모듈:
- continuous_lora     : 큐 + 워커 + 체크포인트
- forgetting_prevention: EWC 정책 + GradientClipper + 도메인별 LoRA 분리
- actual_trainer      : 실제 GPU 학습 (별도 프로세스)
"""

from hwarang_api.learning.online.continuous_lora import (
    init_worker,
    submit_feedback,
    queue_status,
)

__all__ = [
    "init_worker",
    "submit_feedback",
    "queue_status",
]
