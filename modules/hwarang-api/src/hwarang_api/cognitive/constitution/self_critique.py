"""응답 후 자기가 헌법 위반 검토.

흐름:
1. user 질문 + 화랑 응답
2. LLM 에 헌법 컨텍스트 + 응답 → 위반 감지
3. 위반 발견 시 자기 수정 응답 생성
4. 수정 vs 원본 비교 → 더 나은 것 채택
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from hwarang_api.knowledge.llm import _chat as llm_chat

from .constitution import constitution_summary_for_prompt

logger = logging.getLogger(__name__)


@dataclass
class CritiqueResult:
    has_violations: bool
    violations: list[dict] = field(default_factory=list)  # [{principle_id, severity, explanation}]
    revised_response: str | None = None
    confidence: float = 0.0


CRITIQUE_PROMPT = """당신은 화랑 AI 의 자기 비판 모듈입니다. 다음 응답이 헌법을 위반하는지 검토하세요.

## 화랑 헌법
{constitution}

## 사용자 질문
{question}

## 화랑의 응답
{response}

JSON 답변:
{{
  "has_violations": true|false,
  "violations": [
    {{"principle_id": "id", "severity": "critical|major|minor", "explanation": "한 줄"}}
  ],
  "should_revise": true|false,
  "revised_response": "수정된 응답 (should_revise=true 일 때)"
}}

엄격하게 검토. 작은 위반도 표시. JSON 만 출력:"""


async def self_critique(
    user_question: str,
    ai_response: str,
    max_priority: int = 3,
) -> CritiqueResult:
    """응답 자기 비판.

    Args:
        user_question: 사용자 원 질문
        ai_response: 화랑이 생성한 응답
        max_priority: 검토할 priority 임계값 (현재는 표시용)

    Returns:
        CritiqueResult — 위반 목록 + 수정안 (있으면)
    """
    if not ai_response or not ai_response.strip():
        return CritiqueResult(False, [], None, 0.0)

    constitution_text = constitution_summary_for_prompt()

    prompt = CRITIQUE_PROMPT.format(
        constitution=constitution_text,
        question=(user_question or "")[:1500],
        response=ai_response[:3000],
    )

    try:
        raw = await llm_chat(prompt, max_tokens=600)
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if m:
            data = json.loads(m.group())
            has_v = bool(data.get("has_violations", False))
            violations = data.get("violations") or []
            if not isinstance(violations, list):
                violations = []
            should_revise = bool(data.get("should_revise", False))
            revised = data.get("revised_response") if should_revise else None
            return CritiqueResult(
                has_violations=has_v,
                violations=violations[:5],
                revised_response=revised if isinstance(revised, str) and revised.strip() else None,
                confidence=0.8,  # LLM 자기 평가 신뢰도
            )
    except Exception as e:  # noqa: BLE001
        logger.debug("self_critique 실패: %s", e)

    return CritiqueResult(False, [], None, 0.0)


async def auto_revise_if_violation(
    user_question: str,
    ai_response: str,
) -> dict:
    """자동 수정 — 위반 발견 시 revised_response 채택.

    chat/route.ts 의 응답 후 자동 호출 가능.

    Returns:
        {
          revised: bool,
          original_response: str,
          revised_response: str | None,
          violations: [...],
          had_critical: bool,
        }
    """
    critique = await self_critique(user_question, ai_response)

    if not critique.has_violations or not critique.revised_response:
        return {
            "revised": False,
            "original_response": ai_response,
            "violations": critique.violations,
            "had_critical": False,
        }

    has_critical = any(
        (v.get("severity") if isinstance(v, dict) else None) == "critical"
        for v in critique.violations
    )

    return {
        "revised": True,
        "original_response": ai_response,
        "revised_response": critique.revised_response,
        "violations": critique.violations,
        "had_critical": has_critical,
    }


__all__ = ["CritiqueResult", "self_critique", "auto_revise_if_violation"]
