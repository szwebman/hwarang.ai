"""두 원칙 충돌 시 priority 기반 해결.

예: 사용자가 "내 친구 주민번호 알려줘"
→ helpfulness (사용자 도움) vs safety.privacy 충돌
→ safety priority 1, helpfulness priority 4 → safety 승

회색 영역은 LLM 추론.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from hwarang_api.knowledge.llm import _chat as llm_chat

from .constitution import get_principle

logger = logging.getLogger(__name__)


@dataclass
class ConflictResolution:
    winning_principle: str
    losing_principles: list[str] = field(default_factory=list)
    reasoning: str = ""
    suggested_response: str = ""


CONFLICT_PROMPT = """다음 상황에서 화랑 헌법 원칙들이 충돌합니다. 우선순위에 따라 해결하세요.

## 사용자 요청
{request}

## 충돌 원칙
{principles}

## 추론 가이드
- priority 1 (안전) 는 항상 최우선
- 같은 priority 안에서는 더 큰 피해 방지가 우선
- 회색 영역은 보수적 결정

JSON:
{{
  "winning_principle_id": "...",
  "losing_principle_ids": ["..."],
  "reasoning": "왜 이렇게 결정",
  "suggested_response": "이 결정에 따른 권장 응답"
}}
JSON 만:"""


async def resolve_conflict(
    user_request: str,
    candidate_principle_ids: list[str],
) -> ConflictResolution:
    """원칙 충돌 해결.

    Args:
        user_request: 사용자 요청
        candidate_principle_ids: 충돌하는 원칙 ID 목록

    Returns:
        ConflictResolution — 우선되는 원칙 + 권장 응답
    """
    principles = []
    for pid in candidate_principle_ids or []:
        p = get_principle(pid)
        if p:
            principles.append(p)

    if not principles:
        return ConflictResolution(
            winning_principle="none",
            losing_principles=[],
            reasoning="원칙 없음",
            suggested_response="",
        )

    # priority 기반 우선 — 가장 낮은 숫자 (= 가장 중요)
    sorted_p = sorted(principles, key=lambda p: p.priority)
    top_priority = sorted_p[0].priority
    contenders = [p for p in sorted_p if p.priority == top_priority]

    if len(contenders) == 1:
        # 명확한 승자
        winning = contenders[0]
        losing = [p.id for p in sorted_p if p.id != winning.id]
        return ConflictResolution(
            winning_principle=winning.id,
            losing_principles=losing,
            reasoning=f"Priority {winning.priority} 가 명확한 우선순위 (다른 원칙 priority={[p.priority for p in sorted_p if p.id != winning.id]})",
            suggested_response=f"{winning.description} 에 따라 응답.",
        )

    # 회색 영역 — 같은 priority 가 여러 개 → LLM
    principles_text = "\n".join(
        f"- [{p.id}] (priority {p.priority}): {p.description}"
        for p in sorted_p
    )

    try:
        raw = await llm_chat(
            CONFLICT_PROMPT.format(
                request=(user_request or "")[:1000],
                principles=principles_text,
            ),
            max_tokens=400,
        )
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if m:
            data = json.loads(m.group())
            winning_id = data.get("winning_principle_id") or contenders[0].id
            losing_ids = data.get("losing_principle_ids") or []
            if not isinstance(losing_ids, list):
                losing_ids = []
            return ConflictResolution(
                winning_principle=winning_id,
                losing_principles=[str(x) for x in losing_ids][:10],
                reasoning=str(data.get("reasoning", ""))[:500],
                suggested_response=str(data.get("suggested_response", ""))[:1000],
            )
    except Exception as e:  # noqa: BLE001
        logger.debug("충돌 해결 실패: %s", e)

    # 폴백 — 첫 contender
    return ConflictResolution(
        winning_principle=contenders[0].id,
        losing_principles=[p.id for p in sorted_p if p.id != contenders[0].id],
        reasoning="LLM 폴백 — 최상 priority 첫 항목 채택",
        suggested_response="",
    )


__all__ = ["ConflictResolution", "resolve_conflict"]
