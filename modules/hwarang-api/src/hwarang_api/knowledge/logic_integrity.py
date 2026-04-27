"""HLKM - Logical Integrity Check.

사실들 간 논리적 무결성 검증:

    1. 삼단논법 위반 (A ⊂ B, B ⊂ C 인데 A ⊄ C)
    2. 추이성 깨짐 (A→B, B→C 인데 A↛C 가 명시됨)
    3. 양화사 불일치 (모든 X 는 Y vs 어떤 X 는 Y 아님)
    4. 직접 모순 (P vs ¬P)

정규식 기반 부정 감지 + LLM 기반 논리식 추출/함의 검증을 조합하고,
발견된 불일치는 `LogicalInconsistency` 테이블에 기록한다.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from hwarang_api.db import prisma

from .contradiction import detect_contradiction
from .llm import _chat
from .types import KnowledgeFact, KnowledgeStatus

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_fact(row: Any) -> KnowledgeFact:
    """Prisma row → KnowledgeFact (최소 매핑)."""
    return KnowledgeFact(
        id=row.id, content=row.content,
        content_hash=getattr(row, "contentHash", None),
        domain=getattr(row, "domain", "general"),
        entity=getattr(row, "entity", None),
        tags=list(getattr(row, "tags", None) or []),
        language=getattr(row, "language", "ko"),
        valid_from=row.validFrom,
        valid_to=getattr(row, "validTo", None),
        created_at=getattr(row, "createdAt", None),
        confidence_t0=float(getattr(row, "confidenceT0", 1.0)),
        half_life_days=getattr(row, "halfLifeDays", None),
        status=KnowledgeStatus(row.status),
        source=row.source,
        source_url=getattr(row, "sourceUrl", None),
    )


def _negation_patterns_ko_en() -> list[re.Pattern[str]]:
    """한/영 부정 표현 패턴."""
    return [
        re.compile(r"(?:이|가)\s*아니다"),
        re.compile(r"(?:이|가)\s*아닙니다"),
        re.compile(r"(?:하지|되지)\s*않는다"),
        re.compile(r"(?:하지|되지)\s*않습니다"),
        re.compile(r"없다\.?$"),
        re.compile(r"없습니다"),
        re.compile(r"\s*(?:는|은)\s*아니"),
        re.compile(r"\bis\s+not\b", re.IGNORECASE),
        re.compile(r"\bare\s+not\b", re.IGNORECASE),
        re.compile(r"\bwas\s+not\b", re.IGNORECASE),
        re.compile(r"\bdoes\s+not\b", re.IGNORECASE),
        re.compile(r"\bdo\s+not\b", re.IGNORECASE),
        re.compile(r"\bno\s+(?:one|such|longer)\b", re.IGNORECASE),
        re.compile(r"\bnever\b", re.IGNORECASE),
        re.compile(r"\bcannot\b", re.IGNORECASE),
    ]


_NEG_PATTERNS = _negation_patterns_ko_en()


def _has_negation(text: str) -> bool:
    """부정 표현 포함 여부."""
    if not text:
        return False
    return any(p.search(text) for p in _NEG_PATTERNS)


async def extract_logical_form(fact_content: str) -> dict:
    """문장을 논리식 형태로 분해.

    Return: `{subject, predicate, quantifier, negation, conditions}`
    quantifier ∈ {all, exists, none, specific}.
    """
    if not fact_content:
        return {"subject": None, "predicate": None,
                "quantifier": "specific", "negation": False, "conditions": []}

    system = (
        "You extract the logical form of a single Korean or English statement. "
        "Reply ONLY as a compact JSON object with fields: subject, predicate, "
        'quantifier (one of ["all","exists","none","specific"]), negation '
        "(true/false), conditions (list of strings). No prose."
    )
    resp = await _chat(fact_content, system=system, max_tokens=220)
    parsed: dict[str, Any] = {}
    if resp:
        try:
            start = resp.find("{")
            end = resp.rfind("}")
            if start != -1 and end != -1 and end > start:
                parsed = json.loads(resp[start : end + 1])
        except Exception:
            parsed = {}

    neg_regex = _has_negation(fact_content)
    negation = bool(parsed.get("negation")) or neg_regex

    quantifier = str(parsed.get("quantifier") or "specific").lower()
    if quantifier not in {"all", "exists", "none", "specific"}:
        if re.search(r"(?:모든|전부|항상|언제나)", fact_content):
            quantifier = "all"
        elif re.search(r"(?:어떤|일부|몇몇|some)", fact_content, re.IGNORECASE):
            quantifier = "exists"
        elif re.search(r"(?:아무도|없다|never|no one)", fact_content, re.IGNORECASE):
            quantifier = "none"
        else:
            quantifier = "specific"

    conditions = parsed.get("conditions") or []
    if not isinstance(conditions, list):
        conditions = [str(conditions)]

    return {
        "subject": parsed.get("subject"),
        "predicate": parsed.get("predicate"),
        "quantifier": quantifier,
        "negation": negation,
        "conditions": [str(c) for c in conditions],
    }


async def detect_direct_contradiction(fact_a_id: str,
                                       fact_b_id: str) -> dict | None:
    """단순 P vs ¬P 모순. contradiction.detect_contradiction 재사용."""
    a_row = await prisma.knowledgefact.find_unique(where={"id": fact_a_id})
    b_row = await prisma.knowledgefact.find_unique(where={"id": fact_b_id})
    if not a_row or not b_row:
        return None

    fact_a = _row_to_fact(a_row)
    fact_b = _row_to_fact(b_row)
    try:
        report = await detect_contradiction(fact_a, fact_b)
    except Exception as exc:  # noqa: BLE001
        logger.debug("detect_contradiction failed: %s", exc)
        return None
    if not report.is_contradiction:
        return None

    severity = "high" if report.confidence >= 0.8 else "medium"
    return {
        "type": "direct_contradiction",
        "violation": True,
        "explanation": report.reasoning,
        "confidence": float(report.confidence),
        "severity": severity,
        "fact_ids": [fact_a_id, fact_b_id],
    }


async def detect_syllogism_violation(fact_a_id: str, fact_b_id: str,
                                      fact_c_id: str) -> dict | None:
    """P1 ∧ P2 가 암시하는 결론과 P3 이 모순되는지(삼단논법 위반) LLM 판정."""
    rows = []
    for fid in (fact_a_id, fact_b_id, fact_c_id):
        try:
            r = await prisma.knowledgefact.find_unique(where={"id": fid})
        except Exception:
            r = None
        if r is None:
            return None
        rows.append(r)
    a, b, c = rows

    system = (
        "You are a strict logician. Given three statements labeled P1, P2, P3, "
        "determine if P1 and P2 together logically entail a conclusion that P3 "
        "contradicts (a syllogism violation). Reply on the first line with "
        "'YES <severity: low|medium|high>' or 'NO', then one short sentence."
    )
    prompt = (
        f"P1: {a.content}\nP2: {b.content}\nP3: {c.content}\n"
        "Is there a syllogism violation? Consider subset/superset and implications."
    )
    resp = await _chat(prompt, system=system, max_tokens=200)
    if not resp:
        return None
    head = resp.strip().splitlines()[0].upper().strip()
    if not head.startswith("YES"):
        return None
    sev = "medium"
    m = re.match(r"YES\s+(LOW|MEDIUM|HIGH)", head)
    if m:
        sev = m.group(1).lower()
    return {
        "type": "syllogism_violation",
        "violation": True,
        "explanation": resp.strip(),
        "severity": sev,
        "fact_ids": [fact_a_id, fact_b_id, fact_c_id],
    }


async def detect_quantifier_mismatch(fact_a_id: str,
                                      fact_b_id: str) -> dict | None:
    """양화사 충돌 (모든 X는 Y vs 어떤 X는 Y 아님, all vs none 등)."""
    a_row = await prisma.knowledgefact.find_unique(where={"id": fact_a_id})
    b_row = await prisma.knowledgefact.find_unique(where={"id": fact_b_id})
    if not a_row or not b_row:
        return None

    form_a = await extract_logical_form(a_row.content or "")
    form_b = await extract_logical_form(b_row.content or "")

    subj_a = (form_a.get("subject") or "").strip().lower()
    subj_b = (form_b.get("subject") or "").strip().lower()
    if subj_a and subj_b and subj_a != subj_b:
        return None

    q_a, q_b = form_a.get("quantifier"), form_b.get("quantifier")
    neg_a, neg_b = bool(form_a.get("negation")), bool(form_b.get("negation"))

    mismatch = False
    if q_a == "all" and not neg_a and q_b == "exists" and neg_b:
        mismatch = True
    elif q_b == "all" and not neg_b and q_a == "exists" and neg_a:
        mismatch = True
    elif q_a == "all" and q_b == "none":
        mismatch = True
    elif q_b == "all" and q_a == "none":
        mismatch = True

    if not mismatch:
        return None

    return {
        "type": "quantifier_mismatch",
        "violation": True,
        "explanation": (f"양화사 충돌: A={q_a}(neg={neg_a}) / B={q_b}(neg={neg_b}). "
                        f"subject≈{subj_a or subj_b}"),
        "severity": "medium",
        "fact_ids": [fact_a_id, fact_b_id],
    }


async def detect_transitivity_break(entity: str,
                                     relation: str) -> list[dict]:
    """CAUSES/IMPLIES/SUPPORTS 같은 추이성 관계에서 A→B, B→C 인데
    A↛C(CONTRADICTS 엣지) 가 존재하면 flag."""
    if not entity:
        return []

    try:
        fact_rows = await prisma.knowledgefact.find_many(
            where={"entity": entity}, take=200
        )
    except Exception:
        fact_rows = []
    fact_ids = {r.id for r in fact_rows}
    if len(fact_ids) < 3:
        return []

    try:
        edges = await prisma.knowledgeedge.find_many(
            where={
                "relationType": relation,
                "OR": [
                    {"fromFactId": {"in": list(fact_ids)}},
                    {"toFactId": {"in": list(fact_ids)}},
                ],
            },
            take=1000,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("edges lookup failed: %s", exc)
        edges = []

    out: dict[str, list[str]] = {}
    for e in edges:
        out.setdefault(e.fromFactId, []).append(e.toFactId)

    violations: list[dict] = []
    for a, bs in out.items():
        for b in bs:
            for c in out.get(b, []):
                if c == a:
                    continue
                try:
                    neg = await prisma.knowledgeedge.find_first(where={
                        "fromFactId": a, "toFactId": c,
                        "relationType": "CONTRADICTS",
                    })
                except Exception:
                    neg = None
                if neg is not None:
                    violations.append({
                        "type": "transitivity_break",
                        "relation": relation,
                        "chain": [a, b, c],
                        "explanation": f"{a}→{b}, {b}→{c} 인데 {a}↛{c} (CONTRADICTS 엣지 존재)",
                        "severity": "high",
                        "fact_ids": [a, b, c],
                    })
    return violations


async def logical_entailment_check(premises: list[str],
                                    conclusion: str) -> dict:
    """전제들로부터 결론이 논리적으로 따라오는지 LLM 판정."""
    if not premises or not conclusion:
        return {"entails": False, "confidence": 0.0, "reasoning": "empty input"}
    system = (
        "You are a strict logician. Given premises P1..Pn and a conclusion C, "
        "decide whether C is logically entailed. Reply first line "
        "'YES <conf 0-1>' or 'NO <conf 0-1>', then one short sentence."
    )
    body = "\n".join(f"P{i+1}: {p}" for i, p in enumerate(premises))
    prompt = f"{body}\nC: {conclusion}"
    resp = await _chat(prompt, system=system, max_tokens=200)
    if not resp:
        return {"entails": False, "confidence": 0.0, "reasoning": "llm_empty"}
    head = resp.strip().splitlines()[0].upper()
    entails = head.startswith("YES")
    m = re.match(r"(?:YES|NO)\s+([0-9.]+)", head)
    try:
        conf = float(m.group(1)) if m else (0.7 if entails else 0.3)
    except Exception:
        conf = 0.5
    conf = max(0.0, min(1.0, conf))
    return {"entails": entails, "confidence": conf, "reasoning": resp.strip()}


async def _record_inconsistency(fact_ids: list[str], inconsistency_type: str,
                                 explanation: str, severity: str,
                                 detection_method: str) -> str | None:
    """LogicalInconsistency 삽입. 동일 미해결 조합은 중복 방지."""
    try:
        existing = await prisma.logicalinconsistency.find_first(where={
            "inconsistencyType": inconsistency_type,
            "factIds": {"hasEvery": fact_ids},
            "resolved": False,
        })
    except Exception:
        existing = None
    if existing:
        return existing.id
    try:
        row = await prisma.logicalinconsistency.create(data={
            "factIds": fact_ids,
            "inconsistencyType": inconsistency_type,
            "explanation": explanation[:4000],
            "severity": severity,
            "detectionMethod": detection_method,
            "resolved": False,
            "detectedAt": _utcnow(),
        })
        return row.id
    except Exception as exc:  # noqa: BLE001
        logger.warning("inconsistency record failed: %s", exc)
        return None


async def batch_detect_contradictions_in_entity(entity: str) -> dict:
    """Entity 내 사실 쌍(N^2, 최대 N=30) 을 pairwise 모순 검사 + 레코드."""
    if not entity:
        return {"scanned_pairs": 0, "found": 0}
    try:
        rows = await prisma.knowledgefact.find_many(
            where={"entity": entity,
                   "status": {"in": [KnowledgeStatus.CONFIRMED.value,
                                     KnowledgeStatus.PENDING.value]}},
            take=30, order={"validFrom": "desc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("batch fact fetch failed: %s", exc)
        return {"scanned_pairs": 0, "found": 0}

    facts = [_row_to_fact(r) for r in rows]
    n = len(facts)
    scanned = found = 0
    for i in range(n):
        for j in range(i + 1, n):
            scanned += 1
            try:
                report = await detect_contradiction(facts[i], facts[j])
            except Exception as exc:  # noqa: BLE001
                logger.debug("pairwise detect failed: %s", exc)
                continue
            if not report.is_contradiction:
                continue
            sev = "high" if report.confidence >= 0.8 else "medium"
            await _record_inconsistency(
                fact_ids=[facts[i].id or "", facts[j].id or ""],
                inconsistency_type="direct_contradiction",
                explanation=report.reasoning,
                severity=sev,
                detection_method="pairwise_scan",
            )
            found += 1
    return {"entity": entity, "scanned_pairs": scanned, "found": found}


async def run_consistency_scan(domain: str | None = None,
                                limit: int = 100) -> dict:
    """도메인 단위 entity 묶어 pairwise 검사 집계."""
    where: dict[str, Any] = {
        "status": {"in": [KnowledgeStatus.CONFIRMED.value,
                          KnowledgeStatus.PENDING.value]}
    }
    if domain:
        where["domain"] = domain
    try:
        rows = await prisma.knowledgefact.find_many(where=where, take=limit)
    except Exception as exc:  # noqa: BLE001
        logger.warning("run_consistency_scan fetch failed: %s", exc)
        return {"entities_scanned": 0, "pairs_checked": 0, "found": 0}

    entities = {r.entity for r in rows if getattr(r, "entity", None)}
    total_pairs = total_found = 0
    for ent in entities:
        sub = await batch_detect_contradictions_in_entity(ent)
        total_pairs += int(sub.get("scanned_pairs", 0))
        total_found += int(sub.get("found", 0))
    return {"domain": domain, "entities_scanned": len(entities),
            "pairs_checked": total_pairs, "found": total_found}


async def list_inconsistencies(resolved: bool | None = None,
                                severity: str | None = None) -> list[dict]:
    """LogicalInconsistency 목록 조회."""
    where: dict[str, Any] = {}
    if resolved is not None:
        where["resolved"] = resolved
    if severity:
        where["severity"] = severity
    try:
        rows = await prisma.logicalinconsistency.find_many(
            where=where, order={"detectedAt": "desc"}, take=500
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_inconsistencies failed: %s", exc)
        return []
    return [{
        "id": r.id,
        "fact_ids": list(getattr(r, "factIds", None) or []),
        "inconsistency_type": r.inconsistencyType,
        "explanation": r.explanation,
        "severity": r.severity,
        "detection_method": getattr(r, "detectionMethod", None),
        "resolved": bool(r.resolved),
        "resolution": getattr(r, "resolution", None),
        "detected_at": getattr(r, "detectedAt", None),
        "resolved_at": getattr(r, "resolvedAt", None),
        "resolved_by": getattr(r, "resolvedBy", None),
    } for r in rows]


async def resolve_inconsistency(inconsistency_id: str, resolver_id: str,
                                 resolution: str) -> None:
    """관리자/에이전트가 논리 불일치 해결 완료 처리."""
    try:
        await prisma.logicalinconsistency.update(
            where={"id": inconsistency_id},
            data={
                "resolved": True,
                "resolution": resolution[:2000],
                "resolvedAt": _utcnow(),
                "resolvedBy": resolver_id,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("resolve_inconsistency failed id=%s err=%s",
                       inconsistency_id, exc)


async def suggest_resolution(inconsistency_id: str) -> str:
    """LLM 이 불일치 자동 해결안을 한국어로 제안."""
    try:
        row = await prisma.logicalinconsistency.find_unique(
            where={"id": inconsistency_id}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("lookup failed id=%s err=%s", inconsistency_id, exc)
        return ""
    if row is None:
        return ""

    fact_ids = list(getattr(row, "factIds", None) or [])
    facts_text: list[str] = []
    for fid in fact_ids[:6]:
        try:
            f = await prisma.knowledgefact.find_unique(where={"id": fid})
        except Exception:
            f = None
        if f is not None:
            facts_text.append(
                f"- [{fid}] domain={f.domain}, entity={f.entity}\n  {f.content[:300]}"
            )

    system = (
        "You are a knowledge-base resolver. Given a set of facts flagged as "
        "logically inconsistent, propose ONE concise Korean resolution such as: "
        "'사실 A가 도메인 변경으로 더 이상 유효하지 않음', '사실 B의 entity가 잘못 "
        "분류됨', '둘 다 서로 다른 시기의 사실이므로 유효기간 분리 필요'. 한 문단."
    )
    prompt = (
        f"Type: {row.inconsistencyType}\n"
        f"Severity: {row.severity}\n"
        f"Explanation: {row.explanation}\n\n"
        "Facts:\n" + "\n".join(facts_text)
    )
    resp = await _chat(prompt, system=system, max_tokens=260)
    return (resp or "").strip()


__all__ = [
    "detect_syllogism_violation",
    "detect_transitivity_break",
    "detect_quantifier_mismatch",
    "detect_direct_contradiction",
    "extract_logical_form",
    "run_consistency_scan",
    "list_inconsistencies",
    "resolve_inconsistency",
    "suggest_resolution",
    "logical_entailment_check",
    "batch_detect_contradictions_in_entity",
]
