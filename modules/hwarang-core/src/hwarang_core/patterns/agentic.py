"""Agentic Patterns - 자율 에이전트.

LLM이 스스로 계획을 세우고, 도구를 사용하고,
결과를 검증하고, 필요하면 다시 시도하는 자율 에이전트입니다.

패턴:
1. ReAct: Reasoning + Acting (생각 → 행동 → 관찰 반복)
2. Plan-and-Execute: 먼저 계획 → 순서대로 실행
3. Reflection: 자기 답변을 스스로 검토 → 개선
4. Multi-Agent: 여러 에이전트가 협력
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator

logger = logging.getLogger(__name__)


class AgentState(str, Enum):
    THINKING = "thinking"      # 추론 중
    ACTING = "acting"          # 도구 호출 중
    OBSERVING = "observing"    # 결과 관찰
    REFLECTING = "reflecting"  # 자기 검토
    DONE = "done"              # 완료


@dataclass
class AgentStep:
    """에이전트 한 스텝의 기록."""
    state: AgentState
    thought: str = ""        # 에이전트의 생각
    action: str = ""         # 실행한 도구/함수
    action_input: str = ""   # 도구 입력
    observation: str = ""    # 도구 결과
    reflection: str = ""     # 자기 검토


@dataclass
class AgentPlan:
    """Plan-and-Execute 패턴의 실행 계획."""
    goal: str
    steps: list[str]
    current_step: int = 0
    completed_steps: list[str] = field(default_factory=list)
    results: list[str] = field(default_factory=list)


# ============================================================
# ReAct Agent
# ============================================================

class ReActAgent:
    """ReAct 패턴 에이전트.

    루프:
    1. Thought: 현재 상황 분석 + 다음 행동 결정
    2. Action: 도구 호출
    3. Observation: 결과 확인
    4. 반복 (최대 N회)
    5. Final Answer: 최종 답변
    """

    REACT_SYSTEM_PROMPT = """당신은 도구를 사용할 수 있는 AI 에이전트입니다.

매 턴마다 아래 형식으로 응답하세요:

Thought: [현재 상황 분석 + 다음에 뭘 해야 할지]
Action: [사용할 도구 이름]
Action Input: [도구에 전달할 입력 (JSON)]

도구 실행 결과를 받으면:
Observation: [도구 결과]

최종 답변이 준비되면:
Thought: 충분한 정보를 얻었습니다.
Final Answer: [사용자에게 전달할 최종 답변]"""

    def __init__(self, llm, tools, max_iterations: int = 10):
        self.llm = llm
        self.tools = tools  # FunctionRegistry
        self.max_iterations = max_iterations

    async def run(self, query: str) -> AsyncIterator[AgentStep]:
        """에이전트 실행."""
        messages = [
            {"role": "system", "content": self.REACT_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]

        for i in range(self.max_iterations):
            # 1. LLM에게 다음 행동 요청
            response = await self.llm.chat(messages)
            text = response.content or ""

            # 2. 파싱: Thought, Action, Final Answer
            step = self._parse_response(text)
            yield step

            if step.state == AgentState.DONE:
                return

            # 3. 도구 실행
            if step.action:
                from hwarang_core.patterns.function_calling import FunctionCall
                call = FunctionCall(name=step.action, arguments=json.loads(step.action_input or "{}"))
                result = await self.tools.execute(call)

                observation = result.result if result.success else f"Error: {result.error}"
                step.observation = str(observation)

                yield AgentStep(
                    state=AgentState.OBSERVING,
                    observation=str(observation),
                )

                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": f"Observation: {observation}"})

        yield AgentStep(state=AgentState.DONE, thought="최대 반복 횟수에 도달했습니다.")

    def _parse_response(self, text: str) -> AgentStep:
        """LLM 응답에서 Thought/Action/Final Answer 파싱."""
        thought = ""
        action = ""
        action_input = ""

        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("Thought:"):
                thought = line[8:].strip()
            elif line.startswith("Action:"):
                action = line[7:].strip()
            elif line.startswith("Action Input:"):
                action_input = line[13:].strip()
            elif line.startswith("Final Answer:"):
                return AgentStep(
                    state=AgentState.DONE,
                    thought=thought,
                    observation=line[13:].strip(),
                )

        if action:
            return AgentStep(
                state=AgentState.ACTING,
                thought=thought,
                action=action,
                action_input=action_input,
            )

        return AgentStep(state=AgentState.THINKING, thought=thought or text)


# ============================================================
# Plan-and-Execute Agent
# ============================================================

class PlanAndExecuteAgent:
    """Plan-and-Execute 패턴.

    1단계: 계획 세우기 (전체 작업을 하위 작업으로 분해)
    2단계: 하위 작업을 순서대로 실행
    3단계: 결과 종합
    """

    PLAN_PROMPT = """사용자의 요청을 수행하기 위한 단계별 계획을 세우세요.
각 단계는 구체적이고 실행 가능해야 합니다.

JSON 형식으로 응답:
{
  "goal": "전체 목표",
  "steps": ["1단계: ...", "2단계: ...", "3단계: ..."]
}"""

    def __init__(self, llm, tools=None, max_steps: int = 10):
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps

    async def run(self, query: str) -> AsyncIterator[AgentStep]:
        """계획 수립 → 실행."""
        # 1. 계획 수립
        yield AgentStep(state=AgentState.THINKING, thought="계획을 세우고 있습니다...")

        plan = await self._make_plan(query)
        yield AgentStep(
            state=AgentState.THINKING,
            thought=f"계획: {plan.goal}\n" + "\n".join(f"  {s}" for s in plan.steps),
        )

        # 2. 단계별 실행
        for i, step_desc in enumerate(plan.steps[:self.max_steps]):
            plan.current_step = i

            yield AgentStep(
                state=AgentState.ACTING,
                action=f"Step {i+1}/{len(plan.steps)}",
                action_input=step_desc,
            )

            result = await self._execute_step(step_desc, plan.results)
            plan.results.append(result)
            plan.completed_steps.append(step_desc)

            yield AgentStep(
                state=AgentState.OBSERVING,
                observation=result,
            )

        # 3. 결과 종합
        final = await self._summarize(plan)
        yield AgentStep(state=AgentState.DONE, observation=final)

    async def _make_plan(self, query: str) -> AgentPlan:
        messages = [
            {"role": "system", "content": self.PLAN_PROMPT},
            {"role": "user", "content": query},
        ]
        response = await self.llm.chat(messages)

        from hwarang_core.patterns.structured_output import extract_json
        data = extract_json(response.content or "")
        if data and isinstance(data, dict):
            return AgentPlan(
                goal=data.get("goal", query),
                steps=data.get("steps", [query]),
            )
        return AgentPlan(goal=query, steps=[query])

    async def _execute_step(self, step: str, previous_results: list[str]) -> str:
        context = ""
        if previous_results:
            context = "이전 결과:\n" + "\n".join(f"  - {r[:200]}" for r in previous_results[-3:])

        messages = [
            {"role": "system", "content": "주어진 단계를 실행하세요. 간결하게 결과만 답하세요."},
            {"role": "user", "content": f"{context}\n\n실행할 단계: {step}"},
        ]
        response = await self.llm.chat(messages)
        return response.content or ""

    async def _summarize(self, plan: AgentPlan) -> str:
        results_text = "\n".join(f"Step {i+1}: {r}" for i, r in enumerate(plan.results))
        messages = [
            {"role": "system", "content": "모든 단계의 결과를 종합하여 최종 답변을 작성하세요."},
            {"role": "user", "content": f"목표: {plan.goal}\n\n결과:\n{results_text}"},
        ]
        response = await self.llm.chat(messages)
        return response.content or ""


# ============================================================
# Reflection Agent
# ============================================================

class ReflectionAgent:
    """Reflection 패턴 - 자기 답변을 스스로 검토 + 개선.

    1. 초기 답변 생성
    2. 자기 답변 비판적 검토
    3. 개선된 답변 생성
    4. 반복 (최대 N회)
    """

    REFLECT_PROMPT = """아래 답변을 비판적으로 검토하세요.
부정확한 부분, 빠진 내용, 개선할 점을 찾아주세요.

답변:
{answer}

검토 결과를 JSON으로:
{{"issues": ["문제1", "문제2"], "score": 8, "should_improve": true/false}}"""

    def __init__(self, llm, max_reflections: int = 2):
        self.llm = llm
        self.max_reflections = max_reflections

    async def run(self, query: str) -> AsyncIterator[AgentStep]:
        """반성적 답변 생성."""
        # 1. 초기 답변
        messages = [{"role": "user", "content": query}]
        response = await self.llm.chat(messages)
        current_answer = response.content or ""

        yield AgentStep(state=AgentState.THINKING, thought=f"초기 답변 생성 완료")

        # 2. 반복 검토 + 개선
        for i in range(self.max_reflections):
            # 검토
            reflect_messages = [
                {"role": "user", "content": self.REFLECT_PROMPT.format(answer=current_answer)},
            ]
            reflect_response = await self.llm.chat(reflect_messages)

            from hwarang_core.patterns.structured_output import extract_json
            review = extract_json(reflect_response.content or "")

            if review and isinstance(review, dict):
                score = review.get("score", 10)
                should_improve = review.get("should_improve", False)

                yield AgentStep(
                    state=AgentState.REFLECTING,
                    reflection=f"검토 점수: {score}/10, 개선 필요: {should_improve}",
                    observation=str(review.get("issues", [])),
                )

                if not should_improve or score >= 9:
                    break

                # 개선
                improve_messages = [
                    {"role": "user", "content": query},
                    {"role": "assistant", "content": current_answer},
                    {"role": "user", "content": f"다음 문제를 개선해주세요: {review.get('issues', [])}"},
                ]
                improved = await self.llm.chat(improve_messages)
                current_answer = improved.content or current_answer
            else:
                break

        yield AgentStep(state=AgentState.DONE, observation=current_answer)
