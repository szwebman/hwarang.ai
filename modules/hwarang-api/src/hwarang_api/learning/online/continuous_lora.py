"""Online LoRA — 사용자 피드백마다 즉시 1 step gradient.

흐름:
1. 사용자 RLHF 피드백 수신 (positive: 1, negative: -1)
2. 해당 prompt + (긍정이면 그대로 / 부정이면 사용자 수정안 또는 LLM 보정안) 페어
3. 즉시 1 step gradient (background queue)
4. N step 누적 시 LoRA 디스크 저장 + vLLM hot-reload
5. 검증 셋 정확도 떨어지면 자동 롤백

특징 vs Phase 2 batch:
- Phase 2: 1000건 → 라운드 → fed → 통합 (보수적)
- Online: 1건 → 즉시 → hot-swap (공격적, 위험 ↑)
- 둘 다 운영, online 은 평가 통과한 케이스만
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# 환경
ONLINE_LORA_DIR = os.getenv("HWARANG_ONLINE_LORA_DIR", "/var/hwarang/online_lora")
SAVE_EVERY_N_STEPS = int(os.getenv("HWARANG_ONLINE_SAVE_STEPS", "10"))
EVAL_EVERY_N_SAVES = int(os.getenv("HWARANG_ONLINE_EVAL_FREQ", "5"))
ROLLBACK_QUALITY_DROP = float(os.getenv("HWARANG_ONLINE_ROLLBACK_DROP", "0.05"))
ONLINE_ENABLED = os.getenv("HWARANG_ONLINE_LORA_ENABLED", "false").lower() in (
    "1",
    "true",
    "yes",
)


@dataclass
class GradientStep:
    feedback_id: str
    domain: str
    prompt: str
    expected_response: str  # 정답 (긍정 응답 그대로 또는 negative 의 수정안)
    weight: float           # +1 (긍정) / -1 (부정)
    user_id: Optional[str] = None
    is_correction: bool = False  # 사용자가 수정한 답인가


# 내부 큐 (메모리)
_step_queue: Optional[asyncio.Queue] = None
_worker_task: Optional[asyncio.Task] = None
_step_count = {"total": 0, "saved": 0}


async def init_worker() -> None:
    """API 시작 시 호출 — 워커 태스크 시작.

    ``HWARANG_ONLINE_LORA_ENABLED=false`` 면 큐만 만들고 워커는 무동작 모드로
    돌린다 (피드백 큐잉은 silently skip 되도록 submit_feedback 에서 가드).
    """
    global _step_queue, _worker_task
    if _worker_task and not _worker_task.done():
        return

    _step_queue = asyncio.Queue(maxsize=1000)
    try:
        Path(ONLINE_LORA_DIR).mkdir(parents=True, exist_ok=True)
    except Exception as e:  # pragma: no cover
        logger.warning(f"Online LoRA dir 생성 실패 ({ONLINE_LORA_DIR}): {e}")

    if not ONLINE_ENABLED:
        logger.info("Online LoRA 비활성 (HWARANG_ONLINE_LORA_ENABLED=false)")
        return

    _worker_task = asyncio.create_task(_gradient_worker())
    logger.info("Online LoRA worker 시작")


async def submit_feedback(
    feedback_id: str,
    domain: str,
    prompt: str,
    response: str,
    rating: int,                     # -1 / 0 / +1
    correction: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict:
    """RLHF 피드백 → 학습 큐에 push."""
    if not ONLINE_ENABLED:
        return {"queued": False, "reason": "online_disabled"}

    if rating == 0:
        return {"queued": False, "reason": "neutral"}

    if _step_queue is None:
        await init_worker()
        if _step_queue is None:
            return {"queued": False, "reason": "no_queue"}

    if rating > 0:
        # 긍정 — response 가 정답
        step = GradientStep(
            feedback_id=feedback_id,
            domain=domain,
            prompt=prompt,
            expected_response=response,
            weight=1.0,
            user_id=user_id,
            is_correction=False,
        )
    else:
        # 부정 — correction 있으면 그게 정답, 없으면 학습 안 함
        if not correction:
            return {"queued": False, "reason": "negative_no_correction"}
        step = GradientStep(
            feedback_id=feedback_id,
            domain=domain,
            prompt=prompt,
            expected_response=correction,
            weight=2.0,  # 수정안은 가중치 2배
            user_id=user_id,
            is_correction=True,
        )

    try:
        _step_queue.put_nowait(step)
        return {"queued": True, "queue_size": _step_queue.qsize()}
    except asyncio.QueueFull:
        return {"queued": False, "reason": "queue_full"}


async def _gradient_worker() -> None:
    """백그라운드 워커 — 큐에서 step 꺼내 학습."""
    assert _step_queue is not None
    while True:
        try:
            step = await _step_queue.get()
        except asyncio.CancelledError:
            break

        try:
            await _apply_gradient_step(step)
            _step_count["total"] += 1

            if _step_count["total"] % SAVE_EVERY_N_STEPS == 0:
                await _save_checkpoint()
                _step_count["saved"] += 1

                if _step_count["saved"] % EVAL_EVERY_N_SAVES == 0:
                    await _evaluate_and_maybe_rollback()
        except Exception as e:  # pragma: no cover
            logger.exception(f"step 적용 실패: {e}")


async def _apply_gradient_step(step: GradientStep) -> None:
    """torch + peft 로 1 step 학습.

    실제 GPU 워크. 메인 vLLM 과 메모리 공유 시 동시 실행 어려움.
    별도 GPU 또는 시간 분리 필요.

    여기선 prepared sample 만 디스크 jsonl 에 누적.
    실제 학습은 ``actual_trainer.py`` 가 별도 프로세스로 처리.
    """
    if not _torch_available():
        logger.debug("torch 미설치 — gradient step skip")
        return

    sample_path = Path(ONLINE_LORA_DIR) / "pending_samples.jsonl"
    try:
        with open(sample_path, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "domain": step.domain,
                        "prompt": step.prompt,
                        "completion": step.expected_response,
                        "weight": step.weight,
                        "is_correction": step.is_correction,
                        "feedback_id": step.feedback_id,
                        "ts": time.time(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception as e:  # pragma: no cover
        logger.warning(f"pending_samples 기록 실패: {e}")


async def _save_checkpoint() -> None:
    """누적 sample → 별도 학습 프로세스에 신호."""
    try:
        trigger_path = Path(ONLINE_LORA_DIR) / "trigger.flag"
        trigger_path.touch()
        logger.info(f"Online LoRA checkpoint 트리거 — {_step_count['total']} steps")
    except Exception as e:  # pragma: no cover
        logger.warning(f"trigger.flag 작성 실패: {e}")


async def _evaluate_and_maybe_rollback() -> None:
    """평가 셋 돌려 baseline 보다 떨어지면 롤백."""
    try:
        from hwarang_api.grid.code_round.code_round_quality import _evaluate_lora
    except Exception:  # pragma: no cover
        logger.debug("code_round_quality._evaluate_lora 미사용 — eval skip")
        return

    current_path = Path(ONLINE_LORA_DIR) / "current"
    baseline_path = Path(ONLINE_LORA_DIR) / "baseline"

    if not current_path.exists() or not baseline_path.exists():
        return

    try:
        current_score = await _evaluate_lora(str(current_path))
        baseline_score = await _evaluate_lora(str(baseline_path))
    except Exception as e:  # pragma: no cover
        logger.warning(f"evaluate_lora 실패: {e}")
        return

    drop = baseline_score - current_score

    if drop > ROLLBACK_QUALITY_DROP:
        logger.warning(
            f"Online LoRA 롤백 — current={current_score:.3f} baseline={baseline_score:.3f} drop={drop:.3f}"
        )
        # 롤백 — current → baseline
        try:
            import shutil

            shutil.rmtree(current_path)
            shutil.copytree(baseline_path, current_path)
        except Exception as e:  # pragma: no cover
            logger.warning(f"롤백 파일 복사 실패: {e}")

        # 알림
        try:
            from hwarang_api.knowledge.notifier import notify_admin

            await notify_admin(
                f"Online LoRA 자동 롤백\n"
                f"current {current_score:.3f} < baseline {baseline_score:.3f}\n"
                f"drop {drop:.3f}",
                severity="warn",
            )
        except Exception:  # pragma: no cover
            pass


def _torch_available() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def queue_status() -> dict:
    return {
        "enabled": ONLINE_ENABLED,
        "queue_size": _step_queue.qsize() if _step_queue else 0,
        "total_steps": _step_count["total"],
        "saved_checkpoints": _step_count["saved"],
        "save_every_n_steps": SAVE_EVERY_N_STEPS,
        "eval_every_n_saves": EVAL_EVERY_N_SAVES,
        "rollback_quality_drop": ROLLBACK_QUALITY_DROP,
        "lora_dir": ONLINE_LORA_DIR,
    }


__all__ = [
    "GradientStep",
    "init_worker",
    "submit_feedback",
    "queue_status",
]
