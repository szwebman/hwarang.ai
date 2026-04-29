"""사용자 요청 → 2~4개 옵션 자동 생성.

각 옵션:
- 짧은 제목 (한국어, 5~15자)
- 1줄 설명
- 차별화 키워드 (스타일/기술/접근)
- 예상 결과 미리보기 (옵션)

LLM 으로 생성하되, 산출물 종류별 템플릿 활용.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


@dataclass
class ChatOption:
    id: str          # "option_a", "option_b" 등
    title: str       # "미니멀"
    description: str  # "검정 배경 + 큰 타이포 + 단일 CTA"
    keywords: list[str]
    preview_emoji: str  # 시각화


OPTION_GEN_PROMPT = """사용자가 다음 요청을 했다. 답변하기 전에 3가지 다른 접근법을 제시할 거다.

요청: {user_message}
산출물: {deliverable}
이미지 있음: {has_image}

각 접근법은 명확히 구분되어야 함. 예:
- 디자인이면: 스타일 (minimalism / brutalism / playful)
- 코딩이면: 기술 스택 (React vs Vue vs HTML), 또는 패턴 (functional vs class), 또는 복잡도 (단순 vs 풀스택)
- 글쓰기면: 톤 (전문적 vs 친근 vs 유머)

JSON 출력:
{{
  "options": [
    {{
      "title": "5~15자 한국어",
      "description": "30자 이내 한국어 설명",
      "keywords": ["스타일1", "스타일2"],
      "preview_emoji": "🎨"
    }},
    ...
  ]
}}

JSON 만 출력:"""


async def generate_options(
    user_message: str,
    deliverable: str,
    has_image: bool = False,
    image_description: str | None = None,
) -> list[ChatOption]:
    try:
        prompt = OPTION_GEN_PROMPT.format(
            user_message=user_message[:500],
            deliverable=deliverable,
            has_image=has_image,
        )
        if image_description:
            prompt += f"\n\n이미지 분석:\n{image_description[:500]}"

        raw = await llm_chat(prompt, max_tokens=512)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return _fallback_options(deliverable)

        data = json.loads(m.group())
        options = data.get("options", [])

        if not options:
            return _fallback_options(deliverable)

        return [
            ChatOption(
                id=f"option_{chr(97 + i)}",  # option_a, option_b, ...
                title=str(opt.get("title", ""))[:30],
                description=str(opt.get("description", ""))[:150],
                keywords=[str(k) for k in (opt.get("keywords") or [])][:5],
                preview_emoji=str(opt.get("preview_emoji", "✨"))[:8],
            )
            for i, opt in enumerate(options[:4])
        ]
    except Exception as e:
        logger.warning(f"옵션 생성 실패: {e}")
        return _fallback_options(deliverable)


def _fallback_options(deliverable: str) -> list[ChatOption]:
    """LLM 실패 시 산출물 종류별 정적 옵션."""
    if "랜딩" in deliverable or "사이트" in deliverable or "페이지" in deliverable:
        return [
            ChatOption("option_a", "미니멀", "흰 배경 + 큰 타이포 + 단순 CTA",
                       ["minimalism", "monochrome"], "⚪"),
            ChatOption("option_b", "그라데이션", "다채로운 색 + 모던 그라데이션",
                       ["gradient", "vibrant"], "🌈"),
            ChatOption("option_c", "다크 테마", "검정 배경 + 네온 액센트",
                       ["dark", "neon"], "🌙"),
        ]
    if "API" in deliverable or "백엔드" in deliverable:
        return [
            ChatOption("option_a", "FastAPI", "Python 비동기, 빠른 개발",
                       ["python", "fastapi"], "🐍"),
            ChatOption("option_b", "Express", "Node.js, JavaScript",
                       ["nodejs", "express"], "🟨"),
            ChatOption("option_c", "Go", "고성능, 단순 배포",
                       ["go", "fiber"], "🐹"),
        ]
    if "컴포넌트" in deliverable or "UI" in deliverable:
        return [
            ChatOption("option_a", "shadcn/ui", "Tailwind 기반, 접근성 ↑",
                       ["shadcn", "tailwind"], "🎨"),
            ChatOption("option_b", "Material UI", "Google Material Design",
                       ["material", "mui"], "🔷"),
            ChatOption("option_c", "Chakra UI", "쉬운 커스터마이징",
                       ["chakra", "react"], "⚡"),
        ]
    # 기본
    return [
        ChatOption("option_a", "단순 버전", "최소 코드로 빠르게",
                   ["simple", "minimal"], "🔵"),
        ChatOption("option_b", "표준 버전", "베스트 프랙티스 적용",
                   ["standard"], "🟢"),
        ChatOption("option_c", "고급 버전", "프로덕션 수준 + 테스트",
                   ["production", "tested"], "🔴"),
    ]


__all__ = ["ChatOption", "generate_options"]
