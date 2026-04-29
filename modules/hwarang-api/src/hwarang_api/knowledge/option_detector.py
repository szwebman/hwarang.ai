"""사용자 메시지가 선택지 제시 모드에 적합한지 감지.

신호:
- 만들기/생성 의도: "만들어줘", "짜줘", "디자인해줘", "구현해줘"
- 다중 결과 가능: "랜딩페이지", "API", "UI", "함수", "컴포넌트"
- 모호함: 구체 스타일/접근법 미명시

반대 (선택지 불필요):
- 매우 구체적: "useState 훅 사용해서 React 카운터 짜줘" (이미 명확)
- 사실 질문: "Python 이 뭐야?"
- 짧은 후속: "왜?", "더 자세히"
"""

from __future__ import annotations

from dataclasses import dataclass


CREATION_VERBS = [
    "만들", "만들어", "짜줘", "구현해", "디자인해", "디자인 해",
    "작성해", "build", "create", "make", "design", "implement",
]

DELIVERABLE_NOUNS = [
    "랜딩", "랜딩페이지", "사이트", "웹사이트", "페이지",
    "API", "백엔드", "서버", "엔드포인트", "라우터",
    "UI", "컴포넌트", "버튼", "폼", "메뉴",
    "앱", "어플", "프로그램", "스크립트", "함수", "클래스",
    "대시보드", "관리자", "차트", "테이블",
    "로고", "아이콘", "배너", "이미지",
]


@dataclass
class OptionIntent:
    needs_options: bool
    confidence: float
    deliverable: str  # 식별된 산출물 ("랜딩페이지" 등)
    reason: str


def detect_option_intent(user_message: str, has_image: bool = False) -> OptionIntent:
    text = user_message.strip()

    if len(text) < 10:
        return OptionIntent(False, 0.0, "", "too_short")

    # 매우 구체적이면 선택지 불필요
    if _is_too_specific(text):
        return OptionIntent(False, 0.0, "", "already_specific")

    # 만들기 의도 + 산출물 명사 매칭
    has_verb = any(v in text for v in CREATION_VERBS)
    matched_nouns = [n for n in DELIVERABLE_NOUNS if n in text]

    if not (has_verb or has_image) or not matched_nouns:
        return OptionIntent(False, 0.0, "", "no_intent")

    # 이미지 있으면 v0.dev 모드 — 옵션 제시 가치 ↑ (스타일 변형)
    if has_image and has_verb:
        return OptionIntent(True, 0.9, matched_nouns[0], "image_with_creation")

    # 텍스트만 — 산출물 종류에 따라
    return OptionIntent(
        needs_options=True,
        confidence=0.7,
        deliverable=matched_nouns[0],
        reason="creation_intent",
    )


def _is_too_specific(text: str) -> bool:
    """이미 구체적 스펙 있으면 옵션 안 제시.

    예:
    - "React 18 + TypeScript + Tailwind 로 useState 카운터" → too specific
    - "minimalism 스타일 hero section" → moderate (옵션 제시 가능)
    """
    # 기술 스택 명시 + 라이브러리 명시 + 구체 기능
    tech_count = sum(1 for kw in [
        "react", "vue", "svelte", "next", "nuxt",
        "typescript", "javascript", "python", "rust",
        "tailwind", "shadcn", "mui", "chakra",
        "fastapi", "django", "express",
    ] if kw in text.lower())

    return tech_count >= 3  # 3개 이상 명시 = 이미 충분히 구체적


__all__ = ["OptionIntent", "detect_option_intent"]
