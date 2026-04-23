"""HLKM TAL v3 ③ - Retraction Tracking.

정정/철회(retraction) 자동 감지 + 기존 사실 무효화 모듈.

동작:
  1. CONFIRMED 상태 사실의 원출처(source_url)를 주기적으로 재방문.
  2. 한/영 정정 패턴(RETRACTION_PATTERNS) 매칭으로 1차 감지.
  3. 감지 시 RetractionEvent 기록 + KnowledgeFact.retracted=True 로 플래그.
  4. 원본 팩트가 철회되면 ProvenanceEdge 로 연결된 복사본까지 cascading 처리.
  5. 의료 논문은 Retraction Watch, 한국 뉴스는 언론진흥재단 DB (placeholder) 를
     외부 조회해 보강.

관리자는 `verify_retraction` 으로 자동 감지 결과를 최종 승인/반려한다.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma

from .llm import llm_check_contradiction, llm_check_semantic_equivalence  # noqa: F401
from .types import KnowledgeFact, KnowledgeStatus
from .web import fetch_source

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 정정 패턴 (한/영)
# ─────────────────────────────────────────────
RETRACTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"정정\s*보도"),
    re.compile(r"\[바로잡습니다\]"),
    re.compile(r"\[정정\]"),
    re.compile(r"앞선\s*보도.*오보"),
    re.compile(r"앞서\s*보도.*정정"),
    re.compile(r"Retraction[:\s]", re.IGNORECASE),
    re.compile(r"Correction[:\s]", re.IGNORECASE),
    re.compile(
        r"(?:This article|The (?:previous|earlier) article).*corrected",
        re.IGNORECASE,
    ),
    re.compile(r"내용이?\s*(?:수정|정정)\s*되었습니다"),
    re.compile(r"사실과\s*다른\s*내용"),
    re.compile(r"오보[를를]\s*(?:정정|바로잡)"),
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_fact(row: Any) -> KnowledgeFact:
    """Prisma row → Pydantic KnowledgeFact."""
    return KnowledgeFact(
        id=row.id,
        content=row.content,
        content_hash=getattr(row, "contentHash", None),
        domain=row.domain,
        entity=row.entity,
        tags=list(getattr(row, "tags", []) or []),
        language=getattr(row, "language", "ko"),
        valid_from=row.validFrom,
        valid_to=row.validTo,
        created_at=row.createdAt,
        last_verified_at=getattr(row, "lastVerifiedAt", None),
        next_check_at=getattr(row, "nextCheckAt", None),
        confidence_t0=float(getattr(row, "confidenceT0", 1.0)),
        half_life_days=getattr(row, "halfLifeDays", None),
        status=KnowledgeStatus(row.status),
        source=row.source,
        source_url=row.sourceUrl,
    )


def _match_retraction(text: str) -> list[str]:
    """본문에서 매칭된 정정 패턴 리스트를 반환."""
    if not text:
        return []
    matches: list[str] = []
    for pat in RETRACTION_PATTERNS:
        if pat.search(text):
            matches.append(pat.pattern)
    return matches


def _extract_excerpt(text: str, max_chars: int = 400) -> str:
    """정정 표현 주변 발췌문."""
    if not text:
        return ""
    for pat in RETRACTION_PATTERNS:
        m = pat.search(text)
        if m:
            start = max(0, m.start() - 80)
            end = min(len(text), m.end() + 320)
            return text[start:end].strip()
    return text[:max_chars].strip()


# ─────────────────────────────────────────────
# 감지
# ─────────────────────────────────────────────
async def scan_source_for_retraction(fact_id: str) -> dict | None:
    """사실의 source_url 을 재방문해 정정 표현을 탐지.

    반환: 감지 시 dict, 그 외 None.
      {"detected": bool, "patterns_matched": [...], "excerpt": str, "retracted_at": datetime}
    """
    row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if not row or not row.sourceUrl:
        return None

    try:
        fetched = await fetch_source(row.sourceUrl)
    except Exception as exc:  # noqa: BLE001
        logger.warning("retraction fetch failed id=%s url=%s err=%s",
                       fact_id, row.sourceUrl, exc)
        return None

    text = ""
    if isinstance(fetched, dict):
        text = (fetched.get("content") or "").strip()
    elif isinstance(fetched, str):
        text = fetched.strip()
    if not text:
        return None

    patterns = _match_retraction(text)
    if not patterns:
        return None

    return {
        "detected": True,
        "patterns_matched": patterns,
        "excerpt": _extract_excerpt(text),
        "retracted_at": _utcnow(),
    }


# ─────────────────────────────────────────────
# 기록
# ─────────────────────────────────────────────
async def record_retraction(
    fact_id: str,
    retracted_by: str,
    retraction_url: str | None,
    retraction_type: str,
    reason: str,
    detected_by: str = "auto",
) -> str:
    """RetractionEvent insert + KnowledgeFact 무효화.

    - KnowledgeFact: retracted=True, retractedAt=now, retractionReason/Source 세팅
    - status=RETRACTED 로 전이
    - 원본인 경우 복사본(cascade)은 별도 함수에서 선택적으로 수행
    반환: retraction_event_id
    """
    now = _utcnow()
    event = await prisma.retractionevent.create(
        data={
            "factId": fact_id,
            "retractedBy": retracted_by,
            "retractionUrl": retraction_url,
            "retractionDate": now,
            "retractionType": retraction_type,
            "reason": reason[:4000],
            "detectedBy": detected_by,
        }
    )

    try:
        await prisma.knowledgefact.update(
            where={"id": fact_id},
            data={
                "retracted": True,
                "retractedAt": now,
                "retractionReason": reason[:2000],
                "retractionSource": retraction_url or retracted_by,
                "status": KnowledgeStatus.RETRACTED.value,
                "validTo": now,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("fact update failed after retraction id=%s: %s", fact_id, exc)

    logger.info(
        "[retraction] fact=%s type=%s detected_by=%s event=%s",
        fact_id, retraction_type, detected_by, event.id,
    )
    return event.id


async def verify_retraction(
    retraction_id: str, verifier_user_id: str, is_valid: bool
) -> None:
    """관리자가 자동 감지된 정정을 확인.

    is_valid=True  → verified 플래그 확정
    is_valid=False → retracted=False 로 되돌리고 status=CONFIRMED 복구
    """
    now = _utcnow()
    event = await prisma.retractionevent.update(
        where={"id": retraction_id},
        data={
            "verified": True,
            "verifiedBy": verifier_user_id,
            "verifiedAt": now,
        },
    )

    if not is_valid and event is not None:
        try:
            await prisma.knowledgefact.update(
                where={"id": event.factId},
                data={
                    "retracted": False,
                    "retractedAt": None,
                    "retractionReason": None,
                    "retractionSource": None,
                    "status": KnowledgeStatus.CONFIRMED.value,
                    "validTo": None,
                },
            )
            logger.info("[retraction] rolled back fact=%s by admin=%s",
                        event.factId, verifier_user_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("rollback failed for retraction=%s: %s", retraction_id, exc)


# ─────────────────────────────────────────────
# Cascade (원본 정정 → 복사본 일괄 처리)
# ─────────────────────────────────────────────
async def cascade_retraction_to_copies(
    original_fact_id: str, reason_suffix: str = ""
) -> int:
    """ProvenanceEdge 에서 targetFactId=original 인 복사본을 모두 retract.

    단, 복사본의 stance 가 INTERPRETATION/OPINION 이면 제외 — 원본 사실 정정이
    해석/의견까지 무효화하지는 않는다.
    반환: 실제 retract 된 복사본 수.
    """
    try:
        edges = await prisma.provenanceedge.find_many(
            where={"targetFactId": original_fact_id}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("provenance lookup failed for %s: %s", original_fact_id, exc)
        return 0

    if not edges:
        return 0

    count = 0
    for edge in edges:
        copy_id = edge.sourceFactId
        try:
            copy = await prisma.knowledgefact.find_unique(where={"id": copy_id})
        except Exception:  # noqa: BLE001
            continue
        if not copy or copy.retracted:
            continue

        stance = getattr(copy, "stance", None)
        if stance in ("INTERPRETATION", "OPINION"):
            logger.debug("skip cascade: %s stance=%s", copy_id, stance)
            continue

        reason = (
            f"cascaded from original fact {original_fact_id}"
            + (f"; {reason_suffix}" if reason_suffix else "")
        )
        try:
            await record_retraction(
                fact_id=copy_id,
                retracted_by=f"cascade:{original_fact_id}",
                retraction_url=None,
                retraction_type="cascade",
                reason=reason,
                detected_by="auto",
            )
            count += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("cascade retract failed for copy=%s: %s", copy_id, exc)

    logger.info("[retraction] cascaded %d copies of %s", count, original_fact_id)
    return count


# ─────────────────────────────────────────────
# 일일 스캔 배치
# ─────────────────────────────────────────────
async def run_retraction_scan(batch: int = 100, older_than_days: int = 7) -> dict:
    """older_than_days 이전에 기록된 미정정 사실 샘플을 스캔.

    감지된 사실은 record_retraction 으로 자동 등록 (detected_by='auto').
    """
    now = _utcnow()
    cutoff = now - timedelta(days=older_than_days)

    try:
        rows = await prisma.knowledgefact.find_many(
            where={
                "retracted": False,
                "status": KnowledgeStatus.CONFIRMED.value,
                "createdAt": {"lte": cutoff},
            },
            take=batch,
            order={"createdAt": "asc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("retraction scan query failed: %s", exc)
        return {"scanned": 0, "detected": 0, "errors": 1}

    stats = {"scanned": 0, "detected": 0, "cascaded": 0, "errors": 0}
    for row in rows:
        stats["scanned"] += 1
        try:
            result = await scan_source_for_retraction(row.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scan failed id=%s: %s", row.id, exc)
            stats["errors"] += 1
            continue

        if not result or not result.get("detected"):
            continue

        try:
            event_id = await record_retraction(
                fact_id=row.id,
                retracted_by=row.sourceUrl or row.source or "auto-scan",
                retraction_url=row.sourceUrl,
                retraction_type="correction",
                reason="자동 감지: " + "; ".join(result["patterns_matched"])
                       + "\n발췌: " + (result.get("excerpt") or ""),
                detected_by="auto",
            )
            stats["detected"] += 1
            # 복사본까지 cascade
            cascaded = await cascade_retraction_to_copies(
                row.id, reason_suffix=f"event={event_id}"
            )
            stats["cascaded"] += cascaded
        except Exception as exc:  # noqa: BLE001
            logger.error("record_retraction failed id=%s: %s", row.id, exc)
            stats["errors"] += 1

    logger.info("run_retraction_scan done: %s", stats)
    return stats


# ─────────────────────────────────────────────
# 조회
# ─────────────────────────────────────────────
async def list_pending_retractions(limit: int = 50) -> list[dict]:
    """verified=False 인 정정 이벤트 목록 (관리자 검토 대기)."""
    try:
        rows = await prisma.retractionevent.find_many(
            where={"verified": False},
            take=limit,
            order={"detectedAt": "desc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_pending_retractions failed: %s", exc)
        return []

    return [
        {
            "id": r.id,
            "fact_id": r.factId,
            "retracted_by": r.retractedBy,
            "retraction_url": r.retractionUrl,
            "retraction_type": r.retractionType,
            "reason": r.reason,
            "detected_at": r.detectedAt,
            "detected_by": r.detectedBy,
        }
        for r in rows
    ]


async def list_retracted_facts(
    domain: str | None = None, limit: int = 100
) -> list[dict]:
    """retracted=True 인 사실 목록."""
    where: dict[str, Any] = {"retracted": True}
    if domain:
        where["domain"] = domain
    try:
        rows = await prisma.knowledgefact.find_many(
            where=where, take=limit, order={"retractedAt": "desc"}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_retracted_facts failed: %s", exc)
        return []

    return [
        {
            "id": r.id,
            "content": r.content[:200],
            "domain": r.domain,
            "source": r.source,
            "retracted_at": r.retractedAt,
            "retraction_reason": r.retractionReason,
            "retraction_source": r.retractionSource,
        }
        for r in rows
    ]


async def undo_retraction(fact_id: str, admin_user_id: str, reason: str) -> None:
    """잘못된 정정 되돌리기. retracted=False, status=CONFIRMED 로 복귀."""
    now = _utcnow()
    try:
        await prisma.knowledgefact.update(
            where={"id": fact_id},
            data={
                "retracted": False,
                "retractedAt": None,
                "retractionReason": None,
                "retractionSource": None,
                "status": KnowledgeStatus.CONFIRMED.value,
                "validTo": None,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("undo_retraction fact update failed id=%s: %s", fact_id, exc)
        return

    try:
        await prisma.retractionevent.create(
            data={
                "factId": fact_id,
                "retractedBy": f"admin:{admin_user_id}",
                "retractionUrl": None,
                "retractionDate": now,
                "retractionType": "undo",
                "reason": f"UNDO by {admin_user_id}: {reason}"[:4000],
                "detectedBy": "manual",
                "verified": True,
                "verifiedBy": admin_user_id,
                "verifiedAt": now,
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("undo audit insert failed: %s", exc)


# ─────────────────────────────────────────────
# 외부 DB 연동 (placeholder)
# ─────────────────────────────────────────────
async def query_retraction_watch(doi: str) -> dict | None:
    """Retraction Watch (https://retractionwatch.com/) 조회.

    실제 API 계약이 공개돼 있지 않아 현재는 placeholder. httpx 가 없거나
    네트워크 장애 시 None 을 반환한다.
    """
    if not doi:
        return None
    try:
        import httpx  # type: ignore
    except Exception:
        return None

    url = f"https://api.labs.crossref.org/works/{doi}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            msg = data.get("message") if isinstance(data, dict) else None
            if not isinstance(msg, dict):
                return None
            if "retraction" in (msg.get("update-policy") or "").lower() or msg.get("update-to"):
                return {
                    "doi": doi,
                    "retracted": True,
                    "reason": msg.get("update-to") or "crossref: update-policy=retraction",
                    "source": "crossref_labs",
                }
    except Exception as exc:  # noqa: BLE001
        logger.debug("retraction_watch query failed doi=%s err=%s", doi, exc)
    return None


async def query_press_correction_db(article_url: str) -> dict | None:
    """한국언론진흥재단 오보 DB (추상 placeholder).

    공식 API 미확정이라 현재는 항상 None. 실제 연동 시 이 함수 내부만 교체.
    """
    if not article_url:
        return None
    logger.debug("press_correction_db (stub) checked for %s", article_url)
    return None


__all__ = [
    "RETRACTION_PATTERNS",
    "scan_source_for_retraction",
    "record_retraction",
    "verify_retraction",
    "cascade_retraction_to_copies",
    "run_retraction_scan",
    "list_pending_retractions",
    "list_retracted_facts",
    "undo_retraction",
    "query_retraction_watch",
    "query_press_correction_db",
]
