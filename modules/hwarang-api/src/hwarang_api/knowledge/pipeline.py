"""HLKM A4 - Ingestion Pipeline.

신규 팩트 수집 파이프라인:

    hash → dup check → embed → entity resolve → conflict scan →
    supersede/dispute → schedule next check → insert

배치 큐레이션, 지식 공백 기록, 대화-트리거 수집도 여기서 담당.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from hwarang_api.db import prisma
from hwarang_api.knowledge.contradiction import (
    record_conflict,
    scan_new_fact_for_conflicts,
)
from hwarang_api.knowledge.embeddings import embed_text
from hwarang_api.knowledge.entity import resolve_entity
from hwarang_api.knowledge.half_life import next_check_time
from hwarang_api.knowledge.types import (
    ContradictionReport,
    KnowledgeFact,
    KnowledgeStatus,
    KnowledgeVisibility,
)

# 대화-기반 수집을 위한 단순 휴리스틱 (한국어 기준).
_FACT_LIKE_PATTERNS = [
    re.compile(r"(?:이다|입니다|였다|한다|된다)\.?$"),
    re.compile(r"\d{4}년"),
    re.compile(r"(?:법|규정|조항|시행|발효)"),
    re.compile(r"(?:최저시급|금리|세율|규제)"),
]
_POSITIVE_FEEDBACK = {"좋아요", "맞아요", "정확해", "thanks", "감사", "👍"}


def _normalize(text: str) -> str:
    """중복 감지용 정규화 — 공백 축약 + 소문자."""
    return re.sub(r"\s+", " ", text.strip()).lower()


def _content_hash(text: str) -> str:
    return hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()


def _floats_to_hex(vec: list[float] | None) -> str | None:
    if not vec:
        return None
    try:
        return struct.pack(f"<{len(vec)}f", *vec).hex()
    except Exception:
        return None


async def ingest_fact(fact: KnowledgeFact, dry_run: bool = False) -> dict:
    """신규 팩트 수집 파이프라인 본체.

    반환: `{fact_id, action, conflicts}` — action ∈ {inserted, superseded, disputed, duplicate}.
    """
    # 1) content hash
    if not fact.content_hash:
        fact.content_hash = _content_hash(fact.content)

    # 2) 중복 체크
    existing = await prisma.knowledgefact.find_first(
        where={"contentHash": fact.content_hash}
    )
    if existing:
        return {"fact_id": existing.id, "action": "duplicate", "conflicts": []}

    # 3) 임베딩
    if not fact.embedding:
        fact.embedding = await embed_text(fact.content)

    # 4) 엔티티 해결
    if not fact.entity:
        fact.entity = await resolve_entity(fact.content, domain=fact.domain)

    # 5) 모순 스캔
    reports = await scan_new_fact_for_conflicts(fact, top_k=5)

    action = "inserted"
    superseded_target_id: str | None = None

    # 6) 모순 처리
    if reports:
        # reasoning 프리픽스에서 상대 fact id 를 복원.
        top_report = reports[0]
        other_id = _extract_other_id(top_report.reasoning)
        other = (
            await prisma.knowledgefact.find_unique(where={"id": other_id})
            if other_id
            else None
        )

        if other and other.entity == fact.entity and fact.confidence_t0 >= float(other.confidenceT0) and fact.valid_from >= other.validFrom:
            # 같은 엔티티 + 더 최신/동등 신뢰 → 이전 팩트를 supersede.
            superseded_target_id = other.id
            action = "superseded"
        else:
            action = "disputed"
            fact.status = KnowledgeStatus.DISPUTED

    # 7) 다음 재검증 스케줄
    if not fact.last_verified_at:
        fact.last_verified_at = datetime.now(timezone.utc)
    fact.next_check_at = next_check_time(fact)

    if dry_run:
        return {
            "fact_id": None,
            "action": action,
            "conflicts": [r.model_dump() for r in reports],
        }

    # 8) DB insert
    created = await prisma.knowledgefact.create(
        data={
            "content": fact.content,
            "contentHash": fact.content_hash,
            "embeddingHex": _floats_to_hex(fact.embedding),
            "domain": fact.domain,
            "entity": fact.entity,
            "tags": fact.tags,
            "language": fact.language,
            "validFrom": fact.valid_from,
            "validTo": fact.valid_to,
            "lastVerifiedAt": fact.last_verified_at or datetime.now(timezone.utc),
            "nextCheckAt": fact.next_check_at,
            "confidenceT0": fact.confidence_t0,
            "halfLifeDays": fact.half_life_days,
            "status": fact.status.value,
            "predictedValidFrom": fact.predicted_valid_from,
            "predictionConfidence": fact.prediction_confidence,
            "source": fact.source,
            "sourceUrl": fact.source_url,
            "sourceType": fact.source_type,
            "visibility": fact.visibility.value,
            "ownerUserId": fact.owner_user_id,
            "supersedesId": superseded_target_id,
            "contributedBy": fact.contributed_by,
        }
    )

    # 9) 후처리: supersede 시 이전 팩트 validTo 갱신 + 모순 기록
    if superseded_target_id:
        cutoff = fact.valid_from - timedelta(days=1)
        await prisma.knowledgefact.update(
            where={"id": superseded_target_id},
            data={"validTo": cutoff, "status": KnowledgeStatus.EXPIRED.value},
        )
    elif action == "disputed":
        for rep in reports:
            other_id = _extract_other_id(rep.reasoning)
            if other_id:
                await record_conflict(created.id, other_id, rep)

    return {
        "fact_id": created.id,
        "action": action,
        "conflicts": [r.model_dump() for r in reports],
    }


def _extract_other_id(reasoning: str) -> str | None:
    """scan_new_fact_for_conflicts 가 reasoning 앞에 붙이는 `[vs ID]` 패턴을 복원."""
    m = re.match(r"\[vs ([^\]]+)\]", reasoning)
    return m.group(1) if m else None


async def curate_batch(
    pending_file_path: str, auto_approve_threshold: float = 0.9
) -> dict:
    """JSONL 로 쌓인 대기 팩트를 큐레이션.

    품질 점수가 임계치 이상이면 자동 수집, 아니면 관리자 검토 큐에 쌓는다.
    """
    path = Path(pending_file_path)
    if not path.exists():
        return {"auto_approved": 0, "needs_review": 0, "rejected": 0}

    auto = 0
    review: list[dict] = []
    rejected = 0

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
                fact = KnowledgeFact(**raw)
            except Exception:
                rejected += 1
                continue

            length_score = min(len(fact.content) / 500.0, 1.0)
            source_score = 0.3 if fact.source_url or fact.source_type in {"official", "crawl"} else 0.0
            quality = length_score + source_score + fact.confidence_t0
            quality = min(quality / 2.3, 1.0)  # 대략 0~1 정규화

            if quality < 0.3:
                rejected += 1
                continue

            if quality >= auto_approve_threshold:
                try:
                    await ingest_fact(fact)
                    auto += 1
                except Exception:
                    rejected += 1
            else:
                review.append({"fact": fact.model_dump(mode="json"), "score": quality})

    # 검토 필요 목록은 관리자용 파일로 따로 떨어뜨린다.
    if review:
        review_path = path.with_suffix(".review.jsonl")
        with review_path.open("w", encoding="utf-8") as rf:
            for item in review:
                rf.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")

    return {
        "auto_approved": auto,
        "needs_review": len(review),
        "rejected": rejected,
        "review_file": str(review_path) if review else None,
    }


async def record_knowledge_gap(topic: str) -> None:
    """자주 실패하는 질의 주제를 집계한다 (upsert + 카운트 증가)."""
    now = datetime.now(timezone.utc)
    existing = await prisma.knowledgegap.find_unique(where={"topic": topic})
    if existing:
        await prisma.knowledgegap.update(
            where={"topic": topic},
            data={
                "failureCount": existing.failureCount + 1,
                "lastSeenAt": now,
            },
        )
    else:
        await prisma.knowledgegap.create(
            data={
                "topic": topic,
                "failureCount": 1,
                "firstSeenAt": now,
                "lastSeenAt": now,
                "status": "open",
            }
        )


async def trigger_ingestion_from_conversation(
    message_content: str, user_id: str, domain: str
) -> list[str]:
    """대화 중 사용자 긍정 피드백이 달린 사실형 발화를 사적 팩트로 수집."""
    text = message_content.strip()
    if len(text) < 12:
        return []

    has_positive = any(tok in text for tok in _POSITIVE_FEEDBACK)
    fact_like = any(p.search(text) for p in _FACT_LIKE_PATTERNS)
    if not (has_positive or fact_like):
        return []

    # 피드백 토큰은 제거한 원문을 저장.
    cleaned = text
    for tok in _POSITIVE_FEEDBACK:
        cleaned = cleaned.replace(tok, "").strip()
    if len(cleaned) < 12:
        return []

    fact = KnowledgeFact(
        content=cleaned,
        domain=domain,
        source="conversation",
        source_type="user",
        valid_from=datetime.now(timezone.utc),
        visibility=KnowledgeVisibility.PRIVATE,
        owner_user_id=user_id,
        contributed_by=user_id,
        confidence_t0=0.6,  # 대화 기반은 보수적으로
    )
    result = await ingest_fact(fact)
    return [result["fact_id"]] if result.get("fact_id") else []
