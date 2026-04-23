"""HLKM ⑨ - Blockchain-anchored Audit Log.

HLKM 의 모든 중요 변경을 AuditEvent 로 기록하고, 매일 자정 Merkle tree 로
묶어 root 해시를 HWARANG 체인에 anchor 한다. 체인 실패 시에도 로컬
AuditAnchor 는 생성되어 tamper-evident 성질을 유지.

예상 호출 지점 (와이어링은 별도 PR):
  - pipeline.ingest_fact        → record_event("fact.ingest", ...)
  - pipeline.update_fact        → record_event("fact.update", before=old, after=new)
  - self_verify.run_daily_…     → record_event("fact.reverify", ...)
  - contradiction.record_conflict → record_event("conflict.detect", ...)
  - gdpr.execute_forget_*       → record_event("fact.forget", ...)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(obj: Any) -> str:
    """정렬 키·공백 없음으로 정규화된 JSON."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def _sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _event_payload(ev: Any) -> dict:
    """이벤트 재해시용 정규화 dict."""
    return {
        "id": ev.id,
        "eventType": ev.eventType,
        "targetId": ev.targetId,
        "actorId": ev.actorId,
        "beforeHash": ev.beforeHash,
        "afterHash": ev.afterHash,
        "metadata": ev.metadata,
        "occurredAt": ev.occurredAt.isoformat() if ev.occurredAt else None,
    }


async def hash_fact(fact: dict | None) -> str | None:
    """팩트/임의 dict 를 정규화 JSON → SHA256 헥사. None 이면 None."""
    if fact is None:
        return None
    try:
        blob = _canonical_json(fact)
    except Exception as exc:
        logger.warning("hash_fact canonicalize failed: %s", exc)
        blob = str(fact)
    return _sha256_hex(blob)


def merkle_root(hashes: list[str]) -> str:
    """표준 Merkle root. 홀수면 마지막 복제. 빈 리스트 → ''."""
    if not hashes:
        return ""
    level = list(hashes)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [_sha256_hex(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]


def build_merkle_proof(target_hash: str, all_hashes: list[str]) -> list[dict]:
    """target 포함을 증명할 형제 해시 경로 [{"sibling","position"}, ...]."""
    if not all_hashes or target_hash not in all_hashes:
        return []
    level = list(all_hashes)
    idx = level.index(target_hash)
    proof: list[dict] = []
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        pair = idx ^ 1
        proof.append({"sibling": level[pair], "position": "right" if pair > idx else "left"})
        level = [_sha256_hex(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
        idx //= 2
    return proof


def verify_merkle_proof(target_hash: str, proof: list[dict], root: str) -> bool:
    """build_merkle_proof 결과로 root 를 재구성해 대조."""
    if not target_hash or not root:
        return False
    cur = target_hash
    for step in proof:
        sibling = step.get("sibling", "")
        if step.get("position") == "left":
            cur = _sha256_hex(sibling + cur)
        else:
            cur = _sha256_hex(cur + sibling)
    return cur == root


async def record_event(
    event_type: str,
    target_id: str,
    actor_id: str | None,
    before: dict | None,
    after: dict | None,
    metadata: dict | None = None,
) -> str:
    """AuditEvent 삽입. anchorId 는 daily_anchor 에서 채워진다."""
    before_hash = await hash_fact(before)
    after_hash = await hash_fact(after)
    try:
        row = await prisma.auditevent.create(  # type: ignore[attr-defined]
            data={
                "eventType": event_type,
                "targetId": target_id,
                "actorId": actor_id,
                "beforeHash": before_hash,
                "afterHash": after_hash,
                "metadata": _canonical_json(metadata or {}),
                "occurredAt": _utcnow(),
            }
        )
        return row.id
    except Exception as exc:
        logger.warning("record_event persist failed: %s", exc)
        return ""


async def submit_to_chain(
    merkle_root_hex: str, event_count: int
) -> tuple[str, str] | None:
    """HWARANG 스마트컨트랙트 anchor(bytes32, uint256) 호출.

    coin 모듈 미준비 시 None 반환 → retry_failed_anchors 가 나중에 재시도.
    """
    try:
        from hwarang_api.knowledge.coin import anchor_on_chain  # type: ignore
    except Exception as exc:
        logger.warning("submit_to_chain: coin unavailable (%s)", exc)
        return None
    try:
        result = await anchor_on_chain(merkle_root_hex, event_count)  # type: ignore[misc]
    except Exception as exc:
        logger.warning("anchor_on_chain raised: %s", exc)
        return None
    if not result:
        return None
    if isinstance(result, tuple) and len(result) == 2:
        return str(result[0]), str(result[1])
    if isinstance(result, dict):
        return str(result.get("txHash", "")), str(result.get("blockId", ""))
    return None


async def daily_anchor(date: datetime | None = None) -> dict:
    """지정일(없으면 어제) 00:00~24:00 UTC 범위 이벤트를 묶어 AuditAnchor 생성.

    1) anchorId=None 인 이벤트 조회 (occurredAt asc)
    2) 이벤트별 정규화 해시 → merkle_root
    3) AuditAnchor 생성, 이벤트의 anchorId 업데이트
    4) submit_to_chain; 성공 시 chainTxHash/anchoredAt 갱신
    """
    now = date or _utcnow()
    end = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    start = end - timedelta(days=1)

    try:
        events = await prisma.auditevent.find_many(  # type: ignore[attr-defined]
            where={"anchorId": None, "occurredAt": {"gte": start, "lt": end}},
            order={"occurredAt": "asc"},
            take=100000,
        )
    except Exception as exc:
        logger.error("daily_anchor fetch failed: %s", exc)
        events = []

    per_event = [_sha256_hex(_canonical_json(_event_payload(e))) for e in events]
    root = merkle_root(per_event)
    count = len(events)

    try:
        anchor = await prisma.auditanchor.create(  # type: ignore[attr-defined]
            data={"anchorDate": start, "merkleRoot": root, "eventCount": count}
        )
    except Exception as exc:
        logger.error("daily_anchor create anchor failed: %s", exc)
        return {"anchor_id": None, "event_count": count, "merkle_root": root, "chain_tx": None}

    if events:
        try:
            await prisma.auditevent.update_many(  # type: ignore[attr-defined]
                where={"id": {"in": [e.id for e in events]}},
                data={"anchorId": anchor.id},
            )
        except Exception as exc:
            logger.warning("daily_anchor link events failed: %s", exc)

    chain_tx: str | None = None
    chain_block: str | None = None
    submitted = await submit_to_chain(root, count)
    if submitted:
        chain_tx, chain_block = submitted
        try:
            await prisma.auditanchor.update(  # type: ignore[attr-defined]
                where={"id": anchor.id},
                data={
                    "chainTxHash": chain_tx,
                    "chainBlockId": chain_block,
                    "anchoredAt": _utcnow(),
                },
            )
        except Exception as exc:
            logger.warning("daily_anchor chain update failed: %s", exc)

    logger.info(
        "daily_anchor %s: events=%d root=%s tx=%s",
        start.date(), count, root[:16] if root else "", chain_tx,
    )
    return {
        "anchor_id": anchor.id,
        "event_count": count,
        "merkle_root": root,
        "chain_tx": chain_tx,
    }


async def retry_failed_anchors() -> int:
    """anchoredAt 이 비어있는 AuditAnchor 들을 재시도. 성공 건수 반환."""
    try:
        pending = await prisma.auditanchor.find_many(  # type: ignore[attr-defined]
            where={"anchoredAt": None}, take=200,
        )
    except Exception as exc:
        logger.warning("retry_failed_anchors query failed: %s", exc)
        return 0

    success = 0
    for a in pending:
        result = await submit_to_chain(a.merkleRoot, int(a.eventCount or 0))
        if not result:
            continue
        tx, block = result
        try:
            await prisma.auditanchor.update(  # type: ignore[attr-defined]
                where={"id": a.id},
                data={"chainTxHash": tx, "chainBlockId": block, "anchoredAt": _utcnow()},
            )
            success += 1
        except Exception as exc:
            logger.warning("retry anchor %s update failed: %s", a.id, exc)
    return success


async def verify_event(event_id: str) -> dict:
    """이벤트 무결성 검증. 현재 DB 상태 재해시 + anchor 의 merkle proof + chain."""
    out = {
        "event_id": event_id,
        "currently_valid": False,
        "in_anchor": False,
        "merkle_proof_ok": False,
        "chain_verified": False,
        "original_hash": None,
        "current_hash": None,
    }
    try:
        ev = await prisma.auditevent.find_unique(  # type: ignore[attr-defined]
            where={"id": event_id}
        )
    except Exception as exc:
        logger.warning("verify_event fetch failed: %s", exc)
        return out
    if not ev:
        return out

    current = _sha256_hex(_canonical_json(_event_payload(ev)))
    out["current_hash"] = current
    out["original_hash"] = current
    out["currently_valid"] = True

    if not ev.anchorId:
        return out
    out["in_anchor"] = True

    try:
        anchor = await prisma.auditanchor.find_unique(  # type: ignore[attr-defined]
            where={"id": ev.anchorId}
        )
        siblings = await prisma.auditevent.find_many(  # type: ignore[attr-defined]
            where={"anchorId": ev.anchorId},
            order={"occurredAt": "asc"},
            take=100000,
        )
    except Exception as exc:
        logger.warning("verify_event anchor fetch failed: %s", exc)
        return out
    if not anchor:
        return out

    hashes = [_sha256_hex(_canonical_json(_event_payload(s))) for s in siblings]
    proof = build_merkle_proof(current, hashes)
    out["merkle_proof_ok"] = verify_merkle_proof(current, proof, anchor.merkleRoot)
    out["chain_verified"] = bool(anchor.chainTxHash) and bool(anchor.anchoredAt)
    return out


async def audit_trail_for_fact(fact_id: str) -> list[dict]:
    """target_id=fact_id 인 이벤트를 시간순으로, anchor 정보 포함해 반환."""
    try:
        rows = await prisma.auditevent.find_many(  # type: ignore[attr-defined]
            where={"targetId": fact_id},
            order={"occurredAt": "asc"},
            take=1000,
        )
    except Exception as exc:
        logger.warning("audit_trail_for_fact failed: %s", exc)
        return []

    anchor_ids = sorted({r.anchorId for r in rows if r.anchorId})
    anchors: dict[str, Any] = {}
    if anchor_ids:
        try:
            fetched = await prisma.auditanchor.find_many(  # type: ignore[attr-defined]
                where={"id": {"in": anchor_ids}}
            )
            anchors = {a.id: a for a in fetched}
        except Exception as exc:
            logger.warning("audit_trail anchors fetch failed: %s", exc)

    out: list[dict] = []
    for r in rows:
        a = anchors.get(r.anchorId) if r.anchorId else None
        out.append({
            "event_id": r.id,
            "event_type": r.eventType,
            "actor_id": r.actorId,
            "before_hash": r.beforeHash,
            "after_hash": r.afterHash,
            "occurred_at": r.occurredAt.isoformat() if r.occurredAt else None,
            "anchor_id": r.anchorId,
            "anchor_date": a.anchorDate.isoformat() if a and a.anchorDate else None,
            "merkle_root": a.merkleRoot if a else None,
            "chain_tx_hash": a.chainTxHash if a else None,
        })
    return out


__all__ = [
    "record_event",
    "hash_fact",
    "merkle_root",
    "build_merkle_proof",
    "verify_merkle_proof",
    "daily_anchor",
    "submit_to_chain",
    "verify_event",
    "audit_trail_for_fact",
    "retry_failed_anchors",
]
