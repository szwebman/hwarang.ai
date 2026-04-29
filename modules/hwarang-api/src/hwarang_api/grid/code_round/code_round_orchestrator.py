"""코드 도메인 HFL 라운드 자동 오케스트레이션.

매 6 시간 cron 으로 평가:

* 신규 RLHF code feedback 1000+ 누적
* 신규 high-quality CodePair 500+ 누적
* 마지막 코드 라운드로부터 24 시간 경과

→ 모두 만족 시 새 라운드 자동 시작.

실제 라운드 라이프사이클은 :class:`RoundOrchestrator` 가 담당하고, 여기서는
**언제 / 무엇으로 / 누구에게** 만 결정한다.
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
MIN_RLHF_SAMPLES = 1000
MIN_PAIR_SAMPLES = 500
MIN_HOURS_BETWEEN_ROUNDS = 24

# 코드 LoRA 학습 가능 최소 GPU 사양 (RTX 4080 = 16 GB)
MIN_GPU_VRAM_GB = 16

# 한 라운드에 사용할 CodePair 최대 개수
MAX_PAIRS_PER_ROUND = 5000
MIN_PAIRS_TO_BUILD = 100

DEFAULT_TARGET_PARTICIPANTS = 10
MIN_AGENTS_TO_START = 3


BroadcastFn = Callable[..., Awaitable[None]]


@dataclass
class CodeRoundDecision:
    """라운드 시작 가부 + 사유 + 측정값."""

    should_start: bool
    reason: str
    rlhf_count: int = 0
    pair_count: int = 0
    hours_since_last: float = 0.0


# ─────────────────────────────────────────────────────────────────
# 트리거 평가
# ─────────────────────────────────────────────────────────────────
async def evaluate_code_round_trigger() -> CodeRoundDecision:
    """라운드 시작 조건을 체크해 :class:`CodeRoundDecision` 반환.

    Prisma 가 비활성이면 ``reason="db_unavailable"`` 로 즉시 거절.
    """
    if not _is_db_ready():
        return CodeRoundDecision(should_start=False, reason="db_unavailable")

    now = datetime.now(timezone.utc)

    # 마지막 코드 라운드
    try:
        last_round = await prisma.round.find_first(
            where={"domain": "code"},
            order={"createdAt": "desc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("evaluate_code_round_trigger: round lookup 실패: %s", exc)
        return CodeRoundDecision(should_start=False, reason="db_error")

    if last_round and getattr(last_round, "createdAt", None):
        hours_since = (now - last_round.createdAt).total_seconds() / 3600.0
        if hours_since < MIN_HOURS_BETWEEN_ROUNDS:
            return CodeRoundDecision(
                should_start=False,
                reason="too_soon",
                hours_since_last=hours_since,
            )
        cutoff = last_round.createdAt
    else:
        hours_since = 999.0
        cutoff = now - timedelta(days=30)

    # 신규 RLHF (rating 이 채워진 명시 신호만)
    rlhf_count = 0
    try:
        rlhf_count = await prisma.rlhffeedback.count(
            where={
                "domain": "code",
                "createdAt": {"gte": cutoff},
                "rating": {"not": None},
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("RLHFFeedback.count 실패 (무시): %s", exc)

    # 신규 CodePair — 실행 통과 + 미사용
    pair_count = 0
    try:
        pair_count = await prisma.codepair.count(
            where={
                "createdAt": {"gte": cutoff},
                "executionStatus": "passed",
                "isUsedInLora": False,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("CodePair.count 실패 (무시): %s", exc)

    if rlhf_count < MIN_RLHF_SAMPLES and pair_count < MIN_PAIR_SAMPLES:
        return CodeRoundDecision(
            should_start=False,
            reason="insufficient_data",
            rlhf_count=rlhf_count,
            pair_count=pair_count,
            hours_since_last=hours_since,
        )

    return CodeRoundDecision(
        should_start=True,
        reason="ready",
        rlhf_count=rlhf_count,
        pair_count=pair_count,
        hours_since_last=hours_since,
    )


# ─────────────────────────────────────────────────────────────────
# 라운드 시작
# ─────────────────────────────────────────────────────────────────
async def start_code_round(
    broadcast_callback: BroadcastFn | None = None,
) -> dict[str, Any]:
    """평가 통과 시 실제 라운드 시작.

    매 cron 마다 호출. ``evaluate_code_round_trigger`` 통과 못하면
    ``{"started": False, "reason": ...}`` 반환.
    """
    decision = await evaluate_code_round_trigger()
    if not decision.should_start:
        return {
            "started": False,
            "reason": decision.reason,
            "metrics": {
                "rlhf": decision.rlhf_count,
                "pairs": decision.pair_count,
                "hours_since_last": decision.hours_since_last,
            },
        }

    # 1) 데이터셋 구성
    dataset_url, used_count = await _build_code_dataset()
    if not dataset_url or used_count < MIN_PAIRS_TO_BUILD:
        return {
            "started": False,
            "reason": "dataset_build_failed",
            "pairs_available": used_count,
        }

    # 2) 코드 적격 에이전트 (VRAM + 도메인)
    try:
        from hwarang_api.routers.grid import _agents  # type: ignore
    except Exception:  # noqa: BLE001
        _agents = {}  # type: ignore[assignment]

    eligible_agents = [a for a in _agents.values() if _is_code_eligible(a)]

    if len(eligible_agents) < MIN_AGENTS_TO_START:
        return {
            "started": False,
            "reason": "insufficient_agents",
            "active": len(eligible_agents),
            "required": MIN_AGENTS_TO_START,
        }

    # 3) RoundOrchestrator 로 위임
    matcher = AgentMatcher()
    sharder = DataShardingService()
    straggler = StragglerHandler(
        matcher=matcher,
        active_agents_provider=lambda: eligible_agents,
    )
    orch = RoundOrchestrator(matcher, sharder, straggler)

    result = await orch.open_round(
        domain="code",
        data_source_url=dataset_url,
        sample_count=used_count,
        target_participants=min(DEFAULT_TARGET_PARTICIPANTS, len(eligible_agents)),
        strategy="iid",
        active_agents=eligible_agents,
        config={
            "auto_triggered": True,
            "rlhf_signal_count": decision.rlhf_count,
            "pair_count": decision.pair_count,
            "lora_r": 16,
            "lora_alpha": 32,
            "learning_rate": 2e-4,
        },
        broadcast=broadcast_callback,
    )

    round_id = result.get("round_id")

    # 4) 사용한 CodePair 들에 round_id 기록 (best effort)
    if round_id:
        await _mark_pairs_with_round(round_id)

    return {
        "started": True,
        "round_id": round_id,
        "domain": "code",
        "participants": [s.get("agent_id") for s in result.get("selected", [])],
        "samples": used_count,
        "rlhf_signal_count": decision.rlhf_count,
        "dataset_url": dataset_url,
    }


# ─────────────────────────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────────────────────────
def _is_code_eligible(agent: dict[str, Any]) -> bool:
    """코드 LoRA 학습 가능 에이전트 — VRAM + 도메인."""
    vram = float(agent.get("vram_gb", 0) or 0)
    if vram < MIN_GPU_VRAM_GB:
        return False
    domains = agent.get("domains") or agent.get("expert_tags") or []
    if isinstance(domains, str):
        domains = [domains]
    if "code" not in domains and "general" not in domains:
        return False
    # heartbeat 신선도 — 60 초 안 (있을 때만)
    last_hb = agent.get("last_heartbeat")
    if last_hb is not None:
        import time

        if (time.time() - float(last_hb)) > 60:
            return False
    return True


def _is_db_ready() -> bool:
    return getattr(prisma, "is_connected", lambda: False)()


async def _build_code_dataset() -> tuple[str, int]:
    """CodePair → 학습 데이터셋 (jsonl). DataSharder 가 분배할 source URL 반환.

    Returns
    -------
    tuple
        ``(url, sample_count)``. 빌드 실패 시 ``("", 0)``.
    """
    if not _is_db_ready():
        return "", 0

    try:
        pairs = await prisma.codepair.find_many(
            where={
                "executionStatus": "passed",
                "isUsedInLora": False,
            },
            take=MAX_PAIRS_PER_ROUND,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("CodePair.find_many 실패: %s", exc)
        return "", 0

    if len(pairs) < MIN_PAIRS_TO_BUILD:
        return "", len(pairs)

    shard_dir = os.getenv("HWARANG_SHARD_DIR", "/var/hwarang/shards")
    base_dir = Path(shard_dir)
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("shard dir 생성 실패: %s", exc)
        return "", 0

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"code_pairs_{timestamp}.jsonl"
    filepath = base_dir / filename

    pair_ids: list[str] = []
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            for p in pairs:
                f.write(
                    json.dumps(
                        {
                            "instruction": getattr(p, "instruction", ""),
                            "response": getattr(p, "response", ""),
                            "language": getattr(p, "language", None),
                            "framework": getattr(p, "framework", None),
                            "category": getattr(p, "category", None),
                            "domain": "code",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                pid = getattr(p, "id", None)
                if pid:
                    pair_ids.append(pid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("dataset write 실패: %s", exc)
        return "", 0

    # 사용 마킹 — round_id 는 라운드 생성 후 _mark_pairs_with_round 가 갱신
    if pair_ids:
        try:
            await prisma.codepair.update_many(
                where={"id": {"in": pair_ids}},
                data={"isUsedInLora": True},
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("CodePair.update_many 실패 (무시): %s", exc)

    # 다음 단계에서 round_id 매핑에 쓰도록 캐시
    _LAST_BUILD["pair_ids"] = pair_ids

    base_url = os.getenv(
        "HWARANG_SHARD_BASE_URL", "http://localhost:8000/static/shards"
    )
    return f"{base_url}/{filename}", len(pair_ids)


# 직전 빌드의 pair_ids 캐시 (단일 워커 가정)
_LAST_BUILD: dict[str, Any] = {"pair_ids": []}


async def _mark_pairs_with_round(round_id: str) -> None:
    """직전 빌드한 CodePair 들에 round_id (loraRound) 기록."""
    pair_ids = _LAST_BUILD.get("pair_ids") or []
    if not pair_ids or not _is_db_ready():
        return

    # loraRound 는 Int? 이므로 round_id (cuid) 가 아닌 hash 값을 저장.
    # 실제 추적은 별도 매핑 — 여기서는 단순 표식.
    round_marker = abs(hash(round_id)) % (10**9)
    try:
        await prisma.codepair.update_many(
            where={"id": {"in": pair_ids}},
            data={"loraRound": int(round_marker)},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("CodePair.loraRound 갱신 실패 (무시): %s", exc)
    finally:
        _LAST_BUILD["pair_ids"] = []


__all__ = [
    "CodeRoundDecision",
    "evaluate_code_round_trigger",
    "start_code_round",
    "MIN_RLHF_SAMPLES",
    "MIN_PAIR_SAMPLES",
    "MIN_HOURS_BETWEEN_ROUNDS",
    "MIN_GPU_VRAM_GB",
]
