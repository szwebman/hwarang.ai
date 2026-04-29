"""다회차 토론 오케스트레이터.

여러 페르소나가 라운드 단위로 발언 → 마지막에 synthesizer 가
최종 통합 답변 + 변경 클레임 목록 생성.

비용 가드:
  rounds × len(personas) > 12 → ValueError 로 거부.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field

from hwarang_api.knowledge.llm import _chat

from .adversarial_personas import PERSONAS, respond_as

logger = logging.getLogger(__name__)

# 비용 가드 한계 (페르소나×라운드 LLM 호출 수)
MAX_TURNS_HARD_LIMIT = 12

# 기본 페르소나 (일반 토론용)
DEFAULT_PERSONAS: list[str] = ["비판자", "옹호자", "실용주의자"]


@dataclass
class Turn:
    """토론에서의 한 발언."""

    round: int
    persona: str
    content: str
    timestamp: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DebateResult:
    """토론 결과."""

    question: str
    initial_answer: str
    transcript: list[Turn]
    final_answer: str
    key_changes: list[str]
    consensus_reached: bool
    confidence_delta: float

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "initial_answer": self.initial_answer,
            "transcript": [t.to_dict() for t in self.transcript],
            "final_answer": self.final_answer,
            "key_changes": self.key_changes,
            "consensus_reached": self.consensus_reached,
            "confidence_delta": self.confidence_delta,
        }


SYNTHESIZER_SYSTEM = (
    "당신은 화랑 AI 의 통합자(synthesizer)다. 여러 페르소나의 토론을 읽고 "
    "초기 답변을 개선한 최종 답변을 한국어로 작성하라. "
    "비판이 타당하면 답변을 수정하고, 옹호가 타당하면 유지하라. "
    "JSON 만 출력하라."
)


SYNTHESIZER_PROMPT = """## 원 질문
{question}

## 초기 답변
{initial_answer}

## 토론 전체 기록
{transcript}

위 토론을 종합하여 다음 JSON 으로만 답하라:
{{
  "final_answer": "개선된 최종 답변 (한국어)",
  "key_changes": ["초기 답변에서 바뀐 핵심 클레임 1", "..."],
  "consensus_reached": true|false,
  "confidence_delta": -1.0~1.0 (초기 답변 대비 신뢰도 변화)
}}
"""


def _format_transcript(transcript: list[Turn]) -> str:
    if not transcript:
        return "(빈 토론)"
    lines = [
        f"[R{t.round}] {t.persona}: {t.content}"
        for t in transcript
        if t.content
    ]
    return "\n".join(lines)[:5000]


class DebateOrchestrator:
    """다회차 토론 진행자."""

    def __init__(self, max_turns: int = MAX_TURNS_HARD_LIMIT) -> None:
        self.max_turns = max_turns

    def _validate_personas(self, personas: list[str]) -> list[str]:
        """미존재 페르소나 제거 + 빈 리스트면 기본값."""
        valid = [p for p in (personas or []) if p in PERSONAS]
        if not valid:
            valid = list(DEFAULT_PERSONAS)
        return valid

    def _check_cost(self, personas: list[str], rounds: int) -> None:
        """비용 가드 — 한도 초과 시 ValueError."""
        total = max(0, rounds) * len(personas)
        if total > self.max_turns:
            raise ValueError(
                f"debate cost guard: rounds({rounds}) × personas({len(personas)}) "
                f"= {total} > {self.max_turns} (한도 초과)"
            )

    async def run_debate(
        self,
        question: str,
        initial_answer: str,
        personas: list[str] | None = None,
        rounds: int = 3,
    ) -> DebateResult:
        """다회차 토론 실행.

        라운드 구조:
          매 라운드마다 personas 순서대로 1턴씩 발언.
          이전 모든 턴을 history 로 받아 누적 컨텍스트 사용.
          (페르소나 턴은 의존적이므로 asyncio.gather 미사용 — sequential.)
        """
        personas = self._validate_personas(personas or [])
        rounds = max(1, int(rounds))
        self._check_cost(personas, rounds)

        transcript: list[Turn] = []

        for r in range(1, rounds + 1):
            for persona_name in personas:
                history = [t.to_dict() for t in transcript]
                content = await respond_as(
                    persona_name=persona_name,
                    question=question,
                    current_answer=initial_answer,
                    history=history,
                )
                if content:
                    transcript.append(
                        Turn(round=r, persona=persona_name, content=content)
                    )
                else:
                    logger.debug(
                        "respond_as 빈 응답: round=%s persona=%s", r, persona_name
                    )

        # ── Synthesizer 호출 ────────────────────────────────────────
        synth = await self._synthesize(question, initial_answer, transcript)

        return DebateResult(
            question=question,
            initial_answer=initial_answer,
            transcript=transcript,
            final_answer=synth["final_answer"],
            key_changes=synth["key_changes"],
            consensus_reached=synth["consensus_reached"],
            confidence_delta=synth["confidence_delta"],
        )

    async def _synthesize(
        self,
        question: str,
        initial_answer: str,
        transcript: list[Turn],
    ) -> dict:
        """LLM 통합 — 최종 답변 + 변경점 추출."""
        prompt = SYNTHESIZER_PROMPT.format(
            question=(question or "")[:1500],
            initial_answer=(initial_answer or "")[:2000],
            transcript=_format_transcript(transcript),
        )

        # 안전 기본값
        default = {
            "final_answer": initial_answer or "",
            "key_changes": [],
            "consensus_reached": False,
            "confidence_delta": 0.0,
        }

        try:
            raw = await _chat(prompt, system=SYNTHESIZER_SYSTEM, max_tokens=900)
            if not raw:
                return default
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                return default
            data = json.loads(m.group())
            final_answer = str(data.get("final_answer") or default["final_answer"])
            key_changes_raw = data.get("key_changes") or []
            if not isinstance(key_changes_raw, list):
                key_changes_raw = []
            key_changes = [str(x).strip() for x in key_changes_raw if str(x).strip()][:10]
            consensus = bool(data.get("consensus_reached", False))
            try:
                delta = float(data.get("confidence_delta", 0.0))
            except (TypeError, ValueError):
                delta = 0.0
            delta = max(-1.0, min(1.0, delta))
            return {
                "final_answer": final_answer,
                "key_changes": key_changes,
                "consensus_reached": consensus,
                "confidence_delta": delta,
            }
        except Exception as e:  # noqa: BLE001
            logger.debug("synthesizer 실패(default 반환): %s", e)
            return default


__all__ = [
    "DebateOrchestrator",
    "DebateResult",
    "Turn",
    "DEFAULT_PERSONAS",
    "MAX_TURNS_HARD_LIMIT",
]
