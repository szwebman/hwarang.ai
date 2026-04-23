"""HLKM TAL ② — Provenance Chain.

정보가 어디서 최초로 보도되고 어디로 퍼져나갔는지 추적한다.

핵심 아이디어
---------------
1. 같은 entity 의 기존 사실들과 신규 사실의 **자카드 + 임베딩 유사도** 를 계산.
2. 유사도 구간에 따라 관계를 분류:

   - 0.9 이상  → ``COPY_OF``  (거의 동일, 복사/전재)
   - 0.7~0.9   → ``TRANSLATION`` 또는 ``SUMMARY`` (LLM 또는 언어 비율로 구분)
   - 0.5~0.7   → ``DERIVED`` (해석/파생)
   - 그 미만   → ``INDEPENDENT`` (독립 보도)

3. 시간 순서상 **먼저 발행된 쪽을 원본** 으로 본다.
4. `ProvenanceEdge` 에 관계를 기록하고, 신규 사실의 `originalFactId` 에 최상위 원본 id 를 연결.

대규모 비교 시에는 simhash 해밍 거리로 1차 필터 후 자카드로 정밀 비교하면 빠르다.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from hwarang_api.db import prisma

from .embeddings import cosine, embed_text
from .llm import llm_check_semantic_equivalence
from .types import KnowledgeFact

# ─────────────────────────────────────────────────────────────
# 상수/임계치
# ─────────────────────────────────────────────────────────────
_COPY_THRESHOLD = 0.9          # 이 이상은 거의 동일 (복사/번역)
_SUMMARY_THRESHOLD = 0.7       # 이 이상은 요약/번역 의심
_DERIVED_THRESHOLD = 0.5       # 이 이상은 파생
_KOREAN_RATIO_SAME = 0.35      # 두 텍스트 한글 비율 차이가 이 값 이내면 동일 언어로 간주


# ─────────────────────────────────────────────────────────────
# 유틸: N-그램 / 언어 감지 / Simhash
# ─────────────────────────────────────────────────────────────
def _ngrams(text: str, n: int) -> set[str]:
    """문자 N-gram 집합. 공백은 하나로 축약.

    n <= 0 이거나 빈 문자열이면 빈 집합 반환.
    """
    if n <= 0 or not text:
        return set()
    t = re.sub(r"\s+", " ", text.strip())
    if len(t) < n:
        return {t} if t else set()
    return {t[i : i + n] for i in range(len(t) - n + 1)}


def _word_tokens(text: str) -> set[str]:
    """한국어 어절 + 영숫자 토큰 집합."""
    if not text:
        return set()
    return {tok for tok in re.split(r"\s+", text.strip()) if tok}


def _detect_korean_ratio(text: str) -> float:
    """문자열 내 한글 비율 (0~1). 한/영/숫자 합 중 한글이 차지하는 비율."""
    if not text:
        return 0.0
    hangul = 0
    total = 0
    for ch in text:
        code = ord(ch)
        if "가" <= ch <= "힣" or "ᄀ" <= ch <= "ᇿ":
            hangul += 1
            total += 1
        elif ch.isalnum():
            total += 1
    if total == 0:
        return 0.0
    return hangul / total


def jaccard_similarity(a: str, b: str, ngram: int = 3) -> float:
    """자카드 유사도.

    한국어 대응을 위해 **어절 집합** 과 **문자 n-gram 집합** 두 쪽에서 각각
    자카드를 구한 뒤 최대값을 반환한다. 둘 다 비어있으면 0.0.
    """
    if not a or not b:
        return 0.0

    def _jac(s1: set[str], s2: set[str]) -> float:
        if not s1 or not s2:
            return 0.0
        inter = len(s1 & s2)
        union = len(s1 | s2)
        return inter / union if union else 0.0

    word_sim = _jac(_word_tokens(a), _word_tokens(b))
    char_sim = _jac(_ngrams(a, ngram), _ngrams(b, ngram))
    return max(word_sim, char_sim)


def simhash_distance(a: str, b: str) -> int:
    """64-bit simhash 해밍 거리.

    대규모 후보 필터링용. 완전히 동일하면 0, 완전히 다르면 최대 64.
    """
    if not a and not b:
        return 0
    h_a = _simhash64(a)
    h_b = _simhash64(b)
    x = h_a ^ h_b
    # Python 3.10+ 에는 int.bit_count() 가 있음
    try:
        return int(x.bit_count())
    except AttributeError:
        return bin(x).count("1")


def _simhash64(text: str) -> int:
    """64-bit simhash. 어절 + 3gram 토큰 해시를 누적한다."""
    if not text:
        return 0
    tokens = list(_word_tokens(text)) + list(_ngrams(text, 3))
    if not tokens:
        return 0

    bits = [0] * 64
    for tok in tokens:
        digest = hashlib.md5(tok.encode("utf-8")).digest()
        h = int.from_bytes(digest[:8], "big", signed=False)
        for i in range(64):
            if h >> i & 1:
                bits[i] += 1
            else:
                bits[i] -= 1

    out = 0
    for i, v in enumerate(bits):
        if v > 0:
            out |= 1 << i
    return out


# ─────────────────────────────────────────────────────────────
# 복사 vs 번역 판정
# ─────────────────────────────────────────────────────────────
async def classify_copy_vs_translation(a: str, b: str) -> str:
    """두 텍스트가 "복사"인지 "번역"인지 판정.

    1. 두 텍스트의 한글 비율 차이가 `_KOREAN_RATIO_SAME` 이상이면 → 다른 언어로 보고 ``translation``.
    2. 그 외엔 LLM 호출로 의미 동치/언어 판정 시도.
    3. LLM 실패 시 자카드 + 한글 비율 조합으로 fallback.
    """
    ra = _detect_korean_ratio(a)
    rb = _detect_korean_ratio(b)
    ratio_gap = abs(ra - rb)

    if ratio_gap >= _KOREAN_RATIO_SAME:
        return "translation"

    # LLM 확인 (실패 시 빈 튜플 반환 → fallback)
    try:
        same, conf = await llm_check_semantic_equivalence(a, b)
    except Exception:
        same, conf = (False, 0.0)

    if same and conf >= 0.8:
        # 의미는 같은데 한글 비율이 비슷 → 같은 언어 복사
        return "copy_of"

    # fallback: 자카드 높으면 copy, 낮으면 translation
    jac = jaccard_similarity(a, b)
    if jac >= _COPY_THRESHOLD:
        return "copy_of"
    return "translation"


# ─────────────────────────────────────────────────────────────
# Provenance 관계 감지
# ─────────────────────────────────────────────────────────────
async def detect_provenance(
    new_fact: KnowledgeFact,
    candidates: list[KnowledgeFact],
    threshold: float = 0.7,
) -> dict[str, Any]:
    """신규 사실과 후보 사실들 사이의 관계 판정.

    가장 유사도가 높은 후보를 골라 관계(type)와 원본(original_id)을 결정한다.

    반환: ``{type, original_id, similarity, time_gap_hours, matched_fact_id}``

    - ``type`` ∈ INDEPENDENT/COPY_OF/TRANSLATION/QUOTATION/SUMMARY/DERIVED
    - 후보가 없으면 INDEPENDENT.
    """
    result: dict[str, Any] = {
        "type": "INDEPENDENT",
        "original_id": None,
        "similarity": 0.0,
        "time_gap_hours": 0.0,
        "matched_fact_id": None,
    }
    if not new_fact.content or not candidates:
        return result

    # 신규 임베딩 확보
    new_emb = new_fact.embedding
    if not new_emb:
        try:
            new_emb = await embed_text(new_fact.content)
        except Exception:
            new_emb = None

    best_sim = 0.0
    best_cand: KnowledgeFact | None = None

    for cand in candidates:
        if not cand.content or cand.id == new_fact.id:
            continue

        # 1차: 자카드
        jac = jaccard_similarity(new_fact.content, cand.content)

        # 2차: 임베딩 코사인 (있을 때만)
        emb_sim = 0.0
        if new_emb and cand.embedding:
            emb_sim = cosine(new_emb, cand.embedding)

        sim = max(jac, emb_sim)
        if sim > best_sim:
            best_sim = sim
            best_cand = cand

    if best_cand is None or best_sim < _DERIVED_THRESHOLD or best_sim < threshold:
        # 아무 것도 의미있게 비슷하지 않음 → 독립.
        # (단, threshold 미만이면 INDEPENDENT 로 남긴다.)
        if best_sim >= _DERIVED_THRESHOLD and best_cand is not None:
            # threshold 미만이지만 derived 는 된다면 기록만 해둔다.
            pass
        result["similarity"] = best_sim
        return result

    # 시간 순서로 원본 판단 (둘 중 먼저 나온 쪽이 원본)
    new_from = new_fact.valid_from or datetime.now(timezone.utc)
    cand_from = best_cand.valid_from or datetime.now(timezone.utc)
    gap_hours = abs((new_from - cand_from).total_seconds()) / 3600.0

    if cand_from <= new_from:
        original_id = best_cand.id
    else:
        # 신규가 더 오래된 경우 (재수집 시 가능) → 신규가 원본, 후보가 복사
        original_id = new_fact.id

    # 관계 분류
    if best_sim >= _COPY_THRESHOLD:
        kind = await classify_copy_vs_translation(new_fact.content, best_cand.content)
        rel_type = "TRANSLATION" if kind == "translation" else "COPY_OF"
    elif best_sim >= _SUMMARY_THRESHOLD:
        # 한글 비율 차이로 번역 vs 요약 구분
        ra = _detect_korean_ratio(new_fact.content)
        rb = _detect_korean_ratio(best_cand.content)
        if abs(ra - rb) >= _KOREAN_RATIO_SAME:
            rel_type = "TRANSLATION"
        else:
            rel_type = "SUMMARY"
    else:
        rel_type = "DERIVED"

    result.update(
        {
            "type": rel_type,
            "original_id": original_id,
            "similarity": best_sim,
            "time_gap_hours": gap_hours,
            "matched_fact_id": best_cand.id,
        }
    )
    return result


# ─────────────────────────────────────────────────────────────
# DB 기록/조회
# ─────────────────────────────────────────────────────────────
async def record_provenance_edge(
    source_fact_id: str,
    target_fact_id: str,
    relation: str,
    similarity: float,
    time_gap_hours: float,
    evidence: str | None = None,
) -> str:
    """`ProvenanceEdge` 삽입 (복사본→원본). 이미 있으면 기존 id 반환.

    `source_fact_id` 는 복사/파생한 쪽, `target_fact_id` 는 원본.
    """
    if not source_fact_id or not target_fact_id or source_fact_id == target_fact_id:
        return ""

    # unique([sourceFactId, targetFactId]) 에 걸리므로 중복 시 기존 반환
    existing = await prisma.provenanceedge.find_first(
        where={"sourceFactId": source_fact_id, "targetFactId": target_fact_id}
    )
    if existing:
        return existing.id

    created = await prisma.provenanceedge.create(
        data={
            "sourceFactId": source_fact_id,
            "targetFactId": target_fact_id,
            "relationType": relation,
            "similarity": max(0.0, min(1.0, float(similarity))),
            "timeGapHours": float(time_gap_hours),
            "evidence": evidence,
        }
    )
    return created.id


async def find_original_of(fact_id: str, max_hops: int = 20) -> str | None:
    """`fact_id` 의 **궁극 원본** 을 추적.

    `KnowledgeFact.originalFactId` 를 따라 체인을 거슬러 올라간다.
    순환이나 과도한 깊이는 `max_hops` 로 방어.
    자기 자신이 원본이면 ``None`` 반환.
    """
    if not fact_id:
        return None

    visited: set[str] = set()
    current = fact_id
    for _ in range(max_hops):
        if current in visited:
            break
        visited.add(current)
        try:
            row = await prisma.knowledgefact.find_unique(where={"id": current})
        except Exception:
            return None
        if not row:
            return None
        parent = row.originalFactId
        if not parent or parent == current:
            # 체인 종료 — current 가 원본
            return None if current == fact_id else current
        current = parent
    return None if current == fact_id else current


async def count_independent_sources(
    entity: str, as_of: datetime | None = None
) -> int:
    """주제 `entity` 의 **독립 원본** 개수.

    `originalFactId IS NULL` 인 사실만 센다. as_of 가 주어지면 그 시점까지의 것만.
    """
    where: dict[str, Any] = {"entity": entity, "originalFactId": None}
    if as_of is not None:
        where["validFrom"] = {"lte": as_of}
    try:
        return await prisma.knowledgefact.count(where=where)
    except Exception:
        return 0


async def list_copies_of(original_id: str) -> list[dict[str, Any]]:
    """원본의 모든 복사본 목록.

    `ProvenanceEdge` + `KnowledgeFact` 조인 형태로 반환한다. 각 항목::

        {edge_id, relation_type, similarity, time_gap_hours,
         fact_id, content, source, source_url, valid_from}
    """
    if not original_id:
        return []

    edges = await prisma.provenanceedge.find_many(
        where={"targetFactId": original_id},
        order={"detectedAt": "asc"},
    )
    if not edges:
        return []

    out: list[dict[str, Any]] = []
    for e in edges:
        fact = None
        try:
            fact = await prisma.knowledgefact.find_unique(
                where={"id": e.sourceFactId}
            )
        except Exception:
            fact = None

        out.append(
            {
                "edge_id": e.id,
                "relation_type": str(e.relationType),
                "similarity": float(e.similarity),
                "time_gap_hours": float(e.timeGapHours) if e.timeGapHours is not None else None,
                "fact_id": e.sourceFactId,
                "content": fact.content if fact else None,
                "source": fact.source if fact else None,
                "source_url": fact.sourceUrl if fact else None,
                "valid_from": fact.validFrom if fact else None,
            }
        )
    return out


# ─────────────────────────────────────────────────────────────
# 신규 사실 스캔 & 링크
# ─────────────────────────────────────────────────────────────
async def scan_and_link_new_fact(
    new_fact: KnowledgeFact, same_entity_only: bool = True
) -> dict[str, Any]:
    """신규 사실에 대해 기존 사실들을 훑어 복사 관계를 감지·기록.

    - `same_entity_only=True` 면 같은 entity 인 것만 후보.
    - 감지 결과가 INDEPENDENT 가 아니면 `ProvenanceEdge` + `KnowledgeFact.originalFactId` 갱신.
    - `pipeline.ingest_fact` 에서 호출 전제.

    반환: `detect_provenance` 결과 + `edge_id`/`linked` 필드.
    """
    result: dict[str, Any] = {
        "type": "INDEPENDENT",
        "original_id": None,
        "similarity": 0.0,
        "time_gap_hours": 0.0,
        "matched_fact_id": None,
        "edge_id": None,
        "linked": False,
    }
    if not new_fact.content:
        return result

    # 후보 로딩
    where: dict[str, Any] = {}
    if same_entity_only and new_fact.entity:
        where["entity"] = new_fact.entity
    if new_fact.id:
        where["NOT"] = {"id": new_fact.id}

    try:
        rows = await prisma.knowledgefact.find_many(
            where=where,
            take=200,
            order={"validFrom": "asc"},
        )
    except Exception:
        rows = []

    if not rows:
        return result

    # KnowledgeFact 파이단틱 모델로 변환 (최소 필드만)
    candidates: list[KnowledgeFact] = []
    for r in rows:
        try:
            candidates.append(
                KnowledgeFact(
                    id=r.id,
                    content=r.content,
                    domain=r.domain,
                    entity=r.entity,
                    language=r.language or "ko",
                    source=r.source,
                    source_url=r.sourceUrl,
                    valid_from=r.validFrom,
                )
            )
        except Exception:
            continue

    det = await detect_provenance(new_fact, candidates)
    result.update(det)

    if det["type"] == "INDEPENDENT" or not det.get("matched_fact_id"):
        return result

    # source = 복사한 쪽 = 신규 사실, target = 원본
    matched_id = det["matched_fact_id"]
    original_id = det.get("original_id") or matched_id

    if new_fact.id and original_id and new_fact.id != original_id:
        try:
            edge_id = await record_provenance_edge(
                source_fact_id=new_fact.id,
                target_fact_id=original_id,
                relation=det["type"],
                similarity=float(det["similarity"]),
                time_gap_hours=float(det["time_gap_hours"]),
                evidence=f"auto:{det['type']} sim={det['similarity']:.3f}",
            )
            result["edge_id"] = edge_id
        except Exception:
            result["edge_id"] = None

        # 신규 팩트의 originalFactId/provenanceType/copySimilarity 업데이트
        try:
            await prisma.knowledgefact.update(
                where={"id": new_fact.id},
                data={
                    "originalFactId": original_id,
                    "provenanceType": det["type"],
                    "copySimilarity": float(det["similarity"]),
                },
            )
            result["linked"] = True
        except Exception:
            result["linked"] = False

    return result


# ─────────────────────────────────────────────────────────────
# 전파 타임라인
# ─────────────────────────────────────────────────────────────
async def build_propagation_timeline(entity: str) -> list[dict[str, Any]]:
    """주제 `entity` 의 전파 타임라인.

    최초 보도 시점과 이후 복사/요약/번역이 어떤 매체에서 언제 발생했는지
    시간 오름차순으로 반환.

    각 항목::

        {fact_id, content, source, source_url, tier, authority,
         valid_from, role, original_id, similarity}

    ``role`` 은 ``origin`` (최초 보도) 또는 ``copy`` (파생).
    """
    if not entity:
        return []

    try:
        facts = await prisma.knowledgefact.find_many(
            where={"entity": entity}, order={"validFrom": "asc"}
        )
    except Exception:
        return []

    if not facts:
        return []

    timeline: list[dict[str, Any]] = []
    for f in facts:
        role = "origin" if not f.originalFactId else "copy"
        timeline.append(
            {
                "fact_id": f.id,
                "content": f.content,
                "source": f.source,
                "source_url": f.sourceUrl,
                "tier": str(f.sourceTier) if f.sourceTier else None,
                "authority": float(f.sourceAuthority) if f.sourceAuthority is not None else None,
                "valid_from": f.validFrom,
                "role": role,
                "original_id": f.originalFactId,
                "similarity": float(f.copySimilarity) if f.copySimilarity is not None else None,
                "provenance_type": str(f.provenanceType) if f.provenanceType else "INDEPENDENT",
            }
        )
    return timeline


__all__ = [
    "jaccard_similarity",
    "simhash_distance",
    "detect_provenance",
    "classify_copy_vs_translation",
    "record_provenance_edge",
    "find_original_of",
    "count_independent_sources",
    "list_copies_of",
    "scan_and_link_new_fact",
    "build_propagation_timeline",
]
