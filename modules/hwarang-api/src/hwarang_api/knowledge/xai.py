"""HLKM ① XAI Answer Chain.

모든 HLKM 답변이 **검증 가능한 근거 사슬**과 함께 반환되도록 하는 모듈.

핵심 아이디어:
    1. 답변에 사용된 각 KnowledgeFact 를 DB 에서 조회한다.
    2. 사실별로 (현재 신뢰도 × 출처 평판 × 시간 감쇠) 를 계산한다.
    3. 인과/지지 그래프를 확장해 전체 맥락을 수집한다.
    4. 가중 평균으로 overall_confidence 를 산출한다.
    5. AnswerEvidence 테이블에 영속화하여 재사용/감사가 가능하도록 한다.

의존:
    - hwarang_api.db.prisma : Prisma 클라이언트
    - .half_life.current_confidence : 시간 감쇠 적용 신뢰도
    - .graph.find_related          : 인과/지지 엣지 확장
    - .types                       : KnowledgeFact, KnowledgeRelation
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from hwarang_api.db import prisma

from .graph import find_related
from .half_life import current_confidence
from .types import KnowledgeFact, KnowledgeRelation, KnowledgeStatus

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
_DEFAULT_SOURCE_REPUTATION = 0.7
"""SourceReputation 레코드가 없을 때 적용할 중립값."""

_RECENCY_HALF_LIFE_DAYS = 365.0
"""recency 가중치 계산용 기본 반감기 (1년)."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _row_to_fact(row: Any) -> KnowledgeFact:
    """Prisma row → Pydantic KnowledgeFact (최소 필드 매핑)."""
    d = row if isinstance(row, dict) else row.model_dump()
    return KnowledgeFact(
        id=d.get("id"),
        content=d.get("content", ""),
        content_hash=d.get("contentHash"),
        domain=d.get("domain", "general"),
        entity=d.get("entity"),
        tags=d.get("tags", []) or [],
        language=d.get("language", "ko"),
        valid_from=d.get("validFrom"),
        valid_to=d.get("validTo"),
        created_at=d.get("createdAt"),
        last_verified_at=d.get("lastVerifiedAt"),
        next_check_at=d.get("nextCheckAt"),
        confidence_t0=float(d.get("confidenceT0", 1.0)),
        half_life_days=d.get("halfLifeDays"),
        status=KnowledgeStatus(d.get("status", "CONFIRMED")),
        source=d.get("source", ""),
        source_url=d.get("sourceUrl"),
        source_type=d.get("sourceType", "user"),
    )


# ─────────────────────────────────────────────
# 해시 / 캐시 키
# ─────────────────────────────────────────────
def compute_question_hash(question: str, as_of: datetime | None) -> str:
    """질문 + as_of 시점으로 재사용 가능한 SHA-256 해시를 생성한다.

    동일 질문을 동일 시점으로 다시 묻는 경우 AnswerEvidence 를 재활용할 수 있다.
    """
    normalized = (question or "").strip().lower()
    anchor = _as_aware(as_of).isoformat() if as_of else "now"
    raw = f"{normalized}||{anchor}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# ─────────────────────────────────────────────
# 평판 / 시간 점수
# ─────────────────────────────────────────────
async def _lookup_source_reputation(source: str) -> float:
    """SourceReputation 테이블에서 출처 평판을 조회한다.

    레코드가 없거나 예외 발생 시 `_DEFAULT_SOURCE_REPUTATION` (0.7) 반환.
    """
    if not source:
        return _DEFAULT_SOURCE_REPUTATION
    try:
        row = await prisma.sourcereputation.find_unique(where={"source": source})
    except Exception as exc:  # DB 미연결 등
        logger.debug("source reputation lookup failed: %s", exc)
        return _DEFAULT_SOURCE_REPUTATION
    if row is None:
        return _DEFAULT_SOURCE_REPUTATION
    try:
        return float(row.reputation)
    except Exception:
        return _DEFAULT_SOURCE_REPUTATION


def _time_validity_status(fact: KnowledgeFact, now: datetime) -> str:
    """valid_from / valid_to 기준 시간 유효성 상태.

    - `expired`  : valid_to < now
    - `future`   : valid_from > now
    - `stale`    : next_check_at < now (재검증 필요)
    - `valid`   : 그 외
    """
    valid_to = _as_aware(fact.valid_to)
    valid_from = _as_aware(fact.valid_from)
    next_check = _as_aware(fact.next_check_at)

    if valid_to is not None and valid_to < now:
        return "expired"
    if valid_from is not None and valid_from > now:
        return "future"
    if next_check is not None and next_check < now:
        return "stale"
    return "valid"


def _time_decay_factor(fact: KnowledgeFact, now: datetime) -> float:
    """시간 감쇠 보정 factor (0~1).

    last_verified_at 이 최근일수록 1 에 가깝고, 오래 전일수록 감소.
    half_life = _RECENCY_HALF_LIFE_DAYS 를 기본으로 하되,
    사실 고유 half_life_days 가 있으면 그 값을 우선 사용한다.
    """
    anchor = _as_aware(fact.last_verified_at or fact.valid_from)
    if anchor is None:
        return 1.0
    age_days = max(0.0, (now - anchor).total_seconds() / 86_400.0)
    half_life = float(fact.half_life_days) if fact.half_life_days else _RECENCY_HALF_LIFE_DAYS
    if half_life <= 0:
        return 1.0
    return max(0.0, min(1.0, 0.5 ** (age_days / half_life)))


def _assign_role(index: int, total: int) -> str:
    """근거의 역할 태깅.

    - 0번째 팩트: primary
    - 상위 1/3 : supporting
    - 나머지  : corroborating
    """
    if index == 0:
        return "primary"
    if index < max(1, total // 3):
        return "supporting"
    return "corroborating"


# ─────────────────────────────────────────────
# 메인: 근거 사슬 빌더
# ─────────────────────────────────────────────
async def build_evidence_chain(
    question: str,
    used_fact_ids: list[str],
    as_of: datetime | None = None,
    user_id: str | None = None,
) -> dict:
    """답변에 사용된 사실들로부터 검증 가능한 근거 사슬을 생성한다.

    Parameters
    ----------
    question : str
        원본 질문 텍스트. 질문 해시 계산 및 로그용.
    used_fact_ids : list[str]
        답변 생성에 실제 인용된 KnowledgeFact id 목록.
    as_of : datetime | None
        기준 시점. None 이면 현재(UTC) 사용.
    user_id : str | None
        질의자 식별자. AnswerEvidence.userId 에 저장.

    Returns
    -------
    dict
        근거, 인과사슬, 모순 경고, overall_confidence 를 담은 구조체.
    """
    now = _as_aware(as_of) or _utcnow()

    evidences: list[dict[str, Any]] = []
    weighted_sum = 0.0
    weight_total = 0.0
    contradictions: list[dict[str, Any]] = []
    disclaimers: list[str] = []

    # 1) 각 사실별 상세 점수 산출
    for idx, fact_id in enumerate(used_fact_ids):
        try:
            row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
        except Exception as exc:
            logger.warning("fact lookup failed %s: %s", fact_id, exc)
            row = None

        if row is None:
            disclaimers.append(f"사실 {fact_id} 를 찾을 수 없어 제외되었습니다.")
            continue

        fact = _row_to_fact(row)
        cur_conf = current_confidence(fact, now=now)
        source_rep = await _lookup_source_reputation(fact.source)
        time_decay = _time_decay_factor(fact, now=now)
        validity = _time_validity_status(fact, now=now)

        if validity == "expired":
            disclaimers.append(
                f"'{fact.entity or fact.source}' 근거는 {fact.valid_to} 에 만료되었습니다."
            )
        elif validity == "stale":
            disclaimers.append(
                f"'{fact.entity or fact.source}' 근거는 재검증 기한을 넘겼습니다."
            )

        weight = cur_conf * source_rep * time_decay
        weighted_sum += weight
        weight_total += 1.0

        evidences.append(
            {
                "fact_id": fact.id,
                "content": fact.content,
                "source": fact.source,
                "source_url": fact.source_url,
                "source_reputation": round(source_rep, 4),
                "valid_from": fact.valid_from.isoformat() if fact.valid_from else None,
                "valid_to": fact.valid_to.isoformat() if fact.valid_to else None,
                "current_confidence": round(cur_conf, 4),
                "time_decay_applied": round(time_decay, 4),
                "time_validity": validity,
                "status": fact.status.value,
                "role": _assign_role(idx, len(used_fact_ids)),
            }
        )

        # 모순 엣지 감지
        try:
            contra_edges = await find_related(
                fact_id, relation_types=[KnowledgeRelation.CONTRADICTS]
            )
            for edge in contra_edges:
                contradictions.append(
                    {
                        "from": edge.from_fact_id,
                        "to": edge.to_fact_id,
                        "strength": edge.strength,
                        "evidence": edge.evidence,
                    }
                )
        except Exception as exc:
            logger.debug("contradiction scan failed %s: %s", fact_id, exc)

    # 2) 인과/지지 체인 확장 (top 팩트 기준)
    causal_chain: list[dict[str, Any]] = []
    if used_fact_ids:
        try:
            supporting = await find_related(
                used_fact_ids[0],
                relation_types=[
                    KnowledgeRelation.CAUSES,
                    KnowledgeRelation.SUPPORTS,
                    KnowledgeRelation.DERIVED_FROM,
                ],
                min_strength=0.5,
            )
            for edge in supporting[:10]:
                causal_chain.append(
                    {
                        "from": edge.from_fact_id,
                        "to": edge.to_fact_id,
                        "relation": edge.relation_type.value,
                        "strength": round(edge.strength, 3),
                    }
                )
        except Exception as exc:
            logger.debug("causal chain expansion failed: %s", exc)

    overall = (weighted_sum / weight_total) if weight_total > 0 else 0.0

    if contradictions:
        disclaimers.append(
            f"상충하는 근거 {len(contradictions)}건이 감지되어 신뢰도가 보정되었습니다."
        )
        overall *= 0.85  # 모순이 있으면 페널티

    result: dict[str, Any] = {
        "question": question,
        "question_hash": compute_question_hash(question, as_of),
        "as_of": now.isoformat(),
        "overall_confidence": round(max(0.0, min(1.0, overall)), 4),
        "evidence": evidences,
        "causal_chain": causal_chain,
        "contradictions_present": contradictions,
        "disclaimers": disclaimers,
    }

    # 3) AnswerEvidence 에 영속화 (선택)
    try:
        await prisma.answerevidence.create(
            data={
                "questionHash": result["question_hash"],
                "questionText": question,
                "answerText": "",  # 호출측이 업데이트
                "factIds": [e["fact_id"] for e in evidences if e.get("fact_id")],
                "confidenceFactors": json.dumps(
                    {
                        "overall": result["overall_confidence"],
                        "per_evidence": [
                            {
                                "fact_id": e["fact_id"],
                                "cur_conf": e["current_confidence"],
                                "src_rep": e["source_reputation"],
                                "time_decay": e["time_decay_applied"],
                            }
                            for e in evidences
                        ],
                    },
                    ensure_ascii=False,
                ),
                "asOfDate": now,
                "userId": user_id,
            }
        )
    except Exception as exc:
        logger.debug("answerevidence persist failed (non-fatal): %s", exc)

    return result


# ─────────────────────────────────────────────
# Markdown 설명 생성
# ─────────────────────────────────────────────
async def explain_answer_markdown(evidence: dict) -> str:
    """근거 dict 를 한국어 Markdown 으로 변환한다.

    섹션 구조:
      1. 개요 (질문 + 신뢰도)
      2. ## 근거 (각 사실별)
      3. ## 인과 사슬 (있을 때만)
      4. ## 신뢰도 산정
      5. ## 유의사항 (disclaimer)
    """
    lines: list[str] = []
    q = evidence.get("question", "")
    conf = evidence.get("overall_confidence", 0.0)
    as_of = evidence.get("as_of", "")

    lines.append(f"# 답변 근거 보고서\n")
    lines.append(f"- **질문**: {q}")
    lines.append(f"- **기준 시점**: {as_of}")
    lines.append(f"- **전체 신뢰도**: {conf:.1%}\n")

    ev_list = evidence.get("evidence", [])
    if ev_list:
        lines.append("## 근거\n")
        for i, ev in enumerate(ev_list, start=1):
            role = {"primary": "핵심 근거", "supporting": "보조 근거", "corroborating": "보강 근거"}.get(
                ev.get("role", ""), ev.get("role", "")
            )
            lines.append(f"### [{i}] {role} — {ev.get('source', '출처 미상')}")
            lines.append(f"- 내용: {ev.get('content', '').strip()[:300]}")
            if ev.get("source_url"):
                lines.append(f"- 출처 링크: <{ev['source_url']}>")
            lines.append(f"- 출처 평판: {ev.get('source_reputation', 0):.2f}")
            lines.append(f"- 현재 신뢰도: {ev.get('current_confidence', 0):.2f}")
            lines.append(f"- 시간 감쇠: {ev.get('time_decay_applied', 0):.2f}")
            lines.append(
                f"- 시간 유효성: {ev.get('time_validity', '-')} "
                f"(유효기간 {ev.get('valid_from', '-')} ~ {ev.get('valid_to') or '현재'})"
            )
            lines.append("")

    causal = evidence.get("causal_chain", [])
    if causal:
        lines.append("## 인과 사슬\n")
        for c in causal:
            lines.append(
                f"- `{c['from']}` --[{c['relation']} · {c['strength']:.2f}]--> `{c['to']}`"
            )
        lines.append("")

    lines.append("## 신뢰도 산정\n")
    lines.append(
        "전체 신뢰도 = 평균( 사실 신뢰도 × 출처 평판 × 시간 감쇠 ). "
        "모순되는 근거가 감지되면 15% 페널티가 적용됩니다.\n"
    )

    disclaimers = evidence.get("disclaimers", [])
    if disclaimers:
        lines.append("## 유의사항\n")
        for d in disclaimers:
            lines.append(f"- {d}")
        lines.append("")

    contradictions = evidence.get("contradictions_present", [])
    if contradictions:
        lines.append("## 상충 근거\n")
        for c in contradictions:
            lines.append(
                f"- `{c['from']}` ⟷ `{c['to']}` (strength {c['strength']:.2f})"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ─────────────────────────────────────────────
# 캐시 조회
# ─────────────────────────────────────────────
async def get_saved_evidence(question_hash: str) -> dict | None:
    """AnswerEvidence 테이블에서 동일 질문 해시의 최근 레코드를 반환한다.

    여러 건이면 가장 최신 것을 사용한다. 없으면 None.
    """
    try:
        rows = await prisma.answerevidence.find_many(
            where={"questionHash": question_hash},
            order={"createdAt": "desc"},
            take=1,
        )
    except Exception as exc:
        logger.debug("get_saved_evidence failed: %s", exc)
        return None
    if not rows:
        return None
    row = rows[0]
    factors_raw = row.confidenceFactors
    try:
        factors = json.loads(factors_raw) if isinstance(factors_raw, str) else factors_raw
    except Exception:
        factors = {}
    return {
        "question": row.questionText,
        "question_hash": row.questionHash,
        "answer": row.answerText,
        "fact_ids": list(row.factIds or []),
        "confidence_factors": factors,
        "as_of": row.asOfDate.isoformat() if row.asOfDate else None,
        "user_id": row.userId,
        "created_at": row.createdAt.isoformat() if row.createdAt else None,
    }


# ─────────────────────────────────────────────
# 인라인 인용 삽입
# ─────────────────────────────────────────────
async def cite_facts_inline(text: str, fact_ids: list[str]) -> str:
    """LLM 원문 뒤에 [1][2] 형태의 각주 참조와 하단 레퍼런스 블록을 추가한다.

    구현 전략:
        1. 각 fact 의 content 에서 첫 20자를 추출해 텍스트에서 부분 매칭을 시도.
        2. 매칭되면 해당 위치 바로 뒤에 `[n]` 삽입.
        3. 마지막에 `---\\n[1] 출처: ... / [2] 출처: ...` 블록을 덧붙인다.

    매칭이 하나도 되지 않아도 각주 블록은 항상 부착한다.
    """
    if not fact_ids:
        return text

    annotated = text
    refs: list[str] = []
    for i, fid in enumerate(fact_ids, start=1):
        try:
            row = await prisma.knowledgefact.find_unique(where={"id": fid})
        except Exception:
            row = None
        if row is None:
            refs.append(f"[{i}] (알 수 없는 근거 {fid})")
            continue

        snippet = (row.content or "").strip().splitlines()[0][:20]
        marker = f"[{i}]"
        if snippet and snippet in annotated and marker not in annotated:
            annotated = annotated.replace(snippet, f"{snippet}{marker}", 1)

        source_label = row.source or "출처 미상"
        url = getattr(row, "sourceUrl", None)
        if url:
            refs.append(f"[{i}] {source_label} — {url}")
        else:
            refs.append(f"[{i}] {source_label}")

    return annotated.rstrip() + "\n\n---\n" + "\n".join(refs) + "\n"


__all__ = [
    "build_evidence_chain",
    "explain_answer_markdown",
    "get_saved_evidence",
    "cite_facts_inline",
    "compute_question_hash",
]
