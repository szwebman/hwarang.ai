"""Docker 컨테이너 코드 실행.

사전 준비된 Docker 이미지:
  - ``hwarang/python-runner``: python3.11 + 흔한 라이브러리
  - ``hwarang/node-runner``:   node20 + tsx + typescript
  - ``hwarang/rust-runner``:   rust 1.75
  - ``hwarang/go-runner``:     go 1.22

이미지 없으면 ``docker/sandbox/build.sh`` 로 자동 빌드.

격리 옵션:
  - ``--network none``                 (네트워크 차단)
  - ``--read-only --tmpfs /tmp``       (파일시스템 보호)
  - ``--memory 512m --cpus 0.5``       (자원 제한)
  - ``--user 1000:1000``               (root 차단)
  - ``--cap-drop ALL``                 (capability 제거)
  - ``--security-opt no-new-privileges``
  - ``timeout 10s``                    (asyncio.wait_for)
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SandboxResult:
    """샌드박스 실행 결과 — 모든 러너가 공통으로 반환.

    status:
      - ``passed``               — 정상 종료 (exit 0)
      - ``failed``               — 비정상 종료 (exit != 0)
      - ``timeout``              — 시간 초과
      - ``error``                — 실행 자체 실패
      - ``sandbox_unavailable``  — 격리 도구 없음
      - ``unsupported_language`` — 언어 미지원
    runtime:
      - ``docker`` | ``firejail`` | ``subprocess`` | ``none``
    """

    status: str
    stdout: str
    stderr: str
    exit_code: int
    elapsed_ms: int
    runtime: str


DOCKER_IMAGES = {
    "python": "hwarang/python-runner:latest",
    "javascript": "hwarang/node-runner:latest",
    "typescript": "hwarang/node-runner:latest",
    "rust": "hwarang/rust-runner:latest",
    "go": "hwarang/go-runner:latest",
}


_FILE_EXTENSIONS = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "rust": ".rs",
    "go": ".go",
}


def is_docker_available() -> bool:
    """Docker daemon 동작 중인지 검사."""
    if shutil.which("docker") is None:
        return False
    try:
        return os.system("docker info > /dev/null 2>&1") == 0
    except Exception:  # noqa: BLE001
        return False


async def run_in_docker(
    code: str,
    language: str,
    timeout_sec: int = 10,
    memory: str = "512m",
    cpus: str = "0.5",
) -> SandboxResult:
    """단일 코드 → Docker 컨테이너 실행."""
    started = time.time()

    if not is_docker_available():
        return SandboxResult(
            status="sandbox_unavailable",
            stdout="",
            stderr="Docker not available",
            exit_code=-1,
            elapsed_ms=0,
            runtime="none",
        )

    image = DOCKER_IMAGES.get(language)
    if not image:
        return SandboxResult(
            status="unsupported_language",
            stdout="",
            stderr=f"No image for {language}",
            exit_code=-1,
            elapsed_ms=0,
            runtime="none",
        )

    # 임시 디렉토리에 코드 파일 저장
    workdir = tempfile.mkdtemp(prefix="hwarang_sb_")
    code_file = Path(workdir) / f"main{_FILE_EXTENSIONS[language]}"
    code_file.write_text(code, encoding="utf-8")
    try:
        code_file.chmod(0o644)
    except OSError:
        pass

    # 컨테이너 명령 (언어별)
    run_cmd = {
        "python": ["python3", "/code/main.py"],
        "javascript": ["node", "/code/main.js"],
        # tsx 가 TS 자동 컴파일 + 실행
        "typescript": ["npx", "tsx", "/code/main.ts"],
        "rust": [
            "sh",
            "-c",
            "rustc /code/main.rs -o /tmp/main && /tmp/main",
        ],
        "go": ["go", "run", "/code/main.go"],
    }

    docker_args = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",  # 네트워크 차단
        "--memory",
        memory,
        "--cpus",
        cpus,
        "--read-only",
        "--tmpfs",
        "/tmp:rw,exec,size=64m",
        "-v",
        f"{workdir}:/code:ro",
        "--user",
        "1000:1000",  # non-root
        "--security-opt",
        "no-new-privileges",
        "--cap-drop",
        "ALL",
        image,
        *run_cmd[language],
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *docker_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
                stderr="execution timed out",
                exit_code=-1,
                elapsed_ms=int((time.time() - started) * 1000),
                runtime="docker",
            )

        elapsed = int((time.time() - started) * 1000)
        return SandboxResult(
            status="passed" if proc.returncode == 0 else "failed",
            stdout=stdout.decode("utf-8", errors="ignore")[:2000],
            stderr=stderr.decode("utf-8", errors="ignore")[:2000],
            exit_code=proc.returncode or 0,
            elapsed_ms=elapsed,
            runtime="docker",
        )
    except Exception as exc:  # noqa: BLE001
        return SandboxResult(
            status="error",
            stdout="",
            stderr=str(exc)[:1000],
            exit_code=-1,
            elapsed_ms=int((time.time() - started) * 1000),
            runtime="docker",
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


__all__ = [
    "DOCKER_IMAGES",
    "SandboxResult",
    "is_docker_available",
    "run_in_docker",
]
