"""Priority Replay Buffer — Phase 2.

옛 task 의 샘플을 효율적으로 재사용해서 Catastrophic forgetting 을 줄인다.

학습 배치 = 신규 (RLHFFeedback 최근 24h) + 리플레이 (ReplaySample 우선순위 가중)
기본 비율은 7:3.

우선순위 공식:

    score(s) = priority(s) · diversity(s)

    priority(s) = α · fisher_importance + β · |rlhf_rating| + γ · difficulty
    diversity(s) = sigmoid( 0.1 · (days_since_last_sampled − 7) )

- ``priority`` 는 ReplaySample.priority 컬럼에 미리 적재 (학습 직후 add_to_replay).
- ``diversity`` 는 sampling 시각 차이로 계산 — 오래 안 본 sample 우선.

학습 노드뿐 아니라 API 컨테이너에서도 import 가능 (torch 의존성 없음).
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _prisma_ready() -> bool:
    try:
        return bool(prisma.is_connected())
    except Exception:
        return False


# ────────────────────────────────────────────────────────────
# 배치 샘플링 — 학습 직전 호출
# ────────────────────────────────────────────────────────────
async def sample_replay_batch(
    domain: str,
    batch_size: int = 32,
    new_data_ratio: float = 0.7,
) -> dict[str, list[dict]]:
    """신규/리플레이 혼합 배치 생성.

    Parameters
    ----------
    domain : str
        도메인 (legal/coding/medical/general/...).
    batch_size : int
        총 샘플 수.
    new_data_ratio : float
        신규 데이터 비율 (0~1). 나머지는 리플레이.

    Returns
    -------
    dict
        ``{"new": [...], "replay": [...]}`` (각 element 는
        ``{"prompt": str, "completion": str, "source": str}``).
    """
    if not _prisma_ready():
        return {"new": [], "replay": []}

    new_count = max(1, int(batch_size * new_data_ratio))
    replay_count = max(0, batch_size - new_count)

    # ── 신규: 최근 24h RLHFFeedback 중 isSatisfied 가 결정된 것 ──
    cutoff_24h = _utcnow() - timedelta(hours=24)
    try:
        new_rows = await prisma.rlhffeedback.find_many(
            where={
                "domain": domain,
                "createdAt": {"gte": cutoff_24h},
                "isSatisfied": {"not": None},
            },
            take=new_count,
            order={"createdAt": "desc"},
        )
    except Exception as e:  # pragma: no cover
        logger.warning(f"RLHFFeedback 조회 실패: {e}")
        new_rows = []

    new_samples = [_format_rlhf(r) for r in new_rows if _format_rlhf(r)]

    # ── 리플레이: priority desc 로 5 배수 후보 → 다양성 가중 정렬 ──
    replay_samples: list[dict] = []
    if replay_count > 0:
        try:
            candidates = await prisma.replaysample.find_many(
                where={"domain": domain},
                take=replay_count * 5,
                order={"priority": "desc"},
            )
        except Exception as e:  # pragma: no cover
            logger.warning(f"ReplaySample 조회 실패: {e}")
            candidates = []

        now = _utcnow()
        weighted: list[tuple[Any, float]] = []
        for c in candidates:
            recency_days = (
                (now - c.lastSampledAt).total_seconds() / 86400
                if c.lastSampledAt
                else 30.0
            )
            # sigmoid: days=7 일 때 0.5, days≫7 → 1, days<7 → 0
            diversity = 1.0 / (1.0 + math.exp(-0.1 * (recency_days - 7.0)))
            weighted.append((c, c.priority * diversity))

        weighted.sort(key=lambda x: x[1], reverse=True)
        chosen = [w[0] for w in weighted[:replay_count]]

        # 사용 추적 (sampledCount += 1, lastSampledAt = now)
        for r in chosen:
            try:
                await prisma.replaysample.update(
                    where={"id": r.id},
                    data={"sampledCount": {"increment": 1}, "lastSampledAt": now},
                )
            except Exception as e:  # pragma: no cover
                logger.warning(f"ReplaySample {r.id} update 실패: {e}")

        replay_samples = [_format_replay(r) for r in chosen]

    logger.info(
        f"replay batch: domain={domain} new={len(new_samples)} "
        f"replay={len(replay_samples)}"
    )
    return {"new": new_samples, "replay": replay_samples}


# ────────────────────────────────────────────────────────────
# 버퍼에 추가 — 학습 후 가치 있는 샘플 보존
# ────────────────────────────────────────────────────────────
async def add_to_replay(
    domain: str,
    prompt: str,
    expected: str,
    *,
    priority: float = 1.0,
    difficulty: Optional[float] = None,
    rating: Optional[int] = None,
) -> dict:
    """학습 후 가치 있는 샘플을 ReplaySample 로 보존.

    호출 예시:
    - 학습 후 검증 셋에서 모델이 정답을 낸 case (옛 task 보존용)
    - RLHF 양/음 샘플 (둘 다 가치 있음)
    """
    if not _prisma_ready():
        return {"added": False, "reason": "db_unavailable"}

    try:
        row = await prisma.replaysample.create(
            data={
                "domain": domain,
                "prompt": prompt,
                "expectedOutput": expected,
                "priority": float(priority),
                "difficulty": difficulty,
                "rlhfRating": rating,
            }
        )
        return {"added": True, "id": row.id}
    except Exception as e:  # pragma: no cover
        logger.warning(f"ReplaySample create 실패: {e}")
        return {"added": False, "error": str(e)}


async def add_many_to_replay(
    domain: str, items: list[dict[str, Any]]
) -> dict[str, int]:
    """대량 추가 — items 의 각 dict 는
    ``{"prompt", "expected", "priority"?, "difficulty"?, "rating"?}``.
    """
    added = 0
    failed = 0
    for it in items:
        res = await add_to_replay(
            domain=domain,
            prompt=it["prompt"],
            expected=it["expected"],
            priority=float(it.get("priority", 1.0)),
            difficulty=it.get("difficulty"),
            rating=it.get("rating"),
        )
        if res.get("added"):
            added += 1
        else:
            failed += 1
    return {"added": added, "failed": failed}


# ────────────────────────────────────────────────────────────
# 통계 — 관리자 UI / 디버그
# ────────────────────────────────────────────────────────────
async def replay_buffer_stats(domain: Optional[str] = None) -> dict:
    """버퍼 크기, 평균 priority, 최근 사용 비율."""
    if not _prisma_ready():
        return {"db": "unavailable"}

    where = {"domain": domain} if domain else {}
    total = await prisma.replaysample.count(where=where)
    return {"domain": domain or "(all)", "total": total}


# ────────────────────────────────────────────────────────────
# 포맷 헬퍼
# ────────────────────────────────────────────────────────────
def _format_rlhf(row: Any) -> Optional[dict]:
    """RLHFFeedback → 학습 형식. followupMsg 가 없으면 학습 무가치."""
    fup = getattr(row, "followupMsg", None)
    msg_id = getattr(row, "messageId", None) or getattr(row, "id", "?")
    if not fup:
        # 다음 메시지가 없으면 학습 형식 만들 수 없음
        return None
    return {
        "prompt": f"[message:{msg_id}]",  # 실제 prompt 는 conversationId 로 따로 join
        "completion": fup,
        "source": "rlhf",
        "rating": getattr(row, "rating", None),
        "domain": getattr(row, "domain", None),
    }


def _format_replay(row: Any) -> dict:
    """ReplaySample → 학습 형식."""
    return {
        "prompt": row.prompt,
        "completion": row.expectedOutput,
        "source": "replay",
        "priority": row.priority,
        "rating": getattr(row, "rlhfRating", None),
        "domain": row.domain,
    }


__all__ = [
    "sample_replay_batch",
    "add_to_replay",
    "add_many_to_replay",
    "replay_buffer_stats",
]
