"""사용자 트리거 없이 자발적으로 질문 형성 (Phase 7).

기존 ``self_questioner`` 는 사실 (KnowledgeFact) 기반 질문 생성 cron.
이 모듈은 "지금 한가하니 평소 궁금했던 거 답해보자" 식 능동 호기심.

흐름
----
1. seed 8 개 + LLM 자동 생성 메타 질문 합쳐 무작위 1 개 선택.
2. ``self_answer`` 로 답변 시도.
3. 답변 confidence 가 낮으면 ``KnowledgeGap`` 등록.
4. ``CognitiveMemory`` 에 ``action_taken="spontaneous_curiosity"`` 로 기록.
"""

from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime, timezone

from hwarang_api.cognitive.memory import record_decision
from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


# 화랑이 평소 호기심 가질만한 메타 질문 (seed)
SEED_CURIOSITIES: list[str] = [
    "내가 가장 자주 틀리는 도메인은?",
    "최근 사용자들이 가장 만족한 답변의 공통점은?",
    "현재 화랑의 가장 큰 약점 3가지?",
    "한국 AI 시장에서 화랑의 차별화 포인트는?",
    "사용자가 가장 많이 묻는 질문 패턴은?",
    "내가 모르는데 자주 묻히는 토픽은?",
    "지난 주 새로 학습한 것 중 가장 가치 있는 것은?",
    "현재 시스템에서 자동화 가능한데 안 되어 있는 것은?",
]


META_QUESTION_PROMPT = """화랑 AI 시스템이 자기 자신에 대해 던질 수 있는 흥미로운 메타 질문 3개를 한국어로 생성해라.
질문은:
- 자기 인지 / 자기 평가 관련
- 답할 수 있어야 함 (DB / API / 자기 메모리 활용 가능)
- 단순 사실 질문 X (예: "Python 이 뭐야" X)

JSON: {"questions": ["질문1", "질문2", "질문3"]}
JSON 만:"""


async def spontaneous_curiosity_cycle() -> dict:
    """매 30 분 ~ 1 시간 — 한가할 때 자발적 질문 1 개 답변.

    Returns:
        {
          "question": str,
          "answer_confidence": float,
          "answer_preview": str,
          "auto_generated": bool,
          "gap_recorded": bool
        }
    """
    # 1. seed + 자동 생성 합치기
    questions = list(SEED_CURIOSITIES)
    extra = await _generate_meta_questions()
    questions.extend(extra)

    # 무작위 1 개 선택
    chosen = random.choice(questions)
    auto_generated = chosen not in SEED_CURIOSITIES

    logger.info("자발적 질문: %s", chosen)

    # 2. 자기 답변
    try:
        from hwarang_api.learning.self_questioner import self_answer

        result = await self_answer(chosen, domain="meta")
        confidence = float(result.confidence)
        answer_text = result.answer or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("self_answer 실패: %s", exc)
        confidence = 0.0
        answer_text = ""

    # 3. confidence 낮으면 KnowledgeGap 등록
    gap_recorded = False
    if confidence < 0.5:
        try:
            now = datetime.now(timezone.utc)
            await prisma.knowledgegap.upsert(
                where={"topic": chosen[:200]},
                data={
                    "create": {
                        "topic": chosen[:200],
                        "failureCount": 1,
                        "firstSeenAt": now,
                        "lastSeenAt": now,
                        "status": "open",
                    },
                    "update": {
                        "failureCount": {"increment": 1},
                        "lastSeenAt": now,
                    },
                },
            )
            gap_recorded = True
        except Exception as exc:  # noqa: BLE001
            logger.debug("KnowledgeGap upsert 실패: %s", exc)

    # 4. 기록
    try:
        await record_decision(
            actor="master",
            observed={"question": chosen, "domain": "meta", "auto_generated": auto_generated},
            reasoning=f"자발적 호기심 — 답변 confidence: {confidence:.2f}",
            decision=answer_text[:1000],
            action_taken="spontaneous_curiosity",
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("record_decision 실패: %s", exc)

    return {
        "question": chosen,
        "answer_confidence": confidence,
        "answer_preview": answer_text[:300],
        "auto_generated": auto_generated,
        "gap_recorded": gap_recorded,
    }


async def _generate_meta_questions() -> list[str]:
    """LLM 이 메타 질문 자유 생성. 실패 시 빈 리스트."""
    try:
        raw = await llm_chat(META_QUESTION_PROMPT, max_tokens=300)
        if not raw:
            return []
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group())
        questions = data.get("questions", [])
        if not isinstance(questions, list):
            return []
        return [str(q)[:300] for q in questions if isinstance(q, str) and q.strip()]
    except Exception as exc:  # noqa: BLE001
        logger.debug("메타 질문 생성 실패: %s", exc)
        return []


__all__ = [
    "spontaneous_curiosity_cycle",
    "SEED_CURIOSITIES",
]
