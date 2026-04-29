"""Application Engine — 논문 → 화랑 적용 자동 제안 (Group C).

매 6시간 cron — applicabilityScore >= 0.7 + status="summarized" 인 Paper:
1. 어떤 화랑 모듈에 적용 가능한지 LLM 분석
2. 구체 패치 outline + risk + effort 추정
3. PaperApplication 생성 (status="proposed")
4. GrowthDecision 도 자동 생성 (Phase 3 와 통합)
5. 관리자가 검토 후 승인하면 GrowthDecision 실행

흐름::

    Paper(status="summarized", score>=0.7)
        └─ analyze_summarized_papers() 6h cron
              ├─ _generate_applications() → LLM JSON
              ├─ PaperApplication.create(status="proposed") (1~3 개)
              └─ GrowthDecision.create(decisionType="apply_research_paper")
                     ↑
                관리자 UI 가 approve_application / reject_application
                호출하면 GrowthDecision 의 status 도 동기.
                approved 된 GrowthDecision 은 Phase 3 실행 큐가 처리.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


# 화랑 모듈별 상세 — LLM 에게 "어디에 어떻게 박아야 할지" 힌트로 제공.
# 키는 PaperApplication.module 에 그대로 저장되는 정확한 이름.
HWARANG_MODULES_DETAIL: dict[str, str] = {
    "HSEE Phase 1 (compounding loop)": (
        "modules/hwarang-api/src/hwarang_api/learning/compounding_loop.py — "
        "채팅마다 RLHF/HLKM/라우팅/HFL 4 루프"
    ),
    "HSEE Phase 2 (online LoRA)": (
        "learning/online_lora.py — EWC + Replay buffer 점진 학습"
    ),
    "HSEE Phase 3 (self-growing)": (
        "learning/auto_spawn.py — 능력 한계 시 새 LoRA spawn"
    ),
    "HSEE Phase 4 (custom engine)": (
        "modules/hwarang-engine/ — 독자 추론 엔진 (스켈레톤)"
    ),
    "HSEE Phase 5 (curiosity)": (
        "learning/self_questioner.py — 5 패턴 능동 질문"
    ),
    "HNTL (LoRA routing)": (
        "lib/innovation/hntl.ts — 도메인별 LoRA 자동 선택 (DB 기반)"
    ),
    "HRAG (Korean retrieval)": (
        "lib/alignment/hrag.ts — 한국 공식 DB 실시간 검색"
    ),
    "HFL (federated LoRA)": "modules/hwarang-grid — 분산 LoRA 학습",
    "HLKM (knowledge graph)": "knowledge/ — 시간 인식 사실 저장소",
    "TrustedSource": "knowledge/cross_verifier.py — 권위 출처 가중 검증",
    "Speculative Decoding": "vLLM --speculative-config",
    "Quantization": "AWQ / GPTQ — 모델 압축",
    "Korean tokenizer": "mecab + sentencepiece",
}


APPLICATION_PROMPT = """다음 AI 논문이 화랑 시스템의 어떤 모듈에 어떻게 적용 가능한지 구체 제안해라.

논문:
제목: {title}
한국어 요약: {summary}
핵심 기여: {contribution}
방법: {method}
적용 가능 모듈 후보: {modules}

화랑 모듈 상세:
{module_details}

JSON 출력 (1~3개 적용 제안):
{{
  "applications": [
    {{
      "module": "정확한 모듈 이름",
      "description": "이 논문 기법을 해당 모듈에 어떻게 적용할지 (3~5줄 한국어)",
      "patch_outline": "주요 파일/함수 변경 (파일명: 변경 내용)",
      "estimated_effort_hours": 정수,
      "risk": "low|medium|high",
      "expected_improvement": "예상 효과"
    }}
  ]
}}
JSON 만 출력:"""


# ---------------------------------------------------------------------------
# 메인 진입 — 6 시간 cron
# ---------------------------------------------------------------------------
async def analyze_summarized_papers(batch_size: int = 10) -> dict:
    """매 6시간 cron — high-score paper 를 분석해 application + decision 생성."""
    started = datetime.now(timezone.utc)

    try:
        candidates = await prisma.paper.find_many(
            where={
                "status": "summarized",
                "applicabilityScore": {"gte": 0.7},
            },
            order={"applicabilityScore": "desc"},
            take=batch_size,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("analyze_summarized_papers DB 실패: %s", exc)
        return {"analyzed": 0, "error": str(exc)}

    if not candidates:
        return {
            "candidates": 0,
            "papers_analyzed": 0,
            "skipped_existing": 0,
            "applications_created": 0,
            "growth_decisions_created": 0,
            "elapsed_seconds": 0.0,
        }

    success = 0
    skipped = 0
    apps_created = 0
    decisions_created = 0

    for paper in candidates:
        # 이미 application 있으면 skip (중복 제안 방지).
        try:
            existing = await prisma.paperapplication.find_first(
                where={"paperId": paper.id},
            )
        except Exception:  # noqa: BLE001
            existing = None
        if existing:
            skipped += 1
            continue

        try:
            applications = await _generate_applications(paper)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "application analyze 실패 %s: %s", paper.arxivId, exc
            )
            continue

        if not applications:
            continue

        for app in applications[:3]:  # 최대 3 개 제안
            module = str(app.get("module") or "").strip()
            description = str(app.get("description") or "").strip()
            if not module or not description:
                continue

            try:
                pa = await prisma.paperapplication.create(
                    data={
                        "paperId": paper.id,
                        "module": module[:200],
                        "description": description[:2000],
                        "status": "proposed",
                    }
                )
                apps_created += 1
            except Exception as exc:  # noqa: BLE001
                logger.debug("PaperApplication 생성 실패: %s", exc)
                continue

            # GrowthDecision 도 자동 생성 (Phase 3 실행 파이프라인 통합).
            try:
                gd = await prisma.growthdecision.create(
                    data={
                        "decisionType": "apply_research_paper",
                        "triggerDomain": "research",
                        "triggerMetric": "high_applicability_paper",
                        "triggerValue": float(paper.applicabilityScore or 0.7),
                        "proposalJson": {
                            "paper_id": paper.id,
                            "arxiv_id": paper.arxivId,
                            "paper_title": paper.title,
                            "module": module,
                            "description": description,
                            "patch_outline": str(
                                app.get("patch_outline") or ""
                            )[:3000],
                            "estimated_effort_hours": int(
                                app.get("estimated_effort_hours") or 8
                            ),
                            "risk": str(app.get("risk") or "medium"),
                            "expected_improvement": str(
                                app.get("expected_improvement") or ""
                            )[:500],
                        },
                        "status": "proposed",
                    }
                )
                decisions_created += 1

                # PaperApplication ↔ GrowthDecision 연결.
                await prisma.paperapplication.update(
                    where={"id": pa.id},
                    data={"growthDecisionId": gd.id},
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("GrowthDecision 생성 실패: %s", exc)

        # Paper status 업데이트 — 다음 cron 에서 재분석 안 되도록.
        try:
            await prisma.paper.update(
                where={"id": paper.id},
                data={"status": "applied"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Paper status 업데이트 실패: %s", exc)
        success += 1

    return {
        "candidates": len(candidates),
        "papers_analyzed": success,
        "skipped_existing": skipped,
        "applications_created": apps_created,
        "growth_decisions_created": decisions_created,
        "elapsed_seconds": (
            datetime.now(timezone.utc) - started
        ).total_seconds(),
    }


# ---------------------------------------------------------------------------
# LLM 호출 — JSON 파싱 + 안전 fallback
# ---------------------------------------------------------------------------
async def _generate_applications(paper) -> list[dict]:
    """단일 Paper → 1~3 개 application dict.

    LLM 실패/JSON 파싱 실패 시 빈 리스트 반환 — 호출부가 안전하게 skip.
    """
    applicable = list(paper.applicableModules or [])

    # 후보 모듈 텍스트 (논문이 추천한 모듈 우선, 없으면 기본 카탈로그).
    if applicable:
        modules_text = "\n".join(f"- {m}" for m in applicable[:10])
    else:
        modules_text = "\n".join(
            f"- {m}" for m in list(HWARANG_MODULES_DETAIL.keys())[:10]
        )

    # 모듈 상세 — LLM 에게 파일 경로까지 알려줘 patch_outline 정확도 ↑.
    detail_pairs: list[tuple[str, str]] = []
    if applicable:
        for k, v in HWARANG_MODULES_DETAIL.items():
            if k in applicable:
                detail_pairs.append((k, v))
    if not detail_pairs:
        detail_pairs = list(HWARANG_MODULES_DETAIL.items())[:5]
    details_text = "\n".join(f"{k}: {v}" for k, v in detail_pairs)[:2000]

    prompt = APPLICATION_PROMPT.format(
        title=(paper.title or "")[:300],
        summary=(paper.koreanSummary or paper.abstract or "")[:1500],
        contribution=(paper.contribution or "")[:500],
        method=(paper.methodSummary or "")[:1000],
        modules=modules_text,
        module_details=details_text,
    )

    try:
        raw = await llm_chat(prompt)
    except Exception as exc:  # noqa: BLE001
        logger.debug("LLM application 호출 실패: %s", exc)
        return []

    # JSON 추출 — 모델이 ```json``` 펜스나 자유 문장을 섞어 보내도 처음 { ~ 마지막 } 만 사용.
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        logger.debug("LLM application JSON not found in: %s", (raw or "")[:200])
        return []
    try:
        data = json.loads(m.group())
    except Exception as exc:  # noqa: BLE001
        logger.debug("LLM application JSON 파싱 실패: %s", exc)
        return []

    apps = data.get("applications") or []
    if not isinstance(apps, list):
        return []
    # 형식 보정 — dict 만 통과.
    return [a for a in apps if isinstance(a, dict)]


# ---------------------------------------------------------------------------
# 관리자 검토 API
# ---------------------------------------------------------------------------
async def list_pending_applications(limit: int = 50) -> list:
    """관리자 검토 대기 중인 (proposed) application 목록 + Paper 동봉."""
    try:
        return await prisma.paperapplication.find_many(
            where={"status": "proposed"},
            order={"createdAt": "desc"},
            take=limit,
            include={"paper": True},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("list_pending_applications 실패: %s", exc)
        return []


async def approve_application(app_id: str, reviewer: str) -> dict:
    """관리자 승인 → GrowthDecision 도 approve 로 동기."""
    try:
        app = await prisma.paperapplication.find_unique(
            where={"id": app_id},
            include={"paper": True},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("approve find 실패: %s", exc)
        return {"error": "db_error"}

    if not app:
        return {"error": "not_found"}

    try:
        await prisma.paperapplication.update(
            where={"id": app_id},
            data={
                "status": "approved",
                "reviewedAt": datetime.now(timezone.utc),
                "reviewedBy": reviewer,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("approve update 실패: %s", exc)
        return {"error": "update_failed"}

    if app.growthDecisionId:
        try:
            await prisma.growthdecision.update(
                where={"id": app.growthDecisionId},
                data={
                    "status": "approved",
                    "reviewedBy": reviewer,
                    "reviewedAt": datetime.now(timezone.utc),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("GrowthDecision approve 실패: %s", exc)

    return {
        "approved": True,
        "appId": app_id,
        "growthDecisionId": app.growthDecisionId,
    }


async def reject_application(
    app_id: str, reason: str, reviewer: str
) -> dict:
    """관리자 거절 → GrowthDecision 도 rejected + reason 기록."""
    try:
        app = await prisma.paperapplication.find_unique(
            where={"id": app_id}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("reject find 실패: %s", exc)
        return {"error": "db_error"}

    if not app:
        return {"error": "not_found"}

    try:
        await prisma.paperapplication.update(
            where={"id": app_id},
            data={
                "status": "rejected",
                "reviewedAt": datetime.now(timezone.utc),
                "reviewedBy": reviewer,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("reject update 실패: %s", exc)
        return {"error": "update_failed"}

    if app.growthDecisionId:
        try:
            await prisma.growthdecision.update(
                where={"id": app.growthDecisionId},
                data={
                    "status": "rejected",
                    "rejectReason": (reason or "")[:1000],
                    "reviewedBy": reviewer,
                    "reviewedAt": datetime.now(timezone.utc),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("GrowthDecision reject 실패: %s", exc)

    return {"rejected": True, "appId": app_id}


__all__ = [
    "analyze_summarized_papers",
    "list_pending_applications",
    "approve_application",
    "reject_application",
    "HWARANG_MODULES_DETAIL",
]
