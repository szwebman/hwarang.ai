"""토론에서 자기모순 + 근거 없는 클레임 탐지.

ErrorDiscoverer:
  - find_self_contradictions: 페르소나 간 모순 발언
  - find_unsupported_claims: 비판은 받았는데 옹호 못한 초기 답변 클레임
  - propose_corrections: LLM 수정 제안
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass

from hwarang_api.knowledge.llm import _chat

from .debate_orchestrator import Turn

logger = logging.getLogger(__name__)


@dataclass
class Contradiction:
    """두 클레임 간의 모순."""

    claim_a: str
    claim_b: str
    persona_a: str
    persona_b: str
    severity: str  # "critical" | "major" | "minor"

    def to_dict(self) -> dict:
        return asdict(self)


CONTRADICTION_SYSTEM = (
    "당신은 토론 모순 탐지자다. 페르소나 간 직접 충돌하는 클레임만 추출하라. "
    "단순 강조 차이는 무시. JSON 만 출력하라."
)


CONTRADICTION_PROMPT = """다음 토론에서 페르소나 발언들 사이에 직접 모순되는 클레임 쌍을 찾아라.

## 토론
{transcript}

JSON 배열로만 답하라 (모순 없으면 []):
[
  {{
    "claim_a": "한쪽 주장",
    "claim_b": "반대쪽 주장",
    "persona_a": "발언자 A",
    "persona_b": "발언자 B",
    "severity": "critical|major|minor"
  }}
]
"""


UNSUPPORTED_SYSTEM = (
    "당신은 비판 분석가다. 초기 답변의 클레임 중 비판자가 공격했고 "
    "옹호자/다른 페르소나가 방어하지 못한 항목만 추출하라. JSON 배열만 출력하라."
)


UNSUPPORTED_PROMPT = """## 초기 답변
{initial_answer}

## 토론
{transcript}

초기 답변의 클레임 중 비판은 받았으나 옹호되지 못한 것만 JSON 문자열 배열로 답하라:
["근거 없는 클레임 1", "..."]
"""


CORRECTION_SYSTEM = (
    "당신은 답변 교정자다. 주어진 모순과 근거 없는 클레임 목록을 보고 "
    "최종 답변에 적용할 구체적 수정 제안을 한국어로 작성하라. JSON 배열만 출력."
)


CORRECTION_PROMPT = """## 발견된 모순
{contradictions}

## 근거 없는 클레임
{unsupported}

각 항목에 대한 수정 제안을 JSON 문자열 배열로 답하라:
["수정 제안 1", "..."]
"""


def _format_transcript(transcript: list[Turn]) -> str:
    if not transcript:
        return "(빈 토론)"
    return "\n".join(
        f"[R{t.round}] {t.persona}: {t.content}"
        for t in transcript
        if t.content
    )[:5000]


def _extract_json_array(raw: str) -> list:
    """LLM 응답에서 첫 JSON 배열 추출. 실패 시 []."""
    if not raw:
        return []
    try:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group())
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


_VALID_SEVERITY = {"critical", "major", "minor"}


class ErrorDiscoverer:
    """토론 기반 오류 탐지기."""

    async def find_self_contradictions(
        self,
        transcript: list[Turn],
    ) -> list[Contradiction]:
        """페르소나 간 모순 클레임 추출."""
        if not transcript:
            return []
        prompt = CONTRADICTION_PROMPT.format(
            transcript=_format_transcript(transcript)
        )
        try:
            raw = await _chat(prompt, system=CONTRADICTION_SYSTEM, max_tokens=700)
            arr = _extract_json_array(raw)
            out: list[Contradiction] = []
            for item in arr[:10]:
                if not isinstance(item, dict):
                    continue
                sev = str(item.get("severity") or "minor").lower()
                if sev not in _VALID_SEVERITY:
                    sev = "minor"
                claim_a = str(item.get("claim_a") or "").strip()
                claim_b = str(item.get("claim_b") or "").strip()
                if not claim_a or not claim_b:
                    continue
                out.append(
                    Contradiction(
                        claim_a=claim_a,
                        claim_b=claim_b,
                        persona_a=str(item.get("persona_a") or "?").strip(),
                        persona_b=str(item.get("persona_b") or "?").strip(),
                        severity=sev,
                    )
                )
            return out
        except Exception as e:  # noqa: BLE001
            logger.debug("find_self_contradictions 실패: %s", e)
            return []

    async def find_unsupported_claims(
        self,
        initial_answer: str,
        transcript: list[Turn],
    ) -> list[str]:
        """초기 답변에서 비판받았으나 옹호 못 받은 클레임."""
        if not initial_answer or not transcript:
            return []
        prompt = UNSUPPORTED_PROMPT.format(
            initial_answer=(initial_answer or "")[:2000],
            transcript=_format_transcript(transcript),
        )
        try:
            raw = await _chat(prompt, system=UNSUPPORTED_SYSTEM, max_tokens=500)
            arr = _extract_json_array(raw)
            return [str(x).strip() for x in arr if str(x).strip()][:10]
        except Exception as e:  # noqa: BLE001
            logger.debug("find_unsupported_claims 실패: %s", e)
            return []

    async def propose_corrections(
        self,
        contradictions: list[Contradiction],
        unsupported: list[str],
    ) -> list[str]:
        """모순 + 근거 없는 클레임에 대한 수정안 LLM 제안."""
        if not contradictions and not unsupported:
            return []
        contras = [c.to_dict() for c in contradictions]
        prompt = CORRECTION_PROMPT.format(
            contradictions=json.dumps(contras, ensure_ascii=False)[:2000],
            unsupported=json.dumps(unsupported, ensure_ascii=False)[:2000],
        )
        try:
            raw = await _chat(prompt, system=CORRECTION_SYSTEM, max_tokens=600)
            arr = _extract_json_array(raw)
            return [str(x).strip() for x in arr if str(x).strip()][:10]
        except Exception as e:  # noqa: BLE001
            logger.debug("propose_corrections 실패: %s", e)
            return []


__all__ = ["ErrorDiscoverer", "Contradiction"]
