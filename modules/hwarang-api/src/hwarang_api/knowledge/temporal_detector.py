"""사용자 질문이 실시간 검색 필요한지 감지.

신호:
1. 시간 키워드: "현재", "지금", "오늘", "최신", "이번", "올해", "이달"
2. 의문 + 변동 가능 주제: "대통령", "환율", "주가", "날씨", "뉴스"
3. 명시적 연도: "2024", "2025"
4. 동사 시제: "이다" (현재), "였다" (과거 - 검색 안 함)

점수 공식 (대략):
    base = 0.0
    + 시간키워드 매칭   : +0.5
    + 변동주제 매칭     : +0.4 (시간 동반) | +0.6 (단독)
    + 명시연도 매칭     : +0.3
    + 의문문            : +0.1
    × 과거표현 감점     : ×0.3

threshold = 0.5  →  needs_realtime
"""

from __future__ import annotations

import re
from dataclasses import dataclass


REALTIME_KEYWORDS = {
    "현재", "지금", "오늘", "최신", "최근", "이번", "이달", "올해",
    "현행", "최근에", "요즘", "이제",
    "current", "now", "today", "latest", "recent",
}

VOLATILE_TOPICS = {
    "대통령", "수상", "총리", "장관",
    "환율", "주가", "주식", "코스피", "코스닥", "비트코인", "이더리움",
    "날씨", "기온", "비", "눈", "태풍",
    "뉴스", "사건", "사고",
    "최저시급", "금리", "인구",
    "올림픽", "월드컵", "선거", "투표",
}

EXPLICIT_YEAR_PATTERN = re.compile(r"\b(202[3-9]|203\d)\b")  # 2023~2039

PAST_MARKERS = ("였다", "였던", "옛날", "예전", "과거")
QUESTION_MARKERS = ("뭐", "누구", "언제", "어디", "얼마", "몇")


@dataclass
class TemporalSignal:
    needs_realtime: bool
    confidence: float          # 0~1
    signals: list[str]
    suggested_queries: list[str]


def detect_temporal(user_message: str) -> TemporalSignal:
    text = (user_message or "").strip()
    text_lower = text.lower()
    signals: list[str] = []
    score = 0.0

    # 1. 시간 키워드
    matched_time = [k for k in REALTIME_KEYWORDS if k in text_lower]
    if matched_time:
        signals.extend([f"time:{k}" for k in matched_time])
        score += 0.5

    # 2. 변동 주제
    matched_topic = [t for t in VOLATILE_TOPICS if t in text]
    if matched_topic:
        signals.extend([f"topic:{t}" for t in matched_topic])
        # 시간 키워드 동반 시 0.4, 단독이면 0.6 (단독으로도 강한 신호)
        score += 0.4 if matched_time else 0.6

    # 3. 명시 연도
    year_matches = EXPLICIT_YEAR_PATTERN.findall(text)
    if year_matches:
        signals.extend([f"year:{y}" for y in year_matches])
        score += 0.3

    # 4. 의문문 (질문) 약한 가산점
    is_question = "?" in text or any(q in text for q in QUESTION_MARKERS)
    if is_question:
        signals.append("question")
        score += 0.1

    # 5. 명시 과거 표현 → 감점 (실시간 불필요)
    if any(p in text for p in PAST_MARKERS):
        signals.append("past_marker")
        score *= 0.3

    # 검색 쿼리 생성 (단순화)
    suggested: list[str] = []
    if matched_topic and matched_time:
        for topic in matched_topic[:2]:
            for time in matched_time[:1]:
                suggested.append(f"{time} {topic}")
    elif matched_topic:
        suggested = matched_topic[:3]

    if not suggested:
        suggested = [text[:100]]

    return TemporalSignal(
        needs_realtime=score >= 0.5,
        confidence=min(score, 1.0),
        signals=signals,
        suggested_queries=suggested,
    )
