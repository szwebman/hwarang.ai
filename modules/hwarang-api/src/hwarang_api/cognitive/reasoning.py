"""LLM 기반 의사결정 추론 (Phase 6).

JSON 출력 강제 + 정규식 추출 + 폴백.
LLM 응답이 깨지면 안전 모드 (decisions=[]) 로 폴백 — 자율 액션을 안 한다.

사용
----
    plan = await reason_about_state(
        observation=observation,
        past_lessons=lessons,
        available_actions=AVAILABLE_ACTIONS,
        requires_approval=REQUIRES_APPROVAL,
        max_actions_remaining=10,
    )
    for d in plan["decisions"]:
        ...
"""

from __future__ import annotations

import json
import logging
import re

from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


REASON_PROMPT_TEMPLATE = """당신은 화랑 AI 시스템의 인지 엔진입니다. 다음 상태를 분석하고 결정을 내립니다.

## 현재 상태
{observation}

## 이번 주 화랑의 의도 (집중 영역 — 결정 시 가중치 부여)
{current_intent}

## 과거 비슷한 상황의 결정과 결과
{past_lessons}

## 사용 가능한 액션
{available_actions}

## 제약
- 사람 승인 필요 액션: {requires_approval}
- 일일 액션 한도: {max_actions_remaining}

다음 JSON 형식으로 답하세요:
{{
  "analysis": "현재 상태 분석 (3~5줄)",
  "key_issues": ["이슈1", "이슈2"],
  "reasoning": "왜 이 결정을 내렸는지 (chain of thought)",
  "decisions": [
    {{
      "action": "액션 이름",
      "params": {{"key": "value"}},
      "expected_outcome": "예상 결과",
      "risk": "low|medium|high",
      "confidence": 0.0~1.0
    }}
  ],
  "self_assessment": "이 결정이 잘못될 수 있는 경우"
}}

JSON 만 출력:"""


async def reason_about_state(
    observation: dict,
    past_lessons: list[str],
    available_actions: list[str],
    requires_approval: list[str],
    max_actions_remaining: int = 10,
) -> dict:
    """LLM 으로 상태 분석 + 결정 생성.

    실패 시 ``{"decisions": []}`` 인 안전 모드 반환.
    """
    obs_text = "\n".join(f"- {k}: {v}" for k, v in observation.items())[:3000]
    lessons_text = (
        "\n".join(f"- {l}" for l in past_lessons[:5]) or "(과거 기록 없음)"
    )
    actions_text = ", ".join(available_actions)
    approval_text = ", ".join(requires_approval) or "없음"

    # Phase 7 — 현재 주의 의도 (선언적 의도) 주입
    intent_text = "(미선언)"
    try:
        from hwarang_api.cognitive.intent import get_current_intent

        intent = await get_current_intent()
        if intent:
            intent_text = (
                f"Focus: {intent.get('focus', '?')}\n"
                f"Goals: {', '.join(intent.get('specific_goals', []) or [])}\n"
                f"Success metric: {intent.get('success_metric', '')}"
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("intent 조회 실패 (계속): %s", exc)

    prompt = REASON_PROMPT_TEMPLATE.format(
        observation=obs_text,
        past_lessons=lessons_text,
        available_actions=actions_text,
        requires_approval=approval_text,
        max_actions_remaining=max_actions_remaining,
        current_intent=intent_text,
    )

    try:
        raw = await llm_chat(prompt, max_tokens=1200)
        if not raw:
            raise ValueError("LLM empty response")
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            raise ValueError("no JSON in response")
        data = json.loads(m.group())
        # 최소 스키마 보정
        data.setdefault("analysis", "")
        data.setdefault("key_issues", [])
        data.setdefault("reasoning", "")
        data.setdefault("decisions", [])
        data.setdefault("self_assessment", "")
        if not isinstance(data["decisions"], list):
            data["decisions"] = []
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("reasoning 실패: %s", exc)

    # 폴백 — 안전 모드 (아무 액션 안 함)
    return {
        "analysis": "추론 실패 — 안전 모드",
        "key_issues": [],
        "reasoning": "LLM 응답 파싱 실패",
        "decisions": [],
        "self_assessment": "추론 자체가 실패. 다음 사이클에 재시도.",
    }


__all__ = ["reason_about_state", "REASON_PROMPT_TEMPLATE"]
