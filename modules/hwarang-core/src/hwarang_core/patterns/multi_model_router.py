"""Multi-Model Router - 질문 난이도에 따라 모델 자동 선택.

간단한 질문 → 7B (빠르고 저렴)
복잡한 질문 → 30B (정확하고 느림)

토큰 비용 절약 + 응답 속도 최적화.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RoutingResult:
    model: str                # "7b" or "30b"
    reason: str               # 라우팅 이유
    confidence: float         # 0~1
    estimated_tokens: int     # 예상 토큰 수


class MultiModelRouter:
    """질문 복잡도 기반 모델 라우터."""

    def __init__(
        self,
        fast_model: str = "hwarang-code-7b",
        quality_model: str = "hwarang-code-30b",
        complexity_threshold: float = 0.5,
    ):
        self.fast = fast_model
        self.quality = quality_model
        self.threshold = complexity_threshold

    def route(self, messages: list[dict], user_plan: str = "pro") -> RoutingResult:
        """메시지 분석 → 적절한 모델 선택."""
        last_msg = messages[-1]["content"] if messages else ""
        conversation_length = len(messages)

        complexity = self._estimate_complexity(last_msg, conversation_length)

        # Free 플랜은 항상 7B
        if user_plan == "free":
            return RoutingResult(
                model=self.fast, reason="Free 플랜 (7B만)", confidence=1.0,
                estimated_tokens=self._estimate_tokens(last_msg),
            )

        # Starter도 7B만
        if user_plan == "starter":
            return RoutingResult(
                model=self.fast, reason="Starter 플랜 (7B만)", confidence=1.0,
                estimated_tokens=self._estimate_tokens(last_msg),
            )

        # Pro/Business는 복잡도 기반 라우팅
        if complexity > self.threshold:
            return RoutingResult(
                model=self.quality,
                reason=f"복잡한 질문 (복잡도: {complexity:.2f})",
                confidence=complexity,
                estimated_tokens=self._estimate_tokens(last_msg),
            )

        return RoutingResult(
            model=self.fast,
            reason=f"간단한 질문 (복잡도: {complexity:.2f})",
            confidence=1.0 - complexity,
            estimated_tokens=self._estimate_tokens(last_msg),
        )

    def _estimate_complexity(self, text: str, conv_length: int) -> float:
        """질문 복잡도 추정 (0~1)."""
        score = 0.0

        # 1. 길이 (긴 질문 = 복잡)
        if len(text) > 500:
            score += 0.2
        elif len(text) > 200:
            score += 0.1

        # 2. 코드 포함 (코드 분석 = 복잡)
        if "```" in text or re.search(r'(def |class |function |import )', text):
            score += 0.2

        # 3. 전문 도메인 키워드
        legal_kw = ["법률", "판례", "법원", "소송", "계약", "민법", "형법", "헌법"]
        tax_kw = ["세금", "세무", "양도세", "소득세", "부가세", "법인세", "공제", "신고"]
        complex_kw = ["분석", "비교", "설계", "최적화", "아키텍처", "리팩토링", "디버깅"]

        text_lower = text.lower()
        if any(kw in text_lower for kw in legal_kw):
            score += 0.3
        if any(kw in text_lower for kw in tax_kw):
            score += 0.3
        if any(kw in text_lower for kw in complex_kw):
            score += 0.15

        # 4. 다중 질문 ("그리고", "또한", "추가로")
        multi_q = ["그리고", "또한", "추가로", "더불어", "아울러"]
        if any(kw in text for kw in multi_q):
            score += 0.1

        # 5. 대화가 길면 (맥락이 복잡)
        if conv_length > 10:
            score += 0.1

        return min(1.0, score)

    def _estimate_tokens(self, text: str) -> int:
        from hwarang_core.patterns.token_counter import TokenCounter
        return TokenCounter.estimate(text) + 300  # 응답 예상
