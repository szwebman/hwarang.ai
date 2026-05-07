"""HSEE Phase 2 — A/B Test 기반 자동 롤백 모니터.

주간 학습으로 새로 배포된 LoRA (treatment) 가 기존 LoRA (control) 대비 암묵
부정 신호 (isSatisfied=False / followupMsg / editDistance) 가 일정 비율 이상
높으면 자동으로 vLLM ``/v1/unload_lora_adapter`` 호출 + ABTestManager 비활성화.

원칙:
* 명시 피드백 (👍/👎) 사용 X — 암묵 신호 (isSatisfied / followup / editDistance) 만.
* 24h / 48h / 7d 3 단계 게이트.
* 슬랙/이메일 알림 보류 (인프라 부재). 로그 + ``notify_admin`` 로 갈음.

사용:
    from hwarang_api.learning.auto_rollback import monitor_and_rollback
    res = await monitor_and_rollback(experiment_id="weekly_lora_v8")
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# 환경변수 -----------------------------------------------------------------
VLLM_URL = os.getenv("HWARANG_VLLM_URL", "http://localhost:8001")

# treatment 의 부정 신호가 control 대비 이 비율 (배수) 이상이면 롤백.
# 1.20 = "20% 더 많이 발생" → 즉시 롤백.
NEGATIVE_RATIO_TRIGGER = float(os.getenv("HSEE_ROLLBACK_NEG_RATIO", "1.20"))

# 각 게이트별 최소 표본 수 — 표본 부족 시 결정 보류 (PASS).
MIN_SAMPLES_24H = int(os.getenv("HSEE_ROLLBACK_MIN_24H", "50"))
MIN_SAMPLES_48H = int(os.getenv("HSEE_ROLLBACK_MIN_48H", "100"))
MIN_SAMPLES_7D = int(os.getenv("HSEE_ROLLBACK_MIN_7D", "300"))

# A/B 실험 ID 기본값 (주간 학습이 만들 때 동일 ID 사용).
DEFAULT_EXPERIMENT_ID = "weekly_lora_ab"

# vLLM 에 등록된 LoRA 이름 (control / treatment).
DEFAULT_CONTROL_NAME = os.getenv("HWARANG_LORA_CONTROL", "hwarang-v7")
DEFAULT_TREATMENT_NAME = os.getenv("HWARANG_LORA_TREATMENT", "hwarang-v8")


# ─────────────────────────────────────────────────────────────────
# 데이터 구조
# ─────────────────────────────────────────────────────────────────
@dataclass
class GateResult:
    """단일 시간 윈도우 (24h/48h/7d) 평가 결과."""

    window_label: str
    window_hours: int
    control_total: int = 0
    control_negative: int = 0
    treatment_total: int = 0
    treatment_negative: int = 0
    control_neg_rate: float = 0.0
    treatment_neg_rate: float = 0.0
    ratio: float = 0.0  # treatment / control
    decision: str = "pending"  # pass | rollback | insufficient_samples
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "window": self.window_label,
            "hours": self.window_hours,
            "control": {
                "total": self.control_total,
                "negative": self.control_negative,
                "rate": round(self.control_neg_rate, 4),
            },
            "treatment": {
                "total": self.treatment_total,
                "negative": self.treatment_negative,
                "rate": round(self.treatment_neg_rate, 4),
            },
            "ratio": round(self.ratio, 4),
            "decision": self.decision,
            "reason": self.reason,
        }


@dataclass
class RollbackReport:
    """``monitor_and_rollback`` 반환 페이로드."""

    experiment_id: str
    control_lora: str
    treatment_lora: str
    gates: list[GateResult] = field(default_factory=list)
    rolled_back: bool = False
    rollback_reason: str = ""
    vllm_response: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "control": self.control_lora,
            "treatment": self.treatment_lora,
            "rolled_back": self.rolled_back,
            "rollback_reason": self.rollback_reason,
            "gates": [g.to_dict() for g in self.gates],
            "vllm_response": self.vllm_response,
        }


# ─────────────────────────────────────────────────────────────────
# 메인 진입점
# ─────────────────────────────────────────────────────────────────
async def monitor_and_rollback(
    experiment_id: str = DEFAULT_EXPERIMENT_ID,
    control_lora: str = DEFAULT_CONTROL_NAME,
    treatment_lora: str = DEFAULT_TREATMENT_NAME,
    *,
    negative_ratio_trigger: float = NEGATIVE_RATIO_TRIGGER,
) -> dict[str, Any]:
    """A/B 실험 결과 평가 + 임계 초과 시 vLLM unload.

    1. 24h / 48h / 7d 3 게이트 모두 평가 (실패해도 다음 게이트 평가 계속).
    2. 임의 게이트가 ``rollback`` 결정이면 즉시 롤백 (later 게이트 무시).
    3. 모두 ``pass`` / ``insufficient_samples`` 면 유지.

    treatment 만 unload — control 은 그대로 유지하여 fallback 보장.
    """
    report = RollbackReport(
        experiment_id=experiment_id,
        control_lora=control_lora,
        treatment_lora=treatment_lora,
    )

    for label, hours, min_samples in [
        ("24h", 24, MIN_SAMPLES_24H),
        ("48h", 48, MIN_SAMPLES_48H),
        ("7d", 24 * 7, MIN_SAMPLES_7D),
    ]:
        gate = await _evaluate_gate(
            window_label=label,
            window_hours=hours,
            min_samples=min_samples,
            control_lora=control_lora,
            treatment_lora=treatment_lora,
            negative_ratio_trigger=negative_ratio_trigger,
        )
        report.gates.append(gate)

        if gate.decision == "rollback" and not report.rolled_back:
            # 즉시 롤백 — 이후 게이트도 평가는 하지만 unload 는 한 번만
            report.rollback_reason = (
                f"[{label}] treatment_neg={gate.treatment_neg_rate:.3f} / "
                f"control_neg={gate.control_neg_rate:.3f} ratio={gate.ratio:.2f} "
                f">= trigger({negative_ratio_trigger:.2f})"
            )

    if report.rollback_reason:
        report.rolled_back = True
        report.vllm_response = await _unload_treatment(treatment_lora)
        await _disable_experiment(experiment_id)
        await _notify_rollback(report)
    else:
        logger.info(
            "auto_rollback %s: pass — gates=%s",
            experiment_id,
            [g.decision for g in report.gates],
        )

    return report.to_dict()


# ─────────────────────────────────────────────────────────────────
# 게이트 평가 (DB 집계)
# ─────────────────────────────────────────────────────────────────
async def _evaluate_gate(
    *,
    window_label: str,
    window_hours: int,
    min_samples: int,
    control_lora: str,
    treatment_lora: str,
    negative_ratio_trigger: float,
) -> GateResult:
    """단일 시간 윈도우의 control vs treatment 부정 신호 비교."""
    gate = GateResult(window_label=window_label, window_hours=window_hours)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    try:
        from hwarang_api.db import prisma  # type: ignore
    except Exception as exc:  # pragma: no cover
        gate.decision = "insufficient_samples"
        gate.reason = f"prisma_unavailable: {exc}"
        return gate

    if not getattr(prisma, "is_connected", lambda: False)():
        gate.decision = "insufficient_samples"
        gate.reason = "db_disconnected"
        return gate

    # control / treatment 부정 신호 카운트.
    # 부정 신호 = isSatisfied=False 또는 editDistance>=0.5 또는 followupMsg 가
    # 부정 단어 (불만/오류/잘못/안돼/wrong/error 등) 포함 — 단순화를 위해
    # isSatisfied=False 만 우선 카운트 (satisfaction_scorer 가 이미 종합).
    async def _count(lora_name: str, only_negative: bool) -> int:
        where: dict[str, Any] = {
            "loraName": lora_name,
            "createdAt": {"gt": cutoff},
        }
        if only_negative:
            where["isSatisfied"] = False
        try:
            return await prisma.rlhffeedback.count(where=where)
        except Exception as exc:  # noqa: BLE001
            logger.debug("rlhffeedback.count 실패 (%s): %s", lora_name, exc)
            return 0

    gate.control_total = await _count(control_lora, only_negative=False)
    gate.control_negative = await _count(control_lora, only_negative=True)
    gate.treatment_total = await _count(treatment_lora, only_negative=False)
    gate.treatment_negative = await _count(treatment_lora, only_negative=True)

    # 표본 부족 시 PASS (보수적 — 실제론 결정 보류).
    if (
        gate.control_total < min_samples
        or gate.treatment_total < min_samples
    ):
        gate.decision = "insufficient_samples"
        gate.reason = (
            f"control={gate.control_total} treatment={gate.treatment_total} "
            f"min={min_samples}"
        )
        return gate

    gate.control_neg_rate = (
        gate.control_negative / gate.control_total if gate.control_total else 0.0
    )
    gate.treatment_neg_rate = (
        gate.treatment_negative / gate.treatment_total
        if gate.treatment_total
        else 0.0
    )

    # control 부정율이 0 이면 0 으로 나누기 회피 — treatment 부정율이 0.05 이상이면
    # 무조건 rollback (절대 임계).
    if gate.control_neg_rate <= 1e-6:
        if gate.treatment_neg_rate >= 0.05:
            gate.ratio = float("inf")
            gate.decision = "rollback"
            gate.reason = "control_neg≈0 but treatment_neg≥5%"
        else:
            gate.ratio = 1.0
            gate.decision = "pass"
        return gate

    gate.ratio = gate.treatment_neg_rate / gate.control_neg_rate
    if gate.ratio >= negative_ratio_trigger:
        gate.decision = "rollback"
        gate.reason = (
            f"ratio {gate.ratio:.2f} >= trigger {negative_ratio_trigger:.2f}"
        )
    else:
        gate.decision = "pass"

    return gate


# ─────────────────────────────────────────────────────────────────
# 액션 (vLLM unload / 실험 비활성화 / 알림)
# ─────────────────────────────────────────────────────────────────
async def _unload_treatment(treatment_lora: str) -> dict[str, Any]:
    """vLLM 의 LoRA hot-unload 호출. 실패해도 예외 던지지 않음."""
    try:
        import httpx  # type: ignore
    except ImportError:  # pragma: no cover
        logger.warning("httpx 미설치 — vLLM unload skip")
        return {"ok": False, "reason": "httpx_missing"}

    url = f"{VLLM_URL.rstrip('/')}/v1/unload_lora_adapter"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json={"lora_name": treatment_lora})
        logger.warning(
            "auto_rollback unloaded %s — status=%d body=%s",
            treatment_lora,
            resp.status_code,
            resp.text[:200],
        )
        return {"ok": resp.status_code < 400, "status": resp.status_code}
    except Exception as exc:  # noqa: BLE001
        logger.warning("vLLM unload 실패: %s", exc)
        return {"ok": False, "reason": str(exc)}


async def _disable_experiment(experiment_id: str) -> None:
    """ABTestManager 의 실험을 비활성화 — 새 요청부터 control 만 라우팅."""
    try:
        from hwarang_api.middleware.patterns.ab_testing import (
            ABTestManager,  # type: ignore
        )
        from hwarang_api.routers import chat as chat_router  # type: ignore

        mgr: ABTestManager | None = getattr(chat_router, "ab_test_manager", None)
        if mgr is None:
            logger.debug("ab_test_manager 없음 — disable skip")
            return
        exp = mgr._experiments.get(experiment_id)  # noqa: SLF001
        if exp is not None:
            exp.active = False
            logger.warning("Experiment %s deactivated by auto_rollback", experiment_id)
    except Exception as exc:  # noqa: BLE001
        logger.debug("실험 비활성화 실패 (무시): %s", exc)


async def _notify_rollback(report: RollbackReport) -> None:
    """관리자 알림 (Slack/Email 인프라 보류 — notify_admin 만)."""
    try:
        from hwarang_api.knowledge.notifier import notify_admin  # type: ignore

        msg = (
            f"[HSEE Phase 2] auto_rollback 실행\n"
            f"experiment: {report.experiment_id}\n"
            f"treatment: {report.treatment_lora} → unloaded\n"
            f"reason: {report.rollback_reason}"
        )
        await notify_admin(msg, severity="warn")
    except Exception as exc:  # noqa: BLE001
        logger.debug("notify_admin 실패 (무시): %s", exc)


__all__ = [
    "monitor_and_rollback",
    "RollbackReport",
    "GateResult",
    "NEGATIVE_RATIO_TRIGGER",
    "DEFAULT_EXPERIMENT_ID",
]
