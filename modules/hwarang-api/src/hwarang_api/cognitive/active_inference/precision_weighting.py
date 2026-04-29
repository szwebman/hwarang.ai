"""Precision Weighting — belief 의 신뢰도 (= Free Energy 의 inverse variance).

Active Inference 에서 precision π = 1 / σ² 는 belief 가 prediction error
계산에 얼마나 영향을 주는지를 결정한다. LLM 시스템에서는 다음 두 요인으로
근사한다:

* **evidence_count**: 같은 belief 를 뒷받침하는 관찰/출처 개수
* **recency_days**: 마지막 갱신 후 경과일

규칙::

    base = 0.5
    +0.1 per evidence  (cap 0.95)
    decay: × 0.95 ^ (recency_days / 30)

여러 belief 를 LLM 으로 합성할 때는 precision 이 높은 쪽이 답변에 더
강하게 반영된다.
"""

from __future__ import annotations

import logging
from typing import Iterable

from hwarang_api.knowledge.llm import _chat

logger = logging.getLogger(__name__)


class PrecisionWeighter:
    """belief 의 precision 산출 + precision-weighted 합성."""

    BASE = 0.5
    PER_EVIDENCE = 0.1
    CAP = 0.95
    DECAY_PER_30D = 0.95

    # ----------------------------------------------------------- single weight
    def weight_belief(
        self, belief: str, evidence_count: int, recency_days: int
    ) -> float:
        """belief 하나의 precision 점수.

        Parameters
        ----------
        belief : str
            belief 문장 (현재 미사용. 추후 LLM 신뢰도 보정 hook 용).
        evidence_count : int
            belief 를 뒷받침하는 관찰 개수 (>=0).
        recency_days : int
            마지막 갱신 후 경과일 (>=0).
        """
        ev = max(0, int(evidence_count))
        rd = max(0, int(recency_days))

        weight = self.BASE + self.PER_EVIDENCE * ev
        if weight > self.CAP:
            weight = self.CAP

        # 30 일 단위 감쇠
        if rd > 0:
            periods = rd / 30.0
            weight *= self.DECAY_PER_30D ** periods

        # 너무 0 에 붙으면 의미가 없으므로 floor
        weight = max(0.01, min(self.CAP, weight))
        # belief 인자는 future-hook 용 (LLM 자체 평가). 현재는 placeholder.
        _ = belief
        return weight

    # -------------------------------------------------------------- aggregate
    async def aggregate_weighted_beliefs(
        self, beliefs_with_weights: Iterable[tuple[str, float]]
    ) -> str:
        """여러 belief 를 precision 가중으로 합성 (LLM 합성)."""
        items = [
            (str(b).strip(), max(0.0, min(1.0, float(w))))
            for b, w in beliefs_with_weights
            if str(b).strip()
        ]
        if not items:
            return ""

        # 단순 1 개 경우 그대로 반환
        if len(items) == 1:
            return items[0][0]

        # LLM 입력: belief 와 weight 함께 전달
        rendered_lines = [
            f"- (precision={w:.2f}) {b}" for b, w in items
        ]
        rendered = "\n".join(rendered_lines)
        system = (
            "너는 다중 belief 통합기다. 각 belief 에는 precision(신뢰도) 이 "
            "붙어 있고, precision 이 높을수록 최종 결론에 더 강하게 반영해야 "
            "한다. 모순되는 belief 는 precision 이 높은 쪽을 우선한다. "
            "1~3 문장의 한국어 결론만 반환."
        )
        prompt = (
            "다음 belief 들을 precision 가중으로 통합해 한 문단의 결론을 "
            "써라. 결론만 출력:\n" + rendered
        )
        try:
            resp = await _chat(prompt, system=system, max_tokens=240)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("aggregate_weighted_beliefs LLM 실패: %s", e)
            resp = ""

        if not resp:
            # fallback: precision 최고 belief 한 줄 + 보조 하나
            ranked = sorted(items, key=lambda x: x[1], reverse=True)
            top = ranked[0][0]
            if len(ranked) >= 2:
                return f"{top} (보조: {ranked[1][0]})"
            return top
        return resp.strip()


__all__ = ["PrecisionWeighter"]
