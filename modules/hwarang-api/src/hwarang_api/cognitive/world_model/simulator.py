"""LLM 기반 다단계 World Model 시뮬레이터.

각 스텝에서 (현재 상태, 시나리오 규칙, 선택 액션) 을 LLM 에 전달하여
다음 상태(JSON), 위험요소, 신뢰도를 추출한다. 한국 경제·정책 분석가 페르소나.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from hwarang_api.cognitive.world_model.scenarios import Scenario
from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


@dataclass
class SimulationResult:
    """시뮬레이션 결과 묶음.

    Attributes
    ----------
    scenario : str
        시나리오 이름.
    action : str
        시뮬레이션에 사용한 액션.
    trajectory : list[dict]
        스텝별 ``{"step": int, "state": dict, "delta": dict, "narrative": str}``.
    final_state : dict
        마지막 스텝의 상태 (또는 LLM 실패 시 초기 상태).
    confidence : float
        평균 스텝 신뢰도 0~1.
    risks : list[str]
        스텝마다 모인 한국어 리스크 노트.
    """

    scenario: str
    action: str
    trajectory: list[dict] = field(default_factory=list)
    final_state: dict = field(default_factory=dict)
    confidence: float = 0.0
    risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "action": self.action,
            "trajectory": self.trajectory,
            "final_state": self.final_state,
            "confidence": round(float(self.confidence), 4),
            "risks": list(self.risks),
        }


_SYSTEM = (
    "당신은 한국 거시경제·법률·정책 분야의 시뮬레이션 전문가입니다. "
    "주어진 시나리오 규칙과 현재 상태를 바탕으로 액션이 적용된 직후 "
    "1 스텝 후의 다음 상태를 추정하세요. 한국 시장/제도 맥락을 반영하고 "
    "비현실적인 급등락은 피하세요. "
    "오직 다음 형식의 JSON 한 개만 출력하세요. 코드블록·해설 금지.\n"
    '{"next_state": {<key>: <number_or_str>}, '
    '"delta": {<key>: <number>}, '
    '"narrative": "<한국어 1~2문장 변화 요약>", '
    '"risks": ["<한국어 위험요소>", ...], '
    '"confidence": <0.0~1.0>}'
)


def _safe_parse_json(text: str) -> Optional[dict]:
    """LLM 출력에서 첫 JSON 객체 추출 시도.

    코드블록 마커 / 잡담을 흡수한다. 실패 시 ``None``.
    """
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = cleaned[start : end + 1]
    try:
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


def _format_state(state: dict) -> str:
    """LLM 가독성을 위해 한국어 키-값 라인 포맷으로 변환."""
    return "\n".join(f"- {k}: {v}" for k, v in state.items())


class WorldSimulator:
    """LLM 기반 시나리오 시뮬레이터.

    한 인스턴스에서 여러 시나리오를 반복 호출 가능 (상태 무보존).
    """

    def __init__(self, max_tokens_per_step: int = 600) -> None:
        self.max_tokens_per_step = max_tokens_per_step

    async def _step_once(
        self,
        scenario: Scenario,
        action: str,
        current_state: dict,
        step_idx: int,
    ) -> Optional[dict]:
        """한 스텝 LLM 호출. 성공 시 파싱된 dict, 실패 시 ``None``."""
        rules_text = "\n".join(f"- {r}" for r in scenario.rules)
        prompt = (
            f"[시나리오] {scenario.name} (도메인={scenario.domain})\n"
            f"[스텝] {step_idx + 1}\n"
            f"[액션] {action}\n"
            f"[규칙]\n{rules_text}\n"
            f"[현재 상태]\n{_format_state(current_state)}\n\n"
            "위 정보를 바탕으로 다음 1 스텝의 상태를 JSON 으로만 출력하세요."
        )
        resp = await llm_chat(prompt, system=_SYSTEM, max_tokens=self.max_tokens_per_step)
        parsed = _safe_parse_json(resp)
        if parsed is None and resp:
            # 한 번 더 시도 (같은 프롬프트, 모델 재샘플링 의존)
            resp = await llm_chat(prompt, system=_SYSTEM, max_tokens=self.max_tokens_per_step)
            parsed = _safe_parse_json(resp)
        return parsed

    async def simulate(
        self,
        scenario: Scenario,
        action: str,
        steps: int = 5,
    ) -> SimulationResult:
        """``steps`` 단계 시뮬레이션 실행.

        LLM 이 한 스텝이라도 실패하면 그 스텝은 ``stable state`` (변경 없음)
        로 폴백하고 신뢰도 0.0 으로 기록한다. 전체가 실패해도 ``SimulationResult``
        는 항상 반환된다 (호출측에서 절대 예외 받지 않게).
        """
        steps = max(1, min(int(steps), 20))
        current = dict(scenario.initial_state)
        trajectory: list[dict] = []
        risks: list[str] = []
        confidences: list[float] = []

        for i in range(steps):
            try:
                parsed = await self._step_once(scenario, action, current, i)
            except Exception as exc:  # noqa: BLE001
                logger.warning("WorldSimulator 스텝 %d LLM 실패: %s", i, exc)
                parsed = None

            if parsed is None:
                trajectory.append(
                    {
                        "step": i + 1,
                        "state": dict(current),
                        "delta": {},
                        "narrative": "LLM 응답 파싱 실패 — 안정 상태 폴백.",
                        "fallback": True,
                    }
                )
                confidences.append(0.0)
                continue

            next_state = parsed.get("next_state")
            if not isinstance(next_state, dict) or not next_state:
                next_state = dict(current)

            # 누락 키는 직전 값 유지 (LLM 이 일부만 변경할 수 있음)
            merged = dict(current)
            for k, v in next_state.items():
                merged[k] = v

            delta = parsed.get("delta") if isinstance(parsed.get("delta"), dict) else {}
            narrative = str(parsed.get("narrative") or "")
            step_risks = parsed.get("risks") or []
            if isinstance(step_risks, list):
                risks.extend(str(r) for r in step_risks if r)

            try:
                conf = float(parsed.get("confidence", 0.5))
            except (TypeError, ValueError):
                conf = 0.5
            conf = max(0.0, min(1.0, conf))
            confidences.append(conf)

            trajectory.append(
                {
                    "step": i + 1,
                    "state": merged,
                    "delta": delta,
                    "narrative": narrative,
                    "fallback": False,
                }
            )
            current = merged

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        # 중복 리스크 제거 (등장 순서 유지)
        seen: set[str] = set()
        unique_risks: list[str] = []
        for r in risks:
            if r not in seen:
                seen.add(r)
                unique_risks.append(r)

        return SimulationResult(
            scenario=scenario.name,
            action=action,
            trajectory=trajectory,
            final_state=current,
            confidence=avg_conf,
            risks=unique_risks,
        )


__all__ = ["WorldSimulator", "SimulationResult"]
