"""Conversation Summarizer - 긴 대화 자동 요약.

컨텍스트 윈도우가 부족할 때, 오래된 대화를 요약해서 토큰을 절약합니다.

전략:
1. Rolling Summary: 일정 턴마다 이전 대화를 요약
2. Hierarchical: 요약의 요약 (다단계)
3. Key Points: 핵심 포인트만 추출
"""

from __future__ import annotations

import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


class ConversationSummarizer:
    """대화 요약기."""

    def __init__(self, llm_fn: Callable[[list[dict]], Awaitable[str]] = None):
        self.llm_fn = llm_fn  # LLM 호출 함수

    async def summarize(self, messages: list[dict], max_summary_tokens: int = 300) -> str:
        """메시지 리스트를 요약."""
        if self.llm_fn:
            return await self._llm_summarize(messages, max_summary_tokens)
        return self._simple_summarize(messages)

    async def compress_conversation(
        self,
        messages: list[dict],
        max_tokens: int = 4000,
        keep_recent: int = 4,
    ) -> list[dict]:
        """긴 대화를 압축. 최근 N턴은 유지, 나머지 요약."""
        from hwarang_core.patterns.token_counter import TokenCounter
        counter = TokenCounter()

        total = counter.count_messages(messages)
        if total <= max_tokens:
            return messages

        system = [m for m in messages if m["role"] == "system"]
        others = [m for m in messages if m["role"] != "system"]

        if len(others) <= keep_recent:
            return messages

        recent = others[-keep_recent:]
        old = others[:-keep_recent]

        summary = await self.summarize(old)

        return system + [
            {"role": "system", "content": f"[이전 대화 요약]\n{summary}"},
        ] + recent

    async def _llm_summarize(self, messages: list[dict], max_tokens: int) -> str:
        """LLM으로 요약."""
        conversation = "\n".join(
            f"{m['role']}: {m['content'][:200]}" for m in messages
        )
        prompt = [
            {"role": "system", "content": "대화를 핵심만 간결하게 요약하세요."},
            {"role": "user", "content": f"다음 대화를 {max_tokens}토큰 이내로 요약:\n\n{conversation}"},
        ]
        return await self.llm_fn(prompt)

    @staticmethod
    def _simple_summarize(messages: list[dict]) -> str:
        """LLM 없이 간단한 요약 (키 포인트 추출)."""
        points = []
        for m in messages:
            content = m["content"]
            # 첫 문장만 추출
            first = content.split("\n")[0][:100]
            if len(first) > 20:
                points.append(f"- {m['role']}: {first}")
        return "\n".join(points[-10:])  # 최근 10개
