"""HLKM Context Injection — Layer 5.

질문 → HLKM 의미 검색 → top-K 관련 사실 추출.
KV cache 의 system prompt 영역에 selective 주입.
TrustedSource 의 신뢰도 가중치 (cross_verifier.py 결과) 반영.
시간 인식: 사실의 valid_from/valid_to 자동 필터.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol


@dataclass
class FactSnippet:
    fact_id: str
    text: str
    confidence: float  # 0..1, TrustedSource cross_verifier 결과
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    source_url: Optional[str] = None


class HLKMSearchBackend(Protocol):
    """HLKM 모듈에 위치한 의미 검색 인터페이스."""

    def search(self, query: str, top_k: int) -> list[FactSnippet]: ...


class HLKMContextInjector:
    """HLKM 사실을 system prompt 영역에 주입."""

    def __init__(
        self,
        backend: Optional[HLKMSearchBackend] = None,
        top_k: int = 5,
        min_confidence: float = 0.5,
    ):
        self.backend = backend
        self.top_k = top_k
        self.min_confidence = min_confidence

    def fetch_facts(self, query: str, now: Optional[datetime] = None) -> list[FactSnippet]:
        if self.backend is None:
            return []
        now = now or datetime.utcnow()
        snippets = self.backend.search(query, self.top_k)
        return [
            s
            for s in snippets
            if s.confidence >= self.min_confidence
            and (s.valid_from is None or s.valid_from <= now)
            and (s.valid_to is None or s.valid_to >= now)
        ]

    def format_system_prompt(self, facts: list[FactSnippet]) -> str:
        if not facts:
            return ""
        lines = ["[HLKM 검증된 사실]"]
        for f in facts:
            tag = f"신뢰도={f.confidence:.2f}"
            lines.append(f"- ({tag}) {f.text}")
        return "\n".join(lines)

    def inject(self, user_query: str, base_system_prompt: str = "") -> str:
        """system prompt 에 HLKM 사실 prepend. 실 KV-cache 주입은 Phase 4.2."""
        facts = self.fetch_facts(user_query)
        ctx = self.format_system_prompt(facts)
        if not ctx:
            return base_system_prompt
        return f"{ctx}\n\n{base_system_prompt}".strip()
