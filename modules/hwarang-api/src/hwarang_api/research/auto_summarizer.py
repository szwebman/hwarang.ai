"""Paper 한국어 요약 + 화랑 적용성 평가.

매 1시간 cron — status="parsed" 인 Paper 들 처리 → "summarized" 로.

각 Paper 에 대해:
1. 한국어 요약 (5줄)
2. 화랑 적용 가능성 점수 (0~1)
3. 적용 가능 모듈 list (HSEE Phase 2, HNTL 등)
4. 구현 난이도 (easy / medium / hard)
5. 예상 ROI (low / medium / high)
6. HLKM 에 KnowledgeFact 로 저장 (도메인 "research")
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as llm_chat
from hwarang_api.knowledge.pipeline import ingest_fact
from hwarang_api.knowledge.types import KnowledgeFact, KnowledgeVisibility

logger = logging.getLogger(__name__)


# 화랑 시스템 모듈 카탈로그 — LLM 평가 시 후보로 제시.
HWARANG_MODULES = [
    "HSEE Phase 1 (compounding loop)",
    "HSEE Phase 2 (online LoRA + EWC)",
    "HSEE Phase 3 (self-growing architecture)",
    "HSEE Phase 4 (custom inference engine)",
    "HSEE Phase 5 (curiosity / self-questioning)",
    "HNTL (neural topic LoRA routing)",
    "HRAG (Korean retrieval)",
    "HFL (federated LoRA training)",
    "HLKM (knowledge graph)",
    "TrustedSource (fact verification)",
    "Speculative Decoding",
    "Quantization (AWQ/GPTQ)",
    "Korean tokenizer",
    "TACS (Korean alignment)",
    "26 technique stack",
]


SUMMARIZE_PROMPT = """다음 AI 논문에 대해 한국어 요약 + 화랑(한국어 LLM 시스템)에 적용 가능성을 평가해라.

논문:
제목: {title}
초록: {abstract}
기여: {contribution}
방법: {method_summary}

화랑 시스템 모듈:
{modules}

JSON 출력:
{{
  "korean_summary": "5줄 한국어 요약",
  "applicability_score": 0.0~1.0,
  "applicable_modules": ["...", "..."],
  "difficulty": "easy|medium|hard",
  "estimated_roi": "low|medium|high",
  "key_takeaway": "한 줄 핵심"
}}
JSON 만 출력:"""


async def summarize_pending_papers(batch_size: int = 10) -> dict:
    """매 1시간 cron — parsed 상태 Paper → summarized."""
    started = datetime.now(timezone.utc)

    try:
        parsed = await prisma.paper.find_many(
            where={"status": "parsed"},
            take=batch_size,
            order={"publishedAt": "desc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("paper.find_many(parsed) 실패: %s", exc)
        return {"summarized": 0, "reason": "db_error"}

    if not parsed:
        return {"summarized": 0, "candidates": 0}

    success = 0
    failed = 0

    for paper in parsed:
        try:
            result = await summarize_one(paper)
            if not result:
                failed += 1
                continue

            # HLKM 에도 사실로 저장 (도메인 research)
            await _ingest_to_hlkm(paper, result)

            # 필드 길이 제한 + 형 변환
            summary_text = str(result.get("korean_summary", ""))[:2000]
            try:
                score = float(result.get("applicability_score", 0.5))
            except (TypeError, ValueError):
                score = 0.5
            score = max(0.0, min(1.0, score))

            modules = result.get("applicable_modules", []) or []
            if not isinstance(modules, list):
                modules = []
            modules = [str(m)[:120] for m in modules][:10]

            difficulty = str(result.get("difficulty", "medium"))[:20]
            roi = str(result.get("estimated_roi", "medium"))[:20]

            await prisma.paper.update(
                where={"id": paper.id},
                data={
                    "koreanSummary": summary_text,
                    "applicabilityScore": score,
                    "applicableModules": modules,
                    "difficulty": difficulty,
                    "estimatedROI": roi,
                    "status": "summarized",
                    "summarizedAt": datetime.now(timezone.utc),
                },
            )
            success += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("summarize 실패 %s: %s", getattr(paper, "arxivId", "?"), e)
            failed += 1

    return {
        "candidates": len(parsed),
        "summarized": success,
        "failed": failed,
        "elapsed_seconds": (datetime.now(timezone.utc) - started).total_seconds(),
    }


async def summarize_one(paper) -> dict | None:
    """단일 논문 LLM 요약 + 평가.

    paper 는 Prisma Paper 객체 (또는 동등 dict). 실패 시 None.
    """
    title = getattr(paper, "title", None) or ""
    abstract = getattr(paper, "abstract", None) or ""
    contribution = getattr(paper, "contribution", None) or "(없음)"
    method_summary = getattr(paper, "methodSummary", None) or "(없음)"

    modules_text = "\n".join(f"- {m}" for m in HWARANG_MODULES)

    prompt = SUMMARIZE_PROMPT.format(
        title=title[:300],
        abstract=abstract[:2000],
        contribution=contribution[:500],
        method_summary=method_summary[:1000],
        modules=modules_text,
    )

    try:
        raw = await llm_chat(prompt)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:  # noqa: BLE001
        logger.debug("LLM summarize parse 실패: %s", e)
    return None


async def _ingest_to_hlkm(paper, summary: dict) -> None:
    """논문 요약을 HLKM 에 사실로 저장 (도메인 research, 신뢰도 0.85)."""
    arxiv_id = getattr(paper, "arxivId", None) or "(no-id)"
    title = getattr(paper, "title", "") or ""
    published_at = getattr(paper, "publishedAt", None) or datetime.now(timezone.utc)

    try:
        score = float(summary.get("applicability_score", 0) or 0)
    except (TypeError, ValueError):
        score = 0.0

    content = (
        f"[{arxiv_id}] {title}\n\n"
        f"한국어 요약: {summary.get('korean_summary', '')}\n"
        f"핵심: {summary.get('key_takeaway', '')}\n"
        f"화랑 적용성: {score:.2f} "
        f"(난이도: {summary.get('difficulty')}, ROI: {summary.get('estimated_roi')})"
    )

    fact = KnowledgeFact(
        content=content[:5000],
        domain="research",
        source="arxiv",
        source_url=f"https://arxiv.org/abs/{arxiv_id}",
        source_type="official",
        confidence_t0=0.85,  # 학술 1차 출처
        valid_from=published_at,
        visibility=KnowledgeVisibility.PUBLIC,
    )

    try:
        result = await ingest_fact(fact, bypass_gate=True)
        # Paper.factId 연결
        fact_id = result.get("fact_id") if isinstance(result, dict) else None
        if fact_id:
            await prisma.paper.update(
                where={"id": paper.id},
                data={"factId": fact_id},
            )
    except Exception as e:  # noqa: BLE001
        logger.debug("HLKM ingest 실패: %s", e)


__all__ = [
    "summarize_pending_papers",
    "summarize_one",
    "HWARANG_MODULES",
]
