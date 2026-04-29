"""Cognitive Loop guardrails — 액션 실행 전 안전 체크 + 디스패치 (Phase 6).

마스터 LLM 이 생성한 결정을 받아:
  1. 액션 이름이 ``AVAILABLE_ACTIONS`` 카탈로그에 있는지 검증
  2. ``REQUIRES_APPROVAL`` 에 해당하면 ``GrowthDecision`` 으로 큐잉 (사람 검토 대기)
  3. 자유 액션이면 매핑된 핸들러를 즉시 실행
  4. 실패 / 미지원 액션은 ``status="blocked"`` 로 반환

반환 형식 (각 결정당)::

    {
      "action": "trigger_curious_crawl",
      "status": "executed" | "pending_approval" | "blocked",
      "result": {...} | None,
      "reason": "...",
    }
"""

from __future__ import annotations

import json
import logging
from typing import Any

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 자율 실행 핸들러 — 기존 API/잡 함수 재사용 (지연 import 로 의존성 격리)
# ---------------------------------------------------------------------------
async def _h_trigger_curious_crawl(params: dict) -> dict:
    from hwarang_api.learning.curious_crawler import proactive_crawl_cycle

    gap_limit = int(params.get("gap_limit", 10))
    return await proactive_crawl_cycle(gap_limit=gap_limit)


async def _h_trigger_arxiv_summarize(params: dict) -> dict:
    from hwarang_api.research.auto_summarizer import summarize_pending_papers

    batch = int(params.get("batch_size", 15))
    return await summarize_pending_papers(batch_size=batch)


async def _h_rebuild_eval_set(params: dict) -> dict:
    from hwarang_api.grid.code_round.eval_set_builder import rebuild_eval_set

    domain = params.get("domain", "code")
    path = await rebuild_eval_set(domain)
    return {"domain": domain, "path": str(path) if path else None}


async def _h_trigger_self_question_eager(params: dict) -> dict:
    from hwarang_api.learning.self_questioner import eager_questioning_cycle

    return await eager_questioning_cycle(
        topic_count=int(params.get("topic_count", 10)),
        questions_per_topic=int(params.get("questions_per_topic", 5)),
        enable_socratic=bool(params.get("enable_socratic", True)),
    )


async def _h_trigger_sleep_cycle(params: dict) -> dict:
    from hwarang_api.learning.sleep_consolidator import sleep_cycle

    return await sleep_cycle()


async def _h_adjust_quality_threshold(params: dict) -> dict:
    """settings 의 품질 임계 조정 (단순 상한/하한 보호)."""
    new_value = float(params.get("value", 0.7))
    new_value = max(0.3, min(0.95, new_value))
    try:
        from hwarang_api.knowledge.settings import get_settings

        s = await get_settings()
        # 설정 모델에 필드가 없으면 noop — 추후 보강.
        setattr(s, "code_quality_threshold", new_value)
        return {"adjusted_to": new_value}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "attempted": new_value}


async def _h_no_action(params: dict) -> dict:
    return {"noop": True}


# 자유 실행 핸들러 (REQUIRES_APPROVAL 에 없는 것만)
HANDLERS: dict[str, Any] = {
    "trigger_curious_crawl": _h_trigger_curious_crawl,
    "trigger_arxiv_summarize": _h_trigger_arxiv_summarize,
    "rebuild_eval_set": _h_rebuild_eval_set,
    "trigger_self_question_eager": _h_trigger_self_question_eager,
    "trigger_sleep_cycle": _h_trigger_sleep_cycle,
    "adjust_quality_threshold": _h_adjust_quality_threshold,
    "no_action": _h_no_action,
}


async def _queue_for_approval(
    action: str, params: dict, memory_id: str, actor: str
) -> dict:
    """승인 필요 액션 — GrowthDecision(proposed) 으로 큐잉."""
    try:
        record = await prisma.growthdecision.create(
            data={
                "decisionType": action,
                "triggerDomain": params.get("domain"),
                "triggerMetric": "cognitive_loop",
                "status": "proposed",
                "proposalJson": {
                    "action": action,
                    "params": params,
                    "cognitive_memory_id": memory_id,
                    "actor": actor,
                },
            }
        )
        return {"growth_decision_id": record.id}
    except Exception as exc:  # noqa: BLE001
        logger.warning("approval 큐잉 실패: %s", exc)
        return {"error": f"queue_failed: {exc}"}


def _matches_approval(action: str, requires_approval: list[str]) -> bool:
    """와일드카드 (``delete_*``) 지원."""
    for pat in requires_approval:
        if pat.endswith("*") and action.startswith(pat[:-1]):
            return True
        if pat == action:
            return True
    return False


async def check_and_execute(
    decision: dict,
    memory_id: str,
    actor: str,
    *,
    requires_approval: list[str] | None = None,
) -> dict:
    """단일 결정을 검사 + 실행 (또는 승인 큐잉)."""
    from hwarang_api.cognitive.master_loop import REQUIRES_APPROVAL

    requires_approval = requires_approval or REQUIRES_APPROVAL

    action = (decision.get("action") or "").strip()
    params = decision.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    if not action:
        return {"action": action, "status": "blocked", "reason": "empty_action"}

    # 승인 필요
    if _matches_approval(action, requires_approval):
        result = await _queue_for_approval(action, params, memory_id, actor)
        return {
            "action": action,
            "status": "pending_approval",
            "result": result,
            "reason": "requires_human_review",
        }

    handler = HANDLERS.get(action)
    if handler is None:
        return {
            "action": action,
            "status": "blocked",
            "reason": "unknown_action",
        }

    try:
        result = await handler(params)
        return {"action": action, "status": "executed", "result": result}
    except Exception as exc:  # noqa: BLE001
        logger.exception("action[%s] 실행 실패", action)
        return {
            "action": action,
            "status": "blocked",
            "reason": f"exec_failed: {type(exc).__name__}: {exc}",
        }


__all__ = ["check_and_execute", "HANDLERS"]
