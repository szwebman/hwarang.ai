"""HSEE Phase 1 — 복리 루프 오케스트레이터.

채팅 응답이 끝난 직후 호출돼서 4 개의 자기개선 루프를 동시에 발사한다.

각 루프는 비동기로 동시에 돌고, 한 루프가 실패해도 나머지 3 개는 그대로 진행된다.
모든 호출은 채팅 응답 latency 에 영향을 주면 안 되므로, 호출자(라우터)는
``asyncio.create_task(on_chat_response(ctx))`` 식으로 fire-and-forget 으로 사용한다.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from hwarang_api.learning.auto_trigger import maybe_trigger_training
from hwarang_api.learning.fact_extractor import extract_and_ingest_facts
from hwarang_api.learning.rlhf_collector import record_feedback
from hwarang_api.learning.routing_stats import record_routing
from hwarang_api.learning.satisfaction_scorer import combine_scores

logger = logging.getLogger(__name__)


@dataclass
class ChatContext:
    """채팅 응답 1 회의 모든 메타데이터.

    Next.js (`api/chat/route.ts`) 가 응답 직후 이 페이로드를 만들어 보낸다.
    """

    user_id: str
    user_message: str
    response: str
    domain: str = "general"
    model_name: str = "unknown"

    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    lora_name: Optional[str] = None
    latency_ms: int = 0
    quality_score: Optional[float] = None  # 응답 weight (0~1) — 라우팅 통계 보조
    is_kyc_verified: bool = False

    # 후속 신호 (선택)
    followup_msg: Optional[str] = None
    rating: Optional[int] = None  # -1, 0, 1
    edit_distance: Optional[float] = None

    # 디버그/실험용
    extra: dict[str, Any] = field(default_factory=dict)


def _result(value: Any) -> dict:
    """``asyncio.gather(return_exceptions=True)`` 결과 정규화."""
    if isinstance(value, BaseException):
        return {"ok": False, "error": f"{type(value).__name__}: {value}"}
    if isinstance(value, dict):
        return {"ok": True, **value}
    return {"ok": True, "value": value}


async def on_chat_response(ctx: ChatContext) -> dict:
    """채팅 응답 직후의 메인 진입점.

    4 개의 루프를 ``asyncio.gather`` 로 동시 트리거하고 결과를 합쳐 반환한다.
    """
    results = await asyncio.gather(
        loop_a_rlhf(ctx),
        loop_b_facts(ctx),
        loop_c_routing(ctx),
        loop_d_training(ctx),
        return_exceptions=True,
    )
    return {
        "rlhf": _result(results[0]),
        "facts": _result(results[1]),
        "routing": _result(results[2]),
        "training": _result(results[3]),
    }


# ────────────────────────────────────────────────────────────
# 루프 A — RLHF 피드백 풀
# ────────────────────────────────────────────────────────────
async def loop_a_rlhf(ctx: ChatContext) -> dict:
    """``RLHFFeedback`` 행 생성/업데이트 (암묵 + 명시)."""
    try:
        return await record_feedback(
            ctx,
            rating=ctx.rating,
            followup_msg=ctx.followup_msg,
            edit_distance=ctx.edit_distance,
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"loop_a_rlhf 실패: {e}")
        return {"recorded": False, "error": str(e)}


# ────────────────────────────────────────────────────────────
# 루프 B — HLKM 사실 추출
# ────────────────────────────────────────────────────────────
async def loop_b_facts(ctx: ChatContext) -> dict:
    """응답에서 객관 사실 추출 → ``ingest_fact``.

    KYC 비인증자 대화여도 자동 추출은 진행 (사용자 식별 없이 ``bypass_gate``).
    """
    try:
        return await extract_and_ingest_facts(ctx.response, domain=ctx.domain)
    except Exception as e:  # pragma: no cover
        logger.warning(f"loop_b_facts 실패: {e}")
        return {"extracted": 0, "ingested": 0, "error": str(e)}


# ────────────────────────────────────────────────────────────
# 루프 C — 라우팅 통계 (시간 윈도우)
# ────────────────────────────────────────────────────────────
async def loop_c_routing(ctx: ChatContext) -> dict:
    """도메인×모델 단위 시간 윈도우에 latency + 만족도 누적."""
    satisfaction = combine_scores(
        explicit=ctx.rating,
        followup_msg=ctx.followup_msg,
        edit_distance=ctx.edit_distance,
    )
    # 응답 weight 가 있으면 보조 신호로 살짝 가중
    if ctx.quality_score is not None and ctx.rating is None and not ctx.followup_msg:
        # 0~1 의 weight 를 -0.4 ~ +0.4 로 매핑
        satisfaction = max(-1.0, min(1.0, (ctx.quality_score - 0.5) * 0.8))

    try:
        return await record_routing(
            domain=ctx.domain,
            model_name=ctx.model_name,
            latency_ms=ctx.latency_ms,
            satisfaction=satisfaction,
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"loop_c_routing 실패: {e}")
        return {"recorded": False, "error": str(e)}


# ────────────────────────────────────────────────────────────
# 루프 D — HFL/LoRA 학습 자동 트리거
# ────────────────────────────────────────────────────────────
async def loop_d_training(ctx: ChatContext) -> dict:
    """충분히 모이면 학습 라운드 시작 (그렇지 않으면 no-op)."""
    try:
        return await maybe_trigger_training(ctx.domain)
    except Exception as e:  # pragma: no cover
        logger.warning(f"loop_d_training 실패: {e}")
        return {"triggered": False, "error": str(e)}


__all__ = [
    "ChatContext",
    "on_chat_response",
    "loop_a_rlhf",
    "loop_b_facts",
    "loop_c_routing",
    "loop_d_training",
]
