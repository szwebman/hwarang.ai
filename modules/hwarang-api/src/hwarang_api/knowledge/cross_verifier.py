"""다중 신뢰 출처 cross-verification.

응답이나 사실 주장(claim)에 대해:

  1. 화이트리스트 ``TrustedSource`` 들을 도메인 매칭으로 후보화
  2. HLKM 의 의미 검색으로 이미 크롤된 후보 사실들 추출
  3. 각 사실에 연결된 ``SourceCitation`` 의 ``stance`` 를 LLM 으로 분류
     (supports / refutes / unrelated)
  4. ``trust_level`` 가중 합산 → 0~1 신뢰도 점수

majority voting 보다 우수한 이유:
  - 1 차 출처 1 개 (law.go.kr) > 2 차 출처 100 개 (가중치)
  - 출처 추적 가능 (citation chain)
  - Sybil 면역 — 외부 신뢰 출처는 화랑 시스템 내부에서 조작 불가

사용:
    from hwarang_api.knowledge.cross_verifier import verify_claim

    result = await verify_claim("최저시급 2026년 11000원이다", domain="legal")
    print(result.summary())  # 🟢 신뢰도 0.92 (4개 출처 동의)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as llm_chat  # 내부 helper 직접 사용
from hwarang_api.knowledge.search import temporal_search
from hwarang_api.knowledge.types import SearchQuery

logger = logging.getLogger(__name__)


Stance = Literal["supports", "refutes", "unrelated"]


@dataclass
class Evidence:
    source_name: str
    source_url: str
    trust_level: int
    is_primary: bool
    stance: Stance
    excerpt: str


@dataclass
class ClaimVerification:
    """``ClaimVerification`` — Trusted Source Network 의 검증 결과.

    ``hwarang_api.knowledge.types.VerificationResult`` 와 이름이 겹치므로
    여기서는 별도 타입(``ClaimVerification``)을 쓴다.
    """

    claim: str
    confidence: float  # 0~1
    supporting: list[Evidence] = field(default_factory=list)
    contradicting: list[Evidence] = field(default_factory=list)
    primary_count: int = 0
    total_evidence: int = 0
    notes: str = ""

    def summary(self) -> str:
        n = len(self.supporting)
        if self.confidence >= 0.85:
            return f"🟢 신뢰도 {self.confidence:.2f} ({n}개 출처 동의)"
        elif self.confidence >= 0.6:
            return f"🟡 신뢰도 {self.confidence:.2f} (출처 일부 일치)"
        else:
            return f"🔴 신뢰도 {self.confidence:.2f} (출처 부족 또는 충돌)"

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "confidence": self.confidence,
            "summary": self.summary(),
            "primary_count": self.primary_count,
            "total_evidence": self.total_evidence,
            "supporting": [_evidence_dict(e) for e in self.supporting],
            "contradicting": [_evidence_dict(e) for e in self.contradicting],
            "notes": self.notes,
        }


def _evidence_dict(e: Evidence) -> dict[str, Any]:
    return {
        "source_name": e.source_name,
        "source_url": e.source_url,
        "trust_level": e.trust_level,
        "is_primary": e.is_primary,
        "stance": e.stance,
        "excerpt": e.excerpt,
    }


# ---------------------------------------------------------------------------
# LLM 입장 분류
# ---------------------------------------------------------------------------
STANCE_PROMPT = """다음 문서가 주장에 대해 어떤 입장인지 판단해라.

주장: {claim}

문서: {doc_excerpt}

답변: supports | refutes | unrelated 중 하나만 한 단어로."""


async def _classify_stance(claim: str, doc_excerpt: str) -> Stance:
    try:
        response = await llm_chat(
            STANCE_PROMPT.format(claim=claim, doc_excerpt=doc_excerpt[:600]),
            max_tokens=10,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("stance LLM fail: %s", exc)
        return "unrelated"

    text = (response or "").lower().strip()
    if "support" in text:
        return "supports"
    if "refute" in text or "contradict" in text or "반박" in text or "거짓" in text:
        return "refutes"
    return "unrelated"


# ---------------------------------------------------------------------------
# 메인 함수
# ---------------------------------------------------------------------------
async def verify_claim(
    claim: str,
    domain: str = "general",
    top_k: int = 20,
) -> ClaimVerification:
    """주장(claim)을 화이트리스트 출처들로 cross-verify.

    Parameters
    ----------
    claim : str
        검증할 자연어 주장.
    domain : str
        사실 도메인 (legal / medical / news / general …). 출처 후보 필터링.
    top_k : int
        HLKM 에서 가져올 후보 사실 개수.
    """
    # 1) 도메인 매칭 화이트리스트 출처 (참고용 — 어떤 출처가 있는지 stats 용)
    try:
        sources = await prisma.trustedsource.find_many(
            where={
                "isWhitelisted": True,
                "isActive": True,
                "OR": [
                    {"domains": {"has": domain}},
                    {"type": "fact_checker"},  # 팩트체커는 모든 도메인에 유효
                ],
            },
            order={"trustLevel": "desc"},
            take=15,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("trustedsource find_many fail: %s", exc)
        sources = []

    if not sources:
        return ClaimVerification(
            claim=claim,
            confidence=0.5,
            notes="domain 매칭 화이트리스트 출처 없음 — 중립 응답",
        )

    # 2) HLKM 의미 검색 — 이미 크롤된 출처 사실들 중 관련 후보
    try:
        result = await temporal_search(
            SearchQuery(query=claim, domain=domain, limit=top_k)
        )
        related_facts = result.facts
    except Exception as exc:  # noqa: BLE001
        logger.warning("temporal_search fail: %s", exc)
        related_facts = []

    # 3) 각 fact 의 SourceCitation → stance 분류
    evidences: list[Evidence] = []
    for fact in related_facts:
        if not fact.id:
            continue
        try:
            citations = await prisma.sourcecitation.find_many(
                where={"factId": fact.id},
                include={"source": True},
            )
        except Exception:
            citations = []

        for cite in citations:
            src = getattr(cite, "source", None)
            if not src or not getattr(src, "isWhitelisted", False):
                continue
            stance = await _classify_stance(claim, fact.content)
            if stance == "unrelated":
                continue
            evidences.append(
                Evidence(
                    source_name=src.displayName,
                    source_url=cite.url,
                    trust_level=int(src.trustLevel),
                    is_primary=bool(src.isPrimarySource),
                    stance=stance,
                    excerpt=fact.content[:200],
                )
            )

    # 4) 가중 합산
    pro_weight = sum(e.trust_level for e in evidences if e.stance == "supports")
    con_weight = sum(e.trust_level for e in evidences if e.stance == "refutes")
    total_weight = pro_weight + con_weight
    confidence = (pro_weight / total_weight) if total_weight > 0 else 0.5

    # 5) 1 차 출처 특별 처리 — 1 차 출처가 반박하면 confidence 강제 ↓
    primary_refutes = [e for e in evidences if e.is_primary and e.stance == "refutes"]
    if primary_refutes:
        confidence = min(confidence, 0.3)

    # 1 차 출처가 동의하면 살짝 boost (단, 최대 1.0)
    primary_supports = [e for e in evidences if e.is_primary and e.stance == "supports"]
    if primary_supports and not primary_refutes:
        confidence = min(1.0, confidence + 0.1 * len(primary_supports))

    primary_count = sum(1 for e in evidences if e.is_primary)
    notes_parts: list[str] = []
    if primary_refutes:
        notes_parts.append(f"1차 출처 {len(primary_refutes)}개 반박 → confidence cap 0.3")
    if not evidences:
        notes_parts.append("관련 출처 자료 없음 — 추가 크롤 필요")

    return ClaimVerification(
        claim=claim,
        confidence=round(confidence, 4),
        supporting=[e for e in evidences if e.stance == "supports"][:10],
        contradicting=[e for e in evidences if e.stance == "refutes"][:10],
        primary_count=primary_count,
        total_evidence=len(evidences),
        notes="; ".join(notes_parts),
    )


__all__ = [
    "Evidence",
    "ClaimVerification",
    "verify_claim",
]
