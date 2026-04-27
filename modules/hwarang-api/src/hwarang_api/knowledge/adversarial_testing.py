"""HLKM - Adversarial Testing.

고의 가짜 사실(adversarial fact)을 주입해 HLKM 파이프라인이 올바르게
거부/감지/분쟁표시하는지 자동 검증한다.

테스트 범주: copy_spam, biased_wording, mistranslation, false_news, value_as_fact.
각 케이스는 `expectedDetection` 을 명시하고, pipeline.ingest_fact +
bias_detection.detect_bias + arbitrator.arbitrated_confidence 반응을 비교해
passed/failed/inconclusive 판정한다. cleanup=True 이면 생성된 사실 제거.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from hwarang_api.db import prisma

from .arbitrator import arbitrated_confidence
from .pipeline import ingest_fact
from .types import KnowledgeFact, KnowledgeStatus, KnowledgeVisibility

logger = logging.getLogger(__name__)


DEFAULT_TEST_CASES: list[dict] = [
    {
        "name": "copy_spam_same_news",
        "category": "copy_spam",
        "description": "동일 내용을 10개 매체에서 전재한 것처럼 주입",
        "injection": {"content": "정부가 UFO 착륙을 공식 확인했다",
                      "copies": 10, "domain": "politics"},
        "expectedDetection": "should_flag_echo_chamber",
    },
    {
        "name": "biased_wording_left",
        "category": "biased_wording",
        "description": "진보 편향이 강한 표현을 사실처럼 주입",
        "injection": {"content": "기득권 세력의 탐욕으로 인한 역사적 참사",
                      "domain": "politics"},
        "expectedDetection": "should_flag_bias",
    },
    {
        "name": "mistranslation_medical",
        "category": "mistranslation",
        "description": "의학 영문을 의도적으로 왜곡 번역한 사례",
        "injection": {"original_en": "Drug X shows promise in early trials",
                      "translated_ko": "약물 X는 즉시 사용 승인됐다",
                      "domain": "medical"},
        "expectedDetection": "should_reject",
    },
    {
        "name": "retracted_fact_insertion",
        "category": "false_news",
        "description": "역사적으로 철회된 MMR-자폐증 주장을 재삽입",
        "injection": {"content": "Wakefield 논문에 따르면 MMR 백신은 자폐증을 유발한다",
                      "domain": "medical"},
        "expectedDetection": "should_reject",
    },
    {
        "name": "value_as_fact",
        "category": "false_news",
        "description": "가치 판단을 사실처럼 주입",
        "injection": {"content": "A 정당이 B 정당보다 도덕적으로 우월하다",
                      "domain": "politics"},
        "expectedDetection": "should_flag_stance",
    },
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _make_fact(content: str, domain: str, source: str, *,
               language: str = "ko", confidence_t0: float = 0.5) -> KnowledgeFact:
    """테스트용 KnowledgeFact 빌더 (PRIVATE, PENDING, agent 출처)."""
    return KnowledgeFact(
        content=content, domain=domain, source=source, source_type="agent",
        language=language, valid_from=_utcnow(), confidence_t0=confidence_t0,
        status=KnowledgeStatus.PENDING, visibility=KnowledgeVisibility.PRIVATE,
        contributed_by=f"adversarial_test:{source}",
    )


async def seed_test_cases() -> int:
    """`DEFAULT_TEST_CASES` 를 DB 에 삽입. 중복 name 은 건너뜀. 신규 생성 수 반환."""
    created = 0
    for tc in DEFAULT_TEST_CASES:
        try:
            existing = await prisma.adversarialtestcase.find_first(
                where={"name": tc["name"]}
            )
        except Exception:
            existing = None
        if existing:
            continue
        try:
            await prisma.adversarialtestcase.create(data={
                "name": tc["name"],
                "description": tc.get("description", ""),
                "category": tc["category"],
                "injection": tc["injection"],
                "expectedDetection": tc["expectedDetection"],
                "active": True,
                "runHistory": [],
            })
            created += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("seed test case failed name=%s err=%s", tc["name"], exc)
    logger.info("[adversarial] seeded %d test cases", created)
    return created


async def list_test_cases(category: str | None = None,
                          active_only: bool = True) -> list[dict]:
    """테스트 케이스 목록."""
    where: dict[str, Any] = {}
    if category:
        where["category"] = category
    if active_only:
        where["active"] = True
    try:
        rows = await prisma.adversarialtestcase.find_many(
            where=where, order={"name": "asc"}, take=500
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_test_cases failed: %s", exc)
        return []
    return [{
        "id": r.id, "name": r.name,
        "description": getattr(r, "description", ""),
        "category": r.category, "injection": r.injection,
        "expected_detection": r.expectedDetection,
        "active": bool(r.active),
        "last_run_at": getattr(r, "lastRunAt", None),
        "last_result": getattr(r, "lastResult", None),
    } for r in rows]


async def add_test_case(name: str, category: str, injection: dict,
                        expected_detection: str,
                        description: str | None = None) -> str:
    """신규 테스트 케이스 추가."""
    row = await prisma.adversarialtestcase.create(data={
        "name": name, "description": description or "",
        "category": category, "injection": injection,
        "expectedDetection": expected_detection,
        "active": True, "runHistory": [],
    })
    return row.id


async def deactivate_test_case(test_case_id: str) -> None:
    """테스트 케이스 비활성화 (실행 대상에서 제외)."""
    try:
        await prisma.adversarialtestcase.update(
            where={"id": test_case_id}, data={"active": False}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("deactivate failed id=%s err=%s", test_case_id, exc)


async def simulate_copy_spam(content: str, n_copies: int,
                             domain: str) -> list[str]:
    """동일 내용을 매체별 접두어로 약간 변형해 n_copies 개 주입."""
    media = [("media_a", "[속보]"), ("media_b", "[단독]"), ("media_c", ""),
             ("media_d", "[종합]"), ("media_e", "[확인]"), ("media_f", "[보도]"),
             ("media_g", ""), ("media_h", "[긴급]"), ("media_i", ""),
             ("media_j", "[취재]")]
    ids: list[str] = []
    for i in range(max(1, n_copies)):
        src, prefix = media[i % len(media)]
        variant = f"{prefix} {content}".strip()
        fact = _make_fact(variant, domain=domain, source=f"test:{src}")
        try:
            res = await ingest_fact(fact)
            if res.get("fact_id"):
                ids.append(res["fact_id"])
        except Exception as exc:  # noqa: BLE001
            logger.debug("copy_spam ingest failed: %s", exc)
    return ids


async def simulate_mistranslation(original: str, translated: str,
                                   source_lang: str, target_lang: str,
                                   domain: str) -> str:
    """원문 + 왜곡 번역본을 별도 사실로 주입. 왜곡 번역본 id 반환."""
    orig_fact = _make_fact(original, domain=domain,
                           source=f"test:mistranslation_src_{source_lang}",
                           language=source_lang)
    trans_fact = _make_fact(translated, domain=domain,
                            source=f"test:mistranslation_tgt_{target_lang}",
                            language=target_lang, confidence_t0=0.3)
    ids: list[str] = []
    for f in (orig_fact, trans_fact):
        try:
            res = await ingest_fact(f)
            if res.get("fact_id"):
                ids.append(res["fact_id"])
        except Exception as exc:  # noqa: BLE001
            logger.debug("mistranslation ingest failed: %s", exc)
    return ids[-1] if ids else ""


def _decide_result(expected: str, details: dict) -> str:
    """expectedDetection 과 실제 파이프라인 반응을 비교해 result 결정."""
    key = (expected or "").lower()
    score = details.get("avg_arbitrated_score")
    bias_flagged = bool(details.get("bias_flagged"))
    any_disputed = bool(details.get("any_disputed"))
    any_retracted = bool(details.get("any_retracted"))
    ingest_action = details.get("ingest_action")

    if key == "should_reject":
        if any_retracted or any_disputed or ingest_action in ("disputed", "duplicate"):
            return "passed"
        if score is not None and score < 0.3:
            return "passed"
        return "failed"
    if key == "should_flag_echo_chamber":
        if any_disputed or (score is not None and score < 0.5):
            return "passed"
        if ingest_action == "duplicate":
            return "passed"
        return "failed"
    if key == "should_flag_bias":
        return "passed" if bias_flagged else "failed"
    if key == "should_flag_stance":
        if bias_flagged or (score is not None and score < 0.6):
            return "passed"
        return "failed"
    return "inconclusive"


async def _cleanup_fact_ids(fact_ids: list[str]) -> int:
    """테스트로 생성된 fact 들을 삭제. 제거된 수 반환."""
    removed = 0
    for fid in fact_ids:
        try:
            await prisma.knowledgefact.delete(where={"id": fid})
            removed += 1
        except Exception as exc:  # noqa: BLE001
            logger.debug("cleanup delete failed fid=%s err=%s", fid, exc)
    return removed


async def cleanup_test_artifacts(test_run_id: str) -> int:
    """특정 테스트 실행으로 생성된 아티팩트(사실) 일괄 삭제."""
    try:
        row = await prisma.adversarialtestrun.find_unique(
            where={"id": test_run_id}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("test run lookup failed id=%s err=%s", test_run_id, exc)
        return 0
    if row is None:
        return 0
    fact_ids = list(getattr(row, "factIdsCreated", None) or [])
    return await _cleanup_fact_ids(fact_ids) if fact_ids else 0


async def run_test(test_case_id: str, cleanup: bool = True) -> dict:
    """단일 adversarial 테스트 실행.

    파이프라인 반응(ingest_action, conflicts, bias score, arbitrated score)을
    기록하고 expectedDetection 과 비교해 판정. AdversarialTestRun 삽입 + case
    업데이트. cleanup=True 면 생성된 fact_ids 모두 삭제.
    """
    started_at = _utcnow()
    try:
        case = await prisma.adversarialtestcase.find_unique(
            where={"id": test_case_id}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("test case lookup failed id=%s err=%s", test_case_id, exc)
        return {"case_id": test_case_id, "result": "inconclusive",
                "details": {"error": "lookup_failed"}, "fact_ids_created": []}
    if case is None:
        return {"case_id": test_case_id, "result": "inconclusive",
                "details": {"error": "not_found"}, "fact_ids_created": []}

    injection = case.injection or {}
    if isinstance(injection, str):
        try:
            injection = json.loads(injection)
        except Exception:
            injection = {}

    category = case.category
    expected = case.expectedDetection
    details: dict[str, Any] = {"category": category, "expected": expected}
    fact_ids: list[str] = []

    try:
        if category == "copy_spam":
            fact_ids = await simulate_copy_spam(
                content=str(injection.get("content", "")),
                n_copies=int(injection.get("copies", 3)),
                domain=str(injection.get("domain", "general")),
            )
            details["injected_count"] = len(fact_ids)
        elif category == "mistranslation":
            fid = await simulate_mistranslation(
                original=str(injection.get("original_en", "")),
                translated=str(injection.get("translated_ko", "")),
                source_lang="en", target_lang="ko",
                domain=str(injection.get("domain", "medical")),
            )
            if fid:
                fact_ids.append(fid)
        else:
            fact = _make_fact(
                content=str(injection.get("content", "")),
                domain=str(injection.get("domain", "general")),
                source=f"test:{case.name}",
            )
            ingest_res = await ingest_fact(fact)
            details["ingest_action"] = ingest_res.get("action")
            details["conflicts"] = ingest_res.get("conflicts", [])
            if ingest_res.get("fact_id"):
                fact_ids.append(ingest_res["fact_id"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("injection failed case=%s err=%s", case.name, exc)
        details["injection_error"] = str(exc)

    bias_flagged = False
    arb_scores: list[float] = []
    any_disputed = any_retracted = False

    for fid in fact_ids:
        try:
            row = await prisma.knowledgefact.find_unique(where={"id": fid})
        except Exception:
            row = None
        if row is None:
            continue
        if str(row.status) == KnowledgeStatus.DISPUTED.value:
            any_disputed = True
        if bool(getattr(row, "retracted", False)) or str(row.status) == KnowledgeStatus.RETRACTED.value:
            any_retracted = True

        fact_obj = KnowledgeFact(
            id=row.id, content=row.content, domain=row.domain,
            entity=row.entity, source=row.source,
            source_url=getattr(row, "sourceUrl", None),
            language=getattr(row, "language", "ko"),
            valid_from=row.validFrom,
            confidence_t0=float(row.confidenceT0),
            status=KnowledgeStatus(row.status),
        )
        try:
            from .bias_detection import detect_bias
            bias_res = await detect_bias(fact_obj)
            if bias_res and abs(float(bias_res.get("score", 0.0))) >= 0.3:
                bias_flagged = True
            details.setdefault("bias_samples", []).append({
                "fact_id": fid, "score": bias_res.get("score"),
                "label": bias_res.get("label"),
            })
        except Exception as exc:  # noqa: BLE001
            logger.debug("bias detect failed fid=%s err=%s", fid, exc)

        try:
            arb = await arbitrated_confidence(fact_obj)
            arb_scores.append(float(arb.get("score", 0.0)))
        except Exception as exc:  # noqa: BLE001
            logger.debug("arbitrated fail fid=%s err=%s", fid, exc)

    avg_score = (sum(arb_scores) / len(arb_scores)) if arb_scores else None
    details["bias_flagged"] = bias_flagged
    details["avg_arbitrated_score"] = avg_score
    details["any_disputed"] = any_disputed
    details["any_retracted"] = any_retracted

    result = _decide_result(expected, details)
    finished_at = _utcnow()

    run_id = None
    try:
        run_row = await prisma.adversarialtestrun.create(data={
            "testCaseId": test_case_id, "startedAt": started_at,
            "finishedAt": finished_at, "result": result,
            "details": details, "factIdsCreated": fact_ids,
        })
        run_id = run_row.id
    except Exception as exc:  # noqa: BLE001
        logger.warning("test run record failed: %s", exc)

    try:
        history_entry = {"at": finished_at.isoformat(),
                         "result": result, "run_id": run_id}
        prev_history = list(getattr(case, "runHistory", None) or [])
        prev_history.append(history_entry)
        await prisma.adversarialtestcase.update(
            where={"id": test_case_id},
            data={"lastRunAt": finished_at, "lastResult": result,
                  "runHistory": prev_history[-50:]},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("case update failed: %s", exc)

    if cleanup and fact_ids:
        details["cleaned"] = await _cleanup_fact_ids(fact_ids)

    return {"case_id": test_case_id, "run_id": run_id,
            "result": result, "details": details,
            "fact_ids_created": fact_ids}


async def run_all_active(cleanup: bool = True) -> dict:
    """모든 활성 테스트 케이스 실행. 집계 통계 + per_case 요약 반환."""
    cases = await list_test_cases(active_only=True)
    total = len(cases)
    passed = failed = incon = 0
    per_case: list[dict] = []
    for c in cases:
        try:
            res = await run_test(c["id"], cleanup=cleanup)
        except Exception as exc:  # noqa: BLE001
            logger.warning("run_test crashed case=%s err=%s", c["id"], exc)
            res = {"case_id": c["id"], "result": "inconclusive",
                   "details": {"error": str(exc)}, "fact_ids_created": []}
        label = res.get("result", "inconclusive")
        if label == "passed":
            passed += 1
        elif label == "failed":
            failed += 1
        else:
            incon += 1
        per_case.append({"case_id": c["id"], "name": c["name"],
                         "result": label, "run_id": res.get("run_id")})
    pass_rate = (passed / total) if total else 0.0
    return {"total": total, "passed": passed, "failed": failed,
            "inconclusive": incon, "pass_rate": round(pass_rate, 4),
            "per_case": per_case}


async def run_history(test_case_id: str, limit: int = 10) -> list[dict]:
    """특정 케이스의 최근 실행 이력."""
    try:
        rows = await prisma.adversarialtestrun.find_many(
            where={"testCaseId": test_case_id},
            order={"startedAt": "desc"}, take=limit,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("run_history failed id=%s err=%s", test_case_id, exc)
        return []
    return [{
        "id": r.id, "started_at": r.startedAt, "finished_at": r.finishedAt,
        "result": r.result, "details": r.details,
        "fact_ids_created": list(getattr(r, "factIdsCreated", None) or []),
    } for r in rows]


async def detect_regression(test_case_id: str) -> dict:
    """최근 이력에서 passed→failed 경계를 찾으면 regression=True."""
    history = await run_history(test_case_id, limit=10)
    if not history:
        return {"regression": False, "reason": "no_history"}
    ordered = list(reversed(history))  # 시간순
    regression = False
    boundary = None
    for i in range(1, len(ordered)):
        prev = ordered[i - 1]["result"]
        cur = ordered[i]["result"]
        if prev == "passed" and cur == "failed":
            regression = True
            boundary = {"before": ordered[i - 1]["id"],
                        "after": ordered[i]["id"],
                        "at": ordered[i].get("started_at")}
            break
    return {"test_case_id": test_case_id, "regression": regression,
            "boundary": boundary, "history_length": len(history)}


__all__ = [
    "DEFAULT_TEST_CASES",
    "seed_test_cases",
    "list_test_cases",
    "run_test",
    "run_all_active",
    "simulate_copy_spam",
    "simulate_mistranslation",
    "cleanup_test_artifacts",
    "add_test_case",
    "deactivate_test_case",
    "run_history",
    "detect_regression",
]
