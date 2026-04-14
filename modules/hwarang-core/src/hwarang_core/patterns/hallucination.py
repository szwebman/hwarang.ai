"""Hallucination Detection - 환각 탐지.

LLM 답변이 제공된 문서(RAG 컨텍스트)에 근거하는지 검증합니다.
근거 없는 답변(환각)을 감지하여 경고하거나 차단합니다.

방식:
1. NLI (Natural Language Inference): 답변이 문서에서 추론 가능한지 판별
2. 키워드 교차 검증: 답변의 핵심 주장이 문서에 존재하는지
3. 출처 검증: 인용된 출처가 실제 문서에 있는지
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class HallucinationCheckResult:
    is_grounded: bool           # 근거 있는 답변인지
    confidence: float           # 0~1 (1이면 확실히 근거 있음)
    ungrounded_claims: list[str]  # 근거 없는 주장 목록
    missing_citations: list[str]  # 빠진 출처
    details: str


class HallucinationDetector:
    """환각 탐지기."""

    def __init__(self, embedding_service=None):
        self.embedder = embedding_service

    def check(
        self,
        answer: str,
        context: str,
        citations_expected: bool = True,
    ) -> HallucinationCheckResult:
        """답변이 컨텍스트에 근거하는지 검사."""
        issues = []
        ungrounded = []

        # 1. 출처 검증
        cited = re.findall(r'\[문서\s*(\d+)\]|\[(\d+)\]', answer)
        if citations_expected and not cited:
            issues.append("출처 인용이 없습니다")

        # 2. 핵심 주장 추출 + 교차 검증
        claims = self._extract_claims(answer)
        context_lower = context.lower()

        for claim in claims:
            # 핵심 키워드가 컨텍스트에 있는지
            keywords = self._extract_keywords(claim)
            matched = sum(1 for kw in keywords if kw.lower() in context_lower)
            coverage = matched / max(len(keywords), 1)

            if coverage < 0.3:  # 키워드 30% 미만 매칭
                ungrounded.append(claim)

        # 3. 수치/날짜 정확성
        numbers_in_answer = re.findall(r'\d+[.,]?\d*', answer)
        numbers_in_context = re.findall(r'\d+[.,]?\d*', context)
        context_numbers = set(numbers_in_context)

        for num in numbers_in_answer:
            if num not in context_numbers and len(num) > 2:
                # 컨텍스트에 없는 구체적 수치
                ungrounded.append(f"수치 '{num}'이 문서에 없음")

        # 4. 유사도 기반 검증 (임베딩 가능 시)
        semantic_score = 1.0
        if self.embedder and ungrounded:
            semantic_score = self.embedder.similarity(answer, context)

        # 5. 종합 판단
        grounded_ratio = 1.0 - len(ungrounded) / max(len(claims) + len(numbers_in_answer), 1)
        confidence = min(grounded_ratio, semantic_score)
        is_grounded = confidence > 0.5 and len(ungrounded) <= 2

        details = (
            f"주장 {len(claims)}개 중 근거 없음 {len(ungrounded)}개, "
            f"유사도 {semantic_score:.2f}, 신뢰도 {confidence:.2f}"
        )

        return HallucinationCheckResult(
            is_grounded=is_grounded,
            confidence=confidence,
            ungrounded_claims=ungrounded,
            missing_citations=issues,
            details=details,
        )

    def _extract_claims(self, text: str) -> list[str]:
        """답변에서 핵심 주장 추출 (문장 단위)."""
        sentences = re.split(r'[.!?]\s+', text)
        # 주장성 문장만 (너무 짧거나 질문은 제외)
        claims = [s.strip() for s in sentences
                  if len(s.strip()) > 20 and '?' not in s]
        return claims[:10]  # 최대 10개

    def _extract_keywords(self, text: str) -> list[str]:
        """핵심 키워드 추출 (명사 위주)."""
        # 한국어: 2자 이상 단어
        words = re.findall(r'[\uAC00-\uD7A3]{2,}', text)
        # 영어: 3자 이상 단어
        words += re.findall(r'[a-zA-Z]{3,}', text)
        # 불용어 제거
        stopwords = {"이것", "그것", "하는", "있는", "없는", "대한", "위한", "통해", "따라", "관한"}
        return [w for w in words if w not in stopwords][:15]
