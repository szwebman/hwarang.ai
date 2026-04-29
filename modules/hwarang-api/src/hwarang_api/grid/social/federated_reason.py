"""분산 추론 — 신뢰 가중 다중 에이전트 질의.

상위 신뢰 N 명에게 같은 질문을 던지고, 답변이 일치하면 신뢰 가중 투표,
다르면 ``dispute.resolve_dispute`` 로 LLM 심판.

# 주의: 실제 에이전트 콜백 채널은 grid.matcher / inter_agent 의 기존 메커니즘을
# 사용해야 한다. 현재 환경에서 콜백 인프라가 없으면 LLM single-shot 으로 fallback.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

from hwarang_api.grid.social.dispute import resolve_dispute
from hwarang_api.grid.social.reputation import (
    get_trust_score,
    record_failure,
    record_success,
    top_agents,
)
from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


# 외부에서 주입 가능한 dispatcher — (agent_id, question) -> answer text.
# None 이면 LLM single-shot 으로 fallback.
_DISPATCH: Optional[Callable[[str, str], Awaitable[str]]] = None


def set_dispatcher(fn: Optional[Callable[[str, str], Awaitable[str]]]) -> None:
    """grid 라우터/통합 코드가 dispatcher 를 주입할 때 사용."""
    global _DISPATCH
    _DISPATCH = fn


async def _llm_fallback(question: str, agent_id: str) -> str:
    """에이전트 dispatcher 없을 때 LLM 으로 직접 답변 (페르소나 다양화)."""
    system = (
        f"당신은 화랑 분산 네트워크의 에이전트 '{agent_id}' 역할로 "
        "한국어로 정확하고 간결하게 답변합니다. 1~3문장."
    )
    return (await llm_chat(question, system=system, max_tokens=400)) or ""


async def _ask_agent(agent_id: str, question: str) -> str:
    if _DISPATCH is not None:
        try:
            return (await _DISPATCH(agent_id, question)) or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("federated_reason: dispatcher 실패(%s): %s", agent_id, exc)
            return ""
    return await _llm_fallback(question, agent_id)


def _normalize(text: str) -> str:
    return " ".join((text or "").split()).strip().lower()


async def federated_query(question: str, num_agents: int = 3) -> dict:
    """상위 N 명에게 질의 → 합의 또는 분쟁 해결.

    Returns
    -------
    dict
        ``{question, final_answer, agent_contributions, method, confidence}``.
        method ∈ ``trust_weighted_vote`` / ``dispute_judge`` / ``single``.
    """
    num_agents = max(1, min(int(num_agents), 10))
    leaders = await top_agents(num_agents)

    # 평판 데이터가 비었으면 익명 합성 에이전트로 시작 (콜드 스타트)
    if not leaders:
        leaders = [
            {"agentId": f"anon_{i+1}", "trustScore": 0.5}
            for i in range(num_agents)
        ]

    answers: list[dict] = []
    tasks = [_ask_agent(str(l["agentId"]), question) for l in leaders]
    raw = await asyncio.gather(*tasks, return_exceptions=True)
    for leader, content in zip(leaders, raw):
        aid = str(leader["agentId"])
        if isinstance(content, BaseException) or not content:
            try:
                await record_failure(aid)
            except Exception:  # noqa: BLE001
                pass
            continue
        trust = float(leader.get("trustScore", 0.5))
        answers.append(
            {
                "agent_id": aid,
                "content": str(content),
                "trust": trust,
                "sources": [],
            }
        )

    if not answers:
        return {
            "question": question,
            "final_answer": "",
            "agent_contributions": [],
            "method": "none",
            "confidence": 0.0,
        }

    if len(answers) == 1:
        a = answers[0]
        try:
            await record_success(a["agent_id"], quality_score=0.7)
        except Exception:  # noqa: BLE001
            pass
        return {
            "question": question,
            "final_answer": a["content"],
            "agent_contributions": answers,
            "method": "single",
            "confidence": 0.6,
        }

    # 1) 신뢰 가중 투표 — 정규화 후 동일 답변 그룹화
    groups: dict[str, dict[str, Any]] = {}
    for a in answers:
        key = _normalize(a["content"])[:240]
        if not key:
            continue
        g = groups.setdefault(key, {"weight": 0.0, "members": [], "sample": a["content"]})
        g["weight"] += a["trust"]
        g["members"].append(a["agent_id"])

    if groups:
        top_group = max(groups.values(), key=lambda g: g["weight"])
        total_weight = sum(g["weight"] for g in groups.values()) or 1.0
        share = top_group["weight"] / total_weight
        # 60% 이상 가중치 점유 → 합의 인정
        if share >= 0.6:
            for aid in top_group["members"]:
                try:
                    await record_success(aid, quality_score=0.8)
                except Exception:  # noqa: BLE001
                    pass
            return {
                "question": question,
                "final_answer": top_group["sample"],
                "agent_contributions": answers,
                "method": "trust_weighted_vote",
                "confidence": round(min(1.0, share), 4),
            }

    # 2) 의견 충돌 → LLM 심판
    judgment = await resolve_dispute(
        [{"agent_id": a["agent_id"], "content": a["content"], "sources": []} for a in answers],
        update_reputation=True,
    )
    winner_id = judgment.get("winner_agent_id", "")
    winner_content = ""
    for a in answers:
        if a["agent_id"] == winner_id:
            winner_content = a["content"]
            break
    if not winner_content and answers:
        winner_content = answers[0]["content"]

    return {
        "question": question,
        "final_answer": winner_content,
        "agent_contributions": answers,
        "method": "dispute_judge",
        "confidence": float(judgment.get("confidence", 0.5)),
        "judge_reason": judgment.get("reason", ""),
    }


__all__ = ["federated_query", "set_dispatcher"]
