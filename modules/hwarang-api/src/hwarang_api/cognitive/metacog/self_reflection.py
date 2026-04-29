"""Self-Reflection — 답변 자기 비판 (Phase 9.ζ).

LLM 에게 자신의 (질문, 답변, 출처) 를 비판적으로 분석시켜
1) 논리 공백  2) 미입증 주장  3) 누락 관점  4) 전반 품질 (0~1)
을 추출한다.

품질 < 0.6 또는 미입증 주장 > 2 면 ``should_revise`` True →
호출측은 답변 재생성 / 출처 추가검색을 수행하면 된다.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from hwarang_api.knowledge.llm import _chat

logger = logging.getLogger(__name__)


_REFLECTION_SYSTEM = (
    "너는 엄격한 자기 비판자다. 자신의 질문/답변을 가차없이 분석하라. "
    "응답은 반드시 단일 JSON 객체. 코드펜스/주석/추가 설명 금지."
)

_REFLECTION_PROMPT_TMPL = (
    "다음 질문과 답변을 비판적으로 분석해라.\n"
    "1) 추론 단계 누락\n"
    "2) 가정 검증 부족\n"
    "3) 출처 신뢰성\n"
    "4) 반례 가능성\n\n"
    "JSON 응답 스키마:\n"
    "{{\n"
    '  "logical_gaps": [string],\n'
    '  "unsupported_claims": [string],\n'
    '  "missing_perspectives": [string],\n'
    '  "suggestions": [string],\n'
    '  "overall_quality_0_to_1": number\n'
    "}}\n\n"
    "질문:\n{question}\n\n"
    "답변:\n{answer}\n\n"
    "출처({n_sources}개):\n{sources}\n"
)


@dataclass
class ReflectionResult:
    """비판 분석 결과."""

    quality: float = 0.5
    logical_gaps: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    missing_perspectives: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "quality": self.quality,
            "logical_gaps": list(self.logical_gaps),
            "unsupported_claims": list(self.unsupported_claims),
            "missing_perspectives": list(self.missing_perspectives),
            "suggestions": list(self.suggestions),
        }


def _safe_json_extract(raw: str) -> Optional[dict]:
    """LLM 응답에서 첫 JSON 객체를 견고하게 추출.

    코드펜스/잡음 토큰을 잘라낸다. 실패 시 None.
    """
    if not raw:
        return None
    text = raw.strip()
    # ```json ... ``` 또는 ``` ... ``` 제거
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except Exception:
        return None


def _coerce_str_list(v) -> list[str]:
    if not v:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    return []


def _coerce_quality(v) -> float:
    try:
        q = float(v)
    except (TypeError, ValueError):
        return 0.5
    if q != q:  # NaN
        return 0.5
    return max(0.0, min(1.0, q))


class SelfReflection:
    """답변 자기비판 — LLM 기반 4축 분석."""

    def __init__(self, max_tokens: int = 700) -> None:
        self.max_tokens = max_tokens

    async def reflect_on_answer(
        self,
        question: str,
        answer: str,
        sources: list[str] | None = None,
    ) -> ReflectionResult:
        """주어진 (질문, 답변, 출처) 를 LLM 으로 비판 분석.

        파싱 실패 시 안전 기본값 반환 (절대 raise 하지 않음).
        """
        srcs = sources or []
        sources_str = "\n".join(f"- {s}" for s in srcs) if srcs else "(없음)"

        prompt = _REFLECTION_PROMPT_TMPL.format(
            question=question.strip()[:4000],
            answer=answer.strip()[:6000],
            n_sources=len(srcs),
            sources=sources_str[:2000],
        )

        try:
            raw = await _chat(prompt, system=_REFLECTION_SYSTEM, max_tokens=self.max_tokens)
        except Exception as exc:  # noqa: BLE001
            logger.warning("self_reflection LLM 호출 실패: %s", exc)
            return ReflectionResult(quality=0.5, logical_gaps=["LLM 호출 실패"])

        data = _safe_json_extract(raw)
        if data is None:
            logger.warning("self_reflection JSON 파싱 실패: raw=%r", (raw or "")[:200])
            return ReflectionResult(quality=0.5, logical_gaps=["파싱 실패"])

        return ReflectionResult(
            quality=_coerce_quality(data.get("overall_quality_0_to_1", 0.5)),
            logical_gaps=_coerce_str_list(data.get("logical_gaps")),
            unsupported_claims=_coerce_str_list(data.get("unsupported_claims")),
            missing_perspectives=_coerce_str_list(data.get("missing_perspectives")),
            suggestions=_coerce_str_list(data.get("suggestions")),
        )

    @staticmethod
    def should_revise(result: ReflectionResult) -> bool:
        """재작성/추가검색 필요 여부.

        quality < 0.6  OR  미입증 주장 > 2개 → True.
        """
        if result is None:
            return False
        if result.quality < 0.6:
            return True
        if len(result.unsupported_claims) > 2:
            return True
        return False


__all__ = ["SelfReflection", "ReflectionResult"]
