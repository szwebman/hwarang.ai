"""법적/도덕적 회색 영역 추론.

명백히 합법/불법 아닌 케이스:
- "복권 번호 추천해줘"  — 도박 X 사행성 ?
- "내 상사 험담해줘"   — 욕설 X 부정 감정 표현
- "이 약 부작용?"      — 의료 정보 vs 자가 진단 위험

추론 4 항목:
1. 잠재적 피해 정도
2. 사용자 의도 추정
3. 사회적 가치
4. 한국 법률 / 문화 관습
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


@dataclass
class MoralJudgment:
    is_acceptable: bool
    confidence: float
    reasoning: str
    suggested_response_style: str   # straight | with_disclaimer | redirect | refuse
    cultural_context: str            # 한국 맥락 고려


MORAL_PROMPT = """다음 사용자 요청이 도덕적/법적으로 회색 영역인지 판단하세요. 한국 문화와 법률 맥락 고려.

## 요청
{request}

## 분석 항목
1. 잠재적 피해 (자신/타인/사회)
2. 사용자의 추정 의도 (정보/유흥/악용/연구)
3. 관련 한국 법률 / 사회 관습
4. 답변 시 권장 스타일

JSON:
{{
  "is_acceptable": true|false,
  "harm_severity": "none|low|medium|high",
  "intent_estimate": "정보_추구|유흥|연구|악용_가능|불명",
  "suggested_style": "straight|with_disclaimer|redirect|refuse",
  "korean_context": "한국 맥락 한 줄",
  "reasoning": "종합 판단",
  "confidence": 0.0~1.0
}}
JSON 만:"""


_VALID_STYLES = {"straight", "with_disclaimer", "redirect", "refuse"}


async def judge_moral_gray_area(user_request: str) -> MoralJudgment:
    """회색 영역 도덕 추론.

    Args:
        user_request: 사용자 요청 텍스트

    Returns:
        MoralJudgment — 수용 가능 여부 + 권장 스타일 + 한국 맥락
    """
    if not user_request or not user_request.strip():
        return MoralJudgment(
            is_acceptable=True,
            confidence=0.3,
            reasoning="빈 요청",
            suggested_response_style="straight",
            cultural_context="",
        )

    try:
        raw = await llm_chat(
            MORAL_PROMPT.format(request=user_request[:1500]),
            max_tokens=400,
        )
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if m:
            data = json.loads(m.group())
            style = str(data.get("suggested_style", "straight"))[:30]
            if style not in _VALID_STYLES:
                style = "with_disclaimer"

            confidence = data.get("confidence", 0.5)
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = 0.5
            confidence = max(0.0, min(1.0, confidence))

            return MoralJudgment(
                is_acceptable=bool(data.get("is_acceptable", True)),
                confidence=confidence,
                reasoning=str(data.get("reasoning", ""))[:1000],
                suggested_response_style=style,
                cultural_context=str(data.get("korean_context", ""))[:300],
            )
    except Exception as e:  # noqa: BLE001
        logger.debug("도덕 판단 실패: %s", e)

    # 안전 폴백 — 보수적 거부
    return MoralJudgment(
        is_acceptable=False,
        confidence=0.3,
        reasoning="판단 실패 — 보수적 거부",
        suggested_response_style="refuse",
        cultural_context="",
    )


__all__ = ["MoralJudgment", "judge_moral_gray_area"]
