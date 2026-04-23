"""HLKM TAL ⑦ — Counter-Evidence (반대 증거 통합).

핵심: 사용자 질의에 대한 답변에서 **지지 증거와 반박 증거를 동시에 제시**하여
편향을 방지한다. 같은 주제에 대해 서로 다른 입장이 공존할 때, 어느 한쪽만
보여주지 않고 양측을 비율과 함께 노출한다.

제공 기능:
  - ``gather_counter_evidence`` : 주어진 primary_facts 에 반박하는 사실 수집
  - ``build_balanced_answer``    : 지지/반대 비율로 display_mode 결정
  - ``detect_echo_chamber``      : 같은 원본 복사본에만 의존하는지 감지
  - ``find_stance_diverse_facts``: stance 별 분류 수집
  - ``summarize_perspectives``   : LLM 으로 다중 입장 중립 요약
  - ``compute_disagreement_score``: 0~1 불일치 지수
  - ``warn_if_minority_view``    : 소수 입장 경고

의존:
  - ``hwarang_api.db.prisma``
  - ``.contradiction.detect_contradiction``
  - ``.hierarchy.lookup_authority``
  - ``.provenance.find_original_of`` (복사본 추적)
  - ``.primary_source.fact_tier_rank_score``
  - ``.embeddings.embed_text, cosine``
  - ``.llm._chat`` (lazy)
"""

from __future__ import annotations

import logging
import math
import re
import struct
from typing import Any

from hwarang_api.db import prisma

from .embeddings import cosine, embed_text
from .types import KnowledgeFact, KnowledgeStatus

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────────────────────

# tier 권위 순위: 낮은 tier 는 반대 증거로 채택하지 않는다.
TIER_RANK: dict[str, int] = {
    "PRIMARY_OFFICIAL": 5,
    "PEER_REVIEWED": 4,
    "SPECIALIZED_MEDIA": 3,
    "GENERAL_MEDIA": 2,
    "USER_GENERATED": 1,
    "UNKNOWN": 0,
}

# 임베딩 유사도는 높지만 내용(수치/결론)이 달라야 "반대 증거" 자격.
_SIM_SAME_TOPIC = 0.6
_NUMBER_RE = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)")
_NEG_MARKERS = ("아니", "않", "없", "반대", "부정", "틀렸", "오류", "false", "not", "never")


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
        content_hash=getattr(row, "contentHash", None),
        embedding=_hex_to_floats(getattr(row, "embeddingHex", None)),
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


def _extract_numbers(text: str) -> set[str]:
    return {m.group(1).replace(",", "") for m in _NUMBER_RE.finditer(text)}


def _has_negation_conflict(a: str, b: str) -> bool:
    """한쪽은 긍정, 반대쪽은 부정 표현이 있으면 True."""
    a_low = (a or "").lower()
    b_low = (b or "").lower()
    a_neg = any(tok in a_low for tok in _NEG_MARKERS)
    b_neg = any(tok in b_low for tok in _NEG_MARKERS)
    return a_neg != b_neg


def _tier_rank(tier: str | None) -> int:
    return TIER_RANK.get(str(tier or "UNKNOWN"), 0)


def _min_tier_threshold(min_tier: str) -> int:
    return _tier_rank(min_tier)


# ─────────────────────────────────────────────────────────────
# 1) gather_counter_evidence
# ─────────────────────────────────────────────────────────────
async def gather_counter_evidence(
    primary_facts: list[KnowledgeFact],
    domain: str | None = None,
    top_k: int = 5,
    min_tier: str = "SPECIALIZED_MEDIA",
) -> list[KnowledgeFact]:
    """주어진 사실들에 모순되거나 반박하는 사실을 수집한다.

    방법:
      1) CONTRADICTS 엣지로 연결된 상대 사실
      2) 같은 entity + 유효기간 중첩 + 숫자/부정어 차이
      3) 임베딩은 유사하나(≥0.6) 핵심 수치/결론이 다른 사실

    낮은 tier(=USER_GENERATED 등)는 기본 제외. ``min_tier`` 아래 티어는 버림.
    """
    if not primary_facts:
        return []

    min_rank = _min_tier_threshold(min_tier)
    collected: dict[str, tuple[float, KnowledgeFact]] = {}

    # (1) CONTRADICTS 엣지 탐색
    primary_ids = [f.id for f in primary_facts if f.id]
    if primary_ids:
        try:
            edges = await prisma.knowledgeedge.find_many(
                where={
                    "relationType": "CONTRADICTS",
                    "OR": [
                        {"fromFactId": {"in": primary_ids}},
                        {"toFactId": {"in": primary_ids}},
                    ],
                },
                take=top_k * 4,
            )
        except Exception:
            edges = []
        opp_ids: set[str] = set()
        for e in edges:
            if e.fromFactId in primary_ids:
                opp_ids.add(e.toFactId)
            if e.toFactId in primary_ids:
                opp_ids.add(e.fromFactId)
        if opp_ids:
            rows = await prisma.knowledgefact.find_many(
                where={"id": {"in": list(opp_ids)}},
                take=top_k * 4,
            )
            for row in rows:
                rank = _tier_rank(getattr(row, "sourceTier", None))
                if rank < min_rank:
                    continue
                f = _row_to_fact(row)
                score = 1.0  # edge-based 는 최우선
                collected[f.id or row.id] = (score, f)

    # (2) 같은 entity + 시간 중첩 + 내용 상충
    entities = {f.entity for f in primary_facts if f.entity}
    if entities:
        where: dict[str, Any] = {
            "entity": {"in": list(entities)},
            "status": {"in": ["CONFIRMED", "PENDING"]},
        }
        if domain:
            where["domain"] = domain
        try:
            rows = await prisma.knowledgefact.find_many(where=where, take=top_k * 8)
        except Exception:
            rows = []
        primary_id_set = set(primary_ids)
        for row in rows:
            if row.id in primary_id_set or row.id in collected:
                continue
            rank = _tier_rank(getattr(row, "sourceTier", None))
            if rank < min_rank:
                continue
            other = _row_to_fact(row)
            # 어느 primary 하나라도 숫자/부정 충돌이 있으면 후보
            conflict_score = 0.0
            for p in primary_facts:
                if p.entity != other.entity:
                    continue
                p_nums = _extract_numbers(p.content)
                o_nums = _extract_numbers(other.content)
                if p_nums and o_nums and (p_nums - o_nums or o_nums - p_nums):
                    conflict_score = max(conflict_score, 0.7)
                if _has_negation_conflict(p.content, other.content):
                    conflict_score = max(conflict_score, 0.6)
            if conflict_score > 0:
                collected[other.id or row.id] = (conflict_score, other)

    # (3) 임베딩 유사하나 결론 다름 — 모순 감지기로 정밀 판정
    # 비용이 크므로 상위 소량에만 적용.
    if len(collected) < top_k:
        # lazy import 로 순환 회피
        from .contradiction import detect_contradiction

        # 후보 풀: 같은 도메인, primary 와 중복 아닌 최근 팩트
        where: dict[str, Any] = {
            "status": {"in": ["CONFIRMED", "PENDING"]},
        }
        if domain:
            where["domain"] = domain
        elif primary_facts:
            where["domain"] = primary_facts[0].domain
        try:
            rows = await prisma.knowledgefact.find_many(
                where=where,
                take=top_k * 10,
                order={"validFrom": "desc"},
            )
        except Exception:
            rows = []

        # 중심 임베딩 평균
        prim_vecs: list[list[float]] = []
        for p in primary_facts:
            v = p.embedding or await embed_text(p.content)
            if v:
                prim_vecs.append(v)

        primary_id_set = set(primary_ids)
        scanned = 0
        for row in rows:
            if scanned >= top_k * 3:
                break
            if row.id in primary_id_set or row.id in collected:
                continue
            rank = _tier_rank(getattr(row, "sourceTier", None))
            if rank < min_rank:
                continue
            other = _row_to_fact(row)
            o_vec = other.embedding or await embed_text(other.content)
            sim_max = 0.0
            for pv in prim_vecs:
                s = cosine(pv, o_vec)
                if s > sim_max:
                    sim_max = s
            if sim_max < _SIM_SAME_TOPIC:
                continue
            scanned += 1
            # 정밀 모순 판정 (하나의 primary 와만 비교 — 비용 절감)
            if not primary_facts:
                continue
            report = await detect_contradiction(primary_facts[0], other)
            if report.is_contradiction and report.confidence >= 0.5:
                collected[other.id or row.id] = (report.confidence, other)

    ranked = sorted(collected.values(), key=lambda x: x[0], reverse=True)
    return [f for _, f in ranked[:top_k]]


# ─────────────────────────────────────────────────────────────
# 2) build_balanced_answer
# ─────────────────────────────────────────────────────────────
def _fact_dict(fact: KnowledgeFact) -> dict:
    return {
        "id": fact.id,
        "content": fact.content,
        "source": fact.source,
        "source_url": fact.source_url,
        "domain": fact.domain,
        "entity": fact.entity,
        "valid_from": fact.valid_from.isoformat() if fact.valid_from else None,
        "confidence_t0": fact.confidence_t0,
        "status": fact.status.value if hasattr(fact.status, "value") else str(fact.status),
    }


async def build_balanced_answer(
    question: str,
    supporting: list[KnowledgeFact],
    opposing: list[KnowledgeFact],
) -> dict:
    """지지/반대 증거를 조합해 균형 잡힌 답변 번들을 만든다.

    display_mode 판정:
      - 반대 비율 < 30%  → ``consensus``   (소수 의견 보조 표시)
      - 30% ~ 70%        → ``balanced``    (양측 동등 표시)
      - ≥ 70%            → ``contested``   (논쟁 중임을 명시)
    """
    n_sup = len(supporting)
    n_opp = len(opposing)
    total = max(1, n_sup + n_opp)
    opp_ratio = n_opp / total

    if opp_ratio < 0.3:
        display_mode = "consensus"
    elif opp_ratio < 0.7:
        display_mode = "balanced"
    else:
        display_mode = "contested"

    # 지지가 많은 경우는 1위 지지 사실을 main_claim 으로, 아니면 양측 명시.
    if supporting and display_mode != "contested":
        main_claim = supporting[0].content
    elif opposing and display_mode == "contested":
        main_claim = (
            f"이 주제는 논쟁 중입니다. 대표 입장 A: {supporting[0].content if supporting else '(없음)'} "
            f"/ 대표 입장 B: {opposing[0].content}"
        )
    elif supporting:
        main_claim = supporting[0].content
    else:
        main_claim = "관련 사실이 부족합니다."

    # 합의 강도: 지지 비율
    consensus_strength = round(1.0 - opp_ratio, 3)

    # LLM 요약 (실패 시 규칙 기반 문장)
    perspective_summary = await _safe_perspective_summary(supporting, opposing)

    return {
        "main_claim": main_claim,
        "supporting_evidence": [_fact_dict(f) for f in supporting],
        "opposing_evidence": [_fact_dict(f) for f in opposing],
        "consensus_strength": consensus_strength,
        "perspective_summary": perspective_summary,
        "display_mode": display_mode,
    }


async def _safe_perspective_summary(
    supporting: list[KnowledgeFact], opposing: list[KnowledgeFact]
) -> str:
    """LLM 요약 시도 후 실패 시 간단 템플릿."""
    try:
        from .llm import _chat  # type: ignore

        sup_txt = "\n".join(f"- {f.content[:200]}" for f in supporting[:3]) or "(없음)"
        opp_txt = "\n".join(f"- {f.content[:200]}" for f in opposing[:3]) or "(없음)"
        prompt = (
            "다음 지지 증거와 반대 증거를 바탕으로 중립적으로 2~3문장으로 "
            '"다수 입장 X, 소수 입장 Y" 형식의 한국어 요약을 만들어라.\n\n'
            f"[지지]\n{sup_txt}\n\n[반대]\n{opp_txt}"
        )
        resp = await _chat(prompt, system="You summarize two sides neutrally in Korean.", max_tokens=200)
        if resp and resp.strip():
            return resp.strip()
    except Exception as exc:  # pragma: no cover
        logger.debug("perspective summary LLM failed: %s", exc)

    n_s, n_o = len(supporting), len(opposing)
    if n_o == 0:
        return f"지지 {n_s}건, 반대 증거 없음 — 비교적 합의된 주제."
    if n_s == 0:
        return f"반대 {n_o}건 만 존재 — 반증 중심 주제."
    return f"다수 입장은 지지({n_s}건)이며, 소수 입장으로 반대({n_o}건)가 공존함."


# ─────────────────────────────────────────────────────────────
# 3) detect_echo_chamber
# ─────────────────────────────────────────────────────────────
async def detect_echo_chamber(primary_facts: list[KnowledgeFact]) -> dict:
    """primary_facts 가 실제로 독립 출처에 기반하는지 검사한다.

    같은 ``originalFactId`` (복사/재전재) 비율이 높으면 echo chamber 경고.
    """
    total = len(primary_facts)
    if total == 0:
        return {
            "is_echo": False,
            "unique_originals": 0,
            "total": 0,
            "dominant_source_family": None,
        }

    originals: list[str] = []
    source_families: dict[str, int] = {}

    # lazy import 로 순환 방지 + provenance 모듈 선택적
    try:
        from .provenance import find_original_of  # type: ignore
        prov_ok = True
    except Exception:
        prov_ok = False

    for f in primary_facts:
        # 출처 도메인 집계
        fam = (f.source or "").split(".")[-2:] if f.source else []
        fam_key = ".".join(fam) if fam else (f.source or "unknown")
        source_families[fam_key] = source_families.get(fam_key, 0) + 1

        if prov_ok and f.id:
            try:
                orig = await find_original_of(f.id)
            except Exception:
                orig = None
            originals.append(orig or f.id or "")
        else:
            originals.append(f.id or "")

    unique_originals = len(set(o for o in originals if o))
    # 독립성 판정: 원본이 3개 중 1개 이하면 echo
    is_echo = total >= 2 and unique_originals <= max(1, total // 3)

    dominant = None
    if source_families:
        dominant = max(source_families.items(), key=lambda kv: kv[1])[0]
        # 60% 이상 점유면 dominant_source_family 로 보고
        if source_families[dominant] / total < 0.6:
            dominant = None

    return {
        "is_echo": is_echo,
        "unique_originals": unique_originals,
        "total": total,
        "dominant_source_family": dominant,
    }


# ─────────────────────────────────────────────────────────────
# 4) find_stance_diverse_facts
# ─────────────────────────────────────────────────────────────
async def find_stance_diverse_facts(entity: str) -> dict:
    """동일 entity 에 대해 stance 가 다른 사실들을 버킷화한다.

    stance 필드는 {factual, interpretation, opinion, contested} 중 하나로 가정.
    """
    buckets: dict[str, list[dict]] = {
        "factual": [],
        "interpretation": [],
        "opinion": [],
        "contested": [],
    }
    if not entity:
        return buckets

    try:
        rows = await prisma.knowledgefact.find_many(
            where={
                "entity": entity,
                "status": {"in": ["CONFIRMED", "PENDING", "DISPUTED"]},
            },
            take=200,
            order={"validFrom": "desc"},
        )
    except Exception:
        rows = []

    for row in rows:
        stance = (getattr(row, "stance", None) or "factual").lower()
        if stance not in buckets:
            stance = "factual"
        buckets[stance].append(_fact_dict(_row_to_fact(row)))

    return buckets


# ─────────────────────────────────────────────────────────────
# 5) summarize_perspectives
# ─────────────────────────────────────────────────────────────
async def summarize_perspectives(entity: str) -> str:
    """특정 주제/엔티티에 대한 서로 다른 입장을 LLM 으로 중립 요약."""
    if not entity:
        return "대상 엔티티가 지정되지 않았습니다."

    buckets = await find_stance_diverse_facts(entity)
    # 샘플 수집: 각 버킷에서 최대 3건
    sections: list[str] = []
    for key in ("factual", "interpretation", "opinion", "contested"):
        items = buckets.get(key, [])[:3]
        if not items:
            continue
        joined = "\n".join(f"- {it['content'][:180]}" for it in items)
        sections.append(f"[{key}]\n{joined}")

    if not sections:
        return f"'{entity}' 에 대한 기록이 부족해 입장을 요약할 수 없습니다."

    body = "\n\n".join(sections)
    try:
        from .llm import _chat  # type: ignore

        prompt = (
            f"다음은 '{entity}' 에 대한 다양한 기록이다. "
            "진보/보수, 찬성/반대, 주류/비주류 등 서로 다른 입장을 포함하여 "
            "중립적인 어조로 3~5문장으로 한국어 요약을 제공하라. 특정 입장을 옹호하지 말 것.\n\n"
            f"{body}"
        )
        resp = await _chat(
            prompt,
            system="You are a neutral analyst. Summarize multiple perspectives in Korean.",
            max_tokens=400,
        )
        if resp and resp.strip():
            return resp.strip()
    except Exception as exc:  # pragma: no cover
        logger.debug("summarize_perspectives LLM failed: %s", exc)

    return (
        f"'{entity}' 에 대해 사실({len(buckets['factual'])}), "
        f"해석({len(buckets['interpretation'])}), "
        f"의견({len(buckets['opinion'])}), "
        f"논쟁({len(buckets['contested'])}) 입장이 공존한다."
    )


# ─────────────────────────────────────────────────────────────
# 6) compute_disagreement_score
# ─────────────────────────────────────────────────────────────
def compute_disagreement_score(supporting: list, opposing: list) -> float:
    """0~1. 0 = 완전 합의, 1 = 완전 대립.

    가중치: 각 사실의 arbitrated_score(없으면 confidence_t0) 합을 비교.
    """
    def _weight(f: Any) -> float:
        if f is None:
            return 0.0
        # 객체/딕셔너리 양쪽 지원
        if isinstance(f, dict):
            return float(f.get("arbitrated_score") or f.get("confidence_t0") or 0.5)
        score = getattr(f, "arbitrated_score", None)
        if score is None:
            score = getattr(f, "confidence_t0", 0.5)
        try:
            return float(score)
        except Exception:
            return 0.5

    sup_w = sum(_weight(f) for f in supporting)
    opp_w = sum(_weight(f) for f in opposing)
    total = sup_w + opp_w
    if total <= 0:
        return 0.0

    opp_ratio = opp_w / total
    # opp_ratio=0 → 0(합의), 0.5 → 1(정확히 대립), 1.0 → 1 (반대 일색)
    # 대립도는 0.5 에서 최대 → 거리로 변환: 1 - |0.5 - opp_ratio| * 2
    disagreement = 1.0 - abs(0.5 - opp_ratio) * 2
    # 반대쪽이 아예 없으면 합의 → 0
    if opp_w == 0:
        return 0.0
    # 반대 일색이면 강한 대립으로 간주
    if sup_w == 0:
        return 1.0
    return round(max(0.0, min(1.0, disagreement)), 3)


# ─────────────────────────────────────────────────────────────
# 7) warn_if_minority_view
# ─────────────────────────────────────────────────────────────
async def warn_if_minority_view(fact: KnowledgeFact) -> dict | None:
    """이 사실이 소수 입장인지 감지하고 경고 메시지를 생성한다.

    같은 entity 에서 반대 사실(CONTRADICTS 엣지 또는 수치 충돌)이 다수인 경우 경고.
    """
    if not fact or not fact.entity:
        return None

    # 같은 entity 사실들 모집
    try:
        rows = await prisma.knowledgefact.find_many(
            where={
                "entity": fact.entity,
                "status": {"in": ["CONFIRMED", "PENDING"]},
            },
            take=100,
        )
    except Exception:
        rows = []

    if len(rows) < 3:
        return None

    same_ids = {r.id for r in rows if r.id != fact.id}
    # CONTRADICTS 엣지로 연결된 상대 수
    opp_ids: set[str] = set()
    if fact.id:
        try:
            edges = await prisma.knowledgeedge.find_many(
                where={
                    "relationType": "CONTRADICTS",
                    "OR": [
                        {"fromFactId": fact.id},
                        {"toFactId": fact.id},
                    ],
                },
                take=200,
            )
        except Exception:
            edges = []
        for e in edges:
            if e.fromFactId == fact.id and e.toFactId in same_ids:
                opp_ids.add(e.toFactId)
            if e.toFactId == fact.id and e.fromFactId in same_ids:
                opp_ids.add(e.fromFactId)

    # 수치 충돌 기반 대립 추정
    my_nums = _extract_numbers(fact.content)
    for r in rows:
        if r.id in opp_ids or r.id == fact.id:
            continue
        o_nums = _extract_numbers(r.content)
        if my_nums and o_nums and (my_nums - o_nums or o_nums - my_nums):
            opp_ids.add(r.id)

    total = len(rows)
    n_opp = len(opp_ids)
    # 본인 지지측 = total - opp - self
    n_sup = max(1, total - n_opp - 1)

    is_minority = n_opp >= n_sup * 2  # 반대가 지지의 2배 이상
    if not is_minority:
        return None

    return {
        "fact_id": fact.id,
        "entity": fact.entity,
        "minority": True,
        "supporting_count": n_sup,
        "opposing_count": n_opp,
        "warning": (
            f"[소수 입장 경고] 이 사실(entity={fact.entity})은 다수와 배치됩니다. "
            f"반대 {n_opp}건 vs 지지 {n_sup}건. 답변 시 '소수 의견'으로 표시 권장."
        ),
    }


__all__ = [
    "TIER_RANK",
    "gather_counter_evidence",
    "build_balanced_answer",
    "detect_echo_chamber",
    "find_stance_diverse_facts",
    "summarize_perspectives",
    "compute_disagreement_score",
    "warn_if_minority_view",
]
