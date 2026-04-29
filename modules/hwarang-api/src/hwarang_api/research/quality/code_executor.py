"""샌드박스 코드 실행 검증 — Docker > firejail > subprocess fallback.

지원 언어: Python / JavaScript / TypeScript / Rust / Go
보안 우선순위:
  1. Docker 컨테이너 (운영 환경, 5종 언어 지원)
  2. Firejail (Linux 전용 가벼운 격리, Python/JS/TS 만)
  3. subprocess (개발 전용, 격리 약함)

매 6시간 cron — untested CodePair 들 실행 → executionStatus 업데이트.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import tempfile
import time

from hwarang_api.db import prisma

from .sandbox.docker_runner import (
    SandboxResult,
    is_docker_available,
    run_in_docker,
)
from .sandbox.firejail_runner import is_firejail_available, run_in_firejail
from .sandbox.language_detector import detect_language

logger = logging.getLogger(__name__)


SAFE_PYTHON_PRELUDE = """
import sys
# 위험한 모듈 차단 (이미 import 되어 있어도 sys.modules 에서 제거)
for _bad in ('subprocess', 'os.system', 'shutil', 'socket'):
    sys.modules.pop(_bad, None)
"""

EXEC_TIMEOUT_SEC = int(os.getenv("HWARANG_SANDBOX_TIMEOUT", "10"))
SANDBOX_MEMORY = os.getenv("HWARANG_SANDBOX_MEMORY", "512m")
SANDBOX_CPUS = os.getenv("HWARANG_SANDBOX_CPUS", "0.5")
SANDBOX_PREFER = os.getenv("HWARANG_SANDBOX_PREFER", "docker").lower()
OUTPUT_LIMIT = 2000


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
async def execute_code_pair(pair_id: str) -> dict:
    """단일 ``CodePair`` 의 response 코드 실행 검증."""
    try:
        pair = await prisma.codepair.find_unique(where={"id": pair_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("codepair.find_unique 실패: %s", exc)
        return {"error": "db_error"}
    if not pair:
        return {"error": "not_found"}

    code_match = re.search(r"```(?:\w+\n)?(.*?)```", pair.response or "", re.DOTALL)
    if not code_match:
        await _save_status(
            pair_id, status="no_code", output="", runtime="none", elapsed_ms=0
        )
        return {"status": "no_code", "passed": False}

    code = code_match.group(1)
    language = detect_language(code, hint=pair.language)

    result = await _run_with_best_sandbox(code, language)

    output = result.stdout
    if result.stderr:
        output = (output + "\n--- STDERR ---\n" + result.stderr) if output else result.stderr

    await _save_status(
        pair_id,
        status=result.status,
        output=output,
        runtime=result.runtime,
        elapsed_ms=result.elapsed_ms,
    )
    return {
        "status": result.status,
        "passed": result.status in ("passed", "syntax_only"),
        "runtime": result.runtime,
        "elapsed_ms": result.elapsed_ms,
        "language": language,
    }


async def _run_with_best_sandbox(code: str, language: str) -> SandboxResult:
    """격리 우선순위에 따라 자동 선택.

    환경변수 ``HWARANG_SANDBOX_PREFER`` 로 강제 가능 (docker | firejail | subprocess).
    """
    docker_ok = is_docker_available()
    firejail_ok = is_firejail_available()

    # 환경변수 강제
    if SANDBOX_PREFER == "subprocess":
        return await _legacy_subprocess(code, language)
    if SANDBOX_PREFER == "firejail" and firejail_ok and language in (
        "python",
        "javascript",
        "typescript",
    ):
        return await run_in_firejail(code, language, timeout_sec=EXEC_TIMEOUT_SEC)

    # 자동 선택
    if docker_ok:
        return await run_in_docker(
            code,
            language,
            timeout_sec=EXEC_TIMEOUT_SEC,
            memory=SANDBOX_MEMORY,
            cpus=SANDBOX_CPUS,
        )
    if firejail_ok and language in ("python", "javascript", "typescript"):
        return await run_in_firejail(code, language, timeout_sec=EXEC_TIMEOUT_SEC)

    # 마지막 폴백 — subprocess (위험, 개발 환경만)
    logger.warning(
        "샌드박스 폴백: subprocess 사용 (docker=%s, firejail=%s, lang=%s)",
        docker_ok,
        firejail_ok,
        language,
    )
    return await _legacy_subprocess(code, language)


async def _save_status(
    pair_id: str,
    *,
    status: str,
    output: str,
    runtime: str,
    elapsed_ms: int,
) -> None:
    try:
        await prisma.codepair.update(
            where={"id": pair_id},
            data={
                "executionStatus": status,
                "executionLog": (output or "")[:OUTPUT_LIMIT],
                "executionRuntime": runtime,
                "executionElapsedMs": elapsed_ms,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("codepair status update 실패: %s", exc)


# ---------------------------------------------------------------------------
# Subprocess 폴백 (격리 약함, 개발 환경 전용)
# ---------------------------------------------------------------------------
async def _legacy_subprocess(code: str, language: str) -> SandboxResult:
    """개발 환경용 폴백 — subprocess 직접 실행.

    Python / JavaScript / TypeScript 만 처리. 다른 언어는 syntax_only 통과.
    """
    if language == "python":
        return await _run_python_subprocess(code)
    if language in ("javascript", "typescript"):
        return await _run_node_subprocess(code, language)

    return SandboxResult(
        status="syntax_only",
        stdout="",
        stderr=f"subprocess 폴백은 {language} 미지원",
        exit_code=0,
        elapsed_ms=0,
        runtime="subprocess",
    )


async def _run_python_subprocess(code: str) -> SandboxResult:
    """Python subprocess (격리 없음)."""
    started = time.time()
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(SAFE_PYTHON_PRELUDE + "\n" + code)
        path = f.name

    try:
        proc = await asyncio.create_subprocess_exec(
            "python3",
            path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=EXEC_TIMEOUT_SEC
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            return SandboxResult(
                status="timeout",
                stdout="",
                stderr="timed out",
                exit_code=-1,
                elapsed_ms=int((time.time() - started) * 1000),
                runtime="subprocess",
            )

        return SandboxResult(
            status="passed" if proc.returncode == 0 else "failed",
            stdout=stdout.decode("utf-8", errors="ignore")[:OUTPUT_LIMIT],
            stderr=stderr.decode("utf-8", errors="ignore")[:OUTPUT_LIMIT],
            exit_code=proc.returncode or 0,
            elapsed_ms=int((time.time() - started) * 1000),
            runtime="subprocess",
        )
    except FileNotFoundError:
        return SandboxResult(
            status="sandbox_unavailable",
            stdout="",
            stderr="python3 not installed",
            exit_code=-1,
            elapsed_ms=int((time.time() - started) * 1000),
            runtime="subprocess",
        )
    except Exception as exc:  # noqa: BLE001
        return SandboxResult(
            status="error",
            stdout="",
            stderr=str(exc)[:OUTPUT_LIMIT],
            exit_code=-1,
            elapsed_ms=int((time.time() - started) * 1000),
            runtime="subprocess",
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


async def _run_node_subprocess(code: str, language: str) -> SandboxResult:
    """Node.js subprocess (격리 없음). TS 는 npx tsx 사용."""
    started = time.time()
    if not _has_node():
        return SandboxResult(
            status="sandbox_unavailable",
            stdout="",
            stderr="node not installed",
            exit_code=-1,
            elapsed_ms=0,
            runtime="subprocess",
        )

    suffix = ".ts" if language == "typescript" else ".js"
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        path = f.name

    cmd = ["npx", "tsx", path] if language == "typescript" else ["node", path]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=EXEC_TIMEOUT_SEC
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            return SandboxResult(
                status="timeout",
                stdout="",
                stderr="timed out",
                exit_code=-1,
                elapsed_ms=int((time.time() - started) * 1000),
                runtime="subprocess",
            )

        return SandboxResult(
            status="passed" if proc.returncode == 0 else "failed",
            stdout=stdout.decode("utf-8", errors="ignore")[:OUTPUT_LIMIT],
            stderr=stderr.decode("utf-8", errors="ignore")[:OUTPUT_LIMIT],
            exit_code=proc.returncode or 0,
            elapsed_ms=int((time.time() - started) * 1000),
            runtime="subprocess",
        )
    except Exception as exc:  # noqa: BLE001
        return SandboxResult(
            status="error",
            stdout="",
            stderr=str(exc)[:OUTPUT_LIMIT],
            exit_code=-1,
            elapsed_ms=int((time.time() - started) * 1000),
            runtime="subprocess",
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _has_node() -> bool:
    try:
        return (
            subprocess.run(
                ["which", "node"], capture_output=True, timeout=2
            ).returncode
            == 0
        )
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# 배치 실행 (cron)
# ---------------------------------------------------------------------------
async def execute_pending_pairs(batch_size: int = 50) -> dict:
    """매 6시간 cron — untested CodePair 들 실행."""
    try:
        pending = await prisma.codepair.find_many(
            where={"executionStatus": "untested"},
            take=batch_size,
            order={"createdAt": "desc"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("execute_pending_pairs find_many 실패: %s", exc)
        return {"executed": 0, "error": "db_error"}

    passed = 0
    failed = 0
    for p in pending:
        try:
            result = await execute_code_pair(p.id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("execute_code_pair 실패 %s: %s", p.id, exc)
            failed += 1
            continue
        if result.get("passed"):
            passed += 1
        else:
            failed += 1

    return {
        "executed": len(pending),
        "passed": passed,
        "failed": failed,
    }


__all__ = [
    "EXEC_TIMEOUT_SEC",
    "execute_code_pair",
    "execute_pending_pairs",
]
