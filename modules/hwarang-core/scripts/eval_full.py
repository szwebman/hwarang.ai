"""HSEE Phase 2 — 통합 평가 wrapper.

세 종 평가를 한 번에 실행하고 통합 보고서를 JSON 으로 출력 / 저장.

1. eval_identity.py     — 정체성 100 문 (system prompt 없이)
2. eval_tool_calling.py — multi-turn tool calling 10 시나리오
3. lora_evaluator       — 코드 정확도 (vLLM hot-swap, exec 검증)

stdout 의 마지막 줄에 한 줄짜리 JSON 을 출력 → ``weekly_trainer.py`` 가 파싱.
파일은 ``data/eval/hwarang-vN-YYYYMMDD.json`` 로 저장.

사용:
    python modules/hwarang-core/scripts/eval_full.py \\
        --model hwarang-v8 --lora-path /mnt/.../v8 \\
        --url http://localhost:8001
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eval_full")

SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = Path(
    os.getenv("HSEE_EVAL_OUTPUT_DIR", "data/eval")
)


def _run_subprocess(cmd: list[str]) -> tuple[int, str]:
    """subprocess 한 번 실행 → (returncode, combined_output)."""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=1800, check=False
        )
    except subprocess.TimeoutExpired as exc:
        return -1, f"timeout: {exc}"
    except Exception as exc:  # noqa: BLE001
        return -1, f"exception: {exc}"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _parse_identity_pct(log: str) -> float | None:
    """eval_identity.py 출력에서 ``통과: 95/100 (95.0%)`` 파싱."""
    m = re.search(r"통과:\s*(\d+)/(\d+)\s*\(([\d.]+)%\)", log)
    if m:
        try:
            return float(m.group(3))
        except ValueError:
            return None
    return None


def _parse_tool_rate(log: str) -> float | None:
    """eval_tool_calling.py 의 ``최종: N/M PASS (XX%)`` 파싱."""
    m = re.search(r"최종:\s*(\d+)/(\d+)\s*PASS", log)
    if m:
        try:
            passed = int(m.group(1))
            total = int(m.group(2))
            return round(passed / total, 4) if total else None
        except (ValueError, ZeroDivisionError):
            return None
    return None


def run_identity(model: str, url: str) -> dict:
    script = SCRIPTS_DIR / "eval_identity.py"
    rc, log = _run_subprocess(
        ["python", str(script), "--model", model, "--url", url]
    )
    return {
        "rc": rc,
        "identity_pct": _parse_identity_pct(log),
        "tail": log[-1000:],
    }


def run_tool_calling(model: str, url: str) -> dict:
    script = SCRIPTS_DIR / "eval_tool_calling.py"
    rc, log = _run_subprocess(
        ["python", str(script), "--model", model, "--url", url]
    )
    return {
        "rc": rc,
        "tool_rate": _parse_tool_rate(log),
        "tail": log[-1000:],
    }


async def run_code_eval(model: str, lora_path: str | None) -> dict:
    """in-process lora_evaluator — vLLM 로 코드 페어 평가."""
    try:
        sys.path.insert(
            0,
            str(SCRIPTS_DIR.parent.parent / "hwarang-api" / "src"),
        )
        from hwarang_api.grid.code_round.eval_set_builder import (  # type: ignore
            build_or_load_eval_set,
        )
        from hwarang_api.grid.code_round.lora_evaluator import (  # type: ignore
            evaluate_lora,
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": f"import_failed: {exc}"}

    try:
        eval_path = await build_or_load_eval_set(domain="code")
        if not eval_path:
            return {"error": "no_eval_set"}
        result = await evaluate_lora(model, eval_path)
        return {
            "code_score": round(result.final_score, 4),
            "code_total": result.total,
            "exact_match": round(result.exact_match, 4),
            "bleu_avg": round(result.bleu_avg, 4),
            "exec_pass_rate": round(result.execution_pass_rate, 4),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


async def run_baseline_code(baseline_model: str | None) -> float | None:
    """비교용 baseline (직전 LoRA) 코드 점수."""
    if not baseline_model:
        return None
    res = await run_code_eval(baseline_model, None)
    score = res.get("code_score")
    return float(score) if score is not None else None


def write_report(model: str, report: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    path = output_dir / f"{model}-{today}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="HSEE Phase 2 통합 평가")
    parser.add_argument("--model", required=True, help="vLLM 모델 / LoRA 이름 (예: hwarang-v8)")
    parser.add_argument("--lora-path", default=None, help="LoRA 디스크 경로 (옵션)")
    parser.add_argument("--url", default="http://localhost:8001", help="vLLM URL")
    parser.add_argument(
        "--baseline-model",
        default=os.getenv("HWARANG_LORA_CONTROL", "hwarang-v7"),
        help="비교용 baseline 모델 (코드 점수 차이 측정)",
    )
    parser.add_argument(
        "--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="JSON 보고서 저장 디렉토리"
    )
    parser.add_argument("--skip-code", action="store_true", help="코드 평가 생략")
    args = parser.parse_args()

    logger.info("eval_full 시작 model=%s url=%s", args.model, args.url)

    identity_res = run_identity(args.model, args.url)
    tool_res = run_tool_calling(args.model, args.url)
    code_res: dict = {}
    code_baseline: float | None = None
    if not args.skip_code:
        code_res = await run_code_eval(args.model, args.lora_path)
        code_baseline = await run_baseline_code(args.baseline_model)

    report = {
        "model": args.model,
        "lora_path": args.lora_path,
        "url": args.url,
        "ts": datetime.now().isoformat(),
        "identity_pct": identity_res.get("identity_pct"),
        "tool_rate": tool_res.get("tool_rate"),
        "code_score": code_res.get("code_score"),
        "code_baseline": code_baseline,
        "details": {
            "identity": identity_res,
            "tool_calling": tool_res,
            "code": code_res,
        },
    }

    saved = write_report(args.model, report, Path(args.output_dir))
    logger.info("보고서 저장: %s", saved)

    # 요약 + 머신 파싱용 한 줄 JSON.
    flat = {
        "model": report["model"],
        "identity_pct": report["identity_pct"],
        "tool_rate": report["tool_rate"],
        "code_score": report["code_score"],
        "code_baseline": report["code_baseline"],
        "report_path": str(saved),
    }
    print("\n=== eval_full 요약 ===")
    for k, v in flat.items():
        print(f"  {k}: {v}")
    print(json.dumps(flat, ensure_ascii=False))

    # exit code — identity 95 미만이면 실패.
    if isinstance(report["identity_pct"], (int, float)) and report["identity_pct"] < 95:
        return 1
    return 0


def main() -> None:
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
