"""HLKM ⑤ Consensus Mechanism — 다출처 합의 검증.

도메인별 정책(DOMAIN_CONSENSUS_POLICY)을 기준으로,
하나의 사실이 몇 개의 독립적 출처에 의해 뒷받침되는지 평가한다.

핵심 개념:
  - 정책 충족: 최소 출처 수, 공식/학술 요구, 독립성 여부
  - 독립성: 서로 다른 상위 도메인(law.go.kr vs supremecourt.go.kr → OK)
  - 보강 팩트: 임베딩 유사 + 동일 엔티티 + 모순 없음
  - 보강되면 신뢰도 부스트 (+0.2 까지), 정책 미달이면 PENDING 유지

의존:
  - `hwarang_api.db.prisma`
  - `.embeddings.embed_text, cosine`
  - `.contradiction.detect_contradiction` (간접 호출)
  - `.reputation.classify_source_type`
"""

from __future__ import annotations

import logging
import struct
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from hwarang_api.db import prisma

from .embeddings import cosine, embed_text
from .reputation import classify_source_type
from .types import KnowledgeFact, KnowledgeStatus

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# 도메인별 정책
# ─────────────────────────────────────────────
DOMAIN_CONSENSUS_POLICY: dict[str, dict] = {
    "law": {
        "min_sources": 2,
        "require_official": True,
        "max_age_days": 365,
    },
    "medical": {
        "min_sources": 3,
        "require_peer_reviewed": True,
    },
    "tech": {
        "min_sources": 1,
    },
    "news": {
        "min_sources": 2,
        "require_independent": True,
    },
    "general": {
        "min_sources": 1,
    },
}

_SIM_FOR_CORROBORATION = 0.75   # 이 이상이면 "같은 내용" 으로 간주
_BOOST_MAX = 0.2                # 최대 부스트
_BOOST_PER_EXTRA_SOURCE = 0.05  # 추가 독립 출처 하나당 +0.05


# ─────────────────────────────────────────────
# 도메인 추출 / 독립성
# ─────────────────────────────────────────────
def extract_source_domain(source_or_url: str) -> str:
    """출처 또는 URL 에서 정규화된 도메인을 추출한다.

    예)
      https://blog.naver.com/abc    → blog.naver.com
      law.go.kr                     → law.go.kr
      "User: alice"                 → user:alice
    """
    s = (source_or_url or "").strip()
    if not s:
        return ""

    # URL 형식 우선
    if "://" in s:
        host = urlparse(s).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host

    low = s.lower()
    # 사용자/기관 명명 관례 ("user: alice", "community/foo")
    if low.startswith(("user:", "community:", "agent:")):
        return low.replace(" ", "")

    # 호스트-like 문자열
    if "." in low and " " not in low:
        if low.startswith("www."):
            low = low[4:]
        return low
    return low


async def are_sources_independent(source_a: str, source_b: str) -> bool:
    """두 출처가 독립적인지 판정한다.

    규칙 (간이):
      - 빈 값 / 동일 문자열 → False
      - 도메인이 동일 → False (같은 사이트 다른 글)
      - 부모 도메인 공유(blog.naver.com vs cafe.naver.com) → False
      - 그 외 → True
    """
    if not source_a or not source_b:
        return False
    if source_a == source_b:
        return False

    da = extract_source_domain(source_a)
    db = extract_source_domain(source_b)
    if not da or not db:
        return False
    if da == db:
        return False

    # 공통 2차 도메인 공유(naver.com) 검사
    parts_a = [p for p in da.split(".") if p]
    parts_b = [p for p in db.split(".") if p]
    if len(parts_a) >= 2 and len(parts_b) >= 2:
        tail_a = ".".join(parts_a[-2:])
        tail_b = ".".join(parts_b[-2:])
        # .go.kr / .co.kr / .gov.kr 등 2차가 퍼블릭 서픽스인 경우는
        # 3차까지 비교해야 하므로 예외 처리.
        public_suffixes = {"go.kr", "co.kr", "ne.kr", "or.kr", "ac.kr", "gov.kr"}
        if tail_a in public_suffixes and len(parts_a) >= 3:
            tail_a = ".".join(parts_a[-3:])
        if tail_b in public_suffixes and len(parts_b) >= 3:
            tail_b = ".".join(parts_b[-3:])
        if tail_a == tail_b:
            return False
    return True


# ─────────────────────────────────────────────
# 유틸 (Prisma row → KnowledgeFact)
# ─────────────────────────────────────────────
def _hex_to_floats(hex_str: str | None) -> list[float] | None:
    if not hex_str:
        return None
    try:
        raw = bytes.fromhex(hex_str)
        count = len(raw) // 4
        return list(struct.unpack(f"<{count}f", raw)) if count else None
    except Exception:
        return None


def _row_to_fact(row: Any) -> KnowledgeFact:
    return KnowledgeFact(
        id=row.id,
        content=row.content,
        content_hash=row.contentHash,
        embedding=_hex_to_floats(getattr(row, "embeddingHex", None)),
        domain=row.domain,
        entity=row.entity,
        tags=list(row.tags or []),
        language=row.language,
        valid_from=row.validFrom,
        valid_to=row.validTo,
        created_at=row.createdAt,
        last_verified_at=row.lastVerifiedAt,
        next_check_at=row.nextCheckAt,
        confidence_t0=float(row.confidenceT0),
        half_life_days=row.halfLifeDays,
        status=KnowledgeStatus(row.status),
        source=row.source,
        source_url=row.sourceUrl,
    )


# ─────────────────────────────────────────────
# 핵심 로직
# ─────────────────────────────────────────────
async def find_corroborating_facts(
    fact: KnowledgeFact, top_k: int = 5
) -> list[KnowledgeFact]:
    """동일 주제의 보강(corroborating) 팩트를 탐색한다.

    조건:
      - 서로 다른 출처 (완전 일치 X)
      - 엔티티 동일 또는 임베딩 유사도 ≥ 0.75
      - CONTRADICTS 엣지로 연결된 팩트 제외
      - status ∈ {CONFIRMED, PENDING}
    """
    # 후보 탐색 — 동일 도메인/엔티티 기반 1차 필터.
    where: dict[str, Any] = {
        "status": {"in": ["CONFIRMED", "PENDING"]},
        "source": {"not": fact.source},
    }
    if fact.entity:
        where = {
            "AND": [
                {"status": {"in": ["CONFIRMED", "PENDING"]}},
                {"source": {"not": fact.source}},
                {"OR": [{"entity": fact.entity}, {"domain": fact.domain}]},
            ]
        }
    else:
        where = {
            "AND": [
                {"status": {"in": ["CONFIRMED", "PENDING"]}},
                {"source": {"not": fact.source}},
                {"domain": fact.domain},
            ]
        }

    rows = await prisma.knowledgefact.find_many(where=where, take=top_k * 6)
    if not rows:
        return []

    # 모순 상대 set 수집
    excluded_ids: set[str] = set()
    if fact.id:
        edges = await prisma.knowledgeedge.find_many(
            where={
                "OR": [
                    {"fromFactId": fact.id, "relationType": "CONTRADICTS"},
                    {"toFactId": fact.id, "relationType": "CONTRADICTS"},
                ]
            },
            take=200,
        )
        for e in edges:
            excluded_ids.add(e.fromFactId)
            excluded_ids.add(e.toFactId)

    query_vec = fact.embedding or await embed_text(fact.content)
    scored: list[tuple[float, KnowledgeFact]] = []
    for row in rows:
        if row.id == fact.id or row.id in excluded_ids:
            continue
        other = _row_to_fact(row)
        other_vec = other.embedding or await embed_text(other.content)
        sim = cosine(query_vec, other_vec)
        same_entity = bool(
            fact.entity and other.entity and fact.entity == other.entity
        )
        if sim >= _SIM_FOR_CORROBORATION or same_entity:
            scored.append((sim + (0.1 if same_entity else 0.0), other))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in scored[:top_k]]


async def evaluate_consensus(
    fact: KnowledgeFact, similar_facts: list[KnowledgeFact]
) -> dict:
    """주어진 보강 팩트들을 바탕으로 정책 충족 여부를 평가한다.

    반환:
        {
          "meets_policy": bool,
          "sources_found": int,
          "policy": {...},
          "missing": [...],
          "recommendation": "confirm|hold|reject",
        }
    """
    policy = DOMAIN_CONSENSUS_POLICY.get(
        fact.domain, DOMAIN_CONSENSUS_POLICY["general"]
    )
    # 본인 출처 포함해서 distinct 출처 수.
    sources: set[str] = {fact.source}
    source_types: set[str] = {
        classify_source_type(fact.source_url, fact.source)
    }
    for f in similar_facts:
        sources.add(f.source)
        source_types.add(classify_source_type(f.source_url, f.source))

    missing: list[str] = []

    # 1) min_sources
    min_sources = int(policy.get("min_sources", 1))
    if len(sources) < min_sources:
        missing.append(f"need {min_sources} sources, found {len(sources)}")

    # 2) require_official
    if policy.get("require_official") and "official" not in source_types:
        missing.append("official source")

    # 3) require_peer_reviewed
    if policy.get("require_peer_reviewed") and "peer_reviewed" not in source_types:
        missing.append("peer-reviewed source")

    # 4) require_independent — 서로 다른 도메인 쌍 하나라도 있어야
    if policy.get("require_independent"):
        all_srcs = [fact.source] + [f.source for f in similar_facts]
        found_indep = False
        for i in range(len(all_srcs)):
            for j in range(i + 1, len(all_srcs)):
                if await are_sources_independent(all_srcs[i], all_srcs[j]):
                    found_indep = True
                    break
            if found_indep:
                break
        if not found_indep:
            missing.append("independent source pair")

    # 5) max_age_days — 최신 출처가 너무 오래됐으면 경고
    if "max_age_days" in policy:
        max_age = int(policy["max_age_days"])
        newest = fact.valid_from
        for f in similar_facts:
            if f.valid_from and f.valid_from > newest:
                newest = f.valid_from
        age = (datetime.now(timezone.utc) - _as_aware(newest)).days
        if age > max_age:
            missing.append(f"freshness: newest source is {age}d old > {max_age}d")

    meets = len(missing) == 0

    # 추천
    if meets:
        recommendation = "confirm"
    elif "official source" in missing or "peer-reviewed source" in missing:
        recommendation = "reject" if len(similar_facts) == 0 else "hold"
    else:
        recommendation = "hold"

    return {
        "meets_policy": meets,
        "sources_found": len(sources),
        "policy": dict(policy),
        "missing": missing,
        "recommendation": recommendation,
    }


async def consensus_confidence_boost(fact_id: str) -> float:
    """다출처 합의에 따른 신뢰도 부스트 값(0~0.2)을 반환한다.

    - 독립 출처 수 × 0.05, 최대 0.2
    - 보강 팩트 없으면 0
    """
    row = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if row is None:
        return 0.0
    fact = _row_to_fact(row)

    corroborators = await find_corroborating_facts(fact, top_k=8)
    if not corroborators:
        return 0.0

    # 본인과 독립인 출처만 카운트
    independent_count = 0
    for f in corroborators:
        if await are_sources_independent(fact.source, f.source):
            independent_count += 1

    boost = min(_BOOST_MAX, independent_count * _BOOST_PER_EXTRA_SOURCE)
    return round(boost, 4)


async def flag_for_consensus_wait(fact: KnowledgeFact) -> bool:
    """정책 미달이면 status=PENDING 으로 유지하고 notes 를 남긴다.

    반환: True = flag 적용됨, False = 정책 충족 → flag 없음.
    """
    if not fact.id:
        return False

    corroborators = await find_corroborating_facts(fact, top_k=5)
    result = await evaluate_consensus(fact, corroborators)
    if result["meets_policy"]:
        return False

    note = (
        f"[consensus-wait] missing={result['missing']} "
        f"sources_found={result['sources_found']} "
        f"at={datetime.now(timezone.utc).isoformat()}"
    )

    await prisma.knowledgefact.update(
        where={"id": fact.id},
        data={
            "status": KnowledgeStatus.PENDING.value,
            "expiredReason": note[:500],
        },
    )
    # 별도 Verification 로그로도 남긴다 (재검증 배치가 참조).
    try:
        await prisma.knowledgeverification.create(
            data={
                "factId": fact.id,
                "method": "community",
                "result": "unchanged",
                "confidenceDelta": 0.0,
                "notes": note[:1000],
            }
        )
    except Exception:
        pass
    logger.info("flag_for_consensus_wait: %s → PENDING (%s)", fact.id, result["missing"])
    return True


async def promote_when_consensus_met() -> int:
    """PENDING 팩트 중 정책을 새로 충족한 것을 CONFIRMED 로 승격.

    배치 잡에서 주기적으로 호출.
    반환: 승격된 레코드 수.
    """
    rows = await prisma.knowledgefact.find_many(
        where={"status": KnowledgeStatus.PENDING.value},
        take=500,
        order={"lastVerifiedAt": "asc"},
    )
    if not rows:
        return 0

    promoted = 0
    for row in rows:
        fact = _row_to_fact(row)
        corroborators = await find_corroborating_facts(fact, top_k=5)
        result = await evaluate_consensus(fact, corroborators)
        if not result["meets_policy"]:
            continue

        await prisma.knowledgefact.update(
            where={"id": fact.id},
            data={
                "status": KnowledgeStatus.CONFIRMED.value,
                "lastVerifiedAt": datetime.now(timezone.utc),
                "expiredReason": None,
            },
        )
        try:
            await prisma.knowledgeverification.create(
                data={
                    "factId": fact.id,
                    "method": "cross_source",
                    "result": "unchanged",
                    "confidenceDelta": 0.1,
                    "notes": (
                        f"promoted by consensus: "
                        f"{result['sources_found']} sources"
                    ),
                }
            )
        except Exception:
            pass
        promoted += 1

    logger.info("promote_when_consensus_met: %d facts promoted", promoted)
    return promoted


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────
def _as_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


__all__ = [
    "DOMAIN_CONSENSUS_POLICY",
    "extract_source_domain",
    "are_sources_independent",
    "find_corroborating_facts",
    "evaluate_consensus",
    "consensus_confidence_boost",
    "flag_for_consensus_wait",
    "promote_when_consensus_met",
]
