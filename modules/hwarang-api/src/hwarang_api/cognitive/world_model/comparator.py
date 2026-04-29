"""대안 액션 비교 + 최선안 추천.

여러 액션을 ``WorldSimulator`` 로 병렬 시뮬레이션 후 LLM 으로 정성 평가.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from hwarang_api.cognitive.world_model.scenarios import Scenario
from hwarang_api.cognitive.world_model.simulator import (
    SimulationResult,
    WorldSimulator,
)
from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


async def compare_actions(
    scenario: Scenario,
    actions: list[str],
    steps: int = 3,
) -> dict[str, SimulationResult]:
    """여러 액션을 같은 시나리오에서 병렬 시뮬레이션.

    Parameters
    ----------
    scenario : Scenario
        시뮬레이션 시나리오.
    actions : list[str]
        비교할 액션 후보. 빈 리스트면 빈 dict 반환.
    steps : int
        각 액션의 시뮬레이션 단계 수 (기본 3 — 비교용은 짧게).

    Returns
    -------
    dict[str, SimulationResult]
        액션 → 결과 매핑. 일부 실패해도 폴백 결과를 채운다.
    """
    actions = [a for a in (actions or []) if a]
    if not actions:
        return {}

    sim = WorldSimulator()
    tasks = [sim.simulate(scenario, action=a, steps=steps) for a in actions]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    out: dict[str, SimulationResult] = {}
    for action, res in zip(actions, results):
        if isinstance(res, BaseException):
            logger.warning("compare_actions: '%s' 시뮬 실패: %s", action, res)
            out[action] = SimulationResult(
                scenario=scenario.name,
                action=action,
                trajectory=[],
                final_state=dict(scenario.initial_state),
                confidence=0.0,
                risks=[f"시뮬레이션 예외: {res}"],
            )
        else:
            out[action] = res
    return out


def _summarize_for_judge(action: str, r: SimulationResult) -> str:
    """LLM 판정 프롬프트용 압축 요약 (1 액션)."""
    final_pairs = "; ".join(f"{k}={v}" for k, v in list(r.final_state.items())[:8])
    risk_text = " / ".join(r.risks[:4]) if r.risks else "(없음)"
    return (
        f"- 액션: {action}\n"
        f"  신뢰도: {round(r.confidence, 3)}\n"
        f"  주요 최종 상태: {final_pairs}\n"
        f"  리스크: {risk_text}"
    )


async def recommend_best(
    scenario: Scenario,
    actions: list[str],
    criteria: str = "안정성",
    steps: int = 3,
) -> str:
    """LLM 이 시뮬 결과를 보고 최선의 액션을 고른다.

    Parameters
    ----------
    criteria : str
        한국어 평가 기준 — ``안정성``, ``성장성``, ``재정건전성``, ``공정성`` 등.

    Returns
    -------
    str
        선택된 액션 문자열 (후보에 없으면 첫 액션을 폴백 반환).
    """
    if not actions:
        return ""

    results = await compare_actions(scenario, actions, steps=steps)
    if not results:
        return actions[0]

    summaries = "\n".join(_summarize_for_judge(a, r) for a, r in results.items())
    system = (
        "당신은 한국 정책·경제 자문가입니다. 시뮬레이션 결과 요약을 보고 "
        f"평가 기준({criteria}) 에 가장 부합하는 액션 1 개를 선택하세요. "
        "응답은 반드시 다음 형식 한 줄: 'CHOICE: <액션문자열>'. 다른 설명 금지."
    )
    prompt = (
        f"[시나리오] {scenario.name}\n"
        f"[기준] {criteria}\n"
        f"[후보 시뮬 결과]\n{summaries}\n\n"
        "가장 적합한 액션 한 개만 'CHOICE: <문자열>' 형식으로 답하세요."
    )
    resp = await llm_chat(prompt, system=system, max_tokens=120)
    if not resp:
        return actions[0]

    m = re.search(r"CHOICE\s*:\s*(.+)", resp.strip())
    if m:
        choice = m.group(1).strip().strip("'\"")
        # 후보 목록에서 가장 비슷한 것 매칭
        for a in actions:
            if a == choice or a in choice or choice in a:
                return a
    # 자유서술 폴백 — 후보 중 본문에 가장 먼저 등장한 것
    for a in actions:
        if a and a in resp:
            return a
    return actions[0]


__all__ = ["compare_actions", "recommend_best"]
