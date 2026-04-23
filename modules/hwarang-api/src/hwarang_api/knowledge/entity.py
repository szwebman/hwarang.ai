"""HLKM B5: 엔티티 통합/정규화.

동일 주제("최저시급", "근로기준법", "Next.js")를 가리키는 사실들이
서로 다른 표현으로 저장되는 것을 방지하기 위해
entity 키를 결정·통합·분리·타임라인화 한다.

알고리즘:
  1. resolve_entity : 새 fact content 에서 후보 엔티티명을 추출(정규식+LLM),
     기존 엔티티 대표 임베딩과 유사도를 비교해 >0.85 면 기존 키 반환.
     그렇지 않으면 slugify 로 새 키 생성.
  2. merge / split / drift / timeline 은 운영자용 관리 함수.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from typing import Literal

from hwarang_api.db import prisma

from .types import KnowledgeStatus

# placeholder 외부 모듈
from hwarang_api.knowledge.embeddings import embed_text, cosine  # type: ignore
from hwarang_api.knowledge.llm import llm_extract_entity_candidates  # type: ignore

logger = logging.getLogger(__name__)

_MATCH_THRESHOLD = 0.85

# 자주 등장하는 패턴 (법령/기술/지표)
_PATTERNS = [
    re.compile(r"([가-힣]+법(?:률)?(?:\s*제\s*\d+\s*조)?)"),     # 근로기준법, 민법 제750조
    re.compile(r"(최저\s*(?:시급|임금|시간당임금))"),
    re.compile(r"([A-Z][A-Za-z0-9.\-]+(?:\.js|\.ts)?)"),         # Next.js, TypeScript
    re.compile(r"(\d{4}년도?\s*[가-힣A-Za-z0-9 ]+)"),             # 2024년 예산안
]


def _slugify(text: str) -> str:
    """한/영 혼합 문자열 → URL-safe slug."""
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = re.sub(r"[\s　]+", "-", text)
    text = re.sub(r"[^0-9a-z가-힣\-]", "", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:80] or "entity"


def _extract_candidates_regex(content: str) -> list[str]:
    hits: list[str] = []
    for pat in _PATTERNS:
        for m in pat.finditer(content):
            phrase = m.group(1).strip()
            if 2 <= len(phrase) <= 60 and phrase not in hits:
                hits.append(phrase)
    return hits


# ─────────────────────────────────────────────
# 엔티티 해석
# ─────────────────────────────────────────────
async def resolve_entity(content: str, domain: str) -> str | None:
    """content 가 기술하는 엔티티 키를 결정.

    반환: 기존/신규 entity 키. 후보 추출 실패 시 None.
    """
    candidates = _extract_candidates_regex(content)
    try:
        llm_hits = await llm_extract_entity_candidates(content, domain=domain)
        for h in llm_hits or []:
            if h and h not in candidates:
                candidates.append(h)
    except Exception as exc:  # noqa: BLE001
        logger.debug("llm_extract_entity_candidates failed: %s", exc)

    if not candidates:
        return None

    # 기존 도메인의 distinct entity 목록
    existing_rows = await prisma.knowledgefact.find_many(
        where={"domain": domain, "entity": {"not": None}},
        take=2000,
    )
    by_entity: dict[str, list[str]] = defaultdict(list)
    for row in existing_rows:
        if row.entity:
            by_entity[row.entity].append(row.content[:200])

    if by_entity:
        # 대표 임베딩 = 각 엔티티의 첫 fact content 임베딩
        entity_embs: dict[str, list[float]] = {}
        for ent, texts in by_entity.items():
            try:
                entity_embs[ent] = await embed_text(" ".join(texts[:3]))
            except Exception:  # noqa: BLE001
                continue

        for cand in candidates:
            try:
                cand_emb = await embed_text(cand)
            except Exception:  # noqa: BLE001
                continue
            best_ent, best_sim = None, 0.0
            for ent, emb in entity_embs.items():
                sim = cosine(cand_emb, emb)
                if sim > best_sim:
                    best_sim, best_ent = sim, ent
            if best_ent and best_sim >= _MATCH_THRESHOLD:
                logger.debug("resolve_entity: %r matched %r sim=%.3f", cand, best_ent, best_sim)
                return best_ent

    # 매칭되는 기존 엔티티 없음 → 신규 slug
    return _slugify(candidates[0])


# ─────────────────────────────────────────────
# 목록/타임라인
# ─────────────────────────────────────────────
async def list_entities(domain: str | None = None, limit: int = 100) -> list[dict]:
    """distinct 엔티티 + 사실 수 + valid_from 범위."""
    where: dict = {"entity": {"not": None}}
    if domain:
        where["domain"] = domain

    rows = await prisma.knowledgefact.find_many(where=where, take=5000)

    agg: dict[str, dict] = defaultdict(lambda: {
        "count": 0, "earliest": None, "latest": None, "domain": None,
    })
    for row in rows:
        a = agg[row.entity]
        a["count"] += 1
        a["domain"] = row.domain
        vf = row.validFrom
        if a["earliest"] is None or vf < a["earliest"]:
            a["earliest"] = vf
        if a["latest"] is None or vf > a["latest"]:
            a["latest"] = vf

    out = [
        {"entity": k, **v}
        for k, v in sorted(agg.items(), key=lambda kv: -kv[1]["count"])
    ]
    return out[:limit]


async def entity_timeline(entity: str) -> list[dict]:
    """엔티티의 시계열 변화 이력."""
    rows = await prisma.knowledgefact.find_many(
        where={"entity": entity},
        order={"validFrom": "asc"},
        take=1000,
    )
    timeline: list[dict] = []
    for row in rows:
        timeline.append({
            "fact_id": row.id,
            "valid_from": row.validFrom,
            "valid_to": row.validTo,
            "content_summary": row.content[:140],
            "confidence": row.confidenceT0,
            "status": row.status,
            "source": row.source,
        })
    return timeline


# ─────────────────────────────────────────────
# 병합 / 분리
# ─────────────────────────────────────────────
async def merge_entities(
    entity_a: str,
    entity_b: str,
    keep: Literal["a", "b", "new"],
    new_key: str | None = None,
) -> int:
    """두 엔티티를 하나로 통합. 영향 받은 row 수 반환."""
    if keep == "a":
        target = entity_a
    elif keep == "b":
        target = entity_b
    else:
        if not new_key:
            raise ValueError("new_key required when keep='new'")
        target = _slugify(new_key)

    # Prisma update_many
    affected = 0
    for src in (entity_a, entity_b):
        if src == target:
            continue
        res = await prisma.knowledgefact.update_many(
            where={"entity": src},
            data={"entity": target},
        )
        affected += (res if isinstance(res, int) else getattr(res, "count", 0))

    logger.info("merge_entities: %s + %s -> %s (%d facts)", entity_a, entity_b, target, affected)
    return affected


async def split_entity(entity: str, fact_ids_for_new: list[str], new_entity: str) -> None:
    """지정된 fact 들을 새 엔티티로 이동."""
    new_key = _slugify(new_entity)
    if not fact_ids_for_new:
        return

    for fid in fact_ids_for_new:
        await prisma.knowledgefact.update(
            where={"id": fid},
            data={"entity": new_key},
        )
    logger.info("split_entity: %d facts moved from %s to %s", len(fact_ids_for_new), entity, new_key)


# ─────────────────────────────────────────────
# 드리프트 감지
# ─────────────────────────────────────────────
async def detect_entity_drift(entity: str) -> dict:
    """한 엔티티 아래 facts 를 임베딩 기반으로 클러스터링.

    2개 이상 군집이 감지되면 split 을 제안한다.
    간단한 응집형(threshold=0.7) 알고리즘을 사용.
    """
    rows = await prisma.knowledgefact.find_many(
        where={"entity": entity, "status": KnowledgeStatus.CONFIRMED.value},
        take=500,
    )
    if len(rows) < 3:
        return {"entity": entity, "clusters": 1, "suggest_split": False, "groups": []}

    embs: list[tuple[str, list[float]]] = []
    for row in rows:
        try:
            e = await embed_text(row.content[:500])
            embs.append((row.id, e))
        except Exception:  # noqa: BLE001
            continue

    clusters: list[list[tuple[str, list[float]]]] = []
    for fid, emb in embs:
        placed = False
        for cluster in clusters:
            centroid = cluster[0][1]
            if cosine(emb, centroid) >= 0.70:
                cluster.append((fid, emb))
                placed = True
                break
        if not placed:
            clusters.append([(fid, emb)])

    groups = [{"size": len(c), "fact_ids": [fid for fid, _ in c]} for c in clusters]
    meaningful = [g for g in groups if g["size"] >= 2]

    return {
        "entity": entity,
        "clusters": len(meaningful),
        "suggest_split": len(meaningful) > 1,
        "groups": groups,
    }


__all__ = [
    "resolve_entity",
    "list_entities",
    "merge_entities",
    "split_entity",
    "entity_timeline",
    "detect_entity_drift",
]
