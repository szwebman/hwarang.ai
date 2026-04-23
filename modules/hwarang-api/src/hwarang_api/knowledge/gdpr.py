"""HLKM ⑩ - Right-to-be-Forgotten (GDPR).

사용자가 본인 데이터 삭제를 요청하면 scope 별로 처리:
  - all_private    : PRIVATE 팩트 — 암호키 파기(우선) 혹은 행 삭제
  - specific_facts : 지정 fact id 만, 소유권 확인 후 삭제/익명화
  - contributions  : 기여자 식별자 익명화 (팩트는 공공지식으로 유지)
  - all            : 위 전부

처리 이력은 audit.record_event 로 감사 체인에 anchor 된다. 삭제 보고서는
JSON 으로 /var/hlkm/forget_reports/ 하위에 저장되고 머클 감사 해시가 포함.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hwarang_api.db import prisma
from hwarang_api.knowledge import audit

logger = logging.getLogger(__name__)

_REPORT_DIR = Path(os.environ.get("HLKM_FORGET_REPORT_DIR", "/var/hlkm/forget_reports"))
_VALID_SCOPES = {"all_private", "specific_facts", "contributions", "all"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _anon_id(user_id: str) -> str:
    """원본 복원 불가한 익명 식별자."""
    h = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
    return f"deleted_user_{h}"


def _ensure_report_dir() -> None:
    try:
        _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("forget_reports dir create failed: %s", exc)


async def submit_forget_request(
    user_id: str,
    scope: str,
    target_fact_ids: list[str] | None = None,
    reason: str | None = None,
) -> str:
    """ForgetRequest 생성. 반환: 요청 id."""
    if scope not in _VALID_SCOPES:
        raise ValueError(f"invalid scope: {scope}; expected one of {_VALID_SCOPES}")
    try:
        row = await prisma.forgetrequest.create(  # type: ignore[attr-defined]
            data={
                "userId": user_id,
                "scope": scope,
                "targetFactIds": target_fact_ids or [],
                "reason": reason,
                "status": "pending",
                "requestedAt": _utcnow(),
            }
        )
        logger.info("forget_request submitted: user=%s scope=%s id=%s", user_id, scope, row.id)
        return row.id
    except Exception as exc:
        logger.error("submit_forget_request failed: %s", exc)
        return ""


async def list_pending_requests(status: str = "pending") -> list[dict]:
    """관리자 리뷰용 목록."""
    try:
        rows = await prisma.forgetrequest.find_many(  # type: ignore[attr-defined]
            where={"status": status}, order={"requestedAt": "asc"}, take=500,
        )
    except Exception as exc:
        logger.warning("list_pending_requests failed: %s", exc)
        return []
    return [
        {
            "id": r.id,
            "user_id": r.userId,
            "scope": r.scope,
            "target_fact_ids": list(r.targetFactIds or []),
            "reason": r.reason,
            "status": r.status,
            "requested_at": r.requestedAt.isoformat() if r.requestedAt else None,
        }
        for r in rows
    ]


async def reject_request(request_id: str, admin_user_id: str, reason: str) -> None:
    """요청 반려 + 감사 기록."""
    try:
        await prisma.forgetrequest.update(  # type: ignore[attr-defined]
            where={"id": request_id},
            data={
                "status": "rejected",
                "processedAt": _utcnow(),
                "processedBy": admin_user_id,
                "reason": (reason or "")[:2000],
            },
        )
    except Exception as exc:
        logger.warning("reject_request update failed: %s", exc)
    await audit.record_event(
        "forget.reject", request_id, admin_user_id,
        before=None, after=None, metadata={"reason": reason},
    )


async def approve_request(request_id: str, admin_user_id: str) -> dict:
    """요청 승인 + scope 에 따른 실제 삭제 실행."""
    try:
        req = await prisma.forgetrequest.find_unique(  # type: ignore[attr-defined]
            where={"id": request_id}
        )
    except Exception as exc:
        logger.error("approve_request fetch failed: %s", exc)
        return {"error": "fetch_failed"}
    if not req:
        return {"error": "not_found"}
    if req.status != "pending":
        return {"error": f"invalid_status:{req.status}"}

    summary: dict[str, Any] = {
        "scope": req.scope,
        "facts_deleted": 0,
        "contributions_anonymized": 0,
        "keys_destroyed": 0,
    }
    try:
        if req.scope in ("all_private", "all"):
            r = await execute_forget_all_private(req.userId)
            summary["facts_deleted"] += int(r.get("count", 0))
            summary["keys_destroyed"] += int(r.get("keys_destroyed", 0))
            summary["method_private"] = r.get("method")
        if req.scope in ("contributions", "all"):
            r = await execute_forget_contributions(req.userId)
            summary["contributions_anonymized"] += int(r.get("count", 0))
        if req.scope == "specific_facts":
            r = await execute_forget_specific(req.userId, list(req.targetFactIds or []))
            summary["facts_deleted"] += int(r.get("count", 0))
            summary["contributions_anonymized"] += int(r.get("anonymized", 0))
    except Exception as exc:
        logger.error("approve_request exec failed: %s", exc)
        summary["error"] = str(exc)

    report_url: str | None = None
    try:
        report_url = await generate_deletion_report(request_id)
    except Exception as exc:
        logger.warning("generate_deletion_report failed: %s", exc)

    try:
        await prisma.forgetrequest.update(  # type: ignore[attr-defined]
            where={"id": request_id},
            data={
                "status": "approved",
                "processedAt": _utcnow(),
                "processedBy": admin_user_id,
                "reportUrl": report_url,
            },
        )
    except Exception as exc:
        logger.warning("approve_request status update failed: %s", exc)

    await audit.record_event(
        "forget.approve", request_id, admin_user_id,
        before=None, after=None, metadata=summary,
    )
    return summary


async def execute_forget_all_private(user_id: str) -> dict:
    """PRIVATE 팩트 삭제. 우선 암호키 파기(crypto-shred), 없으면 hard delete."""
    try:
        facts = await prisma.knowledgefact.find_many(  # type: ignore[attr-defined]
            where={"ownerUserId": user_id, "visibility": "PRIVATE"}, take=100000,
        )
    except Exception as exc:
        logger.warning("forget_all_private fetch failed: %s", exc)
        facts = []

    method = "hard_delete"
    keys_destroyed = 0
    if await destroy_user_encryption_key(user_id):
        method = "crypto_shred"
        keys_destroyed = 1

    count = 0
    for f in facts:
        before_hash = await audit.hash_fact({"id": f.id, "content": f.content})
        try:
            if method == "crypto_shred":
                await prisma.knowledgefact.update(  # type: ignore[attr-defined]
                    where={"id": f.id},
                    data={
                        "content": "[CRYPTO-SHREDDED]",
                        "contentHash": "",
                        "status": "RETRACTED",
                    },
                )
            else:
                await prisma.knowledgefact.delete(  # type: ignore[attr-defined]
                    where={"id": f.id}
                )
            count += 1
            await audit.record_event(
                "fact.forget", f.id, actor_id=user_id,
                before={"hash": before_hash, "visibility": "PRIVATE"},
                after=None, metadata={"method": method},
            )
        except Exception as exc:
            logger.warning("forget delete fact %s failed: %s", f.id, exc)

    return {"count": count, "method": method, "keys_destroyed": keys_destroyed}


async def execute_forget_contributions(user_id: str) -> dict:
    """기여자 식별자 익명화. 팩트 자체는 유지."""
    anon = _anon_id(user_id)
    count = 0
    try:
        contribs = await prisma.knowledgecontribution.find_many(  # type: ignore[attr-defined]
            where={"contributorId": user_id}, take=100000,
        )
    except Exception as exc:
        logger.warning("forget_contributions fetch failed: %s", exc)
        contribs = []

    for c in contribs:
        try:
            await prisma.knowledgecontribution.update(  # type: ignore[attr-defined]
                where={"id": c.id}, data={"contributorId": anon},
            )
            count += 1
            await audit.record_event(
                "contribution.anonymize", c.id, actor_id=user_id,
                before={"contributor_id": user_id},
                after={"contributor_id": anon},
                metadata={},
            )
        except Exception as exc:
            logger.warning("anonymize contribution %s failed: %s", c.id, exc)

    try:
        await prisma.knowledgefact.update_many(  # type: ignore[attr-defined]
            where={"contributedBy": user_id}, data={"contributedBy": anon},
        )
    except Exception as exc:
        logger.warning("fact.contributedBy anonymize failed: %s", exc)

    return {"count": count, "anon_id": anon}


async def execute_forget_specific(user_id: str, fact_ids: list[str]) -> dict:
    """특정 fact_id 들에 대해 소유권 확인 후 삭제/익명화."""
    deleted = 0
    anonymized = 0
    anon = _anon_id(user_id)

    for fid in fact_ids or []:
        try:
            fact = await prisma.knowledgefact.find_unique(  # type: ignore[attr-defined]
                where={"id": fid}
            )
        except Exception as exc:
            logger.warning("forget_specific find %s failed: %s", fid, exc)
            continue
        if not fact:
            continue

        before_hash = await audit.hash_fact(
            {"id": fact.id, "content": fact.content, "visibility": fact.visibility}
        )
        if fact.visibility == "PRIVATE" and fact.ownerUserId == user_id:
            try:
                await prisma.knowledgefact.delete(where={"id": fid})  # type: ignore[attr-defined]
                deleted += 1
                await audit.record_event(
                    "fact.forget", fid, actor_id=user_id,
                    before={"hash": before_hash}, after=None,
                    metadata={"reason": "specific_private"},
                )
            except Exception as exc:
                logger.warning("forget_specific delete %s failed: %s", fid, exc)
        elif getattr(fact, "contributedBy", None) == user_id:
            try:
                await prisma.knowledgefact.update(  # type: ignore[attr-defined]
                    where={"id": fid}, data={"contributedBy": anon},
                )
                anonymized += 1
                await audit.record_event(
                    "fact.anonymize", fid, actor_id=user_id,
                    before={"contributed_by": user_id},
                    after={"contributed_by": anon},
                    metadata={"reason": "specific_contribution"},
                )
            except Exception as exc:
                logger.warning("forget_specific anonymize %s failed: %s", fid, exc)
        else:
            logger.info("forget_specific: user %s no ownership on %s", user_id, fid)

    return {"count": deleted, "anonymized": anonymized}


async def destroy_user_encryption_key(user_id: str) -> bool:
    """SystemSetting 'privacy.user_key.{user_id}' 제거 (crypto-shred 근간)."""
    key_name = f"privacy.user_key.{user_id}"
    try:
        existing = await prisma.systemsetting.find_unique(  # type: ignore[attr-defined]
            where={"key": key_name}
        )
    except Exception:
        existing = None
    if not existing:
        return False
    try:
        await prisma.systemsetting.delete(where={"key": key_name})  # type: ignore[attr-defined]
        logger.info("destroyed encryption key for user %s", user_id)
        return True
    except Exception as exc:
        logger.warning("destroy key for %s failed: %s", user_id, exc)
        return False


async def generate_deletion_report(request_id: str) -> str:
    """삭제 보고서 JSON 을 파일로 저장 후 경로 반환. 실제 content 는 불포함."""
    _ensure_report_dir()
    try:
        req = await prisma.forgetrequest.find_unique(  # type: ignore[attr-defined]
            where={"id": request_id}
        )
    except Exception as exc:
        logger.warning("generate_deletion_report fetch failed: %s", exc)
        req = None

    events: list[dict] = []
    if req:
        try:
            ev_rows = await prisma.auditevent.find_many(  # type: ignore[attr-defined]
                where={
                    "actorId": req.userId,
                    "eventType": {"in": ["fact.forget", "fact.anonymize", "contribution.anonymize"]},
                },
                order={"occurredAt": "asc"},
                take=10000,
            )
            for ev in ev_rows:
                events.append({
                    "event_id": ev.id,
                    "event_type": ev.eventType,
                    "target_id": ev.targetId,
                    "occurred_at": ev.occurredAt.isoformat() if ev.occurredAt else None,
                    "before_hash": ev.beforeHash,
                    "after_hash": ev.afterHash,
                })
        except Exception as exc:
            logger.warning("generate_deletion_report events fetch failed: %s", exc)

    body = {
        "request_id": request_id,
        "user_id": req.userId if req else None,
        "scope": req.scope if req else None,
        "requested_at": req.requestedAt.isoformat() if req and req.requestedAt else None,
        "processed_at": _utcnow().isoformat(),
        "events": events,
        "event_count": len(events),
    }
    body["audit_hash"] = audit.merkle_root(
        [hashlib.sha256(json.dumps(e, sort_keys=True).encode()).hexdigest() for e in events]
    )

    path = _REPORT_DIR / f"{request_id}.json"
    try:
        path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("write deletion report failed: %s", exc)
    return str(path)


async def right_of_access(user_id: str) -> dict:
    """GDPR Art.15 — 사용자 보유 데이터 전부 export. PRIVATE 은 암호문 그대로."""
    profile: dict[str, Any] = {}
    try:
        u = await prisma.user.find_unique(where={"id": user_id})  # type: ignore[attr-defined]
        if u:
            profile = {
                "id": u.id,
                "email": getattr(u, "email", None),
                "name": getattr(u, "name", None),
                "created_at": u.createdAt.isoformat() if getattr(u, "createdAt", None) else None,
            }
    except Exception as exc:
        logger.warning("right_of_access profile failed: %s", exc)

    facts: list[dict] = []
    try:
        rows = await prisma.knowledgefact.find_many(  # type: ignore[attr-defined]
            where={"ownerUserId": user_id, "visibility": "PRIVATE"}, take=100000,
        )
        facts = [
            {
                "id": r.id,
                "content_encrypted": r.content,
                "domain": r.domain,
                "created_at": r.createdAt.isoformat() if r.createdAt else None,
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("right_of_access facts failed: %s", exc)

    contribs: list[dict] = []
    try:
        cs = await prisma.knowledgecontribution.find_many(  # type: ignore[attr-defined]
            where={"contributorId": user_id}, take=100000,
        )
        contribs = [
            {
                "id": c.id,
                "fact_id": getattr(c, "factId", None),
                "kind": getattr(c, "kind", None),
                "created_at": c.createdAt.isoformat() if getattr(c, "createdAt", None) else None,
            }
            for c in cs
        ]
    except Exception as exc:
        logger.warning("right_of_access contribs failed: %s", exc)

    audit_events: list[dict] = []
    try:
        evs = await prisma.auditevent.find_many(  # type: ignore[attr-defined]
            where={"actorId": user_id}, order={"occurredAt": "asc"}, take=10000,
        )
        audit_events = [
            {
                "id": ev.id,
                "event_type": ev.eventType,
                "target_id": ev.targetId,
                "occurred_at": ev.occurredAt.isoformat() if ev.occurredAt else None,
            }
            for ev in evs
        ]
    except Exception as exc:
        logger.warning("right_of_access audit failed: %s", exc)

    return {
        "user_id": user_id,
        "profile": profile,
        "private_facts": facts,
        "contributions": contribs,
        "audit_events": audit_events,
        "exported_at": _utcnow().isoformat(),
    }


async def scheduled_forget_execution() -> int:
    """approved 이지만 processedAt 이 비어있는 요청 배치 처리 (cron 용)."""
    try:
        pending = await prisma.forgetrequest.find_many(  # type: ignore[attr-defined]
            where={"status": "approved", "processedAt": None}, take=200,
        )
    except Exception as exc:
        logger.warning("scheduled_forget_execution fetch failed: %s", exc)
        return 0

    done = 0
    for req in pending:
        try:
            await approve_request(req.id, req.processedBy or "system")
            done += 1
        except Exception as exc:
            logger.warning("scheduled forget exec %s failed: %s", req.id, exc)
    return done


__all__ = [
    "submit_forget_request",
    "list_pending_requests",
    "approve_request",
    "reject_request",
    "execute_forget_all_private",
    "execute_forget_contributions",
    "execute_forget_specific",
    "destroy_user_encryption_key",
    "generate_deletion_report",
    "right_of_access",
    "scheduled_forget_execution",
]
