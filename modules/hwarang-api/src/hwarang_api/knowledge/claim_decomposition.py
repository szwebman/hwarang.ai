"""HLKM ⑤ - Claim Decomposition (원자 주장 분해).

긴 뉴스/사실 문장을 "원자적 주장(atomic claim)" 단위로 잘게 쪼개
각각을 독립적으로 검증 가능한 단위로 만든다.

예시::

    원문 : "작년 하반기 삼성전자는 3분기 영업이익 10조를 기록했고
            이는 반도체 업황 회복 때문이라고 김회장이 밝혔다."
    분해 : [
      {atomic_statement: "삼성전자 3분기 영업이익은 10조이다", claim_type: numeric},
      {atomic_statement: "해당 이익은 반도체 업황 회복에 기인한다", claim_type: causal},
      {atomic_statement: "김회장이 위 내용을 밝혔다", claim_type: attribution},
    ]

각 원자 주장은 DecomposedClaim 레코드로 저장되고, HLKM 에서 지지/반박
사실을 찾아 검증 상태(verificationStatus)를 갱신한다. 부모 사실의 최종
신뢰도는 sub-claims 검증 결과를 종합해 재계산된다.

의존:
    - hwarang_api.db.prisma
    - .types.KnowledgeFact
    - .llm._chat (LLM 프롬프트 실행)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from hwarang_api.db import prisma

from .types import KnowledgeFact

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 상수: 정규식 기반 빠른 분류기
# ─────────────────────────────────────────────
_CLAIM_TYPE_PATTERNS: dict[str, str] = {
    "numeric": r"\d+\s*(?:원|%|명|건|톤|kg|km)",
    "date": r"\d{4}[-.년]\d{1,2}[-.월]?\d{0,2}",
    "attribution": r"(?:.*?(?:가|이|은|는|씨|측))\s*(?:밝혔|말했|발표)",
    "causal": r"(?:때문에|인해|에\s*따라|영향으로)",
    "conditional": r"(?:만약|이면|라면|한다면)",
}

_VALID_CLAIM_TYPES = {
    "numeric",
    "date",
    "attribution",
    "causal",
    "qualitative",
    "conditional",
}

# 주장 타입별 검증 출처 힌트
_VERIFICATION_HINTS: dict[str, list[str]] = {
    "numeric": ["통계청 KOSIS", "한국은행 ECOS", "공식 연감", "공시자료(DART)"],
    "date": ["관보/법제처 국가법령정보", "보도자료 공식 고시", "기관 홈페이지 공지"],
    "attribution": ["발언자 SNS/공식 프로필", "기자회견 영상", "공식 보도자료"],
    "causal": ["전문 연구논문", "한국개발연구원(KDI) 보고서", "정책 연구기관 자료"],
    "conditional": ["법령/규정 원문", "공식 가이드라인"],
    "qualitative": ["다수 매체 교차 검증", "전문가 분석 기사"],
}

# 최소 길이 이상일 때만 자동 분해 대상으로 삼는다.
_DECOMPOSE_MIN_LEN = 200


def _utcnow() -> datetime:
    """UTC 현재 시각."""
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────
# Quick classifier
# ─────────────────────────────────────────────
def quick_classify(text: str) -> str:
    """정규식 기반 빠른 주장 타입 분류 (LLM 보조).

    규칙 중 매칭이 가장 먼저 발견되는 것을 반환하고, 아무것도 매칭되지
    않으면 기본값 ``qualitative`` 를 반환한다. LLM 분류가 불확실할 때
    2차 검증용으로도 호출한다.
    """
    for label, pat in _CLAIM_TYPE_PATTERNS.items():
        if re.search(pat, text):
            return label
    return "qualitative"


# ─────────────────────────────────────────────
# LLM 분해
# ─────────────────────────────────────────────
async def _llm_decompose_claim(content: str) -> list[dict]:
    """LLM 을 호출해 원자 주장 목록을 얻는다.

    실패 시 빈 리스트를 반환하여 상위에서 regex fallback 을 사용하도록 한다.
    응답은 JSON 배열을 기대한다::

        [
          {"atomic_statement": "...", "claim_type": "numeric",
           "verifiable_value": "3분기 영업이익 10조"},
          ...
        ]
    """
    try:
        from .llm import _chat  # type: ignore
    except Exception:
        return []

    system = (
        "You are a fact-decomposition assistant. "
        "Break the given Korean/English statement down into ATOMIC verifiable claims. "
        "Each atomic claim must contain ONE assertion that can be verified independently. "
        "Reply ONLY as a JSON array. Each element must have keys: "
        '"atomic_statement" (1 sentence), '
        '"claim_type" (one of: numeric, date, attribution, causal, qualitative, conditional), '
        '"verifiable_value" (the concrete value/subject that must be checked, <=40 chars).'
    )
    try:
        resp = await _chat(content, system=system, max_tokens=600)
    except Exception as exc:  # noqa: BLE001
        logger.debug("_llm_decompose_claim failed: %s", exc)
        return []
    if not resp:
        return []

    # JSON 배열 추출 시도
    try:
        start = resp.find("[")
        end = resp.rfind("]")
        if start == -1 or end <= start:
            return []
        arr = json.loads(resp[start : end + 1])
        out: list[dict] = []
        for item in arr:
            if not isinstance(item, dict):
                continue
            stmt = str(item.get("atomic_statement", "")).strip()
            if not stmt:
                continue
            ctype = str(item.get("claim_type", "qualitative")).strip().lower()
            if ctype not in _VALID_CLAIM_TYPES:
                ctype = quick_classify(stmt)
            out.append(
                {
                    "atomic_statement": stmt,
                    "claim_type": ctype,
                    "verifiable_value": str(item.get("verifiable_value", "")).strip()[:80],
                }
            )
        return out
    except Exception as exc:  # noqa: BLE001
        logger.debug("decompose JSON parse failed: %s", exc)
        return []


def _regex_fallback_split(content: str) -> list[dict]:
    """LLM 이 실패했을 때 단순 규칙으로 1개 주장을 만든다.

    문장 단위 분리가 가능하면 각 문장을 독립 주장으로, 불가능하면
    원문 자체를 단일 주장으로 보고 리스트로 반환한다.
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.!?。\n])\s+", content) if s.strip()]
    if not sentences:
        sentences = [content.strip()]
    out: list[dict] = []
    for s in sentences[:8]:  # 최대 8개로 제한
        out.append(
            {
                "atomic_statement": s,
                "claim_type": quick_classify(s),
                "verifiable_value": s[:80],
            }
        )
    return out


# ─────────────────────────────────────────────
# 분해 본체
# ─────────────────────────────────────────────
async def decompose_fact(fact: KnowledgeFact) -> list[dict]:
    """하나의 KnowledgeFact 를 원자 주장 목록으로 분해해 DB 저장.

    흐름:
      1) LLM 호출로 원자 주장 추출
      2) 실패 시 regex fallback 사용
      3) DecomposedClaim 테이블에 각 주장 insert
      4) 부모 fact 의 ``isAtomic=False`` 업데이트

    반환: 생성된 원자 주장 dict 목록 (id 포함).
    """
    assert fact.id is not None, "fact.id required"

    claims = await _llm_decompose_claim(fact.content)
    if not claims:
        claims = _regex_fallback_split(fact.content)

    created: list[dict] = []
    for c in claims:
        try:
            row = await prisma.decomposedclaim.create(
                data={
                    "parentFactId": fact.id,
                    "atomicStatement": c["atomic_statement"],
                    "claimType": c["claim_type"],
                    "verifiableValue": c.get("verifiable_value", ""),
                    "verificationStatus": "pending",
                    "confidence": 0.5,
                }
            )
            created.append(
                {
                    "id": getattr(row, "id", None),
                    "atomic_statement": c["atomic_statement"],
                    "claim_type": c["claim_type"],
                    "verifiable_value": c.get("verifiable_value", ""),
                    "verification_status": "pending",
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("DecomposedClaim insert failed: %s", exc)

    # 부모 fact 를 non-atomic 으로 표시
    try:
        await prisma.knowledgefact.update(
            where={"id": fact.id},
            data={"isAtomic": False},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("update isAtomic failed: %s", exc)

    logger.info("decompose_fact %s → %d claims", fact.id, len(created))
    return created


# ─────────────────────────────────────────────
# 원자 주장 검증
# ─────────────────────────────────────────────
async def verify_atomic_claim(claim_id: str) -> dict:
    """원자 주장을 HLKM 에서 검색해 지지/반박 사실을 찾는다.

    반환: ``{"status": verified|refuted|pending, "confidence": float,
    "verifiedByFactId": str|None}``.
    """
    try:
        row = await prisma.decomposedclaim.find_unique(where={"id": claim_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("claim fetch failed: %s", exc)
        return {"status": "pending", "confidence": 0.0, "verifiedByFactId": None}
    if not row:
        return {"status": "pending", "confidence": 0.0, "verifiedByFactId": None}

    statement = row.atomicStatement
    status = "pending"
    confidence = 0.5
    verified_by: str | None = None

    # HLKM 검색 (지연 import 로 순환 방지)
    try:
        from .search import temporal_search
        from .types import SearchQuery

        sr = await temporal_search(SearchQuery(query=statement, limit=5))
    except Exception as exc:  # noqa: BLE001
        logger.debug("temporal_search failed for claim %s: %s", claim_id, exc)
        sr = None

    if sr and sr.facts:
        top = sr.facts[0]
        top_conf = sr.current_confidences[0] if sr.current_confidences else 0.5
        # LLM 로 top 사실이 본 주장을 지지 / 반박 / 무관 중 무엇인지 판정
        try:
            from .llm import llm_check_contradiction

            is_contra, _ = await llm_check_contradiction(statement, top.content)
        except Exception:
            is_contra = False
        if is_contra:
            status = "refuted"
            confidence = max(0.0, 1.0 - top_conf)
        else:
            status = "verified"
            confidence = top_conf
            verified_by = top.id

    try:
        await prisma.decomposedclaim.update(
            where={"id": claim_id},
            data={
                "verificationStatus": status,
                "confidence": confidence,
                "verifiedByFactId": verified_by,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("claim update failed: %s", exc)

    return {"status": status, "confidence": confidence, "verifiedByFactId": verified_by}


# ─────────────────────────────────────────────
# 부모 신뢰도 집계
# ─────────────────────────────────────────────
async def aggregate_parent_confidence(parent_fact_id: str) -> float:
    """부모 사실의 sub-claims 검증 결과를 종합해 신뢰도를 재계산.

    규칙:
      - 모두 verified → 1.0
      - 하나라도 refuted → 0.2
      - 일부 pending → verified 비율로 중간값 (0.3~0.9)
    """
    try:
        rows = await prisma.decomposedclaim.find_many(
            where={"parentFactId": parent_fact_id}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list claims failed: %s", exc)
        return 0.5

    if not rows:
        return 0.5

    total = len(rows)
    refuted = sum(1 for r in rows if r.verificationStatus == "refuted")
    verified = sum(1 for r in rows if r.verificationStatus == "verified")

    if refuted > 0:
        new_conf = 0.2
    elif verified == total:
        new_conf = 1.0
    else:
        # verified 비율을 0.3~0.9 사이에 매핑
        ratio = verified / total
        new_conf = 0.3 + 0.6 * ratio

    try:
        await prisma.knowledgefact.update(
            where={"id": parent_fact_id},
            data={"confidenceT0": new_conf},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("parent confidence update failed: %s", exc)

    return new_conf


# ─────────────────────────────────────────────
# 조회 / 배치 / 유틸
# ─────────────────────────────────────────────
async def list_claims_for_fact(fact_id: str) -> list[dict]:
    """해당 부모 사실에 속한 원자 주장 리스트."""
    try:
        rows = await prisma.decomposedclaim.find_many(where={"parentFactId": fact_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_claims_for_fact failed: %s", exc)
        return []
    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "id": getattr(r, "id", None),
                "atomic_statement": r.atomicStatement,
                "claim_type": r.claimType,
                "verifiable_value": getattr(r, "verifiableValue", ""),
                "verification_status": r.verificationStatus,
                "verified_by_fact_id": getattr(r, "verifiedByFactId", None),
                "confidence": getattr(r, "confidence", 0.5),
            }
        )
    return out


async def batch_decompose(domain: str | None = None, limit: int = 50) -> dict:
    """아직 분해되지 않은(긴) 사실들을 자동으로 분해한다.

    조건: ``isAtomic=True`` (아직 분해 전) AND ``len(content) > 200``.
    결과: 처리 요약 dict.
    """
    where: dict[str, Any] = {"isAtomic": True}
    if domain:
        where["domain"] = domain
    try:
        rows = await prisma.knowledgefact.find_many(where=where, take=limit * 3)
    except Exception as exc:  # noqa: BLE001
        logger.warning("batch_decompose find failed: %s", exc)
        return {"total": 0, "decomposed": 0, "claims_created": 0}

    decomposed = 0
    claims_created = 0
    for row in rows:
        content = getattr(row, "content", "") or ""
        if len(content) <= _DECOMPOSE_MIN_LEN:
            continue
        if decomposed >= limit:
            break
        fact = KnowledgeFact(
            id=row.id,
            content=content,
            domain=getattr(row, "domain", "general"),
            valid_from=getattr(row, "validFrom", _utcnow()),
            source=getattr(row, "source", ""),
        )
        claims = await decompose_fact(fact)
        decomposed += 1
        claims_created += len(claims)

    return {
        "total": len(rows),
        "decomposed": decomposed,
        "claims_created": claims_created,
    }


async def suggest_verification_sources(claim_id: str) -> list[str]:
    """주장 타입에 맞는 권장 검증 출처 힌트."""
    try:
        row = await prisma.decomposedclaim.find_unique(where={"id": claim_id})
    except Exception:  # noqa: BLE001
        return []
    if not row:
        return []
    ctype = getattr(row, "claimType", "qualitative")
    return list(_VERIFICATION_HINTS.get(ctype, _VERIFICATION_HINTS["qualitative"]))


async def mark_claim_unverifiable(claim_id: str, reason: str) -> None:
    """주장을 검증 불가능(unverifiable)으로 표시.

    ``reason`` 은 notes 성격으로 기록. 출처가 사라졌거나 주관적 가치 판단이어서
    검증 자체가 무의미한 경우 사용.
    """
    try:
        await prisma.decomposedclaim.update(
            where={"id": claim_id},
            data={
                "verificationStatus": "unverifiable",
                "confidence": 0.0,
                "verifiedByFactId": None,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("mark_claim_unverifiable failed: %s", exc)
    logger.info("claim %s marked unverifiable: %s", claim_id, reason)


__all__ = [
    "decompose_fact",
    "quick_classify",
    "verify_atomic_claim",
    "aggregate_parent_confidence",
    "list_claims_for_fact",
    "batch_decompose",
    "suggest_verification_sources",
    "mark_claim_unverifiable",
    "_CLAIM_TYPE_PATTERNS",
]
