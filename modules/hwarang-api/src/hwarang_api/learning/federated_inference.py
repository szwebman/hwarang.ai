"""Multi-Agent Synthesis — 여러 도메인 전문 에이전트 협업 추론 (HSEE Phase 5).

복잡한 다도메인 질문 (예: "임플란트 시술 후 부작용 발생 시 의료배상보험 청구 절차") 은
단일 모델 1회 추론으로는 한 측면만 잡힌다. 도메인 전문 모델 여러 개에 동시 질의
후 합성하면 측면별 정확도 + 모순 검출 + 면책 자동 추가가 가능하다.

5단계 흐름:

1. **Classify** — 질문에 관련 있는 도메인 다중 분류 (legal/medical/tax/finance/coding/general)
2. **Query** — 각 도메인의 ``isDomainDefault`` 모델에 동시 질의 (asyncio.gather)
3. **Contradiction detect** — 답변들 사이 사실관계 모순 LLM 검출
4. **Debate** — 모순 시 최대 ``max_rounds`` 회 토론 후 답변 보강
5. **Synthesize** — 종합 답변 1개 + 측면 표시 + 면책 자동 추가

단일 도메인이면 ``skip=True`` 로 빠르게 우회.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Optional

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────
# 프롬프트
# ────────────────────────────────────────────────────────────
DOMAIN_CLASSIFY_PROMPT = """다음 질문에 관련 있는 도메인을 모두 골라라 (1~3개).
가능한 도메인: legal, medical, tax, finance, coding, general

질문: {question}

JSON: {{"domains": [...]}}
JSON 만 출력:"""


SYNTHESIZE_PROMPT = """다음 도메인 전문가들의 답변을 종합해서 사용자에게 1개 답변을 만들어라.
모순이 있으면 "X 측면에서는 A, Y 측면에서는 B" 처럼 구분 표시해라.
중요한 면책 (예: "정확한 진단/판단은 전문가 직접 상담 필요") 을 마지막에 자동 추가해라.

질문: {question}

전문가 답변:
{expert_answers}

답변:"""


DEBATE_PROMPT = """전문가들의 답변에서 모순 발견. 각자 자기 입장 보강하거나 양보해라.

원래 답변들:
{answers}

모순점: {contradiction}

각 전문가 입장에서 1줄 응답:
{debate_format}"""


VALID_DOMAINS = {"legal", "medical", "tax", "finance", "coding", "general"}


# ────────────────────────────────────────────────────────────
# 메인 진입점
# ────────────────────────────────────────────────────────────
async def federated_inference(
    question: str,
    max_rounds: int = 2,
) -> dict[str, Any]:
    """다도메인 질문 → 전문가 협업 답변.

    Returns
    -------
    dict
        성공 시 ``{"synthesized", "domains", "expert_chains", "contradictions",
        "debate_rounds", "debate_log"}``.

        단일 도메인 → ``{"single_domain", "skip": True}``.
        전문가 부족 → ``{"insufficient_experts": True, "domains": [...]}``.
        호출 모두 실패 → ``{"failed_experts": True}``.
    """
    # 1. 도메인 분류
    domains = await _classify_domains(question)
    domains = [d for d in domains if d in VALID_DOMAINS]
    if len(domains) <= 1:
        return {
            "single_domain": domains[0] if domains else "general",
            "skip": True,
        }

    # 2. 도메인별 전문 모델 선택 (DB AIModel)
    expert_models: list[dict] = []
    for d in domains:
        try:
            model = await prisma.aimodel.find_first(
                where={
                    "category": d,
                    "isActive": True,
                    "isDomainDefault": True,
                },
            )
            if not model:
                model = await prisma.aimodel.find_first(
                    where={"category": d, "isActive": True},
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"federated: aimodel 조회 실패 ({d}): {exc}")
            model = None
        if model:
            expert_models.append({"domain": d, "model": model})

    if len(expert_models) < 2:
        return {
            "insufficient_experts": True,
            "domains": domains,
            "found": len(expert_models),
        }

    # 3. 동시 질의
    answers = await asyncio.gather(
        *[
            _query_expert(question, em["model"], em["domain"])
            for em in expert_models
        ],
        return_exceptions=True,
    )

    expert_answers: list[dict] = []
    for em, ans in zip(expert_models, answers):
        if isinstance(ans, Exception) or not ans:
            continue
        expert_answers.append(
            {
                "domain": em["domain"],
                "model": getattr(em["model"], "name", "?"),
                "answer": ans,
            }
        )

    if len(expert_answers) < 2:
        return {"failed_experts": True, "domains": domains}

    # 4. 모순 검출
    contradiction = await _detect_contradictions(expert_answers)

    # 5. 토론 라운드 (모순 있을 때만)
    debate_log: list[dict] = []
    if contradiction.get("found"):
        for _round in range(max_rounds):
            debate_results = await _debate_round(expert_answers, contradiction)
            debate_log.append(debate_results)

            for d in debate_results.get("updated_answers", []):
                for ea in expert_answers:
                    if ea["domain"] == d.get("domain"):
                        ea["answer"] = d.get("answer", ea["answer"])

            contradiction = await _detect_contradictions(expert_answers)
            if not contradiction.get("found"):
                break

    # 6. 종합 답변
    expert_text = "\n\n".join(
        f"[{ea['domain']}]\n{ea['answer'][:1500]}" for ea in expert_answers
    )

    synthesized = await llm_chat(
        SYNTHESIZE_PROMPT.format(
            question=question,
            expert_answers=expert_text,
        ),
        max_tokens=1024,
    )

    return {
        "domains": [ea["domain"] for ea in expert_answers],
        "synthesized": synthesized,
        "expert_chains": expert_answers,
        "contradictions": contradiction,
        "debate_rounds": len(debate_log),
        "debate_log": debate_log,
    }


# ────────────────────────────────────────────────────────────
# 단계별 헬퍼
# ────────────────────────────────────────────────────────────
async def _classify_domains(question: str) -> list[str]:
    try:
        raw = await llm_chat(
            DOMAIN_CLASSIFY_PROMPT.format(question=question[:1000])
        )
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            data = json.loads(m.group())
            doms = data.get("domains") or []
            return [str(d).lower().strip() for d in doms if d]
    except Exception:  # noqa: BLE001
        pass
    return ["general"]


async def _query_expert(
    question: str, model: Any, domain: str
) -> Optional[str]:
    """특정 모델/LoRA 로 질의 — Next.js /api/chat 우회 호출."""
    api_url = os.getenv("HWARANG_INTERNAL_URL", "http://localhost:3000")
    internal_key = os.getenv("HWARANG_INTERNAL_KEY", "")

    try:
        import httpx
    except Exception:  # pragma: no cover
        return None

    headers = {"Content-Type": "application/json"}
    if internal_key:
        headers["Authorization"] = f"Bearer {internal_key}"

    payload = {
        "model": getattr(model, "name", None),
        "messages": [{"role": "user", "content": question}],
        "stream": False,
        "verify": False,
        "federated": False,  # 무한 재귀 방지
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{api_url.rstrip('/')}/api/chat",
                headers=headers,
                json=payload,
            )
        if resp.status_code != 200:
            logger.debug(f"_query_expert {domain}: status={resp.status_code}")
            return None
        return (
            resp.json()
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content")
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"_query_expert {domain} 실패: {exc}")
        return None


async def _detect_contradictions(answers: list[dict]) -> dict:
    """답변들 사이 사실관계 모순 LLM 검출."""
    if len(answers) < 2:
        return {"found": False}

    answers_text = "\n\n".join(
        f"[{a['domain']}] {a['answer'][:800]}" for a in answers
    )
    prompt = (
        "다음 답변들 사이에 사실관계 모순이 있나?\n"
        f"{answers_text}\n\n"
        "JSON: {\"found\": true|false, \"issue\": \"있으면 모순점 한 줄\"}\n"
        "JSON 만:"
    )

    try:
        raw = await llm_chat(prompt)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:  # noqa: BLE001
        pass
    return {"found": False}


async def _debate_round(answers: list[dict], contradiction: dict) -> dict:
    """전문가들끼리 모순 해결 토론 1라운드."""
    answers_text = "\n".join(
        f"[{a['domain']}] {a['answer'][:500]}" for a in answers
    )
    debate_format = "\n".join(f"- [{a['domain']}]: " for a in answers)

    try:
        raw = await llm_chat(
            DEBATE_PROMPT.format(
                answers=answers_text,
                contradiction=contradiction.get("issue", ""),
                debate_format=debate_format,
            ),
            max_tokens=512,
        )
        # 단순 파싱 — 각 도메인 라벨 라인 추출
        updated: list[dict] = []
        for ln in raw.splitlines():
            ln = ln.strip()
            m = re.match(r"^[-\*•]?\s*\[([a-zA-Z]+)\]\s*:?\s*(.+)$", ln)
            if m:
                updated.append(
                    {
                        "domain": m.group(1).lower().strip(),
                        "answer": m.group(2).strip(),
                    }
                )
        return {"raw": raw, "updated_answers": updated}
    except Exception:  # noqa: BLE001
        return {"raw": "", "updated_answers": []}


__all__ = [
    "federated_inference",
]
