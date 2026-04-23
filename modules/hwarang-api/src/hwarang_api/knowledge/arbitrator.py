"""HLKM TAL 종합 엔진 — Arbitrator.

모든 TAL(Trust Arbitration Layer) 구성요소를 하나로 엮어서 **최종
arbitrated_confidence** 를 계산한다.

다차원 신뢰도 결합식::

    final = base × time_decay
          × (source_reputation × 0.3 + hierarchy_authority × 0.7)
          × (1 + log2(max(1, independence_factor)) × 0.2)
          × stance_multiplier
          × retracted_penalty
          × falsifiability_trust

이 모듈의 책임:
  1. 단일 사실 점수화 (:func:`arbitrated_confidence`)
  2. 배치 재계산 (:func:`batch_arbitrate`)
  3. 질의 전체에 대한 종합 답변 (:func:`arbitrate_answer`)
  4. 사람-가독 감사 리포트 (:func:`explain_arbitration`, :func:`full_trust_audit`)

순환 import 를 피하기 위해 ``counter_evidence`` / ``primary_source`` 등
동일 TAL 레이어 모듈은 **lazy import** 한다.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

from hwarang_api.db import prisma

from .half_life import current_confidence
from .reputation import get_reputation
from .types import KnowledgeFact, KnowledgeStatus

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────────────────────

# falsifiability 별 신뢰 배수
FALSIFIABILITY_TRUST: dict[str, float] = {
    "UNFALSIFIABLE": 1.0,   # 증명된 사실 / 수학·정의
    "FALSIFIABLE": 1.0,     # 재검증 가능
    "TIME_DEPENDENT": 0.7,  # 아직 시간이 확인하지 않음
    "VALUE_JUDGMENT": 0.5,  # 검증 개념 자체가 다름
    "UNCLEAR": 0.6,
}

# reputation / hierarchy 결합 가중치
_W_REPUTATION = 0.3
_W_HIERARCHY = 0.7

# 독립성 보너스 계수: log2(n) × K, K=0.2
_INDEP_BONUS_K = 0.2

# 철회(retracted) 페널티
_RETRACTED_PENALTY = 0.05

# verdict 라벨
_HIGH_MIN = 0.85
_MEDIUM_MIN = 0.6
_LOW_MAX = 0.4


# ─────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────
def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _as_aware(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _row_to_fact(row: Any) -> KnowledgeFact:
    return KnowledgeFact(
        id=row.id,
        content=row.content,
        content_hash=getattr(row, "contentHash", None),
        domain=row.domain,
        entity=row.entity,
        tags=list(row.tags or []),
        language=row.language,
        valid_from=row.validFrom,
        valid_to=getattr(row, "validTo", None),
        created_at=getattr(row, "createdAt", None),
        last_verified_at=getattr(row, "lastVerifiedAt", None),
        confidence_t0=float(row.confidenceT0),
        half_life_days=getattr(row, "halfLifeDays", None),
        status=KnowledgeStatus(row.status),
        source=row.source,
        source_url=getattr(row, "sourceUrl", None),
    )


# ─────────────────────────────────────────────────────────────
# falsifiability
# ─────────────────────────────────────────────────────────────
def falsifiability_trust_factor(fal: str | None) -> float:
    """falsifiability 레이블별 신뢰 배수를 반환."""
    key = (fal or "").upper()
    return FALSIFIABILITY_TRUST.get(key, FALSIFIABILITY_TRUST["UNCLEAR"])


# ─────────────────────────────────────────────────────────────
# 독립 출처 수 집계
# ─────────────────────────────────────────────────────────────
async def independence_bonus(fact: KnowledgeFact) -> int:
    """같은 entity + 같은 주장을 지지하는 **독립** 출처 수.

    ProvenanceEdge 에서 copy 관계인 사실은 동일 원본으로 간주해 제외한다.
    provenance 모듈이 없으면 source 도메인 기준으로 대체 집계한다.
    """
    if not fact or not fact.entity:
        return 1

    try:
        rows = await prisma.knowledgefact.find_many(
            where={
                "entity": fact.entity,
                "status": {"in": ["CONFIRMED", "PENDING"]},
            },
            take=200,
        )
    except Exception:
        rows = []

    if not rows:
        return 1

    # lazy import — provenance 모듈은 병렬 팀에서 추가 예정
    try:
        from .provenance import find_original_of, count_independent_sources  # type: ignore
        prov_ok = True
    except Exception:
        prov_ok = False

    # 독립성 집계: 원본 id 집합 크기
    originals: set[str] = set()
    for r in rows:
        oid = None
        if prov_ok and r.id:
            try:
                oid = await find_original_of(r.id)
            except Exception:
                oid = None
        if not oid:
            # fallback: 소스 도메인의 2차 호스트
            from .consensus import extract_source_domain  # 안전한 로컬 import

            oid = extract_source_domain(r.sourceUrl or r.source or r.id)
        originals.add(oid or r.id)

    # 본인 제외한 독립 출처 수 반환 (최소 1)
    if prov_ok and fact.id:
        try:
            val = await count_independent_sources(fact.entity)
            if isinstance(val, int) and val > 0:
                return val
        except Exception:
            pass
    return max(1, len(originals))


# ─────────────────────────────────────────────────────────────
# 핵심: arbitrated_confidence
# ─────────────────────────────────────────────────────────────
async def arbitrated_confidence(
    fact: KnowledgeFact, now: datetime | None = None
) -> dict:
    """다차원 신뢰도 결합 계산 + DB 업데이트.

    반환::

        {
          "score": float,          # 최종 arbitrated_confidence
          "breakdown": {...},      # 각 요소별 값
          "reasoning": str,        # 한 줄 요약
        }
    """
    now = _as_aware(now)

    base = _clamp01(fact.confidence_t0)
    time_decay = current_confidence(fact, now=now)

    # reputation
    source_reputation = await get_reputation(fact.source)

    # hierarchy authority — fact 에 이미 저장돼 있으면 그대로, 아니면 lookup
    hierarchy_authority: float
    tier_label = getattr(fact, "sourceTier", None)
    auth_raw = getattr(fact, "sourceAuthority", None)
    if auth_raw is None and fact.id:
        try:
            row = await prisma.knowledgefact.find_unique(where={"id": fact.id})
            if row is not None:
                auth_raw = getattr(row, "sourceAuthority", None)
                tier_label = getattr(row, "sourceTier", None)
        except Exception:
            pass

    if auth_raw is None:
        try:
            from .hierarchy import lookup_authority

            tier_label, auth_raw = await lookup_authority(
                fact.source_url or fact.source or "", fact.domain or "general"
            )
        except Exception:
            tier_label, auth_raw = ("UNKNOWN", 0.3)

    hierarchy_authority = _clamp01(float(auth_raw or 0.3))

    # independence
    independence = await independence_bonus(fact)

    # stance multiplier
    try:
        from .stance import stance_weight_multiplier  # type: ignore

        stance_mult = float(stance_weight_multiplier(getattr(fact, "stance", None)))
    except Exception:
        stance_mult = 1.0

    # retracted
    retracted = bool(getattr(fact, "retracted", False))
    if fact.id and not retracted:
        try:
            row = await prisma.knowledgefact.find_unique(where={"id": fact.id})
            if row is not None:
                retracted = bool(getattr(row, "retracted", False)) or (
                    str(row.status) == KnowledgeStatus.RETRACTED.value
                )
        except Exception:
            pass
    retracted_factor = _RETRACTED_PENALTY if retracted else 1.0

    # falsifiability
    fal_label = getattr(fact, "falsifiability", None) or "UNCLEAR"
    fal_factor = falsifiability_trust_factor(fal_label)

    # 결합 공식
    source_trust = source_reputation * _W_REPUTATION + hierarchy_authority * _W_HIERARCHY
    indep_term = 1.0 + math.log2(max(1, independence)) * _INDEP_BONUS_K

    raw = (
        base
        * time_decay
        * source_trust
        * indep_term
        * stance_mult
        * retracted_factor
        * fal_factor
    )
    score = _clamp01(raw)

    breakdown = {
        "base_confidence": round(base, 4),
        "time_decay": round(time_decay, 4),
        "source_reputation": round(source_reputation, 4),
        "hierarchy_authority": round(hierarchy_authority, 4),
        "hierarchy_tier": str(tier_label or "UNKNOWN"),
        "source_trust": round(source_trust, 4),
        "independence_factor": int(independence),
        "independence_term": round(indep_term, 4),
        "stance_multiplier": round(stance_mult, 4),
        "retracted": retracted,
        "retracted_factor": retracted_factor,
        "falsifiability": fal_label,
        "falsifiability_trust": fal_factor,
        "raw_product": round(raw, 6),
    }

    reasoning = (
        f"base={base:.2f} × decay={time_decay:.2f} × "
        f"trust={source_trust:.2f}(rep={source_reputation:.2f},auth={hierarchy_authority:.2f}) × "
        f"indep^{independence}={indep_term:.2f} × stance={stance_mult:.2f} × "
        f"ret={retracted_factor:.2f} × fal[{fal_label}]={fal_factor:.2f} "
        f"→ {score:.3f}"
    )

    # DB 업데이트 (있으면)
    if fact.id:
        try:
            await prisma.knowledgefact.update(
                where={"id": fact.id},
                data={"arbitratedScore": score},
            )
        except Exception as exc:  # 스키마에 arbitratedScore 가 아직 없을 수 있음
            logger.debug("arbitratedScore update skipped: %s", exc)

    return {"score": score, "breakdown": breakdown, "reasoning": reasoning}


# ─────────────────────────────────────────────────────────────
# 배치
# ─────────────────────────────────────────────────────────────
async def batch_arbitrate(
    domain: str | None = None, limit: int = 500
) -> dict:
    """CONFIRMED 사실 전체의 arbitrated_score 를 재계산한다."""
    where: dict[str, Any] = {"status": KnowledgeStatus.CONFIRMED.value}
    if domain:
        where["domain"] = domain

    try:
        rows = await prisma.knowledgefact.find_many(
            where=where, take=limit, order={"lastVerifiedAt": "desc"}
        )
    except Exception:
        rows = []

    processed = 0
    updated = 0
    failed = 0
    score_sum = 0.0

    for r in rows:
        processed += 1
        try:
            fact = _row_to_fact(r)
            res = await arbitrated_confidence(fact)
            score_sum += res["score"]
            updated += 1
        except Exception as exc:
            failed += 1
            logger.warning("batch_arbitrate failed for %s: %s", r.id, exc)

    avg = (score_sum / updated) if updated else 0.0
    return {
        "processed": processed,
        "updated": updated,
        "failed": failed,
        "avg_score": round(avg, 4),
        "domain": domain,
    }


# ─────────────────────────────────────────────────────────────
# 질의 종합 답변
# ─────────────────────────────────────────────────────────────
async def arbitrate_answer(
    question: str, facts: list[KnowledgeFact]
) -> dict:
    """검색 결과 사실들을 arbitrated_confidence 로 재랭킹하고,
    반대 증거 + 경고 + verdict 를 담은 종합 답변 dict 를 반환.
    """
    # 1) 각 사실에 점수 부여
    ranked: list[dict] = []
    for f in facts:
        try:
            res = await arbitrated_confidence(f)
        except Exception as exc:
            logger.warning("score fail: %s", exc)
            res = {"score": f.confidence_t0, "breakdown": {}, "reasoning": f"error: {exc}"}
        ranked.append(
            {
                "fact": {
                    "id": f.id,
                    "content": f.content,
                    "source": f.source,
                    "source_url": f.source_url,
                    "domain": f.domain,
                    "entity": f.entity,
                    "status": f.status.value if hasattr(f.status, "value") else str(f.status),
                },
                "arbitrated_score": res["score"],
                "breakdown": res["breakdown"],
                "reasoning": res.get("reasoning", ""),
            }
        )
    ranked.sort(key=lambda x: x["arbitrated_score"], reverse=True)

    # 2) 반대 증거 수집 (lazy)
    counter: list[KnowledgeFact] = []
    echo_report: dict = {}
    warnings: list[str] = []

    try:
        from .counter_evidence import (
            gather_counter_evidence,
            build_balanced_answer,
            detect_echo_chamber,
            warn_if_minority_view,
        )

        # 상위 5건을 primary 로 간주
        top_primary = facts[:5]
        domain_hint = top_primary[0].domain if top_primary else None
        counter = await gather_counter_evidence(
            top_primary, domain=domain_hint, top_k=5
        )

        # 균형 답변 (supporting=top_primary, opposing=counter)
        balanced = await build_balanced_answer(question, top_primary, counter)

        # echo chamber 검사
        echo_report = await detect_echo_chamber(top_primary)
        if echo_report.get("is_echo"):
            warnings.append(
                "이 답변의 주된 출처는 같은 원본의 복사본들입니다 "
                f"(원본 {echo_report.get('unique_originals')}개 / 총 {echo_report.get('total')}건)."
            )

        # 소수 입장 경고 (1위 사실 기준)
        if top_primary:
            minority = await warn_if_minority_view(top_primary[0])
            if minority and minority.get("minority"):
                warnings.append(minority.get("warning", "소수 입장입니다."))

    except Exception as exc:
        logger.debug("counter_evidence stage failed: %s", exc)
        balanced = {
            "main_claim": facts[0].content if facts else "",
            "supporting_evidence": [],
            "opposing_evidence": [],
            "consensus_strength": 1.0,
            "perspective_summary": "",
            "display_mode": "consensus",
        }

    # 3) falsifiability / stance 관련 경고
    for r in ranked[:3]:
        bd = r.get("breakdown", {})
        if bd.get("falsifiability") == "VALUE_JUDGMENT":
            warnings.append("반증 불가능한 가치 판단이 포함되어 있습니다.")
            break
    for r in ranked[:3]:
        if r.get("breakdown", {}).get("retracted"):
            warnings.append("철회(retracted)된 사실이 답변에 포함되어 있습니다.")
            break

    # 4) verdict 판정
    top_score = ranked[0]["arbitrated_score"] if ranked else 0.0
    verdict = verdict_label(top_score, warnings)
    if counter and len(counter) >= len(facts) * 0.7:
        verdict = "contested"

    # 5) display_advice (LLM 간단 생성)
    display_advice = _verdict_advice(verdict, warnings)

    return {
        "question": question,
        "top_facts": ranked[:10],
        "counter_evidence": [
            {
                "id": f.id,
                "content": f.content,
                "source": f.source,
                "source_url": f.source_url,
            }
            for f in counter
        ],
        "balanced_answer": balanced,
        "echo_chamber": echo_report,
        "warnings": warnings,
        "trust_verdict": verdict,
        "display_advice": display_advice,
    }


def _verdict_advice(verdict: str, warnings: list[str]) -> str:
    """verdict + 경고 수에 따른 간단 한국어 가이드."""
    if verdict == "high":
        return "신뢰도 높음 — 일반적인 맥락에서 안심하고 사용 가능합니다."
    if verdict == "contested":
        return "논쟁 중 — 양측 입장을 함께 제시하고 사용자가 직접 판단하게 하세요."
    if verdict == "medium":
        if warnings:
            return "주의해서 해석하세요 — 아래 경고를 함께 안내하세요."
        return "보통 신뢰도 — 맥락을 덧붙여 전달하세요."
    return "낮은 신뢰도 — 재검증 또는 상위 출처 확인 후 사용하세요."


# ─────────────────────────────────────────────────────────────
# verdict
# ─────────────────────────────────────────────────────────────
def verdict_label(score: float, warnings: list[str]) -> str:
    """점수 + 경고 수로 verdict 라벨을 결정.

    규칙:
      - score ≥ 0.85 AND 경고 없음 → ``high``
      - score ≥ 0.60 OR 경고 2건 이하 → ``medium``
      - score < 0.40 OR 경고 3건 이상 → ``low``
      - (호출측에서 반대 증거 많음이면 ``contested`` 로 override 가능)
    """
    n_warn = len(warnings or [])
    if score >= _HIGH_MIN and n_warn == 0:
        return "high"
    if score < _LOW_MAX or n_warn >= 3:
        return "low"
    if score >= _MEDIUM_MIN or n_warn <= 2:
        return "medium"
    return "medium"


# ─────────────────────────────────────────────────────────────
# 설명 / 감사
# ─────────────────────────────────────────────────────────────
async def explain_arbitration(fact_id: str) -> str:
    """특정 사실의 arbitrated_score 계산 내역을 한국어 마크다운으로 리포트."""
    row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if row is None:
        return f"# 중재 리포트\n\n사실 `{fact_id}` 을 찾을 수 없습니다."

    fact = _row_to_fact(row)
    res = await arbitrated_confidence(fact)
    bd = res["breakdown"]

    lines = [
        f"# 중재(arbitration) 리포트 — {fact_id}",
        "",
        f"**최종 점수: {res['score']:.3f}**",
        "",
        "## 계산 내역",
        "",
        f"- 기초 신뢰도(base): `{bd.get('base_confidence')}`",
        f"- 시간 감쇠(time_decay): `{bd.get('time_decay')}`",
        f"- 출처 평판(source_reputation): `{bd.get('source_reputation')}`",
        f"- 위계 권위(hierarchy_authority): `{bd.get('hierarchy_authority')}` "
        f"(tier: {bd.get('hierarchy_tier')})",
        f"- 결합 trust: `{bd.get('source_trust')}` (= 평판×0.3 + 권위×0.7)",
        f"- 독립 출처 수: `{bd.get('independence_factor')}` "
        f"→ 보너스 계수 `{bd.get('independence_term')}`",
        f"- 입장 가중치(stance): `{bd.get('stance_multiplier')}`",
        f"- 철회 페널티(retracted): `{bd.get('retracted_factor')}` "
        f"(retracted={bd.get('retracted')})",
        f"- 반증가능성(falsifiability): `{bd.get('falsifiability')}` "
        f"× `{bd.get('falsifiability_trust')}`",
        "",
        "## 공식",
        "",
        "```",
        "final = base × time_decay",
        "      × (reputation × 0.3 + authority × 0.7)",
        "      × (1 + log2(max(1, independence)) × 0.2)",
        "      × stance_mult × retracted × falsifiability",
        "```",
        "",
        "## 요약",
        "",
        f"- {res['reasoning']}",
    ]
    return "\n".join(lines)


async def full_trust_audit(fact_id: str) -> dict:
    """한 사실에 대해 TAL 모든 차원을 종합한 감사 리포트."""
    row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if row is None:
        return {"fact_id": fact_id, "error": "not_found"}

    fact = _row_to_fact(row)

    # 점수
    arbitration = await arbitrated_confidence(fact)

    # 위계
    tier = getattr(row, "sourceTier", None) or arbitration["breakdown"].get("hierarchy_tier")
    authority = getattr(row, "sourceAuthority", None) or arbitration["breakdown"].get(
        "hierarchy_authority"
    )

    # provenance
    prov_info: dict[str, Any] = {"type": "unknown", "original_id": None, "independence_count": 1}
    try:
        from .provenance import find_original_of, count_independent_sources  # type: ignore

        orig = await find_original_of(fact_id)
        prov_info["original_id"] = orig
        prov_info["type"] = "copy" if orig and orig != fact_id else "original"
        if fact.entity:
            try:
                prov_info["independence_count"] = await count_independent_sources(fact.entity)
            except Exception:
                prov_info["independence_count"] = arbitration["breakdown"].get(
                    "independence_factor", 1
                )
    except Exception:
        prov_info["independence_count"] = arbitration["breakdown"].get(
            "independence_factor", 1
        )

    # 평판
    reputation = await get_reputation(fact.source)

    # stance / falsifiability
    stance = getattr(row, "stance", None) or "factual"
    falsifiability = getattr(row, "falsifiability", None) or "UNCLEAR"

    # retraction
    retraction = {
        "retracted": bool(getattr(row, "retracted", False))
        or str(row.status) == KnowledgeStatus.RETRACTED.value,
        "reason": getattr(row, "expiredReason", None),
    }

    # claim decomposition (있으면)
    claim_decomposition: list[dict] = []
    try:
        claims = await prisma.knowledgeclaim.find_many(
            where={"factId": fact_id}, take=50
        )
        for c in claims:
            claim_decomposition.append(
                {
                    "id": c.id,
                    "content": getattr(c, "content", None),
                    "kind": getattr(c, "kind", None),
                    "confidence": float(getattr(c, "confidence", 0.0) or 0.0),
                }
            )
    except Exception:
        pass

    # counter evidence 수
    counter_count = 0
    try:
        from .counter_evidence import gather_counter_evidence

        counters = await gather_counter_evidence([fact], domain=fact.domain, top_k=10)
        counter_count = len(counters)
    except Exception:
        counter_count = 0

    # verdict
    warnings: list[str] = []
    if retraction["retracted"]:
        warnings.append("retracted")
    if str(falsifiability).upper() == "VALUE_JUDGMENT":
        warnings.append("value_judgment")
    if prov_info["independence_count"] <= 1 and counter_count == 0:
        warnings.append("single_source_no_counter")

    score = arbitration["score"]
    verdict = verdict_label(score, warnings)
    if counter_count >= 5:
        verdict = "contested"

    # 재검증 권고
    recommendations: list[str] = []
    try:
        from .falsifiability import should_auto_reverify  # type: ignore

        if should_auto_reverify(fact):
            recommendations.append("재검증 권장 (falsifiability rule)")
    except Exception:
        pass
    if str(tier or "UNKNOWN") in {"USER_GENERATED", "UNKNOWN"} and score < 0.7:
        recommendations.append("1차 출처로 업그레이드 권장")
    if counter_count >= 3 and verdict != "contested":
        recommendations.append("반대 증거 검토 후 status 재평가 권장")

    return {
        "fact_id": fact_id,
        "arbitrated_score": score,
        "hierarchy": {"tier": str(tier or "UNKNOWN"), "authority": float(authority or 0.0)},
        "provenance": prov_info,
        "reputation": reputation,
        "stance": stance,
        "falsifiability": falsifiability,
        "retraction": retraction,
        "claim_decomposition": claim_decomposition,
        "counter_evidence_count": counter_count,
        "breakdown": arbitration["breakdown"],
        "verdict": verdict,
        "recommendations": recommendations,
    }


__all__ = [
    "FALSIFIABILITY_TRUST",
    "falsifiability_trust_factor",
    "independence_bonus",
    "arbitrated_confidence",
    "batch_arbitrate",
    "arbitrate_answer",
    "verdict_label",
    "explain_arbitration",
    "full_trust_audit",
]
