"""Knowledge Gap Detector — 자기 지식 공백 식별 (Phase 9.ζ).

LLM 에게 "이 답변에서 모르거나 불확실한 부분" 을 자기진단시켜
외부 검색/크롤러 디스패치 여부를 결정하는 힌트를 제공한다.

이 모듈은 **검색을 직접 수행하지 않는다** — 호출측 (예: pipeline /
crawl_dispatcher) 이 ``should_search_external`` 로 분기한 뒤
원하는 검색 백엔드로 위임한다.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from hwarang_api.knowledge.llm import _chat

logger = logging.getLogger(__name__)

_VALID_SEVERITIES = {"low", "medium", "high"}

_GAP_SYSTEM = (
    "너는 자기진단 보조자다. 답변에서 불확실/추정/모름 인 부분을 식별하라. "
    "응답은 단일 JSON 배열만, 코드펜스 없이."
)

_GAP_PROMPT_TMPL = (
    "이 답변에서 모르거나 불확실한 부분을 식별해라. "
    "각 항목의 severity 는 'low' | 'medium' | 'high'.\n\n"
    "JSON 배열 스키마:\n"
    '[{{"topic": string, "why_uncertain": string, "suggested_lookup": string, '
    '"severity": "low"|"medium"|"high"}}]\n\n'
    "질문:\n{question}\n\n"
    "답변:\n{answer}"
)


@dataclass
class Gap:
    """단일 지식 공백 항목."""

    topic: str
    why_uncertain: str
    suggested_lookup: str
    severity: str = "medium"

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "why_uncertain": self.why_uncertain,
            "suggested_lookup": self.suggested_lookup,
            "severity": self.severity,
        }


def _extract_json_array(raw: str) -> list | None:
    if not raw:
        return None
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        arr = json.loads(text[start : end + 1])
        return arr if isinstance(arr, list) else None
    except Exception:
        return None


def _coerce_severity(s) -> str:
    if isinstance(s, str) and s.strip().lower() in _VALID_SEVERITIES:
        return s.strip().lower()
    return "medium"


class KnowledgeGapDetector:
    """LLM 자기진단 기반 지식 공백 탐지기."""

    def __init__(self, max_tokens: int = 600) -> None:
        self.max_tokens = max_tokens

    async def detect_gaps(self, question: str, answer: str) -> list[Gap]:
        """답변에서 불확실 항목 추출. 실패 시 빈 리스트 (raise 하지 않음)."""
        prompt = _GAP_PROMPT_TMPL.format(
            question=(question or "").strip()[:3000],
            answer=(answer or "").strip()[:6000],
        )
        try:
            raw = await _chat(prompt, system=_GAP_SYSTEM, max_tokens=self.max_tokens)
        except Exception as exc:  # noqa: BLE001
            logger.warning("detect_gaps LLM 실패: %s", exc)
            return []

        arr = _extract_json_array(raw or "")
        if not arr:
            logger.debug("detect_gaps: JSON 배열 파싱 실패 raw=%r", (raw or "")[:200])
            return []

        gaps: list[Gap] = []
        for item in arr:
            if not isinstance(item, dict):
                continue
            topic = str(item.get("topic", "")).strip()
            if not topic:
                continue
            gaps.append(
                Gap(
                    topic=topic[:300],
                    why_uncertain=str(item.get("why_uncertain", "")).strip()[:500],
                    suggested_lookup=str(item.get("suggested_lookup", "")).strip()[:500],
                    severity=_coerce_severity(item.get("severity")),
                )
            )
        return gaps

    @staticmethod
    def should_search_external(gaps: list[Gap]) -> bool:
        """high severity 가 하나라도 있으면 외부 탐색 필요."""
        for g in gaps or []:
            if getattr(g, "severity", "medium") == "high":
                return True
        return False


__all__ = ["KnowledgeGapDetector", "Gap"]
