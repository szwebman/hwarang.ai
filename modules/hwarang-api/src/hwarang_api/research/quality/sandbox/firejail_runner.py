"""Firejail 기반 격리 (Linux 전용, Docker fallback).

firejail 은 Linux namespace + seccomp 으로 격리. Docker 보다 가볍지만
Linux 만 지원하며 Python / JavaScript / TypeScript 만 처리한다.

격리 옵션:
  - ``--net=none``           (네트워크 차단)
  - ``--private``            (임시 home, 호스트 home 노출 안 됨)
  - ``--private-tmp``        (임시 /tmp 격리)
  - ``--seccomp``            (시스템 콜 화이트리스트)
  - ``--no-shell``           (셸 실행 차단)
  - ``--rlimit-as``          (메모리 한도)
  - ``--rlimit-cpu``         (CPU 시간 한도)
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
from pathlib import Path

from .docker_runner import SandboxResult

logger = logging.getLogger(__name__)


def is_firejail_available() -> bool:
    """firejail 바이너리 존재 여부."""
    return shutil.which("firejail") is not None


async def run_in_firejail(
    code: str,
    language: str,
    timeout_sec: int = 10,
) -> SandboxResult:
    """Firejail 격리 실행."""
    started = time.time()

    if not is_firejail_available():
        return SandboxResult(
            status="sandbox_unavailable",
            stdout="",
            stderr="firejail not available",
            exit_code=-1,
            elapsed_ms=0,
            runtime="none",
        )

    extensions = {"python": ".py", "javascript": ".js", "typescript": ".ts"}
    if language not in extensions:
        return SandboxResult(
            status="unsupported_language",
            stdout="",
            stderr=f"firejail doesn't handle {language}",
            exit_code=-1,
            elapsed_ms=0,
            runtime="firejail",
        )

    workdir = tempfile.mkdtemp(prefix="hwarang_fj_")
    code_file = Path(workdir) / f"main{extensions[language]}"
    code_file.write_text(code, encoding="utf-8")

    interpreters = {
        "python": ["python3", str(code_file)],
        "javascript": ["node", str(code_file)],
        "typescript": ["npx", "tsx", str(code_file)],
    }

    cmd = [
        "firejail",
        "--quiet",
        "--net=none",  # 네트워크 차단
        "--noprofile",
        "--private",  # 임시 home
        "--private-tmp",
        "--no-shell",
        "--seccomp",
        "--rlimit-as=536870912",  # 메모리 512MB
        "--rlimit-cpu=10",  # CPU 10초
        "--rlimit-fsize=10485760",  # 파일 10MB
        "--rlimit-nofile=64",
        *interpreters[language],
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workdir,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_sec,
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
                runtime="firejail",
            )

        return SandboxResult(
            status="passed" if proc.returncode == 0 else "failed",
            stdout=stdout.decode("utf-8", errors="ignore")[:2000],
            stderr=stderr.decode("utf-8", errors="ignore")[:2000],
            exit_code=proc.returncode or 0,
            elapsed_ms=int((time.time() - started) * 1000),
            runtime="firejail",
        )
    except Exception as exc:  # noqa: BLE001
        return SandboxResult(
            status="error",
            stdout="",
            stderr=str(exc)[:1000],
            exit_code=-1,
            elapsed_ms=int((time.time() - started) * 1000),
            runtime="firejail",
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


__all__ = ["is_firejail_available", "run_in_firejail"]
