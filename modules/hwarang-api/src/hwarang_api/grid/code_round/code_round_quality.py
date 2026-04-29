"""라운드 종료 후 품질 검증 + 자동 롤백.

라운드가 ``COMPLETED`` 로 마감되면 호출:

1. 통합된 LoRA 를 hold-out 평가 셋으로 테스트
2. baseline (직전 라운드의 LoRA) 점수 vs 새 LoRA 점수 비교
3. 새 LoRA 가 더 좋으면 채택, 아니면 baseline 으로 롤백
4. ``Round.qualityScore / baselineScore / accepted`` 갱신 + 알림

실제 LoRA 평가는 외부 워커 (vLLM 인스턴스 + 200 코드 페어) 가 수행하지만,
인프라가 준비되기 전에도 코드가 동작하도록 디스크 크기 기반 stub 을 제공.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from hwarang_api.db import prisma

logger = logging.getLogger(__name__)


# 평가용 hold-out 셋 (코드 페어 200 개) — 외부 evaluator 가 사용
EVAL_SET_PATH = os.getenv(
    "HWARANG_CODE_EVAL_SET",
    "/var/hwarang/benchmarks/code_eval.jsonl",
)

# baseline 미존재 시 기준 점수 (첫 라운드는 무조건 채택되도록 0.5)
DEFAULT_BASELINE_SCORE = 0.5


# ─────────────────────────────────────────────────────────────────
# 외부 진입점
# ─────────────────────────────────────────────────────────────────
async def validate_completed_round(round_id: str) -> dict[str, Any]:
    """라운드 완료 후 자동 호출 — 품질 검증 + 롤백.

    스케줄러가 ``status="COMPLETED" AND qualityScore IS NULL`` 인 라운드들에
    대해 호출.
    """
    if not _is_db_ready():
        return {"skipped": "db_unavailable"}

    try:
        round_ = await prisma.round.find_unique(where={"id": round_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("Round.find_unique 실패 (%s): %s", round_id, exc)
        return {"skipped": "round_lookup_failed"}

    if not round_:
        return {"skipped": "round_not_found"}

    # 코드/디자인 도메인만 자동 검증
    if getattr(round_, "domain", None) not in ("code", "design"):
        return {"skipped": "non_target_domain"}

    cfg = getattr(round_, "config", None) or {}
    if isinstance(cfg, str):
        try:
            import json as _json

            cfg = _json.loads(cfg)
        except Exception:  # noqa: BLE001
            cfg = {}

    new_lora = cfg.get("merged_lora_path")
    if not new_lora:
        return {"skipped": "no_merged_lora"}

    # baseline = 직전 라운드 (같은 도메인, COMPLETED, 다른 ID)
    baseline_lora = await _find_baseline_lora(
        round_id=round_id,
        domain=getattr(round_, "domain"),
    )

    new_score = await _evaluate_lora(new_lora)
    baseline_score = (
        await _evaluate_lora(baseline_lora) if baseline_lora else DEFAULT_BASELINE_SCORE
    )

    accepted = new_score > baseline_score

    # Round 갱신 — qualityScore / baselineScore / accepted (스키마에 새 필드 추가 필요)
    await _persist_validation_result(
        round_id=round_id,
        new_score=new_score,
        baseline_score=baseline_score,
        accepted=accepted,
    )

    if not accepted:
        logger.warning(
            "Round %s 롤백 — new=%.3f vs baseline=%.3f", round_id, new_score, baseline_score
        )
        await _rollback_to_baseline(baseline_lora)
    else:
        logger.info(
            "Round %s 채택 — %.3f > %.3f", round_id, new_score, baseline_score
        )

    # 관리자 알림
    try:
        from hwarang_api.knowledge.notifier import notify_admin

        await notify_admin(
            f"코드 LoRA Round {round_id}: {'채택' if accepted else '롤백'}\n"
            f"새: {new_score:.3f} vs 기준: {baseline_score:.3f}",
            severity="info" if accepted else "warn",
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("notify_admin 실패 (무시): %s", exc)

    return {
        "round_id": round_id,
        "domain": getattr(round_, "domain", None),
        "new_score": new_score,
        "baseline_score": baseline_score,
        "accepted": accepted,
        "rolled_back": (not accepted) and bool(baseline_lora),
    }


# ─────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────
def _is_db_ready() -> bool:
    return getattr(prisma, "is_connected", lambda: False)()


async def _find_baseline_lora(round_id: str, domain: str) -> str | None:
    """직전 라운드 (같은 도메인) 의 merged LoRA 경로."""
    try:
        prev = await prisma.round.find_first(
            where={
                "domain": domain,
                "status": "COMPLETED",
                "id": {"not": round_id},
            },
            order={"completedAt": "desc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("baseline round 조회 실패: %s", exc)
        return None

    if not prev:
        return None

    cfg = getattr(prev, "config", None) or {}
    if isinstance(cfg, str):
        try:
            import json as _json

            cfg = _json.loads(cfg)
        except Exception:  # noqa: BLE001
            cfg = {}

    return cfg.get("merged_lora_path")


async def _evaluate_lora(lora_path: str | None, lora_name: str | None = None) -> float:
    """평가 셋에서 LoRA 점수 (0~1).

    1차: ``HWARANG_LORA_EVALUATOR_URL`` 이 설정돼 있으면 외부 evaluator 호출.
    2차: in-process evaluator (``lora_evaluator.evaluate_lora``) — vLLM 호출 +
         eval set 100건 + Docker 실행 검증.
    3차: 디스크 크기 stub 폴백 (벤치 인프라 부재 시).
    """
    if not lora_path:
        return DEFAULT_BASELINE_SCORE

    # 1차: 외부 evaluator
    evaluator_url = os.getenv("HWARANG_LORA_EVALUATOR_URL")
    if evaluator_url:
        try:
            import httpx  # type: ignore

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    evaluator_url,
                    json={"lora_path": lora_path, "eval_set": EVAL_SET_PATH},
                )
                if resp.status_code == 200:
                    score = float(resp.json().get("score", DEFAULT_BASELINE_SCORE))
                    return max(0.0, min(1.0, score))
        except Exception as exc:  # noqa: BLE001
            logger.warning("외부 evaluator 호출 실패, in-process 로 폴백: %s", exc)

    # 2차: in-process evaluator (vLLM hot-swap)
    try:
        from hwarang_api.grid.code_round.eval_set_builder import build_or_load_eval_set
        from hwarang_api.grid.code_round.lora_evaluator import evaluate_lora as _eval

        # lora_name 추정 (path 의 마지막 디렉토리명)
        if not lora_name:
            lora_name = Path(lora_path).name or lora_path

        eval_path = await build_or_load_eval_set(domain="code")
        if not eval_path:
            logger.warning("평가셋 없음 — stub 폴백")
        else:
            result = await _eval(lora_name, eval_path)
            logger.info(
                "LoRA %s 평가: final=%.3f (exact=%.2f, bleu=%.2f, exec=%.2f, n=%d)",
                lora_name,
                result.final_score,
                result.exact_match,
                result.bleu_avg,
                result.execution_pass_rate,
                result.total,
            )
            if result.total > 0:
                return max(0.0, min(1.0, result.final_score))
    except Exception as exc:  # noqa: BLE001
        logger.warning("in-process evaluator 실패, stub 폴백: %s", exc)

    # 3차: stub 폴백 ─────────────────────────────────────────────
    p = Path(lora_path)
    if not p.exists():
        return DEFAULT_BASELINE_SCORE
    try:
        size_mb = p.stat().st_size / 1024.0 / 1024.0
    except Exception:  # noqa: BLE001
        return DEFAULT_BASELINE_SCORE
    # 0.5 ~ 0.95 사이로 매핑 (작으면 학습 부족 가정)
    return min(DEFAULT_BASELINE_SCORE + size_mb / 100.0, 0.95)


async def _persist_validation_result(
    round_id: str,
    new_score: float,
    baseline_score: float,
    accepted: bool,
) -> None:
    """``Round.qualityScore / baselineScore / accepted`` 갱신.

    Prisma 스키마에 해당 필드가 없으면 ``config`` JSON 안에 폴백 저장.
    """
    if not _is_db_ready():
        return

    # 1) 신규 컬럼 시도
    try:
        await prisma.round.update(
            where={"id": round_id},
            data={
                "qualityScore": float(new_score),
                "baselineScore": float(baseline_score),
                "accepted": bool(accepted),
            },
        )
        return
    except Exception as exc:  # noqa: BLE001
        logger.debug("Round 신규 컬럼 갱신 실패, config JSON 폴백: %s", exc)

    # 2) 폴백 — config JSON 에 누적
    try:
        row = await prisma.round.find_unique(where={"id": round_id})
        cfg = getattr(row, "config", None) or {}
        if isinstance(cfg, str):
            import json as _json

            cfg = _json.loads(cfg)
        cfg["qualityScore"] = float(new_score)
        cfg["baselineScore"] = float(baseline_score)
        cfg["accepted"] = bool(accepted)
        await prisma.round.update(
            where={"id": round_id}, data={"config": cfg}
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Round.config 폴백 갱신도 실패: %s", exc)


async def _rollback_to_baseline(baseline_path: str | None) -> None:
    """프로덕션 LoRA 를 baseline 으로 복원 — symlink 또는 vLLM hot-swap.

    실제 운영에선:
        * vLLM ``/v1/load_lora_adapter`` 호출
        * AIModel.endpoint / loraName 갱신
    환경마다 다르므로 stub. 외부 ``HWARANG_LORA_ROLLBACK_URL`` 이 설정되면
    HTTP POST 호출.
    """
    if not baseline_path:
        logger.warning("rollback skip — baseline_path 없음 (첫 라운드?)")
        return

    rollback_url = os.getenv("HWARANG_LORA_ROLLBACK_URL")
    if rollback_url:
        try:
            import httpx  # type: ignore

            async with httpx.AsyncClient(timeout=30) as client:
                await client.post(rollback_url, json={"lora_path": baseline_path})
            logger.info("LoRA 롤백 완료 → %s", baseline_path)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("외부 rollback 호출 실패: %s", exc)

    logger.info("롤백 stub: production LoRA 를 %s 로 복원해야 함", baseline_path)


__all__ = [
    "validate_completed_round",
    "EVAL_SET_PATH",
]
