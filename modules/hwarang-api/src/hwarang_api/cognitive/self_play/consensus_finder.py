"""토론 transcript 에서 합의/이견 추출.

LLM 으로 동의점·이견점·미해결 질문을 JSON 으로 받아
0.0~1.0 합의 점수로 환산.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field

from hwarang_api.knowledge.llm import _chat

from .debate_orchestrator import Turn

logger = logging.getLogger(__name__)


@dataclass
class ConsensusAnalysis:
    """합의 분석 결과."""

    agreed_points: list[str] = field(default_factory=list)
    disagreed_points: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    consensus_score_0_to_1: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


CONSENSUS_SYSTEM = (
    "당신은 토론 분석가다. 한국어 토론에서 합의점·이견점·미해결 질문을 추출하라. "
    "JSON 만 출력하라."
)


CONSENSUS_PROMPT = """다음 토론에서 모든 페르소나가 동의한 점, 의견 갈린 점, 미해결 질문을 추출하라.

## 토론 기록
{transcript}

JSON 으로만 답하라:
{{
  "agreed_points": ["동의된 클레임 1", "..."],
  "disagreed_points": ["이견 있는 클레임 1", "..."],
  "unresolved_questions": ["미해결 질문 1", "..."]
}}
"""


def _format_transcript(transcript: list[Turn]) -> str:
    if not transcript:
        return "(빈 토론)"
    return "\n".join(
        f"[R{t.round}] {t.persona}: {t.content}"
        for t in transcript
        if t.content
    )[:5000]


def _safe_str_list(raw: object, limit: int = 10) -> list[str]:
    """JSON 필드 → 문자열 리스트 (안전 변환)."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for x in raw:
        s = str(x).strip()
        if s:
            out.append(s)
        if len(out) >= limit:
            break
    return out


class ConsensusFinder:
    """토론 합의 분석기."""

    async def analyze_consensus(
        self,
        transcript: list[Turn],
    ) -> ConsensusAnalysis:
        """합의 분석.

        Returns:
            ConsensusAnalysis. LLM 실패 시 빈 리스트 + 0.0 점수.
        """
        if not transcript:
            return ConsensusAnalysis()

        prompt = CONSENSUS_PROMPT.format(transcript=_format_transcript(transcript))

        try:
            raw = await _chat(prompt, system=CONSENSUS_SYSTEM, max_tokens=600)
            if not raw:
                return ConsensusAnalysis()
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                return ConsensusAnalysis()
            data = json.loads(m.group())
            agreed = _safe_str_list(data.get("agreed_points"))
            disagreed = _safe_str_list(data.get("disagreed_points"))
            unresolved = _safe_str_list(data.get("unresolved_questions"))
            score = self._compute_score(agreed, disagreed, unresolved)
            return ConsensusAnalysis(
                agreed_points=agreed,
                disagreed_points=disagreed,
                unresolved_questions=unresolved,
                consensus_score_0_to_1=score,
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("analyze_consensus 실패: %s", e)
            return ConsensusAnalysis()

    @staticmethod
    def _compute_score(
        agreed: list[str],
        disagreed: list[str],
        unresolved: list[str],
    ) -> float:
        """합의 점수 계산.

        agreed / (agreed + disagreed + 0.5×unresolved). 분모 0 이면 0.0.
        """
        a = len(agreed)
        d = len(disagreed)
        u = len(unresolved)
        denom = a + d + 0.5 * u
        if denom <= 0:
            return 0.0
        return round(max(0.0, min(1.0, a / denom)), 3)

    @staticmethod
    def is_consensus(analysis: ConsensusAnalysis, threshold: float = 0.7) -> bool:
        """점수가 threshold 이상이면 합의 도달로 판단."""
        return analysis.consensus_score_0_to_1 >= threshold


__all__ = ["ConsensusFinder", "ConsensusAnalysis"]
