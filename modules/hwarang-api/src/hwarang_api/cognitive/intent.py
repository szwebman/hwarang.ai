"""화랑의 장기 의도 — "이번 주는 X 에 집중하겠다" 같은 선언 (Phase 7).

매 주 1 회 (일요일 23:00 KST) 자기가 의도 선언.
이후 사이클들 (``reasoning``) 이 그 의도를 프롬프트에 주입해 결정에 가중치.

저장
----
``SystemSetting`` 테이블의 ``key="weekly_intent"`` 행에 JSON 문자열로 저장.
스키마에 ``metadata`` 컬럼이 없으므로 declared_at 도 JSON 안에 포함.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone

from hwarang_api.db import prisma
from hwarang_api.knowledge.llm import _chat as llm_chat

logger = logging.getLogger(__name__)


# 화랑이 선택할 수 있는 집중 영역 (LLM 프롬프트에 명시)
FOCUS_AREAS: list[str] = [
    "code_quality",          # 코딩 LoRA 품질 ↑
    "domain_expansion",       # 새 도메인 학습
    "user_satisfaction",      # 사용자 만족도 ↑
    "knowledge_breadth",      # HLKM 다양성 ↑
    "cost_efficiency",        # LLM 비용 ↓
    "exploration",            # 새 출처/기능 발견
]


INTENT_GENERATE_PROMPT = """당신은 화랑 AI 입니다. 이번 주 (다음 7일) 동안 자기가 집중할 의도를 1개 선언하세요.

## 지난 주 성과
{last_week_metrics}

## 가능한 집중 영역
- code_quality (코딩 LoRA 품질 ↑)
- domain_expansion (새 도메인 학습)
- user_satisfaction (사용자 만족도 ↑)
- knowledge_breadth (HLKM 다양성 ↑)
- cost_efficiency (LLM 비용 ↓)
- exploration (새 출처/기능 발견)

JSON:
{{
  "focus": "위 영역 중 하나",
  "specific_goals": ["구체 목표 1", "목표 2"],
  "success_metric": "어떻게 성공 측정",
  "rationale": "왜 이 의도를 선택"
}}

JSON 만:"""


# ---------------------------------------------------------------------------
# 의도 선언 (매주)
# ---------------------------------------------------------------------------
async def declare_weekly_intent() -> dict:
    """매 주 일요일 — 다음 주 의도 선언.

    Returns:
        선언된 intent dict (실패 시 {}).
    """
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    last_week_obs = await _last_week_metrics(week_ago)

    metrics_text = "\n".join(f"- {k}: {v}" for k, v in last_week_obs.items()) or "(데이터 없음)"

    try:
        raw = await llm_chat(
            INTENT_GENERATE_PROMPT.format(last_week_metrics=metrics_text),
            max_tokens=600,
        )
        if not raw:
            return {}
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return {}
        intent = json.loads(m.group())
        if not isinstance(intent, dict):
            return {}

        # focus 검증 — 허용 영역 외면 user_satisfaction 으로 폴백
        if intent.get("focus") not in FOCUS_AREAS:
            logger.warning("intent focus 부적합 (%s) → user_satisfaction 폴백", intent.get("focus"))
            intent["focus"] = "user_satisfaction"

        # 메타데이터 — declared_at 을 JSON 안에 (SystemSetting 에 metadata 컬럼 없음)
        intent["declared_at"] = datetime.now(timezone.utc).isoformat()

        # SystemSetting 에 저장 — upsert
        try:
            await prisma.systemsetting.upsert(
                where={"key": "weekly_intent"},
                data={
                    "create": {
                        "key": "weekly_intent",
                        "value": json.dumps(intent, ensure_ascii=False),
                    },
                    "update": {
                        "value": json.dumps(intent, ensure_ascii=False),
                    },
                },
            )
        except Exception as exc:  # noqa: BLE001
            # prisma-client-py upsert payload 변형 폴백
            logger.debug("systemsetting upsert 1차 실패, fallback: %s", exc)
            try:
                await prisma.systemsetting.upsert(
                    where={"key": "weekly_intent"},
                    create={
                        "key": "weekly_intent",
                        "value": json.dumps(intent, ensure_ascii=False),
                    },
                    update={
                        "value": json.dumps(intent, ensure_ascii=False),
                    },
                )
            except Exception as exc2:  # noqa: BLE001
                logger.warning("intent SystemSetting 저장 실패: %s", exc2)

        # 알림 (선택, 실패 무시)
        try:
            from hwarang_api.knowledge.notifier import notify_admin

            await notify_admin(
                f"📌 *이번 주 화랑 의도 선언*\n\n"
                f"**Focus**: {intent.get('focus')}\n"
                f"**목표**: {', '.join(intent.get('specific_goals', []) or [])}\n"
                f"**성공 측정**: {intent.get('success_metric', '')}\n"
                f"**근거**: {intent.get('rationale', '')}",
                severity="info",
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("notify_admin 실패 (계속 진행): %s", exc)

        return intent
    except Exception as exc:  # noqa: BLE001
        logger.warning("intent 선언 실패: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# 의도 조회 (사이클들이 사용)
# ---------------------------------------------------------------------------
async def get_current_intent() -> dict | None:
    """현재 주 의도 가져오기. 없으면 None."""
    try:
        setting = await prisma.systemsetting.find_unique(where={"key": "weekly_intent"})
        if not setting:
            return None
        value = getattr(setting, "value", None)
        if not value:
            return None
        return json.loads(value)
    except Exception as exc:  # noqa: BLE001
        logger.debug("get_current_intent 실패: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 지난 주 핵심 메트릭
# ---------------------------------------------------------------------------
async def _last_week_metrics(since: datetime) -> dict:
    """지난 주 핵심 메트릭 — RLHF 만족도 / 새 사실 / 라운드 / 결정 수."""
    metrics: dict = {}

    # RLHF
    try:
        rlhf = await prisma.rlhffeedback.find_many(
            where={"createdAt": {"gte": since}, "isSatisfied": {"not": None}},
            take=500,
        )
        if rlhf:
            metrics["rlhf_count"] = len(rlhf)
            metrics["rlhf_satisfaction"] = round(
                sum(1 for r in rlhf if getattr(r, "isSatisfied", False)) / len(rlhf), 2
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("rlhf metrics 실패: %s", exc)

    # 새 사실
    try:
        metrics["new_facts"] = await prisma.knowledgefact.count(
            where={"createdAt": {"gte": since}}
        )
    except Exception:  # noqa: BLE001
        metrics["new_facts"] = None

    # 완료 라운드
    try:
        metrics["rounds_completed"] = await prisma.round.count(
            where={"completedAt": {"gte": since}}
        )
    except Exception:  # noqa: BLE001
        metrics["rounds_completed"] = None

    # GrowthDecision
    try:
        metrics["decisions_proposed"] = await prisma.growthdecision.count(
            where={"createdAt": {"gte": since}}
        )
    except Exception:  # noqa: BLE001
        metrics["decisions_proposed"] = None

    return metrics


__all__ = [
    "declare_weekly_intent",
    "get_current_intent",
    "FOCUS_AREAS",
    "INTENT_GENERATE_PROMPT",
]
