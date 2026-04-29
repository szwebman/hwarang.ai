"""코드 응답에 대한 사용자 피드백 수집 — 코드 도메인 RLHF.

신호 4 유형:
  - ``executed``  : 코드가 잘 실행됨 (긍정)
  - ``accepted``  : 사용자가 채택 (긍정)
  - ``broken``    : 에러/안 됨 토글 (부정)
  - ``edited``    : 사용자가 응답 코드를 수정 후 재제출 (부정 + 수정안)

이 데이터가 다음 LoRA 학습 라운드의 ``ReplaySample`` 에 priority 10 으로 들어감.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


POSITIVE_SIGNALS = {"executed", "accepted"}
NEGATIVE_SIGNALS = {"broken", "edited"}
ALL_SIGNALS = POSITIVE_SIGNALS | NEGATIVE_SIGNALS


async def record_code_feedback(
    user_id: str,
    conversation_id: str,
    message_id: str,
    feedback_type: str,
    edited_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> dict:
    """사용자가 코드 응답에 피드백 보낼 때 호출.

    - 모든 피드백은 ``RLHFFeedback`` 으로 upsert.
    - 부정 + ``edited_code`` 가 있으면 ``ReplaySample`` 에 priority 10 추가
      (사용자가 직접 고친 코드는 정답에 가까움).
    """
    if feedback_type not in ALL_SIGNALS:
        return {"error": "invalid_feedback_type", "valid": list(ALL_SIGNALS)}

    # 1) 메시지 검증
    try:
        msg = await prisma.message.find_unique(where={"id": message_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("message.find_unique 실패: %s", exc)
        return {"error": "db_error"}
    if not msg or getattr(msg, "role", None) != "assistant":
        return {"error": "invalid_message"}

    is_satisfied = feedback_type in POSITIVE_SIGNALS
    rating = 1 if is_satisfied else -1
    now = datetime.now(timezone.utc)
    followup = error_message or edited_code or feedback_type

    # 2) RLHFFeedback upsert
    try:
        await prisma.rlhffeedback.upsert(
            where={"messageId": message_id},
            data={
                "create": {
                    "messageId": message_id,
                    "userId": user_id,
                    "conversationId": conversation_id,
                    "domain": "code",
                    "rating": rating,
                    "isSatisfied": is_satisfied,
                    "ratedAt": now,
                    "followupMsg": (followup or "")[:5000],
                },
                "update": {
                    "rating": rating,
                    "isSatisfied": is_satisfied,
                    "ratedAt": now,
                    "followupMsg": (followup or "")[:5000],
                },
            },
        )
    except Exception as exc:  # noqa: BLE001
        # prisma-client-py 의 upsert payload 형식이 다를 수 있어 fallback
        logger.debug("rlhffeedback upsert 1차 실패, fallback 시도: %s", exc)
        try:
            await prisma.rlhffeedback.upsert(
                where={"messageId": message_id},
                create={
                    "messageId": message_id,
                    "userId": user_id,
                    "conversationId": conversation_id,
                    "domain": "code",
                    "rating": rating,
                    "isSatisfied": is_satisfied,
                    "ratedAt": now,
                    "followupMsg": (followup or "")[:5000],
                },
                update={
                    "rating": rating,
                    "isSatisfied": is_satisfied,
                    "ratedAt": now,
                    "followupMsg": (followup or "")[:5000],
                },
            )
        except Exception as exc2:  # noqa: BLE001
            logger.warning("rlhffeedback upsert 실패: %s", exc2)
            return {"error": "rlhf_save_failed"}

    # 3) 부정 + 수정안 → ReplaySample priority 10
    replay_added = False
    if (not is_satisfied) and edited_code:
        try:
            # 가능한 한 prompt 도 가져와 컨텍스트 보존
            prompt_text = await _resolve_prompt(conversation_id, message_id)
            await prisma.replaysample.create(
                data={
                    "domain": "code",
                    "prompt": prompt_text[:5000],
                    "expectedOutput": edited_code[:5000],
                    "priority": 10.0,
                    "difficulty": 1.0,
                    "rlhfRating": -1,
                },
            )
            replay_added = True
        except Exception as exc:  # noqa: BLE001
            logger.debug("replaysample create 실패: %s", exc)

    return {
        "recorded": True,
        "is_satisfied": is_satisfied,
        "feedback_type": feedback_type,
        "replay_added": replay_added,
    }


async def _resolve_prompt(conversation_id: str, assistant_msg_id: str) -> str:
    """assistant 메시지 직전의 user 메시지를 prompt 로 사용."""
    try:
        msg = await prisma.message.find_unique(where={"id": assistant_msg_id})
        if not msg:
            return "(컨텍스트 없음)"
        prior = await prisma.message.find_many(
            where={
                "conversationId": conversation_id,
                "createdAt": {"lt": msg.createdAt},
                "role": "user",
            },
            order={"createdAt": "desc"},
            take=1,
        )
        if prior:
            return (prior[0].content or "")[:5000]
    except Exception as exc:  # noqa: BLE001
        logger.debug("_resolve_prompt 실패: %s", exc)
    return "(이전 대화 컨텍스트)"


__all__ = [
    "POSITIVE_SIGNALS",
    "NEGATIVE_SIGNALS",
    "ALL_SIGNALS",
    "record_code_feedback",
]
