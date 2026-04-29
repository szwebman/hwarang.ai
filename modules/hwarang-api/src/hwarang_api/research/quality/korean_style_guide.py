"""한국어 코딩 스타일 자동 적용 — LoRA 학습 데이터 정규화.

규칙:
  - 변수명/함수명/import: 영어 (camelCase / snake_case 일관) 유지
  - 주석: 한국어 우선
  - 함수 docstring: 한국어
  - 에러 메시지(throw/raise 문자열 리터럴): 한국어

CodePair 의 ``response`` 를 후처리해 학습 데이터의 한국어 일관성을 확보.
영어 주석이 임계치 미만이면 LLM 호출을 생략하고 원본을 반환한다.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


KOREANIZE_PROMPT = """다음 코드의 주석/docstring/에러 메시지만 한국어로 번역해라.
변수명/함수명/import 경로/문자열 식별자는 그대로 유지.

코드:
{code}

번역된 코드만 ```언어\\n...``` fence 로 감싸서 출력:"""


# 영어 주석 임계치 — 이 미만이면 LLM 호출 생략
MIN_ENGLISH_COMMENTS = 3
MAX_INPUT_LEN = 3000


def _count_english_comments(code: str) -> int:
    """영어가 포함된 주석/문서 라인 개수 추정."""
    candidates = re.findall(
        r"#[^\n]*[a-zA-Z]+|//[^\n]*[a-zA-Z]+|/\*.*?\*/",
        code,
        re.DOTALL,
    )
    # 한글이 충분히 섞인 라인은 영어 주석으로 안 봄
    english_only = []
    for c in candidates:
        if not re.search(r"[가-힣]", c):
            english_only.append(c)
    return len(english_only)


async def koreanize_response(code: str) -> str:
    """주석/docstring/에러 메시지 한국어화.

    영어 주석이 ``MIN_ENGLISH_COMMENTS`` 미만이면 원본 그대로 반환.
    LLM 호출 실패/빈 응답 시에도 원본 그대로 반환 (graceful fallback).
    """
    if not code:
        return code
    if _count_english_comments(code) < MIN_ENGLISH_COMMENTS:
        return code

    try:
        translated = await llm_chat(
            KOREANIZE_PROMPT.format(code=code[:MAX_INPUT_LEN]),
            max_tokens=2000,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("koreanize llm_chat 실패: %s", exc)
        return code

    if not translated:
        return code

    # LLM 출력에서 fence 안의 코드만 추출
    m = re.search(r"```(?:\w+\n)?(.*?)```", translated, re.DOTALL)
    if m:
        result = m.group(1)
        # 너무 짧아지면 (LLM 이 거부했거나 잘림) 원본 유지
        if len(result.strip()) < max(30, len(code) // 4):
            return code
        return result
    # fence 없으면 그냥 출력 사용
    if len(translated.strip()) < max(30, len(code) // 4):
        return code
    return translated


async def koreanize_pair_response(response_markdown: Optional[str]) -> Optional[str]:
    """``CodePair.response`` 처럼 마크다운 fence 가 포함된 텍스트의 코드 부분만 번역."""
    if not response_markdown:
        return response_markdown
    fence = re.search(r"```(\w+)?\n?(.*?)```", response_markdown, re.DOTALL)
    if not fence:
        return response_markdown
    code = fence.group(2)
    translated = await koreanize_response(code)
    if translated == code:
        return response_markdown
    lang = fence.group(1) or ""
    new_block = f"```{lang}\n{translated}\n```"
    return response_markdown[: fence.start()] + new_block + response_markdown[fence.end():]


__all__ = [
    "KOREANIZE_PROMPT",
    "MIN_ENGLISH_COMMENTS",
    "koreanize_response",
    "koreanize_pair_response",
]
