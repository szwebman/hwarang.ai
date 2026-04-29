"""디자인 도메인 HFL 라운드 자동 오케스트레이션.

코드 라운드와 동일한 패턴이지만 데이터 소스가 다르다:

* 코드 → :class:`CodePair` (instruction + response)
* 디자인 → :class:`DesignPattern` (summary + 키워드 + layout) → 학습용
  ``{"instruction": "...요청", "response": "...code"}`` 페어로 변환

DesignPattern 은 RLHF 신호와 직접 연결돼 있지 않으므로 (디자인 ``KnowledgeFact``
의 ``isHighQuality`` + ``popularity`` 로 대신) 트리거 조건은 코드와 살짝 다르다.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from hwarang_api.db import prisma
from hwarang_api.grid.matcher import AgentMatcher
from hwarang_api.grid.round_orchestrator import RoundOrchestrator
from hwarang_api.grid.sharder import DataShardingService
from hwarang_api.grid.straggler import StragglerHandler

logger = logging.getLogger(__name__)


# ── 트리거 임계치 ────────────────────────────────────────────────
MIN_RLHF_SAMPLES_DESIGN = 500  # 디자인은 RLHF 가 더 적게 모이므로 절반
MIN_PATTERN_SAMPLES = 200
MIN_HOURS_BETWEEN_ROUNDS_DESIGN = 48  # 디자인은 좀 더 천천히

MIN_GPU_VRAM_GB_DESIGN = 24  # 비전 LoRA 는 더 무거움 (RTX 3090/4090)

MAX_PATTERNS_PER_ROUND = 3000
MIN_PATTERNS_TO_BUILD = 50

DEFAULT_TARGET_PARTICIPANTS_DESIGN = 6
MIN_AGENTS_TO_START_DESIGN = 2


BroadcastFn = Callable[..., Awaitable[None]]


@dataclass
class DesignRoundDecision:
    should_start: bool
    reason: str
    rlhf_count: int = 0
    pattern_count: int = 0
    hours_since_last: float = 0.0


# ─────────────────────────────────────────────────────────────────
# 트리거
# ─────────────────────────────────────────────────────────────────
async def evaluate_design_round_trigger() -> DesignRoundDecision:
    """디자인 라운드 시작 조건 체크."""
    if not _is_db_ready():
        return DesignRoundDecision(should_start=False, reason="db_unavailable")

    now = datetime.now(timezone.utc)

    try:
        last_round = await prisma.round.find_first(
            where={"domain": "design"},
            order={"createdAt": "desc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("design round lookup 실패: %s", exc)
        return DesignRoundDecision(should_start=False, reason="db_error")

    if last_round and getattr(last_round, "createdAt", None):
        hours_since = (now - last_round.createdAt).total_seconds() / 3600.0
        if hours_since < MIN_HOURS_BETWEEN_ROUNDS_DESIGN:
            return DesignRoundDecision(
                should_start=False,
                reason="too_soon",
                hours_since_last=hours_since,
            )
        cutoff = last_round.createdAt
    else:
        hours_since = 999.0
        cutoff = now - timedelta(days=30)

    rlhf_count = 0
    try:
        rlhf_count = await prisma.rlhffeedback.count(
            where={
                "domain": "design",
                "createdAt": {"gte": cutoff},
                "rating": {"not": None},
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("RLHFFeedback design count 실패: %s", exc)

    pattern_count = 0
    try:
        # DesignPattern 자체에 isUsedInLora 플래그가 없으므로 createdAt 기준으로
        # 신규 패턴 누적 수만 본다.
        pattern_count = await prisma.designpattern.count(
            where={"createdAt": {"gte": cutoff}},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("DesignPattern.count 실패: %s", exc)

    if rlhf_count < MIN_RLHF_SAMPLES_DESIGN and pattern_count < MIN_PATTERN_SAMPLES:
        return DesignRoundDecision(
            should_start=False,
            reason="insufficient_data",
            rlhf_count=rlhf_count,
            pattern_count=pattern_count,
            hours_since_last=hours_since,
        )

    return DesignRoundDecision(
        should_start=True,
        reason="ready",
        rlhf_count=rlhf_count,
        pattern_count=pattern_count,
        hours_since_last=hours_since,
    )


# ─────────────────────────────────────────────────────────────────
# 시작
# ─────────────────────────────────────────────────────────────────
async def start_design_round(
    broadcast_callback: BroadcastFn | None = None,
) -> dict[str, Any]:
    decision = await evaluate_design_round_trigger()
    if not decision.should_start:
        return {
            "started": False,
            "reason": decision.reason,
            "metrics": {
                "rlhf": decision.rlhf_count,
                "patterns": decision.pattern_count,
                "hours_since_last": decision.hours_since_last,
            },
        }

    dataset_url, used_count = await _build_design_dataset()
    if not dataset_url or used_count < MIN_PATTERNS_TO_BUILD:
        return {
            "started": False,
            "reason": "dataset_build_failed",
            "patterns_available": used_count,
        }

    try:
        from hwarang_api.routers.grid import _agents  # type: ignore
    except Exception:  # noqa: BLE001
        _agents = {}  # type: ignore[assignment]

    eligible = [a for a in _agents.values() if _is_design_eligible(a)]
    if len(eligible) < MIN_AGENTS_TO_START_DESIGN:
        return {
            "started": False,
            "reason": "insufficient_agents",
            "active": len(eligible),
            "required": MIN_AGENTS_TO_START_DESIGN,
        }

    matcher = AgentMatcher()
    sharder = DataShardingService()
    straggler = StragglerHandler(
        matcher=matcher, active_agents_provider=lambda: eligible
    )
    orch = RoundOrchestrator(matcher, sharder, straggler)

    result = await orch.open_round(
        domain="design",
        data_source_url=dataset_url,
        sample_count=used_count,
        target_participants=min(DEFAULT_TARGET_PARTICIPANTS_DESIGN, len(eligible)),
        strategy="iid",
        active_agents=eligible,
        config={
            "auto_triggered": True,
            "rlhf_signal_count": decision.rlhf_count,
            "pattern_count": decision.pattern_count,
            "lora_r": 16,
            "lora_alpha": 32,
            "learning_rate": 1.5e-4,
        },
        broadcast=broadcast_callback,
    )

    return {
        "started": True,
        "round_id": result.get("round_id"),
        "domain": "design",
        "participants": [s.get("agent_id") for s in result.get("selected", [])],
        "samples": used_count,
        "rlhf_signal_count": decision.rlhf_count,
        "dataset_url": dataset_url,
    }


# ─────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────
def _is_design_eligible(agent: dict[str, Any]) -> bool:
    """디자인 LoRA 학습 가능 — 비전 모델용 VRAM 더 필요."""
    vram = float(agent.get("vram_gb", 0) or 0)
    if vram < MIN_GPU_VRAM_GB_DESIGN:
        return False
    domains = agent.get("domains") or agent.get("expert_tags") or []
    if isinstance(domains, str):
        domains = [domains]
    if "design" not in domains and "general" not in domains:
        return False
    last_hb = agent.get("last_heartbeat")
    if last_hb is not None:
        import time

        if (time.time() - float(last_hb)) > 60:
            return False
    return True


def _is_db_ready() -> bool:
    return getattr(prisma, "is_connected", lambda: False)()


async def _build_design_dataset() -> tuple[str, int]:
    """DesignPattern → 학습 데이터셋 (jsonl).

    DesignPattern 은 ``summary`` + 키워드 + ``applicableTo`` 만 가지고 있으므로,
    instruction/response 페어를 동적으로 합성::

        {
          "instruction": "이런 디자인의 hero section 만들어줘",
          "response": "<summary + keywords + applicableTo 조합>",
          "domain": "design"
        }

    실제 코드 출력을 위한 fine-tuning 은 별도 vLM (Qwen2.5-VL) 단계에서 수행.
    """
    if not _is_db_ready():
        return "", 0

    try:
        patterns = await prisma.designpattern.find_many(
            order={"popularity": "desc"},
            take=MAX_PATTERNS_PER_ROUND,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("DesignPattern.find_many 실패: %s", exc)
        return "", 0

    if len(patterns) < MIN_PATTERNS_TO_BUILD:
        return "", len(patterns)

    shard_dir = os.getenv("HWARANG_SHARD_DIR", "/var/hwarang/shards")
    base_dir = Path(shard_dir)
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("shard dir 생성 실패: %s", exc)
        return "", 0

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"design_patterns_{timestamp}.jsonl"
    filepath = base_dir / filename

    written = 0
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            for p in patterns:
                instruction = _design_instruction_template(p)
                response = _design_response_template(p)
                if not instruction or not response:
                    continue
                f.write(
                    json.dumps(
                        {
                            "instruction": instruction,
                            "response": response,
                            "domain": "design",
                            "layout": getattr(p, "layoutCategory", None),
                            "trends": list(getattr(p, "trendKeywords", []) or []),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                written += 1
    except Exception as exc:  # noqa: BLE001
        logger.warning("design dataset write 실패: %s", exc)
        return "", 0

    if written < MIN_PATTERNS_TO_BUILD:
        return "", written

    base_url = os.getenv(
        "HWARANG_SHARD_BASE_URL", "http://localhost:8000/static/shards"
    )
    return f"{base_url}/{filename}", written


def _design_instruction_template(p: Any) -> str:
    layout = getattr(p, "layoutCategory", None) or "section"
    trends = list(getattr(p, "trendKeywords", []) or [])
    trend_str = ", ".join(trends[:3]) if trends else "modern"
    return f"이런 {trend_str} 디자인의 {layout} section 만들어줘"


def _design_response_template(p: Any) -> str:
    summary = (getattr(p, "summary", None) or "").strip()
    if not summary:
        return ""
    layout = getattr(p, "layoutCategory", None) or "section"
    color = getattr(p, "colorMood", None)
    typography = getattr(p, "typographyStyle", None)
    applicable = list(getattr(p, "applicableTo", []) or [])
    parts = [summary, f"layout={layout}"]
    if color:
        parts.append(f"color={color}")
    if typography:
        parts.append(f"typography={typography}")
    if applicable:
        parts.append(f"use_for={','.join(applicable[:3])}")
    return " | ".join(parts)


__all__ = [
    "DesignRoundDecision",
    "evaluate_design_round_trigger",
    "start_design_round",
    "MIN_RLHF_SAMPLES_DESIGN",
    "MIN_PATTERN_SAMPLES",
    "MIN_HOURS_BETWEEN_ROUNDS_DESIGN",
]
