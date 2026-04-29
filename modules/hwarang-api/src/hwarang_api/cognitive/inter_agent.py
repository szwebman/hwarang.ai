"""에이전트 간 다회차 토론 + 의견 변경 추적 (Phase 6 보강).

Phase 5 ``federated_inference`` 와 다른 점
------------------------------------------
* 다회차 (debate rounds 3+)
* 각 에이전트가 다른 에이전트 의견에 반응 (rebuttal)
* 의견 변경 추적 (누가 누구한테 설득됐나)
* 합의 도달 또는 timeout 시 종료
* CognitiveMemory 에 토론 이력 저장

흐름
----
1. ``Round 0`` — 초기 답변을 ``AgentOpinion`` 으로 변환.
2. 합의 체크 (``_check_consensus``) → 즉시 종료 가능.
3. 각 라운드:
   - 모든 에이전트가 다른 답변을 보고 ``_agent_rebut`` 으로 자기 의견 재평가.
   - 결정: maintain / agree_with / partial_accept / new_synthesis.
   - 합의 체크.
4. ``_synthesize_consensus`` 로 최종 합의안 + ``_summarize_debate`` 로 요약.
5. ``record_decision`` 으로 ``inter_agent_debate`` actor 에 영구 보존.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from hwarang_api.cognitive.memory import record_decision
from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────
# 데이터 모델
# ────────────────────────────────────────────────────────────
@dataclass
class AgentOpinion:
    agent_id: str
    domain: str
    answer: str
    confidence: float
    reasoning: str
    round_num: int = 0
    changed_from: Optional[str] = None  # 의견 변경 시 직전 agent_id 표시


@dataclass
class DebateState:
    question: str
    domains_involved: list[str]
    rounds: list[list[AgentOpinion]] = field(default_factory=list)
    consensus_reached: bool = False
    final_answer: str = ""
    debate_summary: str = ""


# ────────────────────────────────────────────────────────────
# 프롬프트
# ────────────────────────────────────────────────────────────
REBUTTAL_PROMPT = """당신은 {domain} 전문 에이전트입니다. 다른 에이전트들의 답변을 보고 자기 의견을 다시 평가하세요.

## 원래 질문
{question}

## 내 이전 답변
{my_previous}

## 다른 에이전트들의 답변
{others_text}

## 결정 옵션
1. 내 답변을 유지 — 더 강한 근거 제시
2. 다른 에이전트 답변에 동의 — 어떤 부분을 수용하는지
3. 부분 수용 — 일부만 받아들이고 다른 부분은 재반박
4. 새로운 합의안 제시 — 모두를 통합하는 새 답변

JSON 답변:
{{
  "decision": "maintain|agree_with|partial_accept|new_synthesis",
  "agreed_with_agent": "agent_id (decision=agree_with 일 때)",
  "new_answer": "수정된 답변",
  "confidence": 0.0~1.0,
  "reasoning": "왜 이렇게 결정했는지"
}}

JSON 만 출력:"""


CONSENSUS_CHECK_PROMPT = """다음 답변들이 합의에 도달했는지 평가해라.

답변들:
{answers}

JSON: {{"consensus": true|false, "summary": "합의 요약 또는 남은 모순"}}
JSON 만:"""


SYNTHESIZE_PROMPT = """다음 전문가 답변들을 종합한 최종 답변을 한국어로 작성해라.

질문: {question}

전문가 답변:
{answers_text}

종합 답변 (5~10줄, 면책 조항 자동 추가):"""


# ────────────────────────────────────────────────────────────
# 메인 진입점
# ────────────────────────────────────────────────────────────
async def multi_round_debate(
    question: str,
    expert_answers: list[dict],
    max_rounds: int = 3,
) -> DebateState:
    """다회차 토론.

    Args:
        question: 사용자 질문
        expert_answers: 초기 전문가 답변 ``[{agent_id, domain, answer, confidence, reasoning}]``
        max_rounds: 최대 토론 라운드

    Returns:
        ``DebateState`` — rounds 누적, 합의 여부, final_answer, summary 포함
    """
    state = DebateState(
        question=question,
        domains_involved=sorted({a.get("domain", "general") for a in expert_answers}),
    )

    # Round 0 — 초기 답변
    initial_round: list[AgentOpinion] = [
        AgentOpinion(
            agent_id=a.get("agent_id") or a.get("domain") or f"agent_{i}",
            domain=a.get("domain", "general"),
            answer=a.get("answer", ""),
            confidence=float(a.get("confidence", 0.7)),
            reasoning=a.get("reasoning", ""),
            round_num=0,
        )
        for i, a in enumerate(expert_answers)
    ]
    state.rounds.append(initial_round)

    # 단일 에이전트면 토론 불가
    if len(initial_round) < 2:
        state.consensus_reached = True
        state.final_answer = initial_round[0].answer if initial_round else ""
        state.debate_summary = "단일 도메인 — 토론 불필요"
        return state

    # 초기 합의 체크
    if await _check_consensus(initial_round):
        state.consensus_reached = True
        state.final_answer = await _synthesize_consensus(question, initial_round)
        state.debate_summary = (
            f"{len(state.domains_involved)}개 도메인 — Round 0 즉시 합의."
        )
        await _persist_debate(state, len(expert_answers))
        return state

    # 다회차 토론
    current_opinions = initial_round
    for round_num in range(1, max_rounds + 1):
        next_opinions: list[AgentOpinion] = []
        for agent in current_opinions:
            others = [o for o in current_opinions if o.agent_id != agent.agent_id]
            new_opinion = await _agent_rebut(agent, others, question, round_num)
            next_opinions.append(new_opinion)

        state.rounds.append(next_opinions)
        current_opinions = next_opinions

        if await _check_consensus(current_opinions):
            state.consensus_reached = True
            break

    # 최종 합의 (timeout 시에도 강제 종합)
    state.final_answer = await _synthesize_consensus(question, current_opinions)
    state.debate_summary = await _summarize_debate(state)

    await _persist_debate(state, len(expert_answers))
    return state


# ────────────────────────────────────────────────────────────
# 라운드 동작
# ────────────────────────────────────────────────────────────
async def _agent_rebut(
    agent: AgentOpinion,
    others: list[AgentOpinion],
    question: str,
    round_num: int,
) -> AgentOpinion:
    """단일 에이전트의 반박/재평가 라운드."""

    others_text = "\n\n".join(
        f"### [{o.domain}/{o.agent_id}] (신뢰도 {o.confidence:.2f})\n{o.answer[:600]}"
        for o in others
    )

    prompt = REBUTTAL_PROMPT.format(
        domain=agent.domain,
        question=question[:500],
        my_previous=agent.answer[:800],
        others_text=others_text,
    )

    try:
        raw = await llm_chat(prompt)
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if m:
            data = json.loads(m.group())

            new_answer = (data.get("new_answer") or agent.answer)[:2000]
            decision = (data.get("decision") or "maintain").lower()
            agreed_with = data.get("agreed_with_agent") or ""

            # changed_from = 어떤 에이전트한테 영향받았는지
            changed_from: Optional[str] = None
            if decision != "maintain":
                changed_from = agreed_with or "synthesis"

            return AgentOpinion(
                agent_id=agent.agent_id,
                domain=agent.domain,
                answer=new_answer,
                confidence=float(data.get("confidence", agent.confidence)),
                reasoning=str(data.get("reasoning", ""))[:500],
                round_num=round_num,
                changed_from=changed_from,
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("agent %s 반박 실패: %s", agent.agent_id, exc)

    # 폴백 — 기존 의견 유지
    return AgentOpinion(
        agent_id=agent.agent_id,
        domain=agent.domain,
        answer=agent.answer,
        confidence=agent.confidence,
        reasoning=agent.reasoning,
        round_num=round_num,
    )


async def _check_consensus(opinions: list[AgentOpinion]) -> bool:
    """합의 도달 판정 — LLM 호출 실패 시 보수적으로 False."""
    if len(opinions) < 2:
        return True

    answers_text = "\n".join(
        f"[{o.domain}] {o.answer[:400]}" for o in opinions
    )

    try:
        raw = await llm_chat(CONSENSUS_CHECK_PROMPT.format(answers=answers_text))
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if m:
            return bool(json.loads(m.group()).get("consensus", False))
    except Exception as exc:  # noqa: BLE001
        logger.debug("consensus 체크 실패: %s", exc)
    return False


async def _synthesize_consensus(question: str, opinions: list[AgentOpinion]) -> str:
    """최종 합의안 생성 — LLM 실패 시 가장 신뢰도 높은 답변 폴백."""
    answers_text = "\n\n".join(
        f"### [{o.domain}] (신뢰도 {o.confidence:.2f})\n{o.answer[:800]}"
        for o in opinions
    )

    prompt = SYNTHESIZE_PROMPT.format(
        question=question[:300],
        answers_text=answers_text,
    )

    try:
        out = (await llm_chat(prompt)) or ""
        if out.strip():
            return out[:3000]
    except Exception as exc:  # noqa: BLE001
        logger.debug("synthesize 실패: %s", exc)

    # 폴백 — 신뢰도 최상위 답변 또는 단순 join
    if opinions:
        best = max(opinions, key=lambda o: o.confidence)
        return best.answer[:3000]
    return ""


async def _summarize_debate(state: DebateState) -> str:
    """토론 요약 — 누가 누구를 설득했는지 등."""
    changes = []
    for round_n, opinions in enumerate(state.rounds[1:], start=1):
        for op in opinions:
            if op.changed_from:
                changes.append(
                    f"Round {round_n}: {op.agent_id} ({op.domain}) "
                    f"가 {op.changed_from} 영향으로 의견 변경"
                )

    return (
        f"{len(state.domains_involved)}개 도메인 전문가 토론. "
        f"{len(state.rounds)} 라운드, "
        f"{'합의 도달' if state.consensus_reached else 'timeout — 합의 강제 종합'}. "
        f"{len(changes)}회 의견 변경. "
        + ("주요 변경: " + " | ".join(changes[:3]) if changes else "")
    )


async def _persist_debate(state: DebateState, agent_count: int) -> None:
    """CognitiveMemory 에 토론 이력 저장."""
    try:
        await record_decision(
            actor="inter_agent_debate",
            observed={
                "question": state.question[:300],
                "domains": state.domains_involved,
                "agent_count": agent_count,
                "rounds": len(state.rounds),
                "consensus_reached": state.consensus_reached,
            },
            reasoning=state.debate_summary[:2000],
            decision=state.final_answer[:1500],
            action_taken="federated_synthesis",
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("debate persist 실패: %s", exc)


__all__ = [
    "AgentOpinion",
    "DebateState",
    "multi_round_debate",
]
