"""HLKM B3 - 3-Layer Contradiction Detector.

세 단계 파이프라인으로 모순 감지 비용을 낮춘다.

    L1: 임베딩 유사도 (빠른 제외 필터)
    L2: 규칙 기반 — 엔티티/시간 겹침 + 숫자/날짜 차이
    L3: LLM — L1/L2 가 잠재 모순을 시사할 때만 호출

최종 리포트는 세 신호의 가중 합으로 신뢰도를 계산한다.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Literal

from hwarang_api.db import prisma
from hwarang_api.knowledge.embeddings import embed_text
from hwarang_api.knowledge.llm import llm_check_contradiction
from hwarang_api.knowledge.types import (
    ContradictionReport,
    KnowledgeFact,
    KnowledgeRelation,
)

# 임베딩 유사도 최소 임계치 — 이하이면 주제 자체가 다르다고 보고 조기 종료.
_SIM_THRESHOLD = 0.4
# L2 규칙층에서 숫자/날짜 차이를 판단하기 위한 정규식.
_NUMBER_RE = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)")
_DATE_RE = re.compile(r"\b(\d{4})[-/.](\d{1,2})(?:[-/.](\d{1,2}))?\b")


def _cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _ranges_overlap(
    a_from: datetime,
    a_to: datetime | None,
    b_from: datetime,
    b_to: datetime | None,
) -> bool:
    """두 유효기간이 겹치는가."""
    a_end = a_to or datetime.max.replace(tzinfo=timezone.utc)
    b_end = b_to or datetime.max.replace(tzinfo=timezone.utc)
    return a_from <= b_end and b_from <= a_end


def _extract_numbers(text: str) -> set[str]:
    return {m.group(1).replace(",", "") for m in _NUMBER_RE.finditer(text)}


def _extract_dates(text: str) -> set[tuple[str, str, str]]:
    return {(m.group(1), m.group(2), m.group(3) or "") for m in _DATE_RE.finditer(text)}


async def detect_contradiction(
    fact_a: KnowledgeFact, fact_b: KnowledgeFact
) -> ContradictionReport:
    """두 팩트 사이의 모순 감지.

    3층 신호를 종합해 `ContradictionReport` 를 생성한다.
    """
    # L1: 임베딩 유사도
    a_vec = fact_a.embedding or await embed_text(fact_a.content)
    b_vec = fact_b.embedding or await embed_text(fact_b.content)
    sim = _cosine(a_vec, b_vec)

    if sim < _SIM_THRESHOLD:
        return ContradictionReport(
            is_contradiction=False,
            confidence=0.0,
            reasoning=f"임베딩 유사도 {sim:.2f} < {_SIM_THRESHOLD} — 관련 없는 주제로 판단.",
        )

    # L2: 규칙 기반
    same_entity = bool(
        fact_a.entity and fact_b.entity and fact_a.entity == fact_b.entity
    )
    overlap = _ranges_overlap(
        fact_a.valid_from, fact_a.valid_to, fact_b.valid_from, fact_b.valid_to
    )
    nums_a = _extract_numbers(fact_a.content)
    nums_b = _extract_numbers(fact_b.content)
    shared_nums = nums_a & nums_b
    differing_nums = (nums_a | nums_b) - shared_nums
    dates_a = _extract_dates(fact_a.content)
    dates_b = _extract_dates(fact_b.content)
    differing_dates = (dates_a ^ dates_b)

    rule_signal = 0.0
    rule_notes: list[str] = []
    if same_entity:
        rule_signal += 0.35
        rule_notes.append("동일 엔티티")
    if overlap:
        rule_signal += 0.2
        rule_notes.append("유효기간 겹침")
    if differing_nums and (nums_a and nums_b):
        rule_signal += 0.25
        rule_notes.append(f"숫자 차이: {sorted(differing_nums)[:3]}")
    if differing_dates:
        rule_signal += 0.2
        rule_notes.append("날짜 차이 존재")
    rule_signal = min(rule_signal, 1.0)

    # 잠재적 모순 조짐이 약하면 LLM 은 건너뛴다.
    if rule_signal < 0.3:
        return ContradictionReport(
            is_contradiction=False,
            confidence=sim * 0.5,
            reasoning="유사하나 규칙층 신호 약함. " + "; ".join(rule_notes),
        )

    # L3: LLM
    try:
        is_conflict, llm_reason = await llm_check_contradiction(fact_a, fact_b)
    except Exception as exc:  # pragma: no cover — LLM 오류 시 규칙층으로 폴백
        is_conflict = rule_signal >= 0.6
        llm_reason = f"LLM 호출 실패 ({exc}); 규칙층 결정."

    # 최종 신뢰도 = 0.3*sim + 0.3*rule + 0.4*llm_bool
    llm_weight = 1.0 if is_conflict else 0.0
    final_conf = 0.3 * sim + 0.3 * rule_signal + 0.4 * llm_weight
    final_conf = min(max(final_conf, 0.0), 1.0)

    resolution_hint: str | None = None
    if is_conflict:
        if fact_a.valid_from > fact_b.valid_from:
            resolution_hint = "A 가 더 최신 → A 우선 검토"
        elif fact_b.valid_from > fact_a.valid_from:
            resolution_hint = "B 가 더 최신 → B 우선 검토"
        else:
            resolution_hint = "발효일 동일 → 출처 신뢰도로 판단"

    reasoning = (
        f"sim={sim:.2f}, rule={rule_signal:.2f} ({'; '.join(rule_notes)}). "
        f"LLM: {llm_reason}"
    )
    return ContradictionReport(
        is_contradiction=is_conflict,
        confidence=final_conf,
        reasoning=reasoning,
        resolution_hint=resolution_hint,
    )


async def scan_new_fact_for_conflicts(
    new_fact: KnowledgeFact, top_k: int = 5
) -> list[ContradictionReport]:
    """신규 팩트에 대해 유사 기존 팩트 top_k 를 뽑아 모순 판정."""
    candidates_where: dict = {"status": {"in": ["CONFIRMED", "PENDING"]}}
    if new_fact.entity:
        candidates_where = {"OR": [{"entity": new_fact.entity}, {"domain": new_fact.domain}]}

    rows = await prisma.knowledgefact.find_many(where=candidates_where, take=top_k * 4)
    if not rows:
        return []

    new_vec = new_fact.embedding or await embed_text(new_fact.content)

    scored: list[tuple[float, KnowledgeFact]] = []
    for row in rows:
        if row.id == new_fact.id:
            continue
        emb_hex = getattr(row, "embeddingHex", None)
        other_vec = _hex_to_floats(emb_hex)
        sim = _cosine(new_vec, other_vec) if other_vec else 0.0
        other = KnowledgeFact(
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
            confidence_t0=float(row.confidenceT0),
            half_life_days=row.halfLifeDays,
            status=row.status,
            source=row.source,
            source_url=row.sourceUrl,
            source_type=row.sourceType,
            visibility=row.visibility,
            owner_user_id=row.ownerUserId,
        )
        scored.append((sim, other))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [f for _, f in scored[:top_k]]

    reports: list[ContradictionReport] = []
    for other in top:
        report = await detect_contradiction(new_fact, other)
        if report.is_contradiction:
            # 상대 fact id 를 reasoning 앞에 끼워 호출측이 추적 가능하게 함.
            report = report.model_copy(
                update={"reasoning": f"[vs {other.id}] " + report.reasoning}
            )
            reports.append(report)
    return reports


async def explain_conflict(fact_a_id: str, fact_b_id: str) -> str:
    """사람이 읽기 쉬운 모순 설명 문자열."""
    a = await prisma.knowledgefact.find_unique(where={"id": fact_a_id})
    b = await prisma.knowledgefact.find_unique(where={"id": fact_b_id})
    if not a or not b:
        return "해당 팩트를 찾을 수 없습니다."

    newer, older = (a, b) if a.validFrom >= b.validFrom else (b, a)
    return (
        f"A (출처 {a.source}, {a.validFrom.date()}) vs "
        f"B (출처 {b.source}, {b.validFrom.date()}). "
        f"{'A' if newer is a else 'B'} 가 더 최신이며, "
        f"{newer.source} 기준으로 업데이트 검토가 필요합니다. "
        f"내용 요약 — A: {a.content[:80]}… / B: {b.content[:80]}…"
    )


async def record_conflict(
    fact_a_id: str, fact_b_id: str, report: ContradictionReport
) -> str:
    """KnowledgeConflict 레코드 + CONTRADICTS 엣지를 함께 생성."""
    conflict = await prisma.knowledgeconflict.create(
        data={
            "factAId": fact_a_id,
            "factBId": fact_b_id,
            "resolutionState": "open",
            "resolutionNote": report.reasoning[:1000],
        }
    )
    # upsert 비슷하게 — 중복 엣지는 unique([from,to,relation]) 로 실패할 수 있음.
    try:
        await prisma.knowledgeedge.create(
            data={
                "fromFactId": fact_a_id,
                "toFactId": fact_b_id,
                "relationType": KnowledgeRelation.CONTRADICTS.value,
                "strength": report.confidence,
                "evidence": report.reasoning[:1000],
                "verifiedBy": "ai",
            }
        )
    except Exception:
        pass
    return conflict.id


async def resolve_conflict(
    conflict_id: str,
    resolution: Literal["resolved_A", "resolved_B", "coexist", "escalated"],
    resolver_user_id: str,
    note: str,
) -> None:
    """관리자가 내린 모순 해결 결과를 기록한다."""
    await prisma.knowledgeconflict.update(
        where={"id": conflict_id},
        data={
            "resolutionState": resolution,
            "resolutionNote": note,
            "resolvedBy": resolver_user_id,
            "resolvedAt": datetime.now(timezone.utc),
        },
    )


def _hex_to_floats(hex_str: str | None) -> list[float] | None:
    if not hex_str:
        return None
    try:
        import struct

        raw = bytes.fromhex(hex_str)
        count = len(raw) // 4
        return list(struct.unpack(f"<{count}f", raw)) if count else None
    except Exception:
        return None
