"""암묵/명시 피드백 점수화.

명시 피드백(👍/👎/별점)이 없어도 다음 user 메시지의 톤·타이밍·편집 거리로 만족도 추정.
모든 점수는 ``-1.0 ~ +1.0`` 사이의 float.
"""

from __future__ import annotations

import re
from typing import Optional

POSITIVE_TOKENS = {
    "고마워", "감사", "맞아", "좋아", "좋다", "정확", "ㄱㅅ",
    "perfect", "thanks", "thank you", "great", "nice", "good",
    "👍", "✅", "❤", "최고",
}

NEGATIVE_TOKENS = {
    "아니", "틀렸", "다시", "잘못", "이상해", "이상하",
    "wrong", "incorrect", "no ", "nope", "bad",
    "👎", "❌", "별로",
}

# "다시", "재실행", "고쳐" 류 — 즉시 재요청
RETRY_TOKENS = {"다시", "재실행", "고쳐", "다른", "redo", "retry", "again"}

_NORM = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _NORM.sub(" ", text.strip().lower())


def score_explicit(rating: Optional[int]) -> float:
    """명시 평가 ``rating`` ∈ {-1, 0, +1} → float 점수."""
    if rating is None:
        return 0.0
    if rating > 0:
        return 1.0
    if rating < 0:
        return -1.0
    return 0.0


def score_implicit(
    followup_msg: Optional[str],
    time_to_followup_sec: Optional[float] = None,
    edit_distance: Optional[float] = None,
) -> float:
    """다음 user 메시지(있다면)와 후속 행동에서 만족도 추정.

    신호:
    - 긍정 토큰 → +0.7
    - 부정 토큰 → -0.7
    - 즉시 재요청(30 초 내) → -0.3
    - edit_distance 가 큼(0.5 이상) → -0.5 (사용자가 수정해서 다시 보냄)
    """
    score = 0.0

    if followup_msg:
        text = _norm(followup_msg)

        if any(tok in text for tok in POSITIVE_TOKENS):
            score = max(score, 0.7)
        if any(tok in text for tok in NEGATIVE_TOKENS):
            score = min(score, -0.7)
        elif any(tok in text for tok in RETRY_TOKENS):
            score = min(score, -0.4)

    # 즉시 재질문 = 만족 못 함
    if (
        time_to_followup_sec is not None
        and time_to_followup_sec >= 0
        and time_to_followup_sec < 30
        and score >= 0
    ):
        score = -0.3

    # 사용자가 응답을 손봐서 다시 보내면 부정 신호
    if edit_distance is not None and edit_distance >= 0.5 and score >= 0:
        score = -0.5

    return max(-1.0, min(1.0, score))


def combine_scores(
    explicit: Optional[int] = None,
    followup_msg: Optional[str] = None,
    time_to_followup_sec: Optional[float] = None,
    edit_distance: Optional[float] = None,
) -> float:
    """명시 + 암묵을 결합 (명시가 있으면 명시 우선, 암묵으로 보강)."""
    if explicit is not None:
        return score_explicit(explicit)
    return score_implicit(followup_msg, time_to_followup_sec, edit_distance)


def is_satisfied(score: float) -> Optional[bool]:
    """이진 만족도 판정.

    0.2 이상 → True, -0.2 이하 → False, 그 사이는 None (모름).
    """
    if score >= 0.2:
        return True
    if score <= -0.2:
        return False
    return None


__all__ = [
    "score_explicit",
    "score_implicit",
    "combine_scores",
    "is_satisfied",
    "POSITIVE_TOKENS",
    "NEGATIVE_TOKENS",
]
