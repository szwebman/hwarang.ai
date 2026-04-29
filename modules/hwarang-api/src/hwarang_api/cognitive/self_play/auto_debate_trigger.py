"""자동 토론 트리거 — 언제 자기-토론을 실행할지 판단.

규칙 기반 (LLM 호출 없음 — 게이트로만 사용):
  - 신뢰도 < 0.7 → True
  - 한국어 위험 키워드 포함 → True
  - 절대주의 표현 포함 → True
  - 단순 인사/잡담 → False (위 트리거가 없으면)
"""

from __future__ import annotations

# ────────────────────────────────────────────────────────────
# 키워드 사전
# ────────────────────────────────────────────────────────────
RISK_KEYWORDS: tuple[str, ...] = (
    "투자",
    "의료",
    "법률",
    "약물",
    "자살",
    "폭력",
    "계약",
)

ABSOLUTE_CLAIMS: tuple[str, ...] = (
    "항상",
    "절대",
    "확실히",
    "100%",
)

GREETINGS: tuple[str, ...] = (
    "안녕",
    "하이",
    "헬로",
    "ㅎㅇ",
    "고마워",
    "감사",
    "ㅋㅋ",
    "ㅎㅎ",
    "잘자",
    "잘가",
    "반가워",
)


# ────────────────────────────────────────────────────────────
# 카테고리 → 추천 페르소나
# ────────────────────────────────────────────────────────────
MEDICAL_KEYWORDS: tuple[str, ...] = ("의료", "약물", "병원", "치료", "진단", "처방")
LEGAL_KEYWORDS: tuple[str, ...] = ("법률", "계약", "소송", "판결", "법령", "변호사")
ETHICS_KEYWORDS: tuple[str, ...] = ("윤리", "가치", "도덕", "공정", "차별", "인권")


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(k in text for k in keywords)


class AutoDebateTrigger:
    """토론 자동 실행 여부 판단기."""

    def __init__(self, confidence_threshold: float = 0.7) -> None:
        self.confidence_threshold = confidence_threshold

    def should_debate(
        self,
        question: str,
        draft_answer: str,
        confidence: float,
    ) -> bool:
        """토론 실행 여부.

        True:
          - confidence < threshold
          - question 에 위험 키워드
          - draft_answer 에 절대주의 표현
        False:
          - 위 트리거 없고, 단순 인사/잡담일 때
        """
        q = (question or "").strip()
        a = (draft_answer or "").strip()

        # 1) 낮은 신뢰도
        try:
            conf = float(confidence)
        except (TypeError, ValueError):
            conf = 0.0
        if conf < self.confidence_threshold:
            return True

        # 2) 위험 키워드
        if _contains_any(q, RISK_KEYWORDS) or _contains_any(a, RISK_KEYWORDS):
            return True

        # 3) 절대주의 표현
        if _contains_any(a, ABSOLUTE_CLAIMS):
            return True

        # 4) 단순 인사/잡담 → False
        # 짧고 인사 포함이면 토론 불필요
        if len(q) <= 20 and _contains_any(q, GREETINGS):
            return False

        return False

    def recommended_personas(self, question: str) -> list[str]:
        """질문 도메인에 따른 추천 페르소나 조합."""
        q = (question or "").strip()

        if _contains_any(q, MEDICAL_KEYWORDS):
            return ["비판자", "회의주의자", "법률가"]
        if _contains_any(q, LEGAL_KEYWORDS):
            return ["법률가", "비판자", "실용주의자"]
        if _contains_any(q, ETHICS_KEYWORDS):
            return ["윤리학자", "비판자", "옹호자"]
        return ["비판자", "옹호자", "실용주의자"]


__all__ = [
    "AutoDebateTrigger",
    "RISK_KEYWORDS",
    "ABSOLUTE_CLAIMS",
    "GREETINGS",
]
