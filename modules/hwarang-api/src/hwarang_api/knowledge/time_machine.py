"""HLKM ⑥ - Time Machine (지식 타임머신).

특정 시점의 전체/부분 지식 상태를 gzip+JSON 으로 "녹화" 하여, 나중에
(1) 비교,
(2) 감사,
(3) 위험한 롤백 복원
을 수행한다. 스냅샷은 ``merkleRoot`` 로 tamper-evident 성질을 가지며
원본 KnowledgeFact 테이블을 직접 덮어쓰지 않는다. 복원은 지정된 fact id
목록에 대해서만 허용되며, 직전 상태는 backup 스냅샷으로 자동 보관된다.

주요 진입점:
    - create_snapshot(name, scope, scope_value)
    - list_snapshots / get_snapshot
    - compare_snapshots(snap_a_id, snap_b_id)
    - restore_snapshot_to_readonly(snapshot_id)
    - rollback_facts_to_snapshot(snapshot_id, fact_ids, admin)
    - diff_timeline_view(entity, between_dates)
    - what_if_rollback(snapshot_id, fact_ids)
    - cleanup_expired_snapshots()

파일 경로: ``$HLKM_SNAPSHOT_DIR`` (기본 ``/var/hlkm/snapshots/``).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hwarang_api.db import prisma

from .audit import hash_fact, merkle_root, record_event
from .types import KnowledgeFact, KnowledgeStatus

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────────────────────
_SNAPSHOT_DIR = Path(os.environ.get("HLKM_SNAPSHOT_DIR", "/var/hlkm/snapshots"))
_COMPRESSION = "gzip"
_VALID_SCOPES = {"full", "domain", "entity", "user"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_dir() -> None:
    try:
        _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        logger.warning("snapshot dir create failed: %s", exc)


def _snapshot_path(snapshot_id: str) -> Path:
    return _SNAPSHOT_DIR / f"{snapshot_id}.json.gz"


# ─────────────────────────────────────────────────────────────
# 직렬화 유틸
# ─────────────────────────────────────────────────────────────
def _serialize_facts_stream(facts: list[dict]) -> bytes:
    """사실 목록을 정규화 JSON + gzip 압축하여 bytes 로 반환.

    키 정렬은 merkle 재계산 가능성을 보장하기 위함.
    """
    blob = json.dumps(facts, sort_keys=True, ensure_ascii=False, default=str)
    return gzip.compress(blob.encode("utf-8"))


def _deserialize_snapshot(data: bytes) -> list[dict]:
    """_serialize_facts_stream 의 역연산."""
    try:
        text = gzip.decompress(data).decode("utf-8")
    except Exception as exc:
        logger.warning("deserialize: gunzip failed: %s", exc)
        return []
    try:
        obj = json.loads(text)
    except Exception as exc:
        logger.warning("deserialize: json parse failed: %s", exc)
        return []
    return list(obj) if isinstance(obj, list) else []


def _row_to_plain(row: Any) -> dict:
    """Prisma row 를 스냅샷용 dict 로 변환 (스키마 변동에 관대)."""
    if isinstance(row, dict):
        src = row
    else:
        try:
            src = row.model_dump()  # type: ignore[attr-defined]
        except Exception:
            src = {
                k: getattr(row, k)
                for k in dir(row)
                if not k.startswith("_") and not callable(getattr(row, k, None))
            }
    out: dict[str, Any] = {}
    for k, v in src.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


# ─────────────────────────────────────────────────────────────
# scope → prisma where
# ─────────────────────────────────────────────────────────────
def _where_for_scope(scope: str, scope_value: str | None) -> dict:
    if scope not in _VALID_SCOPES:
        raise ValueError(f"invalid scope: {scope}; expected one of {_VALID_SCOPES}")
    if scope == "full":
        return {}
    if scope == "domain":
        if not scope_value:
            raise ValueError("scope=domain requires scope_value")
        return {"domain": scope_value}
    if scope == "entity":
        if not scope_value:
            raise ValueError("scope=entity requires scope_value")
        return {"entity": scope_value}
    if scope == "user":
        if not scope_value:
            raise ValueError("scope=user requires scope_value")
        return {"ownerUserId": scope_value}
    return {}


# ─────────────────────────────────────────────────────────────
# 스냅샷 생성
# ─────────────────────────────────────────────────────────────
async def create_snapshot(
    name: str,
    scope: str = "full",
    scope_value: str | None = None,
    created_by: str | None = None,
) -> str:
    """지정 scope 의 사실들을 압축 저장하고 KnowledgeSnapshot 레코드를 만든다.

    반환: 새로 생성된 snapshot_id (문자열).
    """
    if scope not in _VALID_SCOPES:
        raise ValueError(f"invalid scope: {scope}")
    _ensure_dir()

    where = _where_for_scope(scope, scope_value)
    try:
        rows = await prisma.knowledgefact.find_many(where=where, take=1_000_000)
    except Exception as exc:
        logger.warning("create_snapshot: find_many failed: %s", exc)
        rows = []

    facts = [_row_to_plain(r) for r in rows]

    # merkle 해시 계산 (audit.hash_fact 재사용)
    hashes: list[str] = []
    for f in facts:
        h = await hash_fact(f)
        if h:
            hashes.append(h)
    root = merkle_root(hashes)

    # 파일 저장
    snapshot_id = uuid.uuid4().hex
    path = _snapshot_path(snapshot_id)
    data = _serialize_facts_stream(facts)
    try:
        path.write_bytes(data)
    except Exception as exc:
        logger.error("create_snapshot write failed: %s", exc)
        raise

    # DB 레코드 생성
    try:
        row = await prisma.knowledgesnapshot.create(  # type: ignore[attr-defined]
            data={
                "name": name,
                "snapshotAt": _utcnow(),
                "scope": scope,
                "scopeValue": scope_value,
                "factCount": len(facts),
                "merkleRoot": root,
                "storageLocation": str(path),
                "compressionMethod": _COMPRESSION,
                "sizeBytes": len(data),
                "createdBy": created_by,
                "createdAt": _utcnow(),
            }
        )
        snapshot_id = row.id if getattr(row, "id", None) else snapshot_id
    except Exception as exc:
        logger.warning("create_snapshot DB insert failed (keeping file): %s", exc)

    # audit
    try:
        await record_event(
            event_type="snapshot.create",
            target_id=snapshot_id,
            actor_id=created_by,
            before=None,
            after={
                "name": name,
                "scope": scope,
                "scope_value": scope_value,
                "fact_count": len(facts),
                "merkle_root": root,
                "size_bytes": len(data),
            },
            metadata={"path": str(path)},
        )
    except Exception as exc:
        logger.debug("audit record_event snapshot.create skipped: %s", exc)

    return snapshot_id


# ─────────────────────────────────────────────────────────────
# 조회
# ─────────────────────────────────────────────────────────────
async def list_snapshots(scope: str | None = None) -> list[dict]:
    """스냅샷 메타데이터 목록. scope 지정 시 해당 scope 만 반환."""
    where: dict[str, Any] = {}
    if scope:
        if scope not in _VALID_SCOPES:
            raise ValueError(f"invalid scope: {scope}")
        where["scope"] = scope
    try:
        rows = await prisma.knowledgesnapshot.find_many(  # type: ignore[attr-defined]
            where=where, order={"snapshotAt": "desc"}, take=500,
        )
    except Exception as exc:
        logger.warning("list_snapshots failed: %s", exc)
        return []
    out: list[dict] = []
    for r in rows:
        out.append({
            "id": r.id,
            "name": r.name,
            "snapshot_at": r.snapshotAt.isoformat() if r.snapshotAt else None,
            "scope": r.scope,
            "scope_value": r.scopeValue,
            "fact_count": int(r.factCount or 0),
            "merkle_root": r.merkleRoot,
            "size_bytes": int(r.sizeBytes or 0),
            "compression": r.compressionMethod,
            "created_by": r.createdBy,
            "created_at": r.createdAt.isoformat() if r.createdAt else None,
            "expires_at": r.expiresAt.isoformat() if getattr(r, "expiresAt", None) else None,
        })
    return out


async def get_snapshot(snapshot_id: str) -> dict:
    """스냅샷 메타데이터 + merkle 재검증. 파일 존재/무결성 확인."""
    try:
        row = await prisma.knowledgesnapshot.find_unique(  # type: ignore[attr-defined]
            where={"id": snapshot_id}
        )
    except Exception as exc:
        logger.warning("get_snapshot lookup failed: %s", exc)
        return {"id": snapshot_id, "error": "lookup_failed"}
    if row is None:
        return {"id": snapshot_id, "error": "not_found"}

    path = Path(row.storageLocation or _snapshot_path(snapshot_id))
    integrity_ok = False
    recomputed_root = ""
    fact_count = 0
    if path.exists():
        try:
            data = path.read_bytes()
            facts = _deserialize_snapshot(data)
            fact_count = len(facts)
            hashes: list[str] = []
            for f in facts:
                h = await hash_fact(f)
                if h:
                    hashes.append(h)
            recomputed_root = merkle_root(hashes)
            integrity_ok = (recomputed_root == (row.merkleRoot or ""))
        except Exception as exc:
            logger.warning("get_snapshot verify failed: %s", exc)

    return {
        "id": row.id,
        "name": row.name,
        "snapshot_at": row.snapshotAt.isoformat() if row.snapshotAt else None,
        "scope": row.scope,
        "scope_value": row.scopeValue,
        "fact_count_db": int(row.factCount or 0),
        "fact_count_file": fact_count,
        "merkle_root": row.merkleRoot,
        "recomputed_merkle_root": recomputed_root,
        "integrity_ok": integrity_ok,
        "storage_location": str(path),
        "compression_method": row.compressionMethod,
        "size_bytes": int(row.sizeBytes or 0),
        "created_by": row.createdBy,
        "created_at": row.createdAt.isoformat() if row.createdAt else None,
        "expires_at": row.expiresAt.isoformat() if getattr(row, "expiresAt", None) else None,
    }


# ─────────────────────────────────────────────────────────────
# 임시 복원 (read-only)
# ─────────────────────────────────────────────────────────────
async def restore_snapshot_to_readonly(
    snapshot_id: str, target_path: str | None = None
) -> dict:
    """스냅샷을 임시 디렉토리로 펼친다. 실제 KnowledgeFact 테이블은 건드리지 않음.

    반환: {"facts_loaded", "temp_path", "merkle_ok"}
    """
    meta = await get_snapshot(snapshot_id)
    if meta.get("error"):
        return {"facts_loaded": 0, "temp_path": None, "error": meta["error"]}

    try:
        data = Path(meta["storage_location"]).read_bytes()
    except Exception as exc:
        logger.warning("restore read failed: %s", exc)
        return {"facts_loaded": 0, "temp_path": None, "error": "read_failed"}

    facts = _deserialize_snapshot(data)

    if target_path:
        out_dir = Path(target_path)
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = Path(tempfile.mkdtemp(prefix=f"hlkm_snapshot_{snapshot_id}_"))

    out_file = out_dir / "facts.json"
    try:
        out_file.write_text(
            json.dumps(facts, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("restore write failed: %s", exc)
        return {"facts_loaded": 0, "temp_path": str(out_dir), "error": "write_failed"}

    return {
        "facts_loaded": len(facts),
        "temp_path": str(out_file),
        "merkle_ok": bool(meta.get("integrity_ok")),
    }


# ─────────────────────────────────────────────────────────────
# 비교
# ─────────────────────────────────────────────────────────────
def _index_by_id(facts: list[dict]) -> dict[str, dict]:
    return {str(f.get("id")): f for f in facts if f.get("id")}


def _content_hash_of(fact: dict) -> str:
    h = fact.get("contentHash") or fact.get("content_hash")
    if h:
        return str(h)
    return _sha256_hex(str(fact.get("content", "")))


async def compare_snapshots(snap_a_id: str, snap_b_id: str) -> dict:
    """두 스냅샷 간 변경 사항(added/removed/modified/retracted_since) 리포트."""
    meta_a = await get_snapshot(snap_a_id)
    meta_b = await get_snapshot(snap_b_id)
    if meta_a.get("error") or meta_b.get("error"):
        return {
            "error": "snapshot_missing",
            "a_error": meta_a.get("error"),
            "b_error": meta_b.get("error"),
        }

    try:
        a_facts = _deserialize_snapshot(Path(meta_a["storage_location"]).read_bytes())
        b_facts = _deserialize_snapshot(Path(meta_b["storage_location"]).read_bytes())
    except Exception as exc:
        logger.warning("compare read failed: %s", exc)
        return {"error": "read_failed"}

    a_idx = _index_by_id(a_facts)
    b_idx = _index_by_id(b_facts)
    a_ids = set(a_idx.keys())
    b_ids = set(b_idx.keys())

    added_ids = b_ids - a_ids
    removed_ids = a_ids - b_ids
    common_ids = a_ids & b_ids

    modified: list[dict] = []
    retracted_since: list[dict] = []
    for fid in common_ids:
        a = a_idx[fid]
        b = b_idx[fid]
        if _content_hash_of(a) != _content_hash_of(b):
            modified.append({
                "id": fid,
                "a_hash": _content_hash_of(a),
                "b_hash": _content_hash_of(b),
                "a_status": a.get("status"),
                "b_status": b.get("status"),
            })
        a_status = str(a.get("status") or "")
        b_status = str(b.get("status") or "")
        if a_status not in {KnowledgeStatus.RETRACTED.value, "EXPIRED"} and b_status == KnowledgeStatus.RETRACTED.value:
            retracted_since.append({"id": fid, "a_status": a_status, "b_status": b_status})

    return {
        "snap_a": {"id": snap_a_id, "name": meta_a.get("name"), "at": meta_a.get("snapshot_at")},
        "snap_b": {"id": snap_b_id, "name": meta_b.get("name"), "at": meta_b.get("snapshot_at")},
        "added": [b_idx[i] for i in sorted(added_ids)],
        "removed": [a_idx[i] for i in sorted(removed_ids)],
        "modified": modified,
        "retracted_since": retracted_since,
        "summary": {
            "added": len(added_ids),
            "removed": len(removed_ids),
            "modified": len(modified),
            "retracted_since": len(retracted_since),
        },
    }


# ─────────────────────────────────────────────────────────────
# 롤백
# ─────────────────────────────────────────────────────────────
async def rollback_facts_to_snapshot(
    snapshot_id: str,
    target_fact_ids: list[str],
    admin_user_id: str,
) -> dict:
    """지정 fact 들을 스냅샷 시점 상태로 되돌린다. 위험 작업 — admin 전용.

    1. 현재 상태를 별도 backup 스냅샷으로 저장
    2. 스냅샷에서 지정 id 들을 읽어 KnowledgeFact 업데이트
    3. record_event("fact.rollback") 로 감사
    """
    if not admin_user_id:
        raise PermissionError("rollback requires admin_user_id")
    if not target_fact_ids:
        return {"restored": 0, "backup_snapshot_id": None, "error": "no_targets"}

    # 1) 백업
    backup_id = await create_snapshot(
        name=f"rollback_backup_{snapshot_id[:8]}_{_utcnow().isoformat()}",
        scope="full",
        scope_value=None,
        created_by=admin_user_id,
    )

    # 2) 스냅샷 로딩
    meta = await get_snapshot(snapshot_id)
    if meta.get("error"):
        return {"restored": 0, "backup_snapshot_id": backup_id, "error": meta["error"]}
    try:
        data = Path(meta["storage_location"]).read_bytes()
    except Exception as exc:
        logger.warning("rollback read failed: %s", exc)
        return {"restored": 0, "backup_snapshot_id": backup_id, "error": "read_failed"}
    snap_facts = _index_by_id(_deserialize_snapshot(data))

    restored = 0
    failed: list[str] = []
    for fid in target_fact_ids:
        snap = snap_facts.get(fid)
        if not snap:
            failed.append(fid)
            continue
        try:
            current_row = await prisma.knowledgefact.find_unique(where={"id": fid})
        except Exception:
            current_row = None
        before = _row_to_plain(current_row) if current_row is not None else None

        update_data: dict[str, Any] = {}
        # 안전한 필드만 복원 (스키마 종속)
        for k in ("content", "contentHash", "domain", "entity", "language",
                  "status", "confidenceT0", "validFrom", "validTo"):
            if k in snap:
                update_data[k] = snap[k]

        try:
            await prisma.knowledgefact.update(
                where={"id": fid}, data=update_data,
            )
            restored += 1
            try:
                await record_event(
                    event_type="fact.rollback",
                    target_id=fid,
                    actor_id=admin_user_id,
                    before=before,
                    after=snap,
                    metadata={
                        "snapshot_id": snapshot_id,
                        "backup_snapshot_id": backup_id,
                    },
                )
            except Exception as exc:
                logger.debug("audit record_event fact.rollback skipped: %s", exc)
        except Exception as exc:
            logger.warning("rollback update failed id=%s: %s", fid, exc)
            failed.append(fid)

    return {
        "restored": restored,
        "failed": failed,
        "backup_snapshot_id": backup_id,
        "snapshot_id": snapshot_id,
    }


# ─────────────────────────────────────────────────────────────
# 자동화 / 정리
# ─────────────────────────────────────────────────────────────
async def schedule_auto_snapshot(cron_expr: str = "0 2 * * 0") -> None:
    """자동 스냅샷 스케줄링 (placeholder).

    실제 스케줄러 연결은 workers 모듈에서 cron_expr 를 읽어 등록한다.
    여기서는 설정을 로그로만 남긴다.
    """
    logger.info("auto snapshot scheduled (cron=%s) — register in workers.", cron_expr)


async def cleanup_expired_snapshots() -> int:
    """expiresAt 이 지난 스냅샷의 파일/행을 정리한다. 삭제된 건수 반환."""
    try:
        rows = await prisma.knowledgesnapshot.find_many(  # type: ignore[attr-defined]
            where={"expiresAt": {"lt": _utcnow()}}, take=1000,
        )
    except Exception as exc:
        logger.warning("cleanup_expired query failed: %s", exc)
        return 0

    removed = 0
    for r in rows:
        path = Path(r.storageLocation or _snapshot_path(r.id))
        try:
            if path.exists():
                path.unlink()
        except Exception as exc:
            logger.warning("cleanup unlink failed %s: %s", path, exc)
        try:
            await prisma.knowledgesnapshot.delete(where={"id": r.id})  # type: ignore[attr-defined]
            removed += 1
        except Exception as exc:
            logger.warning("cleanup delete failed %s: %s", r.id, exc)
    return removed


# ─────────────────────────────────────────────────────────────
# 타임라인 / dry-run
# ─────────────────────────────────────────────────────────────
async def diff_timeline_view(
    entity: str, between_dates: tuple[datetime, datetime]
) -> list[dict]:
    """지정 entity 가 두 시점 사이에 어떻게 변했는지 타임라인 생성.

    스냅샷 + 감사 이벤트를 병합해 시간순 리스트로 반환.
    """
    start, end = between_dates
    events: list[dict] = []

    # 1) 스냅샷들에서 해당 entity 추출
    try:
        snap_rows = await prisma.knowledgesnapshot.find_many(  # type: ignore[attr-defined]
            where={"snapshotAt": {"gte": start, "lte": end}},
            order={"snapshotAt": "asc"},
            take=100,
        )
    except Exception:
        snap_rows = []

    for s in snap_rows:
        path = Path(s.storageLocation or _snapshot_path(s.id))
        if not path.exists():
            continue
        try:
            facts = _deserialize_snapshot(path.read_bytes())
        except Exception:
            continue
        matched = [f for f in facts if f.get("entity") == entity]
        if matched:
            events.append({
                "type": "snapshot",
                "at": s.snapshotAt.isoformat() if s.snapshotAt else None,
                "snapshot_id": s.id,
                "fact_count": len(matched),
                "sample_contents": [f.get("content") for f in matched[:3]],
            })

    # 2) audit event 중 해당 entity 관련
    try:
        fact_rows = await prisma.knowledgefact.find_many(
            where={"entity": entity}, take=500,
        )
        fact_ids = [r.id for r in fact_rows]
        if fact_ids:
            audits = await prisma.auditevent.find_many(  # type: ignore[attr-defined]
                where={
                    "targetId": {"in": fact_ids},
                    "occurredAt": {"gte": start, "lte": end},
                },
                order={"occurredAt": "asc"},
                take=1000,
            )
            for a in audits:
                events.append({
                    "type": "audit",
                    "at": a.occurredAt.isoformat() if a.occurredAt else None,
                    "event_type": a.eventType,
                    "target_id": a.targetId,
                    "actor_id": a.actorId,
                })
    except Exception as exc:
        logger.debug("timeline audit fetch skipped: %s", exc)

    events.sort(key=lambda e: e.get("at") or "")
    return events


async def what_if_rollback(snapshot_id: str, fact_ids: list[str]) -> dict:
    """롤백을 실행하지 않고 변경 사항만 미리보기 (dry run)."""
    meta = await get_snapshot(snapshot_id)
    if meta.get("error"):
        return {"error": meta["error"]}
    try:
        data = Path(meta["storage_location"]).read_bytes()
    except Exception as exc:
        logger.warning("what_if_rollback read failed: %s", exc)
        return {"error": "read_failed"}

    snap_facts = _index_by_id(_deserialize_snapshot(data))
    diffs: list[dict] = []
    missing: list[str] = []
    unchanged = 0

    for fid in fact_ids:
        snap = snap_facts.get(fid)
        if not snap:
            missing.append(fid)
            continue
        try:
            current_row = await prisma.knowledgefact.find_unique(where={"id": fid})
        except Exception:
            current_row = None
        if current_row is None:
            diffs.append({"id": fid, "change": "recreate", "from": None, "to": snap})
            continue
        current = _row_to_plain(current_row)
        if _content_hash_of(current) == _content_hash_of(snap) and current.get("status") == snap.get("status"):
            unchanged += 1
            continue
        diffs.append({
            "id": fid,
            "change": "revert",
            "current_content": current.get("content"),
            "snapshot_content": snap.get("content"),
            "current_status": current.get("status"),
            "snapshot_status": snap.get("status"),
        })

    return {
        "snapshot_id": snapshot_id,
        "total_targets": len(fact_ids),
        "will_change": len(diffs),
        "unchanged": unchanged,
        "missing_in_snapshot": missing,
        "diffs": diffs,
    }


__all__ = [
    "create_snapshot",
    "list_snapshots",
    "get_snapshot",
    "restore_snapshot_to_readonly",
    "compare_snapshots",
    "rollback_facts_to_snapshot",
    "schedule_auto_snapshot",
    "cleanup_expired_snapshots",
    "diff_timeline_view",
    "what_if_rollback",
    "_serialize_facts_stream",
    "_deserialize_snapshot",
]
