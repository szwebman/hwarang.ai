"""Generative Model — LLM 이 다음 관찰을 예측한다.

Active Inference 에서 generative model 은 ``p(observation | hidden state)``
를 정의한다. 본 모듈은 LLM 자체를 generative model 로 취급하고, 다음
세 가지 예측을 제공한다:

1. ``predict_next_observation`` — 일반 컨텍스트 다음 관찰
2. ``predict_user_response`` — draft 답변에 대한 사용자 반응
3. ``predict_external_state`` — 행동 후 외부 세계 상태

모든 예측은 in-memory dict 에 ``prediction_id`` 로 캐시되어 추후
:class:`PredictionErrorTracker` 가 실제 관찰과 비교할 수 있게 한다.

TODO: 50 개 캐시는 in-memory 임. 영속화는 Prisma ``Prediction`` 테이블로
이전.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from hwarang_api.knowledge.llm import _chat

logger = logging.getLogger(__name__)

_MAX_CACHE = 50


@dataclass
class Prediction:
    """generative model 의 예측 결과."""

    predicted_text: str
    predicted_intent: str
    predicted_sentiment: str
    confidence: float
    prediction_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    kind: str = "generic"  # generic | user_response | external_state
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_json(text: str) -> dict[str, Any] | None:
    """LLM 응답에서 JSON 객체만 추려 파싱."""
    if not text:
        return None
    # 코드 펜스 제거
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except Exception:
        return None


def _to_float(v: Any, default: float = 0.5) -> float:
    try:
        f = float(v)
        return max(0.0, min(1.0, f))
    except Exception:
        return default


class GenerativeModel:
    """LLM-기반 generative model. Process-local cache 보유."""

    def __init__(self, max_cache: int = _MAX_CACHE) -> None:
        self._cache: OrderedDict[str, Prediction] = OrderedDict()
        self._max_cache = max_cache

    # ---------------------------------------------------------------- cache
    def _store(self, pred: Prediction) -> None:
        self._cache[pred.prediction_id] = pred
        while len(self._cache) > self._max_cache:
            self._cache.popitem(last=False)

    def get(self, prediction_id: str) -> Prediction | None:
        return self._cache.get(prediction_id)

    def all_predictions(self) -> list[Prediction]:
        return list(self._cache.values())

    # ------------------------------------------------------------- core LLM
    async def _llm_predict(
        self, prompt: str, system: str, kind: str, extra: dict[str, Any] | None = None
    ) -> Prediction:
        # 1차 호출
        raw = await _chat(prompt, system=system, max_tokens=320)
        data = _safe_json(raw)
        if data is None:
            # 1회 재시도 (조금 더 강제적인 system)
            retry_system = (
                system
                + " 반드시 JSON 객체만 응답해라. 추가 설명/코드 펜스 금지."
            )
            raw = await _chat(prompt, system=retry_system, max_tokens=320)
            data = _safe_json(raw)
        if data is None:
            # safe fallback
            pred = Prediction(
                predicted_text="(예측 실패: LLM 응답을 파싱할 수 없음)",
                predicted_intent="unknown",
                predicted_sentiment="neutral",
                confidence=0.0,
                kind=kind,
                extra=extra or {},
            )
            self._store(pred)
            return pred

        pred = Prediction(
            predicted_text=str(data.get("predicted_text", "")).strip()
            or "(no text)",
            predicted_intent=str(data.get("predicted_intent", "unknown")).strip()
            or "unknown",
            predicted_sentiment=str(
                data.get("predicted_sentiment", "neutral")
            ).strip()
            or "neutral",
            confidence=_to_float(data.get("confidence_0_to_1", 0.5)),
            kind=kind,
            extra=extra or {},
        )
        self._store(pred)
        return pred

    # ----------------------------------------------------------- predictions
    async def predict_next_observation(self, context: dict[str, Any]) -> Prediction:
        """현재 컨텍스트 다음에 관찰될 가장 가능성 높은 사건을 예측."""
        system = (
            "너는 Hwarang 의 generative model 이다. 주어진 상황에서 다음에 "
            "일어날 가장 가능성 높은 관찰/사용자 반응을 예측한다."
        )
        ctx_str = json.dumps(context, ensure_ascii=False)[:1500]
        prompt = (
            f"현재 상황: {ctx_str}\n"
            "다음에 일어날 가장 가능성 높은 관찰/사용자 반응을 예측해라. "
            "JSON 만 응답: "
            "{\"predicted_text\": str, \"predicted_intent\": str, "
            "\"predicted_sentiment\": str, \"confidence_0_to_1\": float}"
        )
        return await self._llm_predict(
            prompt, system, kind="generic", extra={"context": context}
        )

    async def predict_user_response(
        self, question: str, draft_answer: str
    ) -> Prediction:
        """draft 답변에 대해 사용자가 어떻게 반응할지 예측."""
        system = (
            "너는 사용자 반응 예측기다. draft 답변을 받은 사용자의 다음 "
            "반응(만족/혼란/정정/추가질문 등)을 예측한다."
        )
        prompt = (
            f"질문: {question}\n"
            f"draft 답변: {draft_answer}\n"
            "사용자 반응 예측. JSON 만: "
            "{\"predicted_text\": <예상 반응문>, "
            "\"predicted_intent\": <satisfied|confused|correcting|"
            "follow_up|negative>, "
            "\"predicted_sentiment\": <positive|neutral|negative>, "
            "\"confidence_0_to_1\": float}"
        )
        return await self._llm_predict(
            prompt,
            system,
            kind="user_response",
            extra={"question": question, "draft": draft_answer},
        )

    async def predict_external_state(
        self, domain: str, action: str
    ) -> Prediction:
        """행동을 취한 후 외부 세계가 어떻게 변할지 예측."""
        system = (
            "너는 외부 세계 상태 예측기다. 특정 도메인에서 행동을 했을 때 "
            "환경이 어떻게 변할지 예측한다."
        )
        prompt = (
            f"도메인: {domain}\n"
            f"행동: {action}\n"
            "행동 후 외부 세계의 상태 예측. JSON 만: "
            "{\"predicted_text\": <예상 상태 설명>, "
            "\"predicted_intent\": <행동의 의도>, "
            "\"predicted_sentiment\": <positive|neutral|negative>, "
            "\"confidence_0_to_1\": float}"
        )
        return await self._llm_predict(
            prompt,
            system,
            kind="external_state",
            extra={"domain": domain, "action": action},
        )


__all__ = ["GenerativeModel", "Prediction"]
