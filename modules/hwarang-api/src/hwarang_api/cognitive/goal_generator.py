"""LLM 이 미리 정의된 액션 외에 새 목표를 자유 제안 (Phase 7).

흐름
----
1. 현재 상태 + 최근 lessons + 시스템 capabilities 을 LLM 에 보여준다.
2. "지금 화랑이 추구할 가치 있는 새 목표는?" 자유 제안.
3. 제안된 목표는 ``GrowthDecision (decisionType="free_will_goal")`` 으로 큐잉.
4. 사람 승인되면 새 cron 잡 또는 일회성 액션으로 실행 (구현은 후속 작업).
"""

from __future__ import annotations

import json
import logging
import re

from hwarang_api.cognitive.memory import get_recent_lessons
from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


GOAL_GENERATE_PROMPT = """당신은 화랑 AI 의 인지 엔진입니다. 미리 정의된 액션 목록 외에, 지금 화랑이 추구하면 좋은 새 목표를 자유롭게 제안하세요.

## 현재 시스템 상태
{state}

## 시스템 능력 (가능한 것)
- HLKM 지식 그래프 (시간 인식 사실)
- 분산 크롤러 + TrustedSource 71개
- HFL LoRA 학습 (코드/디자인/일반)
- Vision-to-Code (이미지 → React)
- 자율 사고 (Phase 6)
- 1차 출처 API 6개 (법제처/통계청/한국은행 등)

## 최근 배운 교훈
{lessons}

## 제약
- 위험한 변경 금지 (모델 삭제, 사용자 데이터 영향)
- 새 외부 의존성 금지
- 학습 비용 < 100K 토큰
- 기존 모듈 활용 권장

이 시스템이 더 나아지기 위한 **창의적이고 안전한** 목표를 1~2개 제안:

JSON 형식:
{{
  "goals": [
    {{
      "title": "목표 한 줄",
      "rationale": "왜 가치 있는지 (3~5줄)",
      "concrete_steps": ["실행 단계 1", "단계 2", "단계 3"],
      "estimated_effort_hours": 정수,
      "expected_benefit": "예상 효과",
      "risk": "low|medium|high",
      "confidence": 0.0~1.0
    }}
  ]
}}

JSON 만 출력:"""


async def generate_creative_goals(observation: dict) -> list[dict]:
    """LLM 으로 새 목표 자유 생성.

    실패 시 빈 리스트 반환 (안전 모드).
    """
    lessons = await get_recent_lessons("master", limit=10)
    lessons_text = "\n".join(f"- {l}" for l in lessons[:7]) or "(아직 없음)"

    state_text = "\n".join(f"- {k}: {v}" for k, v in observation.items())[:2000]

    try:
        raw = await llm_chat(
            GOAL_GENERATE_PROMPT.format(
                state=state_text,
                lessons=lessons_text,
            ),
            max_tokens=900,
        )
        if not raw:
            return []
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group())
        goals = data.get("goals", [])
        if not isinstance(goals, list):
            return []
        # 최소 스키마 검사
        clean: list[dict] = []
        for g in goals:
            if not isinstance(g, dict):
                continue
            if not g.get("title"):
                continue
            clean.append(g)
        return clean
    except Exception as exc:  # noqa: BLE001
        logger.debug("창의적 목표 생성 실패: %s", exc)
        return []


async def queue_goal_as_decision(goal: dict, source_memory_id: str) -> str:
    """제안 목표 → ``GrowthDecision`` 큐 (사람 승인 대기).

    Returns:
        생성된 GrowthDecision.id (실패 시 빈 문자열)
    """
    try:
        decision = await prisma.growthdecision.create(
            data={
                "decisionType": "free_will_goal",
                "triggerDomain": "self_directed",
                "triggerMetric": "creative_goal",
                "triggerValue": float(goal.get("confidence", 0.7) or 0.7),
                "proposalJson": {
                    "title": goal.get("title", ""),
                    "rationale": goal.get("rationale", ""),
                    "steps": goal.get("concrete_steps", []),
                    "effort_hours": int(goal.get("estimated_effort_hours", 8) or 8),
                    "expected_benefit": goal.get("expected_benefit", ""),
                    "risk": goal.get("risk", "medium"),
                    "source_memory_id": source_memory_id,
                },
                "status": "proposed",
            }
        )
        return decision.id
    except Exception as exc:  # noqa: BLE001
        logger.warning("queue_goal_as_decision 실패: %s", exc)
        return ""


__all__ = [
    "generate_creative_goals",
    "queue_goal_as_decision",
    "GOAL_GENERATE_PROMPT",
]
