"""Multi-turn Memory - 대화 장기 기억.

컨텍스트 윈도우를 넘어서는 이전 대화를 기억합니다.

방식:
1. 매 대화를 Vector DB에 저장
2. 새 질문이 들어오면 관련 이전 대화 검색
3. 검색된 기억을 컨텍스트에 삽입
4. "지난번에 말했던 그거" 같은 참조 가능
"""

from __future__ import annotations

import json
import time
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """기억 항목."""
    user_id: str
    conversation_id: str
    role: str           # "user" or "assistant"
    content: str
    timestamp: float
    metadata: dict = None


class ConversationMemory:
    """대화 장기 기억 시스템."""

    def __init__(self, retriever=None, max_memories: int = 5):
        self.retriever = retriever  # HwarangRetriever 인스턴스
        self.max_memories = max_memories
        self._short_term: list[dict] = []  # 현재 세션
        self._max_short_term = 20  # 최근 20턴 유지

    async def save(self, user_id: str, conv_id: str, role: str, content: str):
        """대화를 기억에 저장."""
        self._short_term.append({
            "role": role, "content": content, "timestamp": time.time()
        })
        if len(self._short_term) > self._max_short_term:
            self._short_term.pop(0)

        # Vector DB에도 저장 (장기 기억)
        if self.retriever:
            from hwarang_core.rag.retriever import Document
            doc = Document(
                id=f"{conv_id}-{int(time.time()*1000)}",
                content=f"[{role}] {content}",
                metadata={"user_id": user_id, "conv_id": conv_id,
                          "role": role, "timestamp": time.time()},
            )
            await self.retriever.add_documents([doc])

    async def recall(self, user_id: str, query: str) -> list[dict]:
        """관련 이전 대화 검색."""
        if not self.retriever:
            return []

        results = await self.retriever.search(
            query, top_k=self.max_memories,
            filter_metadata={"user_id": user_id},
        )

        return [
            {"content": r.document.content, "timestamp": r.document.metadata.get("timestamp", 0)}
            for r in results
        ]

    def build_memory_context(self, memories: list[dict]) -> str:
        """기억을 컨텍스트 문자열로."""
        if not memories:
            return ""
        lines = ["[이전 대화 기억]"]
        for m in memories:
            lines.append(f"  {m['content']}")
        return "\n".join(lines)

    def get_short_term(self) -> list[dict]:
        """현재 세션 대화 기록."""
        return list(self._short_term)

    def clear_short_term(self):
        self._short_term.clear()
