"""HLKM - Realtime Retraction Notification.

어떤 사실이 철회(retraction)되면, 과거에 그 사실을 근거로 답변을 받았던
사용자들에게 실시간으로 알림을 보낸다.

흐름:
    RetractionEvent → AnswerEvidence.factIds 검색 → RetractionNotification 생성
    → dispatch_pending 배치가 실제 push (email/webhook/WebSocket) → acknowledge.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _truncate(text: str, limit: int = 240) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def find_affected_answers(retraction_event_id: str) -> list[dict]:
    """RetractionEvent → 해당 factId 를 근거로 사용한 AnswerEvidence 목록.

    Return: `[{"evidence_id", "user_id", "question_text", "created_at", "fact_id"}]`
    """
    try:
        event = await prisma.retractionevent.find_unique(
            where={"id": retraction_event_id}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("retraction lookup failed id=%s err=%s",
                       retraction_event_id, exc)
        return []
    if event is None:
        return []

    fact_id = event.factId
    try:
        evidences = await prisma.answerevidence.find_many(
            where={"factIds": {"has": fact_id}},
            order={"createdAt": "desc"},
            take=1000,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("answer evidence scan failed fact=%s err=%s", fact_id, exc)
        return []

    affected = [
        {
            "evidence_id": ev.id,
            "user_id": ev.userId,
            "question_text": getattr(ev, "questionText", "") or "",
            "created_at": ev.createdAt,
            "fact_id": fact_id,
        }
        for ev in evidences
    ]
    logger.info("[notify] retraction=%s affected=%d",
                retraction_event_id, len(affected))
    return affected


async def create_notifications_for_retraction(
    retraction_event_id: str, retracted_fact_id: str
) -> int:
    """영향받은 사용자 각각에 대해 RetractionNotification 을 upsert-like 생성.

    동일 (user, evidence, fact) 조합 중복은 건너뛰고, 신규 생성된 알림 수 반환.
    """
    affected = await find_affected_answers(retraction_event_id)
    if not affected:
        return 0

    reason = ""
    try:
        event = await prisma.retractionevent.find_unique(
            where={"id": retraction_event_id}
        )
        if event is not None:
            reason = (event.reason or "")[:400]
    except Exception:
        pass

    created = 0
    for item in affected:
        user_id = item.get("user_id")
        if not user_id:
            continue  # 익명 사용자는 알림 불가
        evidence_id = item["evidence_id"]
        try:
            existing = await prisma.retractionnotification.find_first(
                where={
                    "userId": user_id,
                    "affectedAnswerEvidenceId": evidence_id,
                    "retractedFactId": retracted_fact_id,
                }
            )
        except Exception:
            existing = None
        if existing:
            continue

        q = _truncate(item.get("question_text") or "(질문 없음)", 120)
        r = _truncate(reason or "사실이 정정/철회되었습니다.", 200)
        message = f"이전 질문 '{q}'에 대한 답변의 근거 사실이 정정되었습니다. 사유: {r}"

        try:
            await prisma.retractionnotification.create(
                data={
                    "userId": user_id,
                    "affectedAnswerEvidenceId": evidence_id,
                    "retractedFactId": retracted_fact_id,
                    "retractionEventId": retraction_event_id,
                    "message": message,
                    "notified": False,
                    "acknowledged": False,
                }
            )
            created += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("notification create failed user=%s err=%s",
                           user_id, exc)

    logger.info("[notify] created=%d retraction=%s fact=%s",
                created, retraction_event_id, retracted_fact_id)
    return created


async def list_notifications(
    user_id: str, unacknowledged_only: bool = True
) -> list[dict]:
    """사용자의 알림 목록 (최신순, 최대 200건)."""
    where: dict[str, Any] = {"userId": user_id}
    if unacknowledged_only:
        where["acknowledged"] = False
    try:
        rows = await prisma.retractionnotification.find_many(
            where=where, order={"createdAt": "desc"}, take=200
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_notifications failed user=%s err=%s", user_id, exc)
        return []
    return [
        {
            "id": r.id,
            "retracted_fact_id": r.retractedFactId,
            "retraction_event_id": r.retractionEventId,
            "evidence_id": r.affectedAnswerEvidenceId,
            "message": r.message,
            "notified": bool(r.notified),
            "notified_at": getattr(r, "notifiedAt", None),
            "acknowledged": bool(r.acknowledged),
            "acknowledged_at": getattr(r, "acknowledgedAt", None),
            "created_at": getattr(r, "createdAt", None),
        }
        for r in rows
    ]


async def acknowledge_notification(notification_id: str, user_id: str) -> None:
    """사용자가 알림을 확인했음을 기록. 소유자 불일치 시 무시."""
    try:
        row = await prisma.retractionnotification.find_unique(
            where={"id": notification_id}
        )
    except Exception:
        row = None
    if row is None or row.userId != user_id:
        logger.debug("acknowledge: not found or owner mismatch id=%s", notification_id)
        return
    try:
        await prisma.retractionnotification.update(
            where={"id": notification_id},
            data={"acknowledged": True, "acknowledgedAt": _utcnow()},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("acknowledge failed id=%s err=%s", notification_id, exc)


async def acknowledge_all(user_id: str) -> int:
    """사용자의 모든 미확인 알림 일괄 acknowledged 처리. 건수 반환."""
    try:
        res = await prisma.retractionnotification.update_many(
            where={"userId": user_id, "acknowledged": False},
            data={"acknowledged": True, "acknowledgedAt": _utcnow()},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("acknowledge_all failed user=%s err=%s", user_id, exc)
        return 0
    try:
        return int(getattr(res, "count", res) or 0)
    except Exception:
        return 0


async def _send_push(user_id: str, message: str, meta: dict) -> bool:
    """실제 push 채널로 전송 (placeholder — email/webhook/WebSocket)."""
    logger.info("[push] user=%s meta=%s msg=%s",
                user_id, meta, _truncate(message, 180))
    return True


async def dispatch_pending(max_batch: int = 100) -> dict:
    """notified=False 알림을 push 전송. 성공 시 notified=True 기록.

    Return: `{"sent", "failed", "scanned"}`.
    """
    try:
        rows = await prisma.retractionnotification.find_many(
            where={"notified": False}, order={"createdAt": "asc"}, take=max_batch,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("dispatch scan failed: %s", exc)
        return {"sent": 0, "failed": 0, "scanned": 0}

    now = _utcnow()
    sent = failed = 0
    for r in rows:
        meta = {
            "notification_id": r.id,
            "retracted_fact_id": r.retractedFactId,
            "retraction_event_id": r.retractionEventId,
            "evidence_id": r.affectedAnswerEvidenceId,
        }
        try:
            ok = await _send_push(r.userId, r.message or "", meta)
        except Exception as exc:  # noqa: BLE001
            logger.warning("push failed id=%s err=%s", r.id, exc)
            ok = False
        if ok:
            try:
                await prisma.retractionnotification.update(
                    where={"id": r.id},
                    data={"notified": True, "notifiedAt": now},
                )
                sent += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("mark-notified failed id=%s err=%s", r.id, exc)
                failed += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed, "scanned": len(rows)}


async def unread_count(user_id: str) -> int:
    """사용자의 미확인 알림 수."""
    try:
        return int(
            await prisma.retractionnotification.count(
                where={"userId": user_id, "acknowledged": False}
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("unread_count failed user=%s err=%s", user_id, exc)
        return 0


async def notification_stats() -> dict:
    """전체 알림 통계 `{total, acknowledged, unread, recent_7d}`."""
    cutoff = _utcnow() - timedelta(days=7)
    stats: dict[str, int] = {"total": 0, "acknowledged": 0, "unread": 0, "recent_7d": 0}
    try:
        stats["total"] = int(await prisma.retractionnotification.count())
        stats["acknowledged"] = int(
            await prisma.retractionnotification.count(where={"acknowledged": True})
        )
        stats["unread"] = int(
            await prisma.retractionnotification.count(where={"acknowledged": False})
        )
        stats["recent_7d"] = int(
            await prisma.retractionnotification.count(
                where={"createdAt": {"gte": cutoff}}
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("notification_stats failed: %s", exc)
    return stats


async def on_retraction_recorded(retraction_event_id: str) -> dict:
    """retraction.record_retraction 에서 hook 으로 호출될 entry point."""
    try:
        event = await prisma.retractionevent.find_unique(
            where={"id": retraction_event_id}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("on_retraction_recorded lookup failed id=%s err=%s",
                       retraction_event_id, exc)
        return {"created": 0, "affected": 0, "error": "lookup_failed"}
    if event is None:
        return {"created": 0, "affected": 0, "error": "not_found"}

    affected = await find_affected_answers(retraction_event_id)
    created = await create_notifications_for_retraction(
        retraction_event_id=retraction_event_id,
        retracted_fact_id=event.factId,
    )
    return {
        "retraction_event_id": retraction_event_id,
        "retracted_fact_id": event.factId,
        "affected": len(affected),
        "created": created,
    }


__all__ = [
    "find_affected_answers",
    "create_notifications_for_retraction",
    "list_notifications",
    "acknowledge_notification",
    "acknowledge_all",
    "dispatch_pending",
    "unread_count",
    "notification_stats",
    "on_retraction_recorded",
]
