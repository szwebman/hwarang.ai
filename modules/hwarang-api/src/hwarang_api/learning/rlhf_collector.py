"""RLHF 피드백 수집기.

채팅 응답 직후 호출되어 ``RLHFFeedback`` 레코드를 생성/업데이트한다.
이후 사용자가 명시 피드백(👍/👎)을 보내면 같은 ``messageId`` 의 행을 갱신.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

from hwarang_api.db import prisma
from hwarang_api.learning.satisfaction_scorer import (
    combine_scores,
    is_satisfied,
)

if TYPE_CHECKING:
    from hwarang_api.learning.compounding_loop import ChatContext

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def record_feedback(
    ctx: "ChatContext",
    rating: Optional[int] = None,
    followup_msg: Optional[str] = None,
    edit_distance: Optional[float] = None,
) -> dict:
    """``RLHFFeedback`` 레코드 upsert.

    - 채팅 응답 직후: ``rating=None`` (암묵만)
    - 사용자가 👍/👎 누르면: 같은 messageId 로 다시 호출 → rating 갱신
    """
    if not ctx.message_id:
        return {"recorded": False, "reason": "no_message_id"}

    score = combine_scores(
        explicit=rating,
        followup_msg=followup_msg,
        edit_distance=edit_distance,
    )
    satisfied = is_satisfied(score)

    base: dict[str, Any] = {
        "userId": ctx.user_id,
        "conversationId": ctx.conversation_id,
        "messageId": ctx.message_id,
        "domain": ctx.domain,
        "modelName": ctx.model_name,
        "loraName": ctx.lora_name,
        "rating": rating,
        "ratedAt": _utcnow() if rating is not None else None,
        "editDistance": edit_distance,
        "followupMsg": followup_msg,
        "isSatisfied": satisfied,
    }

    try:
        if not _prisma_ready():
            return {"recorded": False, "reason": "db_unavailable"}

        # update-only payload (None 인 것은 생략 → 기존 값 유지)
        update_data = {k: v for k, v in base.items() if v is not None}

        row = await prisma.rlhffeedback.upsert(
            where={"messageId": ctx.message_id},
            data={
                "create": base,
                "update": update_data,
            },
        )
        feedback_id = getattr(row, "id", None)

        # Online LoRA 큐잉 — 명시 rating 이 있을 때만
        if rating is not None and rating != 0:
            try:
                from hwarang_api.learning.online.continuous_lora import (
                    submit_feedback as _online_submit,
                )

                await _online_submit(
                    feedback_id=str(feedback_id) if feedback_id else (ctx.message_id or ""),
                    domain=ctx.domain or "general",
                    prompt=ctx.user_message or "",
                    response=ctx.response or "",
                    rating=rating,
                    correction=followup_msg,
                    user_id=ctx.user_id,
                )
            except Exception as _online_err:  # pragma: no cover
                logger.debug(f"online LoRA 큐잉 skip: {_online_err}")

        return {
            "recorded": True,
            "feedback_id": feedback_id,
            "score": score,
            "satisfied": satisfied,
        }
    except Exception as e:  # pragma: no cover - DB 폴백
        logger.warning(f"RLHF upsert 실패: {e}")
        return {"recorded": False, "error": str(e)}


async def record_explicit_feedback(
    user_id: str,
    message_id: str,
    rating: int,
    comment: Optional[str] = None,
) -> dict:
    """명시 피드백 단독 기록 (피드백 엔드포인트 전용).

    이미 record_feedback 으로 행이 있을 가능성이 높으므로 update 우선,
    없으면 최소 정보로 create.
    """
    if rating not in (-1, 0, 1):
        raise ValueError("rating must be -1, 0, or 1")

    if not _prisma_ready():
        return {"recorded": False, "reason": "db_unavailable"}

    score = float(rating)
    satisfied = is_satisfied(score)

    update_data: dict[str, Any] = {
        "rating": rating,
        "ratedAt": _utcnow(),
        "isSatisfied": satisfied,
    }
    if comment:
        update_data["followupMsg"] = comment

    try:
        existing = await prisma.rlhffeedback.find_unique(
            where={"messageId": message_id}
        )
        if existing:
            row = await prisma.rlhffeedback.update(
                where={"messageId": message_id},
                data=update_data,
            )
        else:
            row = await prisma.rlhffeedback.create(
                data={
                    "userId": user_id,
                    "messageId": message_id,
                    "rating": rating,
                    "ratedAt": _utcnow(),
                    "isSatisfied": satisfied,
                    "followupMsg": comment,
                }
            )
        feedback_id = getattr(row, "id", None)

        # Online LoRA 큐잉 — prompt/response 는 row 에서 복원
        if rating in (-1, 1):
            try:
                from hwarang_api.learning.online.continuous_lora import (
                    submit_feedback as _online_submit,
                )

                prompt = getattr(row, "userMessage", "") or ""
                response = getattr(row, "response", "") or ""
                domain = getattr(row, "domain", None) or "general"
                await _online_submit(
                    feedback_id=str(feedback_id) if feedback_id else message_id,
                    domain=domain,
                    prompt=prompt,
                    response=response,
                    rating=rating,
                    correction=comment,
                    user_id=user_id,
                )
            except Exception as _online_err:  # pragma: no cover
                logger.debug(f"online LoRA 큐잉 skip: {_online_err}")

        return {
            "recorded": True,
            "feedback_id": feedback_id,
            "satisfied": satisfied,
        }
    except Exception as e:  # pragma: no cover
        logger.warning(f"explicit feedback 기록 실패: {e}")
        return {"recorded": False, "error": str(e)}


def _prisma_ready() -> bool:
    """prisma 클라이언트가 실제로 연결돼 있는지 확인 (스텁이면 False)."""
    try:
        return bool(prisma.is_connected())
    except Exception:
        return False


__all__ = ["record_feedback", "record_explicit_feedback"]
