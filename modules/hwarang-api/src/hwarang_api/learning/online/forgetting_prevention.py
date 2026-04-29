"""Online learning 의 catastrophic forgetting 방지.

기존 EWC (Phase 2 ``learning/ewc.py``) 활용 + 다음 추가:
1. Replay Buffer 우선순위 — 중요 sample 재사용
2. 도메인별 격리 학습 — 코드 학습 시 법률 LoRA 안 건드림
3. Gradient norm clipping — 큰 변화 차단
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# 도메인별 LoRA 분리 정책
# - 학습 시 어느 LoRA adapter 를 trainable target 으로 잡을지 결정
# - 미학습 도메인은 None → general 로 폴백
DOMAIN_LORA_MAP: dict[str, Optional[str]] = {
    "code": "hwarang-code-32b-v1",
    "design": "hwarang-design-v1",
    "legal": None,           # 미학습 — general 사용
    "medical": None,
    "tax": None,
    "general": "hwarang-general-v1",
}


def select_lora_for_step(domain: str) -> Optional[str]:
    """이 도메인 학습 시 어느 LoRA 사용?"""
    return DOMAIN_LORA_MAP.get(domain) or DOMAIN_LORA_MAP["general"]


def should_use_ewc(domain: str, recent_step_count: int) -> bool:
    """언제 EWC penalty 적용?

    너무 자주 적용하면 학습 못 함, 너무 안 하면 잊음.
    매 100 step 마다 한 번 EWC 강하게.
    """
    if recent_step_count <= 0:
        return False
    return recent_step_count % 100 == 0


class GradientClipper:
    """Gradient norm 폭주 방지.

    한 step 의 변화량이 평소보다 5배 크면 차단.
    """

    def __init__(self, max_history: int = 100, multiplier: float = 5.0) -> None:
        self._recent_norms: list[float] = []
        self._max_history = max_history
        self._multiplier = multiplier

    def should_apply(self, current_norm: float) -> bool:
        if len(self._recent_norms) < 10:
            self._recent_norms.append(current_norm)
            return True  # 초기엔 무조건 적용

        avg = sum(self._recent_norms) / len(self._recent_norms)
        if current_norm > avg * self._multiplier:
            logger.warning(
                f"Gradient 폭주 차단 — {current_norm:.4f} > {avg:.4f} × {self._multiplier}"
            )
            return False

        self._recent_norms.append(current_norm)
        if len(self._recent_norms) > self._max_history:
            self._recent_norms.pop(0)
        return True

    def stats(self) -> dict:
        if not self._recent_norms:
            return {"count": 0}
        return {
            "count": len(self._recent_norms),
            "mean": sum(self._recent_norms) / len(self._recent_norms),
            "max": max(self._recent_norms),
            "min": min(self._recent_norms),
        }


__all__ = [
    "DOMAIN_LORA_MAP",
    "select_lora_for_step",
    "should_use_ewc",
    "GradientClipper",
]
