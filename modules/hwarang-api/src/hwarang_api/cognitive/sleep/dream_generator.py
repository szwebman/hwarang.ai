"""Dream Generator — REM 단계의 생성적 연습.

각 seed memory 에 대해 LLM 으로 "what-if" 변형 시나리오를 만들고, 비평 LLM 이
이상적 응답과 교훈을 평가한다. 마지막에 메타-LLM 이 dream 들 사이의 반복 패턴
(lessons) 을 추출해 저-confidence semantic rule 로 재투입.

이는 Reinforcement Learning 의 "imagined rollout" 과 인지심리학의 dream
rehearsal 가설을 결합한 형태.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from hwarang_api.knowledge.llm import _chat

from .consolidator import MemoryConsolidator
from .replay_buffer import Memory

logger = logging.getLogger(__name__)


@dataclass
class Dream:
    """한 번의 변형 시나리오 + 비평 결과."""

    seed_memory_id: str
    variation: str
    plausibility: float
    ideal_response: str
    lessons_learned: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def _safe_json(text: str) -> dict | list | None:
    """consolidator 와 동일 안전 추출 (의존성 없이 로컬)."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fenced:
        text = fenced.group(1)
    for opener, closer in (("{", "}"), ("[", "]")):
        s = text.find(opener)
        e = text.rfind(closer)
        if s != -1 and e != -1 and e > s:
            try:
                return json.loads(text[s : e + 1])
            except Exception:
                continue
    return None


class DreamGenerator:
    """seed → variation → critic → lesson 4-stage 파이프라인."""

    VARIATION_SYSTEM = (
        "당신은 창의적 시나리오 생성기입니다. 주어진 상황의 그럴듯한 변형을 만드세요. "
        "응답은 JSON 만, 다른 설명 없이."
    )
    CRITIC_SYSTEM = (
        "당신은 화랑(Hwarang)의 비평가입니다. 제시된 시나리오에서 어떻게 답해야 "
        "이상적인지, 어떤 교훈을 얻을 수 있는지 평가하세요. JSON 만."
    )
    META_SYSTEM = (
        "당신은 메타 학습자입니다. 여러 dream 의 교훈에서 반복되는 패턴을 추출하세요. "
        "JSON 배열만."
    )

    def __init__(self, num_variations: int = 5):
        self.num_variations = max(1, int(num_variations))

    async def _make_variation(self, seed: Memory) -> tuple[str, float] | None:
        prompt = (
            f"다음 상황의 변형 시나리오를 생성하세요:\n\n{seed.content[:600]}\n\n"
            'JSON: {"variation": "변형된 상황 설명", "plausibility": 0.0~1.0}'
        )
        resp = await _chat(prompt, system=self.VARIATION_SYSTEM, max_tokens=350)
        data = _safe_json(resp)
        if not isinstance(data, dict):
            return None
        var = str(data.get("variation", "")).strip()
        if not var:
            return None
        try:
            plaus = float(data.get("plausibility", 0.5))
        except Exception:
            plaus = 0.5
        plaus = max(0.0, min(1.0, plaus))
        return (var, plaus)

    async def _critique(self, variation: str) -> tuple[str, list[str]]:
        prompt = (
            f"시나리오:\n{variation}\n\n"
            "이 상황에서 화랑이 어떻게 답해야 하는가? 어떤 교훈을 얻나?\n"
            'JSON: {"ideal_response": "이상적 답변 한 단락", '
            '"lessons_learned": ["교훈1","교훈2"]}'
        )
        resp = await _chat(prompt, system=self.CRITIC_SYSTEM, max_tokens=500)
        data = _safe_json(resp)
        if not isinstance(data, dict):
            return ("", [])
        ideal = str(data.get("ideal_response", "")).strip()
        lessons = data.get("lessons_learned") or []
        if not isinstance(lessons, list):
            lessons = [str(lessons)]
        lessons = [str(x).strip() for x in lessons if str(x).strip()][:5]
        return (ideal, lessons)

    async def dream(
        self,
        seed_memories: list[Memory],
        num_variations: int | None = None,
    ) -> list[Dream]:
        """seed 별 num_variations 만큼 dream 생성. 빈 입력은 빈 결과."""
        n = self.num_variations if num_variations is None else max(1, int(num_variations))
        out: list[Dream] = []
        if not seed_memories:
            return out
        for seed in seed_memories:
            for _ in range(n):
                var = await self._make_variation(seed)
                if not var:
                    continue
                variation_text, plausibility = var
                ideal, lessons = await self._critique(variation_text)
                out.append(
                    Dream(
                        seed_memory_id=seed.id,
                        variation=variation_text,
                        plausibility=plausibility,
                        ideal_response=ideal,
                        lessons_learned=lessons,
                    )
                )
        return out

    async def extract_lessons(self, dreams: list[Dream]) -> list[str]:
        """dream 들의 교훈에서 반복 패턴 메타-추출."""
        if not dreams:
            return []
        all_lessons: list[str] = []
        for d in dreams:
            all_lessons.extend(d.lessons_learned)
        if not all_lessons:
            return []
        listing = "\n".join(f"- {l}" for l in all_lessons[:50])
        prompt = (
            f"다음 교훈들에서 반복 패턴을 추출하세요:\n\n{listing}\n\n"
            'JSON 배열: ["패턴1", "패턴2", ...]'
        )
        resp = await _chat(prompt, system=self.META_SYSTEM, max_tokens=400)
        data = _safe_json(resp)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()][:10]
        if isinstance(data, dict):
            arr = data.get("patterns") or data.get("lessons") or []
            if isinstance(arr, list):
                return [str(x).strip() for x in arr if str(x).strip()][:10]
        return []

    async def feed_back_to_semantic_rules(
        self, lessons: list[str], topic_prefix: str = "dream"
    ) -> int:
        """추출된 패턴을 저-confidence semantic rule 로 저장.

        from_dream=True 마크. 실패해도 사이클 중단하지 않음.
        """
        if not lessons:
            return 0
        consolidator = MemoryConsolidator()
        saved = 0
        for i, lesson in enumerate(lessons):
            rule = {
                "topic": f"{topic_prefix}:{lesson[:40]}",
                "rule": lesson,
                "confidence": 0.3,  # dream 출신 → 낮은 신뢰도
                "exceptions": [],
                "sourceCount": 1,
            }
            status = await consolidator._upsert_rule(rule, from_dream=True)
            if status in ("created", "updated"):
                saved += 1
        return saved


__all__ = ["Dream", "DreamGenerator"]
