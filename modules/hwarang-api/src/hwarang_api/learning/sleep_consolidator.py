"""HSEE Phase 5 — Sleep Consolidation.

매일 새벽 3시 (KST) 화랑이 "자면서" 24시간 누적분을 정교화하는 사이클.

수행:
  1. 새 ``KnowledgeFact`` 도메인별 카운트 → 50건 이상이면 도메인별 mini LoRA
     학습 잡 enqueue (Phase 2 ``maybe_enqueue_training``)
  2. 모순 스캔 (``contradiction.scan_recent_contradictions`` — 있으면)
  3. ``current_confidence`` 가 0.3 미만이면서 30일 이상 된 fact 를 ``EXPIRED``
     로 archive
  4. 검증된 가설 → fact 승격 (``promote_validated_hypotheses`` 가 있으면)
  5. ``crawling`` 상태 gap 에 대해 토픽 매칭 새 fact 5+ 건이면 ``filled``
     로 마킹
  6. 적대적 자가 검증 (``adversarial_tester.run_adversarial_self_play`` —
     있으면)

각 단계는 의존 모듈 부재 / 예외 시 그 단계만 skip. 사이클 자체는 항상 완주.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from hwarang_api.db import prisma
from hwarang_api.learning.auto_trainer import maybe_enqueue_training

logger = logging.getLogger(__name__)


_STALE_AGE_DAYS = 30
_STALE_CONF_THRESHOLD = 0.3
_TRAINING_THRESHOLD_FACTS = 50
_GAP_RESOLVE_FACT_THRESHOLD = 5


def _prisma_ready() -> bool:
    try:
        return bool(prisma.is_connected())
    except Exception:
        return False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ───────────────────────────────────────────────────────────────
# 진입점 : sleep_cycle
# ───────────────────────────────────────────────────────────────
async def sleep_cycle() -> dict[str, Any]:
    """매일 새벽 3시 (KST) 1회 — 화랑 자가 통합 사이클."""
    started = _utcnow()
    results: dict[str, Any] = {"started_at": started.isoformat()}

    if not _prisma_ready():
        results["error"] = "db_unavailable"
        return results

    window_start = started - timedelta(hours=24)

    # ─────────────────────────────────────────────
    # 1) 새 사실 도메인별 클러스터링 → 학습 트리거
    # ─────────────────────────────────────────────
    try:
        new_facts = await prisma.knowledgefact.find_many(
            where={"createdAt": {"gte": window_start}},
            take=2000,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("sleep: new fact query failed: %s", exc)
        new_facts = []

    domains: dict[str, int] = {}
    for f in new_facts:
        d = (getattr(f, "domain", None) or "general").lower()
        domains[d] = domains.get(d, 0) + 1

    training_jobs = 0
    training_per_domain: dict[str, dict[str, Any]] = {}
    for dom, count in domains.items():
        if count >= _TRAINING_THRESHOLD_FACTS:
            try:
                r = await maybe_enqueue_training(
                    dom,
                    threshold=_TRAINING_THRESHOLD_FACTS,
                    triggered_by="sleep_cycle",
                )
                training_per_domain[dom] = r
                if r.get("triggered"):
                    training_jobs += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "sleep: maybe_enqueue_training(%s) failed: %s", dom, exc
                )

    # ─────────────────────────────────────────────
    # 2) 모순 스캔 (선택적)
    # ─────────────────────────────────────────────
    contradictions: dict[str, Any] = {"skipped": True}
    try:
        from hwarang_api.knowledge import contradiction as _con  # type: ignore

        if hasattr(_con, "scan_recent_contradictions"):
            contradictions = await _con.scan_recent_contradictions(hours=24)
        else:
            contradictions = {"skipped": True, "reason": "no_function"}
    except ImportError:
        contradictions = {"skipped": True, "reason": "no_module"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("sleep: contradiction scan failed: %s", exc)
        contradictions = {"error": str(exc)}

    # ─────────────────────────────────────────────
    # 3) Stale fact archive
    # ─────────────────────────────────────────────
    archived = 0
    try:
        from hwarang_api.knowledge.half_life import current_confidence
        from hwarang_api.knowledge.types import KnowledgeFact as _KF  # noqa: F401

        stale_cutoff = started - timedelta(days=_STALE_AGE_DAYS)
        stale_candidates = await prisma.knowledgefact.find_many(
            where={
                "status": "CONFIRMED",
                "createdAt": {"lt": stale_cutoff},
                "validTo": None,
            },
            take=500,
        )
        for f in stale_candidates:
            try:
                conf = current_confidence(f)
            except Exception:  # noqa: BLE001
                conf = 1.0
            if conf < _STALE_CONF_THRESHOLD:
                try:
                    await prisma.knowledgefact.update(
                        where={"id": f.id},
                        data={
                            "status": "EXPIRED",
                            "expiredReason": (
                                f"sleep_cycle: stale_confidence={conf:.2f}"
                            ),
                        },
                    )
                    archived += 1
                except Exception as exc:  # noqa: BLE001
                    logger.debug("archive failed for %s: %s", f.id, exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("sleep: stale-archive step failed: %s", exc)

    # ─────────────────────────────────────────────
    # 4) 검증된 가설 → fact 승격 (선택적)
    # ─────────────────────────────────────────────
    hypotheses_promoted = 0
    promoted_meta: dict[str, Any] = {"skipped": True}
    try:
        from hwarang_api.knowledge import hypothesis as _hy  # type: ignore

        if hasattr(_hy, "promote_validated_hypotheses"):
            r = await _hy.promote_validated_hypotheses()
            promoted_meta = (
                r if isinstance(r, dict) else {"promoted": int(r or 0)}
            )
            hypotheses_promoted = int(promoted_meta.get("promoted", 0) or 0)
        elif hasattr(_hy, "auto_accept_high_confidence"):
            n = await _hy.auto_accept_high_confidence(threshold=0.85)
            hypotheses_promoted = int(n or 0)
            promoted_meta = {
                "promoted": hypotheses_promoted,
                "via": "auto_accept_high_confidence",
            }
        else:
            promoted_meta = {"skipped": True, "reason": "no_function"}
    except ImportError:
        promoted_meta = {"skipped": True, "reason": "no_module"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("sleep: hypothesis promote failed: %s", exc)
        promoted_meta = {"error": str(exc)}

    # ─────────────────────────────────────────────
    # 5) Resolved gaps 마킹
    # ─────────────────────────────────────────────
    resolved_count = 0
    try:
        crawling_gaps = await prisma.knowledgegap.find_many(
            where={"status": "crawling"},
            take=200,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("sleep: crawling gap query failed: %s", exc)
        crawling_gaps = []

    for g in crawling_gaps:
        topic = getattr(g, "topic", "") or ""
        if not topic:
            continue
        last_seen = getattr(g, "lastSeenAt", None) or window_start
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        # 거친 매칭 — content contains topic[:20]
        try:
            count = await prisma.knowledgefact.count(
                where={
                    "createdAt": {"gte": last_seen},
                    "content": {"contains": topic[:20]},
                },
            )
        except Exception:  # noqa: BLE001
            count = 0
        if count >= _GAP_RESOLVE_FACT_THRESHOLD:
            try:
                await prisma.knowledgegap.update(
                    where={"id": g.id},
                    data={"status": "filled"},
                )
                resolved_count += 1
            except Exception as exc:  # noqa: BLE001
                logger.debug("gap resolve update failed: %s", exc)

    # ─────────────────────────────────────────────
    # 6) 적대적 자가 검증 (선택적, 미구현 모듈 안전)
    # ─────────────────────────────────────────────
    adv_result: dict[str, Any] = {"skipped": True}
    try:
        from hwarang_api.learning import adversarial_tester as _adv  # type: ignore

        if hasattr(_adv, "run_adversarial_self_play"):
            adv_result = await _adv.run_adversarial_self_play(samples=20)
        else:
            adv_result = {"skipped": True, "reason": "no_function"}
    except ImportError:
        adv_result = {"skipped": True, "reason": "no_module"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("sleep: adversarial play failed: %s", exc)
        adv_result = {"error": str(exc)}

    elapsed = (_utcnow() - started).total_seconds()
    results.update(
        {
            "new_facts": len(new_facts),
            "fact_domains": domains,
            "training_jobs_triggered": training_jobs,
            "training_per_domain": training_per_domain,
            "contradictions": contradictions,
            "archived_stale": archived,
            "hypotheses_promoted": hypotheses_promoted,
            "hypotheses_meta": promoted_meta,
            "gaps_resolved": resolved_count,
            "adversarial": adv_result,
            "elapsed_seconds": round(elapsed, 2),
        }
    )
    logger.info(
        "sleep_cycle done: new_facts=%d trained=%d archived=%d "
        "hyp_promoted=%d gaps_resolved=%d elapsed=%.1fs",
        len(new_facts),
        training_jobs,
        archived,
        hypotheses_promoted,
        resolved_count,
        elapsed,
    )
    return results


__all__ = ["sleep_cycle"]
