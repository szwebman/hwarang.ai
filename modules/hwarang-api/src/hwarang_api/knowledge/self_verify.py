"""HLKM A5: 자가 검증 에이전트.

주기적으로 CONFIRMED 사실의 출처를 재확인하고
변경/무효화/출처소실 여부를 판단해 다음 상태로 전이시킨다.

동작:
  1. next_check_at <= now 인 사실을 조회.
  2. verify_fact() 로 출처와 현재 내용을 비교.
  3. 결과에 따라 KnowledgeVerification 기록을 남기고
     - updated : pipeline.ingest_fact 로 새 버전 등록, 기존은 supersede.
     - invalidated : RETRACTED 로 상태 변경.
     - source_gone : 대체 출처 탐색 후 재검증.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from hwarang_api.db import prisma

from .half_life import current_confidence
from .types import KnowledgeFact, KnowledgeStatus, VerificationResult

# 외부 연동 placeholder 모듈 (다른 PR 에서 구현)
from hwarang_api.knowledge.embeddings import embed_text, cosine  # type: ignore
from hwarang_api.knowledge.llm import (  # type: ignore
    llm_check_semantic_equivalence,
    llm_summarize_changes,
)
from hwarang_api.knowledge.web import fetch_source, web_search  # type: ignore

logger = logging.getLogger(__name__)

_SIM_THRESHOLD_UNCHANGED = 0.92
_SIM_THRESHOLD_UPDATED = 0.55


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_fact(row: Any) -> KnowledgeFact:
    """Prisma row → Pydantic KnowledgeFact 변환."""
    return KnowledgeFact(
        id=row.id,
        content=row.content,
        content_hash=row.contentHash,
        domain=row.domain,
        entity=row.entity,
        tags=list(row.tags or []),
        language=row.language,
        valid_from=row.validFrom,
        valid_to=row.validTo,
        created_at=row.createdAt,
        last_verified_at=row.lastVerifiedAt,
        next_check_at=row.nextCheckAt,
        confidence_t0=row.confidenceT0,
        half_life_days=row.halfLifeDays,
        status=KnowledgeStatus(row.status),
        predicted_valid_from=row.predictedValidFrom,
        prediction_confidence=row.predictionConfidence,
        expired_reason=row.expiredReason,
        source=row.source,
        source_url=row.sourceUrl,
    )


# ─────────────────────────────────────────────
# 단일 사실 재검증
# ─────────────────────────────────────────────
async def verify_fact(fact: KnowledgeFact) -> VerificationResult:
    """출처 재인출 + 임베딩 유사도 + LLM 교차 판정.

    반환: VerificationResult(result=unchanged|updated|invalidated|source_gone).
    """
    assert fact.id is not None, "fact.id required"

    if not fact.source_url:
        # 출처 URL 이 없으면 LLM self-consistency 만 수행
        return VerificationResult(
            fact_id=fact.id,
            method="llm_check",
            result="unchanged",
            confidence_delta=0.0,
            notes="source_url missing; skipped refetch",
        )

    try:
        fetched = await fetch_source(fact.source_url)
    except FileNotFoundError:
        return VerificationResult(
            fact_id=fact.id,
            method="source_refetch",
            result="source_gone",
            confidence_delta=-0.3,
            notes="HTTP 404 / unreachable",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_source failed for %s: %s", fact.source_url, exc)
        return VerificationResult(
            fact_id=fact.id,
            method="source_refetch",
            result="source_gone",
            confidence_delta=-0.1,
            notes=f"fetch error: {exc}",
        )

    if not fetched or not fetched.strip():
        return VerificationResult(
            fact_id=fact.id,
            method="source_refetch",
            result="source_gone",
            confidence_delta=-0.2,
            notes="empty body",
        )

    # 임베딩 유사도
    emb_old = await embed_text(fact.content)
    emb_new = await embed_text(fetched)
    sim = cosine(emb_old, emb_new)

    if sim >= _SIM_THRESHOLD_UNCHANGED:
        return VerificationResult(
            fact_id=fact.id,
            method="source_refetch",
            result="unchanged",
            confidence_delta=0.05,
            notes=f"sim={sim:.3f}",
        )

    # 약간이라도 달라졌으면 LLM 으로 의미 변화 판별
    equiv = await llm_check_semantic_equivalence(fact.content, fetched)
    # equiv: {"equivalent": bool, "contradicts": bool, "confidence": float}

    if equiv.get("contradicts"):
        return VerificationResult(
            fact_id=fact.id,
            method="llm_check",
            result="invalidated",
            confidence_delta=-0.5,
            notes=f"contradiction detected (sim={sim:.3f})",
        )

    if equiv.get("equivalent") and sim >= _SIM_THRESHOLD_UPDATED:
        return VerificationResult(
            fact_id=fact.id,
            method="llm_check",
            result="unchanged",
            confidence_delta=0.0,
            notes=f"semantic equivalent (sim={sim:.3f})",
        )

    summary = await llm_summarize_changes(fact.content, fetched)
    return VerificationResult(
        fact_id=fact.id,
        method="source_refetch",
        result="updated",
        confidence_delta=-0.1,
        notes=summary,
        new_content=fetched,
    )


# ─────────────────────────────────────────────
# 대체 출처 탐색
# ─────────────────────────────────────────────
async def find_alternative_source(fact: KnowledgeFact) -> str | None:
    """content 핵심 구절을 웹검색해 신뢰 URL 하나를 반환."""
    snippet = fact.content[:160]
    query = f"{fact.entity or ''} {snippet}".strip()
    try:
        hits = await web_search(query, limit=5)
    except Exception as exc:  # noqa: BLE001
        logger.warning("web_search failed: %s", exc)
        return None

    if not hits:
        return None

    # 원 출처 도메인 우선
    preferred = None
    if fact.source_url:
        try:
            from urllib.parse import urlparse

            host = urlparse(fact.source_url).netloc
            preferred = next((h["url"] for h in hits if host and host in h.get("url", "")), None)
        except Exception:  # noqa: BLE001
            preferred = None

    return preferred or hits[0].get("url")


# ─────────────────────────────────────────────
# 노후 사실 탐지
# ─────────────────────────────────────────────
async def detect_aging_facts(confidence_threshold: float = 0.5) -> list[str]:
    """현재 신뢰도가 임계치 이하인 사실 ID 목록."""
    rows = await prisma.knowledgefact.find_many(
        where={"status": KnowledgeStatus.CONFIRMED.value},
        take=2000,
        order={"lastVerifiedAt": "asc"},
    )
    aged: list[str] = []
    now = _utcnow()
    for row in rows:
        fact = _row_to_fact(row)
        if current_confidence(fact, now) < confidence_threshold:
            aged.append(row.id)
    return aged


# ─────────────────────────────────────────────
# 관리자 알림
# ─────────────────────────────────────────────
async def notify_admin_of_changes(changes: list[dict]) -> None:
    """중요한 상태 변경을 관리자에게 알림 (logging + TODO: Slack/email)."""
    if not changes:
        return
    for c in changes:
        logger.warning("[HLKM admin] fact=%s result=%s notes=%s", c.get("fact_id"), c.get("result"), c.get("notes"))


# ─────────────────────────────────────────────
# 일일 배치
# ─────────────────────────────────────────────
async def run_daily_verification(limit: int = 100) -> dict:
    """next_check_at 이 도래한 사실들을 재검증."""
    from .pipeline import ingest_fact  # 순환 import 방지

    now = _utcnow()
    rows = await prisma.knowledgefact.find_many(
        where={
            "status": KnowledgeStatus.CONFIRMED.value,
            "nextCheckAt": {"lte": now},
        },
        take=limit,
        order={"nextCheckAt": "asc"},
    )

    stats = {"total": len(rows), "unchanged": 0, "updated": 0, "invalidated": 0, "source_gone": 0}
    admin_changes: list[dict] = []

    for row in rows:
        fact = _row_to_fact(row)
        result = await verify_fact(fact)

        await prisma.knowledgeverification.create(
            data={
                "factId": fact.id,
                "method": result.method,
                "result": result.result,
                "confidenceDelta": result.confidence_delta,
                "notes": result.notes or "",
            }
        )

        if result.result == "unchanged":
            stats["unchanged"] += 1
            await prisma.knowledgefact.update(
                where={"id": fact.id},
                data={"lastVerifiedAt": now},
            )
        elif result.result == "updated":
            stats["updated"] += 1
            if result.new_content:
                # 기존 fact 를 supersede + 새 버전 등록
                new_fact = fact.model_copy(update={
                    "id": None,
                    "content": result.new_content,
                    "valid_from": now,
                    "last_verified_at": now,
                    "supersedes_id": fact.id,
                })
                try:
                    await ingest_fact(new_fact)
                    await prisma.knowledgefact.update(
                        where={"id": fact.id},
                        data={"validTo": now},
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error("ingest_fact failed during update: %s", exc)
            admin_changes.append({"fact_id": fact.id, "result": "updated", "notes": result.notes})
        elif result.result == "invalidated":
            stats["invalidated"] += 1
            await prisma.knowledgefact.update(
                where={"id": fact.id},
                data={
                    "status": KnowledgeStatus.RETRACTED.value,
                    "expiredReason": result.notes or "invalidated by self-verify",
                    "validTo": now,
                },
            )
            admin_changes.append({"fact_id": fact.id, "result": "invalidated", "notes": result.notes})
        elif result.result == "source_gone":
            stats["source_gone"] += 1
            alt = await find_alternative_source(fact)
            if alt:
                fact_alt = fact.model_copy(update={"source_url": alt})
                alt_result = await verify_fact(fact_alt)
                await prisma.knowledgeverification.create(
                    data={
                        "factId": fact.id,
                        "method": "cross_source",
                        "result": alt_result.result,
                        "confidenceDelta": alt_result.confidence_delta,
                        "notes": f"alt={alt}; {alt_result.notes or ''}",
                    }
                )
                if alt_result.result == "unchanged":
                    await prisma.knowledgefact.update(
                        where={"id": fact.id},
                        data={"sourceUrl": alt, "lastVerifiedAt": now},
                    )
            admin_changes.append({"fact_id": fact.id, "result": "source_gone", "notes": result.notes})

    await notify_admin_of_changes(admin_changes)
    logger.info("run_daily_verification done: %s", stats)
    return stats


__all__ = [
    "run_daily_verification",
    "verify_fact",
    "find_alternative_source",
    "notify_admin_of_changes",
    "detect_aging_facts",
]
