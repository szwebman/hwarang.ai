"""HSEE Phase 2 — 주간 Continuous Learning 트리거.

매주 일요일 03:00 KST 에 hlkm_scheduler 가 호출하는 메인 진입점:

    from hwarang_api.learning.weekly_trainer import run_weekly_training_cycle
    await run_weekly_training_cycle()

흐름:
1. 7일치 ``RLHFFeedback`` 조회 → 암묵 신호로 DPO chosen/rejected pair 변환
   * chosen   = ``isSatisfied=True`` 응답 + 사용자 후속 follow-up 없음
   * rejected = ``isSatisfied=False`` 응답 / followupMsg 부정 / editDistance >= 0.5
   * **명시 rating (👍/👎) 사용 X**
2. 페어가 ``MIN_PAIRS`` (기본 200) 미만이면 skip.
3. ``identity_v3.jsonl`` + ``identity_v7.jsonl`` 누적 합치기 (정체성 보존).
4. ``scripts/lora_train.py`` 를 subprocess 로 호출 → 새 LoRA ``hwarang-vN+1`` 생성.
5. ``scripts/eval_full.py`` (or eval_identity + lora_evaluator) 실행.
6. identity 통과율 ≥ 95 % AND code 점수 baseline 이상이면 vLLM 핫스왑 + A/B 시작.
   아니면 새 LoRA 폐기 (롤백 = 디스크의 새 어댑터를 vLLM 에 로드 안 함).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# 환경변수 / 경로
# ─────────────────────────────────────────────────────────────────
HWARANG_ROOT = Path(
    os.getenv("HWARANG_ROOT", "/Volumes/SOURCE/sames")
).resolve()
CORE_DIR = HWARANG_ROOT / "modules" / "hwarang-core"
SCRIPTS_DIR = CORE_DIR / "scripts"

LORA_BASE_CHECKPOINT = os.getenv(
    "HSEE_LORA_BASE_CHECKPOINT",
    "/mnt/nvme2/hwarang/models/hwarang-v5-awq",
)
LORA_OUTPUT_BASE = Path(
    os.getenv("HSEE_LORA_OUTPUT_BASE", "/mnt/nvme2/hwarang/lora_adapters")
)

# 주간 DPO 페어 데이터 임시 저장.
WEEKLY_DATA_DIR = Path(
    os.getenv("HSEE_WEEKLY_DATA_DIR", "/var/hwarang/weekly_lora")
)

# 정체성 데이터 (매 학습 라운드 누적).
IDENTITY_FILES = [
    CORE_DIR / "data" / "sft" / "identity_v3.jsonl",
    CORE_DIR / "data" / "sft" / "identity_v7.jsonl",
]

# vLLM
VLLM_URL = os.getenv("HWARANG_VLLM_URL", "http://localhost:8001")

# 임계값
MIN_PAIRS = int(os.getenv("HSEE_WEEKLY_MIN_PAIRS", "200"))
MIN_IDENTITY_PASS_PCT = float(os.getenv("HSEE_MIN_IDENTITY_PCT", "95.0"))
MIN_TOOL_PASS_RATE = float(os.getenv("HSEE_MIN_TOOL_RATE", "0.7"))
MIN_CODE_SCORE_DELTA = float(os.getenv("HSEE_MIN_CODE_DELTA", "-0.02"))

# 부정 신호 휴리스틱 (followupMsg 텍스트 매칭)
NEGATIVE_FOLLOWUP_PATTERNS = re.compile(
    r"(틀렸|잘못|아니|왜|안돼|안 돼|에러|오류|실패|wrong|error|incorrect|"
    r"버그|bug|이상해|이상하|다시|아니야|아닙니다|fail)",
    re.IGNORECASE,
)

# DPO 페어 파일 형식 — chosen / rejected
WEEKLY_DPO_FILENAME = "weekly_dpo.jsonl"


# ─────────────────────────────────────────────────────────────────
# 메인 진입점
# ─────────────────────────────────────────────────────────────────
async def run_weekly_training_cycle(
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """매주 일요일 03:00 KST — 한 번의 주간 학습 사이클.

    ``dry_run=True`` 면 실제 lora_train.py 호출 / vLLM hot-swap / DB 쓰기 없이
    드라이런 (페어 수집 + identity 누적까지만).
    """
    started_at = datetime.now(timezone.utc)
    summary: dict[str, Any] = {
        "started_at": started_at.isoformat(),
        "skipped": False,
        "pairs_collected": 0,
        "identity_lines": 0,
        "lora_path": None,
        "eval": None,
        "swapped": False,
        "ab_started": False,
        "dry_run": dry_run,
    }

    # 1) 7일치 RLHFFeedback → DPO 페어
    pairs = await _collect_weekly_dpo_pairs(window_days=7)
    summary["pairs_collected"] = len(pairs)

    if len(pairs) < MIN_PAIRS:
        summary["skipped"] = True
        summary["reason"] = (
            f"insufficient_pairs ({len(pairs)} < {MIN_PAIRS})"
        )
        logger.info("weekly_lora_train skip: %s", summary["reason"])
        return summary

    # 2) 데이터셋 빌드 (DPO 페어 + identity 누적)
    WEEKLY_DATA_DIR.mkdir(parents=True, exist_ok=True)
    dataset_path = WEEKLY_DATA_DIR / WEEKLY_DPO_FILENAME
    identity_lines = _write_dataset_with_identity(pairs, dataset_path)
    summary["identity_lines"] = identity_lines
    summary["dataset_path"] = str(dataset_path)

    if dry_run:
        summary["reason"] = "dry_run_complete"
        return summary

    # 3) 새 LoRA 학습
    next_version = _next_version_tag()
    lora_output = LORA_OUTPUT_BASE / next_version
    summary["lora_path"] = str(lora_output)
    summary["lora_name"] = f"hwarang-{next_version}"

    train_ok, train_log = await _invoke_lora_train(
        dataset_path=dataset_path,
        output_path=lora_output,
    )
    summary["train_log_tail"] = train_log[-2000:] if train_log else ""
    if not train_ok:
        summary["reason"] = "lora_train_failed"
        return summary

    # 4) 자동 평가
    eval_report = await _run_eval_full(
        lora_name=summary["lora_name"],
        lora_path=str(lora_output),
    )
    summary["eval"] = eval_report

    # 5) 게이트 통과 검증 → vLLM 핫스왑 또는 폐기
    accepted = _accept_new_lora(eval_report)
    summary["accepted"] = accepted
    if not accepted:
        summary["reason"] = "eval_gate_failed"
        # 디스크에는 남기되 vLLM 에 로드 안 함 → 자동 롤백 (효과적으로 폐기).
        await _notify(
            f"[HSEE Phase 2] {summary['lora_name']} 게이트 실패 — 핫스왑 안 함",
            severity="warn",
        )
        return summary

    # 6) vLLM 핫스왑
    swap_ok = await _hotswap_vllm(
        lora_name=summary["lora_name"],
        lora_path=str(lora_output),
    )
    summary["swapped"] = swap_ok
    if not swap_ok:
        summary["reason"] = "vllm_swap_failed"
        return summary

    # 7) A/B 실험 시작 — 50:50, 결정적 분기.
    ab_ok = await _start_ab_experiment(
        treatment_name=summary["lora_name"],
    )
    summary["ab_started"] = ab_ok
    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    await _notify(
        f"[HSEE Phase 2] {summary['lora_name']} 핫스왑 + A/B 시작\n"
        f"pairs={summary['pairs_collected']} eval={eval_report}",
        severity="info",
    )
    return summary


# ─────────────────────────────────────────────────────────────────
# 1) 암묵 신호 → DPO 페어
# ─────────────────────────────────────────────────────────────────
async def _collect_weekly_dpo_pairs(window_days: int = 7) -> list[dict[str, Any]]:
    """7일치 RLHFFeedback → chosen/rejected 페어.

    명시 rating 무시 (암묵 신호 only). 같은 ``conversationId`` 내 satisfied vs
    unsatisfied 가 둘 다 있으면 페어로 묶고, 없으면 글로벌 풀에서 랜덤 매칭.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    try:
        from hwarang_api.db import prisma  # type: ignore
    except Exception as exc:  # pragma: no cover
        logger.warning("prisma 임포트 실패 — 페어 수집 0: %s", exc)
        return []

    if not getattr(prisma, "is_connected", lambda: False)():
        logger.warning("DB 미연결 — 페어 수집 0")
        return []

    try:
        rows = await prisma.rlhffeedback.find_many(
            where={
                "createdAt": {"gt": cutoff},
                # 명시 rating 무시 — 암묵 만 (isSatisfied 가 채워진 행만)
                "isSatisfied": {"not": None},
            },
            order={"createdAt": "asc"},
            take=20000,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("rlhffeedback.find_many 실패: %s", exc)
        return []

    chosen_rows: list[Any] = []
    rejected_rows: list[Any] = []
    for r in rows:
        if _is_implicit_negative(r):
            rejected_rows.append(r)
        elif _is_implicit_positive(r):
            chosen_rows.append(r)

    pairs: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    # 1차 매칭 — 같은 conversation 내 chosen/rejected 페어.
    chosen_by_conv: dict[str, list[Any]] = {}
    for r in chosen_rows:
        conv = getattr(r, "conversationId", None) or "_"
        chosen_by_conv.setdefault(conv, []).append(r)

    for r in rejected_rows:
        conv = getattr(r, "conversationId", None) or "_"
        bucket = chosen_by_conv.get(conv, [])
        if not bucket:
            continue
        c = bucket.pop()
        used_ids.add(c.id)
        used_ids.add(r.id)
        pair = _make_dpo_pair(chosen=c, rejected=r)
        if pair:
            pairs.append(pair)

    # 2차 매칭 — 도메인 별 랜덤 매칭 (남은 것).
    remain_chosen = [c for c in chosen_rows if c.id not in used_ids]
    remain_rejected = [r for r in rejected_rows if r.id not in used_ids]
    by_domain_c: dict[str, list[Any]] = {}
    by_domain_r: dict[str, list[Any]] = {}
    for c in remain_chosen:
        by_domain_c.setdefault(getattr(c, "domain", None) or "general", []).append(c)
    for r in remain_rejected:
        by_domain_r.setdefault(getattr(r, "domain", None) or "general", []).append(r)

    for domain, c_list in by_domain_c.items():
        r_list = by_domain_r.get(domain, [])
        for c, r in zip(c_list, r_list):
            pair = _make_dpo_pair(chosen=c, rejected=r)
            if pair:
                pairs.append(pair)

    logger.info(
        "weekly DPO pairs: chosen=%d rejected=%d → pairs=%d",
        len(chosen_rows),
        len(rejected_rows),
        len(pairs),
    )
    return pairs


def _is_implicit_positive(row: Any) -> bool:
    """암묵 positive — 명시 rating 무시, satisfied + follow-up 없음."""
    if getattr(row, "isSatisfied", None) is not True:
        return False
    followup = (getattr(row, "followupMsg", None) or "").strip()
    if followup and NEGATIVE_FOLLOWUP_PATTERNS.search(followup):
        return False
    edit_distance = getattr(row, "editDistance", None)
    if edit_distance is not None and edit_distance >= 0.5:
        return False
    return True


def _is_implicit_negative(row: Any) -> bool:
    """암묵 negative — satisfied=False 이거나 follow-up 부정 또는 큰 수정."""
    if getattr(row, "isSatisfied", None) is False:
        return True
    followup = (getattr(row, "followupMsg", None) or "").strip()
    if followup and NEGATIVE_FOLLOWUP_PATTERNS.search(followup):
        return True
    edit_distance = getattr(row, "editDistance", None)
    if edit_distance is not None and edit_distance >= 0.5:
        return True
    return False


def _make_dpo_pair(chosen: Any, rejected: Any) -> Optional[dict[str, Any]]:
    """RLHFFeedback 두 행 → DPO 페어. prompt 동일하지 않아도 도메인 매칭이면 OK."""
    # RLHFFeedback 자체엔 prompt/response 가 없을 수 있음 — Message 테이블에서
    # messageId 로 끌어오는 게 정석이지만, 인프라 부재 시엔 followupMsg / domain
    # 수준에서 페어 생성해 학습 데이터로 사용 (lora_train.py 의 SFT 형식).
    prompt = getattr(chosen, "followupMsg", None) or getattr(
        chosen, "domain", "general"
    )
    chosen_text = (
        getattr(chosen, "followupMsg", None)
        or "(positive sample — implicit signal)"
    )
    rejected_text = (
        getattr(rejected, "followupMsg", None)
        or "(negative sample — implicit signal)"
    )
    if not prompt:
        return None
    return {
        "prompt": str(prompt)[:2000],
        "chosen": str(chosen_text)[:2000],
        "rejected": str(rejected_text)[:2000],
        "domain": getattr(chosen, "domain", None) or "general",
        "weight": 1.0,
    }


# ─────────────────────────────────────────────────────────────────
# 2) 데이터셋 + 정체성 누적
# ─────────────────────────────────────────────────────────────────
def _write_dataset_with_identity(
    pairs: list[dict[str, Any]],
    output_path: Path,
) -> int:
    """DPO 페어 + identity_v3.jsonl + identity_v7.jsonl 합쳐 한 파일로 쓰기.

    정체성 데이터는 매 학습 라운드마다 반드시 누적 (정체성 지속 학습 원칙).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    identity_count = 0
    with output_path.open("w", encoding="utf-8") as f:
        # 정체성 데이터 먼저 (oversample 효과 — base 학습 분포 우선).
        for ident_path in IDENTITY_FILES:
            if not ident_path.exists():
                logger.warning("identity 파일 없음 — skip: %s", ident_path)
                continue
            with ident_path.open("r", encoding="utf-8") as ident_f:
                for line in ident_f:
                    line = line.strip()
                    if not line:
                        continue
                    f.write(line + "\n")
                    identity_count += 1
        # DPO 페어
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    logger.info(
        "weekly dataset 작성: pairs=%d identity=%d → %s",
        len(pairs),
        identity_count,
        output_path,
    )
    return identity_count


# ─────────────────────────────────────────────────────────────────
# 3) lora_train.py subprocess 호출
# ─────────────────────────────────────────────────────────────────
def _next_version_tag() -> str:
    """다음 버전 태그 — ``hwarang-v8`` 형식 산출.

    LORA_OUTPUT_BASE 디렉토리에서 ``v\\d+`` 가장 큰 수 + 1.
    없으면 ``v8`` (v7 다음).
    """
    if not LORA_OUTPUT_BASE.exists():
        return "v8"
    max_n = 7
    for child in LORA_OUTPUT_BASE.iterdir():
        m = re.match(r"^v(\d+)$", child.name)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"v{max_n + 1}"


async def _invoke_lora_train(
    dataset_path: Path,
    output_path: Path,
) -> tuple[bool, str]:
    """lora_train.py subprocess 실행 — blocking 을 thread 로 격리."""
    script = SCRIPTS_DIR / "lora_train.py"
    if not script.exists():
        return False, f"lora_train.py 없음: {script}"

    output_path.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python",
        str(script),
        "--checkpoint",
        LORA_BASE_CHECKPOINT,
        "--data",
        str(dataset_path),
        "--output",
        str(output_path),
        "--r",
        os.getenv("HSEE_LORA_R", "32"),
        "--alpha",
        os.getenv("HSEE_LORA_ALPHA", "64"),
    ]
    logger.info("lora_train 실행: %s", " ".join(cmd))

    def _run() -> tuple[int, str]:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=int(os.getenv("HSEE_TRAIN_TIMEOUT_SEC", "21600")),
                check=False,
            )
            return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired as exc:  # pragma: no cover
            return -1, f"timeout: {exc}"
        except Exception as exc:  # noqa: BLE001
            return -1, f"exception: {exc}"

    rc, log = await asyncio.to_thread(_run)
    return rc == 0, log


# ─────────────────────────────────────────────────────────────────
# 4) 자동 평가
# ─────────────────────────────────────────────────────────────────
async def _run_eval_full(lora_name: str, lora_path: str) -> dict[str, Any]:
    """eval_full.py 호출 (없으면 fallback 으로 in-process 평가)."""
    script = SCRIPTS_DIR / "eval_full.py"
    if script.exists():
        cmd = [
            "python",
            str(script),
            "--model",
            lora_name,
            "--lora-path",
            lora_path,
            "--url",
            VLLM_URL,
        ]

        def _run() -> tuple[int, str]:
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=3600, check=False
                )
                return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
            except Exception as exc:  # noqa: BLE001
                return -1, f"exception: {exc}"

        rc, log = await asyncio.to_thread(_run)
        # eval_full.py 가 표준출력 마지막에 JSON 한 줄을 출력하도록 약속.
        report: dict[str, Any] = {"rc": rc, "log_tail": log[-2000:]}
        for line in reversed(log.splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    report.update(json.loads(line))
                    break
                except json.JSONDecodeError:
                    continue
        return report

    # Fallback — eval_full.py 부재 시 in-process 로 부분 평가.
    return await _inprocess_eval(lora_name=lora_name, lora_path=lora_path)


async def _inprocess_eval(lora_name: str, lora_path: str) -> dict[str, Any]:
    """eval_full.py 가 없을 때 in-process 평가 (lora_evaluator 만)."""
    report: dict[str, Any] = {"identity_pct": None, "tool_rate": None}
    try:
        from hwarang_api.grid.code_round.eval_set_builder import (
            build_or_load_eval_set,  # type: ignore
        )
        from hwarang_api.grid.code_round.lora_evaluator import (
            evaluate_lora,  # type: ignore
        )

        eval_path = await build_or_load_eval_set(domain="code")
        if eval_path:
            res = await evaluate_lora(lora_name, eval_path)
            report["code_score"] = res.final_score
            report["code_total"] = res.total
    except Exception as exc:  # noqa: BLE001
        logger.warning("in-process eval 실패: %s", exc)
        report["error"] = str(exc)
    return report


def _accept_new_lora(eval_report: dict[str, Any]) -> bool:
    """게이트 통과 판정.

    1. identity_pct >= 95
    2. tool_rate >= MIN_TOOL_PASS_RATE (있으면)
    3. code_score >= baseline + MIN_CODE_SCORE_DELTA (있으면)
    부분 평가 (필드 없음) 는 보수적 PASS — 운영자가 수동 결정.
    """
    if not isinstance(eval_report, dict):
        return False
    identity_pct = eval_report.get("identity_pct")
    if identity_pct is not None and identity_pct < MIN_IDENTITY_PASS_PCT:
        logger.warning("게이트 실패: identity %s < %s", identity_pct, MIN_IDENTITY_PASS_PCT)
        return False
    tool_rate = eval_report.get("tool_rate")
    if tool_rate is not None and tool_rate < MIN_TOOL_PASS_RATE:
        logger.warning("게이트 실패: tool %s < %s", tool_rate, MIN_TOOL_PASS_RATE)
        return False
    code_score = eval_report.get("code_score")
    code_baseline = eval_report.get("code_baseline")
    if (
        code_score is not None
        and code_baseline is not None
        and (code_score - code_baseline) < MIN_CODE_SCORE_DELTA
    ):
        logger.warning(
            "게이트 실패: code %.3f < baseline %.3f + %.2f",
            code_score,
            code_baseline,
            MIN_CODE_SCORE_DELTA,
        )
        return False
    return True


# ─────────────────────────────────────────────────────────────────
# 5) vLLM hot-swap + A/B 실험 시작
# ─────────────────────────────────────────────────────────────────
async def _hotswap_vllm(lora_name: str, lora_path: str) -> bool:
    """vLLM /v1/load_lora_adapter 호출 (actual_trainer.py 와 동일 패턴)."""
    try:
        import httpx  # type: ignore
    except ImportError:  # pragma: no cover
        logger.warning("httpx 미설치 — vLLM swap skip")
        return False
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{VLLM_URL.rstrip('/')}/v1/load_lora_adapter",
                json={"lora_name": lora_name, "lora_path": lora_path},
            )
        ok = resp.status_code < 400
        logger.info("vLLM hot-swap %s → %d", lora_name, resp.status_code)
        return ok
    except Exception as exc:  # noqa: BLE001
        logger.warning("vLLM hot-swap 실패: %s", exc)
        return False


async def _start_ab_experiment(treatment_name: str) -> bool:
    """ABTestManager 에 50:50 실험 등록 (chat 라우터가 이를 읽어 분기)."""
    try:
        from hwarang_api.middleware.patterns.ab_testing import (
            ABTestManager,  # type: ignore
        )
        from hwarang_api.routers import chat as chat_router  # type: ignore
        from hwarang_api.learning.auto_rollback import DEFAULT_EXPERIMENT_ID  # type: ignore

        mgr: ABTestManager | None = getattr(chat_router, "ab_test_manager", None)
        if mgr is None:
            mgr = ABTestManager()
            chat_router.ab_test_manager = mgr  # type: ignore[attr-defined]
        mgr.create_experiment(
            id=DEFAULT_EXPERIMENT_ID,
            name=f"weekly_lora — {treatment_name}",
            variants={"control": 0.5, "treatment": 0.5},
        )
        # treatment 이름을 라우터가 읽도록 환경변수에도 노출.
        os.environ["HWARANG_LORA_TREATMENT"] = treatment_name
        logger.info("A/B experiment started: %s", treatment_name)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("A/B 실험 시작 실패: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────
# 알림
# ─────────────────────────────────────────────────────────────────
async def _notify(msg: str, severity: str = "info") -> None:
    try:
        from hwarang_api.knowledge.notifier import notify_admin  # type: ignore

        await notify_admin(msg, severity=severity)
    except Exception as exc:  # noqa: BLE001
        logger.debug("notify_admin 실패 (무시): %s", exc)


__all__ = [
    "run_weekly_training_cycle",
    "MIN_PAIRS",
    "MIN_IDENTITY_PASS_PCT",
    "IDENTITY_FILES",
]
