"""HLKM ⑦ - Hypothesis Generation.

기존 KnowledgeEdge 위에서 2-hop 전이 추론으로 "있을 법한" 새 관계를 제안한다.

    (A → B via CAUSES) ∧ (B → C via CAUSES/ENABLES/SUPPORTS)
    ⇒ 직접 엣지 A→C 가 없을 때 가설 "A CAUSES/ENABLES C" 를 생성.

또한 임베딩 유사도 기반 RELATED_TO 가설, 반사실 질의로 구조적 취약점 가설을 만든다.
생성된 가설은 KnowledgeHypothesis(status=pending)로 저장되어 관리자 검토 큐에 오른다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from hwarang_api.db import prisma
from hwarang_api.knowledge.embeddings import batch_cosine, embed_text
from hwarang_api.knowledge.types import KnowledgeRelation

logger = logging.getLogger(__name__)


# 전이 가중치: A→B→C 에서 최종 관계/가중치 매핑
_TRANSITIVITY: dict[tuple[str, str], tuple[str, float]] = {
    ("CAUSES", "CAUSES"): ("CAUSES", 0.7),
    ("CAUSES", "ENABLES"): ("ENABLES", 0.6),
    ("CAUSES", "SUPPORTS"): ("SUPPORTS", 0.55),
    ("ENABLES", "CAUSES"): ("ENABLES", 0.55),
    ("ENABLES", "ENABLES"): ("ENABLES", 0.5),
    ("SUPPORTS", "CAUSES"): ("SUPPORTS", 0.5),
    ("SUPPORTS", "ENABLES"): ("SUPPORTS", 0.45),
    ("SUPPORTS", "SUPPORTS"): ("SUPPORTS", 0.4),
}

_SIMILARITY_THRESHOLD = 0.85


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────
# LLM 근거 생성
# ─────────────────────────────────────────────
async def _llm_rationale(
    fact_a_content: str,
    fact_c_content: str,
    relation: str,
    path_contents: list[str],
) -> str:
    """가설의 한국어 근거(rationale) 문자열 생성."""
    try:
        from hwarang_api.knowledge.llm import _chat  # type: ignore
    except Exception:
        return ""

    mid = "\n".join(f"- {c[:140]}" for c in path_contents)
    system = (
        "You are a knowledge-graph hypothesis reasoner. "
        "Given two facts and the intermediate chain, produce ONE concise Korean sentence "
        "(<=80자) explaining why the proposed relation plausibly holds. No preface."
    )
    prompt = (
        f"관계: {relation}\n"
        f"A: {fact_a_content[:200]}\n"
        f"C: {fact_c_content[:200]}\n"
        f"중간 경로:\n{mid}"
    )
    try:
        resp = await _chat(prompt, system=system, max_tokens=160)
    except Exception as exc:  # noqa: BLE001
        logger.debug("rationale LLM failed: %s", exc)
        resp = ""
    return resp.strip()


# ─────────────────────────────────────────────
# 2-hop 전이 가설 생성
# ─────────────────────────────────────────────
async def generate_hypotheses(
    max_count: int = 20, confidence_threshold: float = 0.5
) -> list[dict]:
    """CAUSES 로 시작하는 2-hop 경로를 스캔해 누락된 전이 관계 가설을 제안."""
    first_hops = await prisma.knowledgeedge.find_many(
        where={"relationType": KnowledgeRelation.CAUSES.value},
        take=2000,
    )
    if not first_hops:
        return []

    second_rel_types = [
        KnowledgeRelation.CAUSES.value,
        KnowledgeRelation.ENABLES.value,
        KnowledgeRelation.SUPPORTS.value,
    ]

    # A → B 인덱스
    by_from: dict[str, list[Any]] = {}
    for e in first_hops:
        by_from.setdefault(e.fromFactId, []).append(e)

    b_set = sorted({e.toFactId for e in first_hops})
    if not b_set:
        return []

    second_hops = await prisma.knowledgeedge.find_many(
        where={
            "fromFactId": {"in": b_set},
            "relationType": {"in": second_rel_types},
        },
        take=5000,
    )
    by_from_b: dict[str, list[Any]] = {}
    for e in second_hops:
        by_from_b.setdefault(e.fromFactId, []).append(e)

    # 기존 직접 엣지 (A→C) 룩업 집합
    direct = await prisma.knowledgeedge.find_many(take=20000)
    existing_pairs: set[tuple[str, str, str]] = {
        (e.fromFactId, e.toFactId, e.relationType) for e in direct
    }
    existing_any_pair: set[tuple[str, str]] = {
        (e.fromFactId, e.toFactId) for e in direct
    }

    # 이미 제안된 pending 가설도 중복 제외
    pending = await prisma.knowledgehypothesis.find_many(
        where={"status": "pending"}, take=5000
    )
    pending_pairs: set[tuple[str, str, str]] = {
        (h.fromFactId, h.toFactId, h.relation) for h in pending
    }

    candidates: list[dict] = []
    for a_id, ab_edges in by_from.items():
        for ab in ab_edges:
            b_id = ab.toFactId
            for bc in by_from_b.get(b_id, []):
                c_id = bc.toFactId
                if c_id == a_id or c_id == b_id:
                    continue
                if (a_id, c_id) in existing_any_pair:
                    continue
                key = ("CAUSES", bc.relationType)
                mapping = _TRANSITIVITY.get(key)
                if mapping is None:
                    continue
                new_rel, factor = mapping
                conf = float(ab.strength) * float(bc.strength) * factor
                if conf < confidence_threshold:
                    continue
                if (a_id, c_id, new_rel) in existing_pairs:
                    continue
                if (a_id, c_id, new_rel) in pending_pairs:
                    continue
                candidates.append(
                    {
                        "a_id": a_id,
                        "b_id": b_id,
                        "c_id": c_id,
                        "relation": new_rel,
                        "confidence": min(1.0, conf),
                    }
                )

    candidates.sort(key=lambda c: c["confidence"], reverse=True)
    candidates = candidates[:max_count]

    # 팩트 본문 일괄 조회
    fact_ids_needed = {c["a_id"] for c in candidates} | {c["b_id"] for c in candidates} | {c["c_id"] for c in candidates}
    facts = (
        await prisma.knowledgefact.find_many(where={"id": {"in": list(fact_ids_needed)}})
        if fact_ids_needed
        else []
    )
    fact_map = {f.id: f for f in facts}

    created: list[dict] = []
    for c in candidates:
        fa = fact_map.get(c["a_id"])
        fc = fact_map.get(c["c_id"])
        fb = fact_map.get(c["b_id"])
        if fa is None or fc is None:
            continue

        statement = _build_statement(fa, fc, c["relation"])
        rationale = await _llm_rationale(
            fa.content,
            fc.content,
            c["relation"],
            [fb.content] if fb is not None else [],
        )
        if not rationale:
            rationale = (
                f"{fa.entity or '?'} → {fb.entity or '?'} → {fc.entity or '?'} "
                f"(conf={c['confidence']:.2f})"
            )

        row = await prisma.knowledgehypothesis.create(
            data={
                "statement": statement,
                "relation": c["relation"],
                "fromFactId": c["a_id"],
                "toFactId": c["c_id"],
                "pathFactIds": [c["a_id"], c["b_id"], c["c_id"]],
                "confidence": c["confidence"],
                "rationale": rationale[:1000],
                "status": "pending",
            }
        )
        created.append(
            {
                "hypothesis_id": row.id,
                "statement": statement,
                "relation": c["relation"],
                "from_fact_id": c["a_id"],
                "to_fact_id": c["c_id"],
                "confidence": c["confidence"],
                "rationale": rationale,
            }
        )

    logger.info("generate_hypotheses: %d created", len(created))
    return created


def _build_statement(fa: Any, fc: Any, relation: str) -> str:
    """사람이 읽을 수 있는 한국어 가설 문장."""
    a_label = fa.entity or (fa.content[:40] + "…")
    c_label = fc.entity or (fc.content[:40] + "…")
    verb_map = {
        "CAUSES": "는(은)",
        "ENABLES": "는(은) ",
        "SUPPORTS": "는(은)",
        "RELATED_TO": "와(과)",
    }
    if relation == "CAUSES":
        return f"{a_label}{verb_map[relation]} {c_label}을(를) 유발한다."
    if relation == "ENABLES":
        return f"{a_label}{verb_map[relation]}{c_label}을(를) 가능하게 한다."
    if relation == "SUPPORTS":
        return f"{a_label}{verb_map[relation]} {c_label}을(를) 뒷받침한다."
    if relation == "RELATED_TO":
        return f"{a_label}{verb_map[relation]} {c_label}은(는) 관련이 있다."
    return f"{a_label} —[{relation}]→ {c_label}"


# ─────────────────────────────────────────────
# 임베딩 유사도 기반 가설
# ─────────────────────────────────────────────
async def propose_hypothesis_from_similarity(fact_id: str) -> dict | None:
    """엣지가 없지만 임베딩 유사도가 매우 높은 팩트 쌍에 RELATED_TO 가설을 제안."""
    target = await prisma.knowledgefact.find_unique(where={"id": fact_id})
    if target is None:
        return None

    q_vec = target.embedding or await embed_text(target.content)
    candidates = await prisma.knowledgefact.find_many(
        where={
            "id": {"not": fact_id},
            "domain": target.domain,
        },
        take=300,
    )
    if not candidates:
        return None

    matrix: list[list[float]] = []
    for c in candidates:
        if c.embedding:
            matrix.append([float(x) for x in c.embedding])
        else:
            matrix.append(await embed_text(c.content))

    sims = batch_cosine(q_vec, matrix)
    order = sorted(range(len(candidates)), key=lambda i: sims[i], reverse=True)

    # 기존 엣지 제외
    existing = await prisma.knowledgeedge.find_many(
        where={
            "OR": [
                {"fromFactId": fact_id},
                {"toFactId": fact_id},
            ]
        },
        take=5000,
    )
    linked = {e.toFactId for e in existing} | {e.fromFactId for e in existing}

    for idx in order[:20]:
        sim = sims[idx]
        cand = candidates[idx]
        if sim < _SIMILARITY_THRESHOLD:
            return None
        if cand.id in linked:
            continue
        if cand.content == target.content:
            continue

        # 중복 가설 체크
        dup = await prisma.knowledgehypothesis.find_first(
            where={
                "fromFactId": fact_id,
                "toFactId": cand.id,
                "relation": KnowledgeRelation.RELATED_TO.value,
                "status": "pending",
            }
        )
        if dup is not None:
            continue

        rationale = f"임베딩 유사도 {sim:.3f} — 동일 도메인({target.domain}) 내 강한 의미적 근접성."
        statement = _build_statement(target, cand, KnowledgeRelation.RELATED_TO.value)
        row = await prisma.knowledgehypothesis.create(
            data={
                "statement": statement,
                "relation": KnowledgeRelation.RELATED_TO.value,
                "fromFactId": fact_id,
                "toFactId": cand.id,
                "pathFactIds": [fact_id, cand.id],
                "confidence": float(sim),
                "rationale": rationale,
                "status": "pending",
            }
        )
        return {
            "hypothesis_id": row.id,
            "statement": statement,
            "confidence": float(sim),
            "to_fact_id": cand.id,
        }
    return None


# ─────────────────────────────────────────────
# 검토 / 승인
# ─────────────────────────────────────────────
async def review_hypothesis(
    hypothesis_id: str,
    reviewer_id: str,
    decision: str,
    note: str | None = None,
) -> None:
    """관리자가 가설을 승인 또는 거절. 승인 시 KnowledgeEdge 생성."""
    if decision not in {"accepted", "rejected"}:
        raise ValueError(f"invalid decision: {decision}")

    hyp = await prisma.knowledgehypothesis.find_unique(where={"id": hypothesis_id})
    if hyp is None:
        raise ValueError(f"hypothesis not found: {hypothesis_id}")
    if hyp.status != "pending":
        logger.warning("hypothesis %s already reviewed (%s)", hypothesis_id, hyp.status)
        return

    if decision == "accepted":
        await prisma.knowledgeedge.create(
            data={
                "fromFactId": hyp.fromFactId,
                "toFactId": hyp.toFactId,
                "relationType": hyp.relation,
                "strength": float(hyp.confidence),
                "evidence": (hyp.rationale or "")[:1000],
                "verifiedBy": "human",
            }
        )

    await prisma.knowledgehypothesis.update(
        where={"id": hypothesis_id},
        data={
            "status": decision,
            "reviewedBy": reviewer_id,
            "reviewedAt": _utcnow(),
            "reviewNote": note,
        },
    )
    logger.info("review_hypothesis: %s → %s by %s", hypothesis_id, decision, reviewer_id)


# ─────────────────────────────────────────────
# 목록
# ─────────────────────────────────────────────
async def list_pending_hypotheses(
    limit: int = 50,
    min_confidence: float = 0.5,
    domain: str | None = None,
) -> list[dict]:
    """관리자 UI 용 pending 가설 목록."""
    rows = await prisma.knowledgehypothesis.find_many(
        where={
            "status": "pending",
            "confidence": {"gte": min_confidence},
        },
        order={"confidence": "desc"},
        take=max(limit * 3, limit),
    )
    if not rows:
        return []

    if domain:
        fact_ids = {r.fromFactId for r in rows} | {r.toFactId for r in rows}
        facts = await prisma.knowledgefact.find_many(
            where={"id": {"in": list(fact_ids)}, "domain": domain}
        )
        allowed = {f.id for f in facts}
        rows = [r for r in rows if r.fromFactId in allowed or r.toFactId in allowed]

    out: list[dict] = []
    for h in rows[:limit]:
        out.append(
            {
                "hypothesis_id": h.id,
                "statement": h.statement,
                "relation": h.relation,
                "from_fact_id": h.fromFactId,
                "to_fact_id": h.toFactId,
                "path_fact_ids": h.pathFactIds,
                "confidence": float(h.confidence),
                "rationale": h.rationale,
                "created_at": h.createdAt,
            }
        )
    return out


# ─────────────────────────────────────────────
# 자동 승인
# ─────────────────────────────────────────────
async def auto_accept_high_confidence(threshold: float = 0.85) -> int:
    """신뢰도 > threshold 인 pending 가설을 AI 자동 승인한다."""
    rows = await prisma.knowledgehypothesis.find_many(
        where={"status": "pending", "confidence": {"gt": threshold}},
        take=500,
    )
    accepted = 0
    for h in rows:
        try:
            await prisma.knowledgeedge.create(
                data={
                    "fromFactId": h.fromFactId,
                    "toFactId": h.toFactId,
                    "relationType": h.relation,
                    "strength": float(h.confidence),
                    "evidence": (h.rationale or "")[:1000],
                    "verifiedBy": "ai",
                }
            )
            await prisma.knowledgehypothesis.update(
                where={"id": h.id},
                data={
                    "status": "accepted",
                    "reviewedBy": "system:auto",
                    "reviewedAt": _utcnow(),
                    "reviewNote": f"auto-accept (conf>{threshold})",
                },
            )
            accepted += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("auto-accept failed for %s: %s", h.id, exc)
    logger.info("auto_accept_high_confidence: %d accepted", accepted)
    return accepted


# ─────────────────────────────────────────────
# 반사실 가설
# ─────────────────────────────────────────────
async def counterfactual_hypothesis(removed_fact_id: str) -> list[dict]:
    """`removed_fact_id` 제거 시 주요 인과 경로를 잃게 되는 하류 팩트 가설 생성.

    각 하류 팩트에 대해 counterfactual_query 를 돌려, 대체 경로가 없는 경우
    "removed_fact 가 없으면 downstream_fact 의 근거 경로가 사라진다" 가설을 만든다.
    관계는 CAUSES (가설 상태) 로 저장.
    """
    from hwarang_api.knowledge.graph import (
        counterfactual_query,
        traverse_causal_chain,
    )

    chain = await traverse_causal_chain(
        removed_fact_id, KnowledgeRelation.CAUSES, max_depth=3
    )
    if not chain:
        return []

    out: list[dict] = []
    source = await prisma.knowledgefact.find_unique(where={"id": removed_fact_id})
    if source is None:
        return []

    for node in chain[:30]:
        target_id = node["fact_id"]
        report = await counterfactual_query(removed_fact_id, target_id)
        if report["still_reachable"]:
            continue  # 대체 경로가 있으면 구조적 취약점 아님

        target = await prisma.knowledgefact.find_unique(where={"id": target_id})
        if target is None:
            continue

        confidence = min(1.0, 0.5 + 0.1 * node.get("depth", 1) + 0.2 * node.get("strength_product", 0.5))
        rationale = (
            f"{source.entity or removed_fact_id} 제거 시 {target.entity or target_id} 으로 가는 "
            f"{report['total_paths']}개 경로가 모두 차단됨 (depth={node.get('depth')})."
        )
        statement = (
            f"{source.entity or removed_fact_id}가 없으면 "
            f"{target.entity or target_id}의 인과 사슬이 붕괴된다."
        )

        dup = await prisma.knowledgehypothesis.find_first(
            where={
                "fromFactId": removed_fact_id,
                "toFactId": target_id,
                "relation": KnowledgeRelation.CAUSES.value,
                "status": "pending",
            }
        )
        if dup is not None:
            continue

        row = await prisma.knowledgehypothesis.create(
            data={
                "statement": statement,
                "relation": KnowledgeRelation.CAUSES.value,
                "fromFactId": removed_fact_id,
                "toFactId": target_id,
                "pathFactIds": node.get("path", [removed_fact_id, target_id]),
                "confidence": float(confidence),
                "rationale": rationale[:1000],
                "status": "pending",
            }
        )
        out.append(
            {
                "hypothesis_id": row.id,
                "statement": statement,
                "to_fact_id": target_id,
                "confidence": float(confidence),
                "blocked_paths": report["total_paths"],
            }
        )
    logger.info("counterfactual_hypothesis: %d proposals from %s", len(out), removed_fact_id)
    return out


__all__ = [
    "generate_hypotheses",
    "propose_hypothesis_from_similarity",
    "review_hypothesis",
    "list_pending_hypotheses",
    "auto_accept_high_confidence",
    "counterfactual_hypothesis",
]
