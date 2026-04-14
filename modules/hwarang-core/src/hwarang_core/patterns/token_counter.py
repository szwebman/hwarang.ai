"""Token Counter - 정확한 토큰 수 계산.

과금 정확성을 위해 요청/응답의 토큰 수를 정확히 계산합니다.
토크나이저 없이도 대략적 추정 가능.
"""

from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)


class TokenCounter:
    """토큰 수 계산."""

    def __init__(self, tokenizer=None):
        self._tokenizer = tokenizer

    def count(self, text: str) -> int:
        """정확한 토큰 수 (토크나이저 있을 때)."""
        if self._tokenizer:
            return len(self._tokenizer.encode(text, add_special_tokens=False))
        return self.estimate(text)

    @staticmethod
    def estimate(text: str) -> int:
        """대략적 토큰 수 추정 (토크나이저 없이).

        규칙:
        - 한국어: 1글자 ≈ 0.7 토큰
        - 영어: 1단어 ≈ 1.3 토큰
        - 코드: 1문자 ≈ 0.25 토큰
        """
        korean = len(re.findall(r'[\uAC00-\uD7A3]', text))
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        numbers = len(re.findall(r'\d+', text))
        symbols = len(re.findall(r'[^\w\s\uAC00-\uD7A3]', text))
        spaces = text.count(' ') + text.count('\n')

        tokens = (
            korean * 0.7 +
            english_words * 1.3 +
            numbers * 0.5 +
            symbols * 0.3 +
            spaces * 0.1
        )
        return max(1, int(tokens))

    def count_messages(self, messages: list[dict]) -> int:
        """메시지 리스트의 총 토큰 수."""
        total = 0
        for msg in messages:
            total += 4  # role 오버헤드
            total += self.count(msg.get("content", ""))
        total += 2  # start/end 토큰
        return total

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int,
                      model: str = "7b") -> dict:
        """토큰 사용량 → 비용 추정."""
        rates = {"7b": 10, "13b": 15, "30b": 30}  # 원/1K토큰
        rate = rates.get(model, 10)
        total_tokens = prompt_tokens + completion_tokens
        cost_krw = (total_tokens / 1000) * rate
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_krw": round(cost_krw, 1),
            "model": model,
        }
