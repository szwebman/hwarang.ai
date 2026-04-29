"""격리된 git worktree에서 제안 코드를 테스트하는 샌드박스.

작동 방식:
    1. `git worktree add /tmp/hwarang-sandbox-{uuid} HEAD` 로 격리된 작업 트리 생성
    2. 제안된 변경을 worktree 내부 파일에 적용
    3. test_command 를 60초 timeout 으로 실행
    4. 결과 캡처 후 worktree 강제 삭제 (try/finally 보장)

worktree 는 메인 체크아웃을 건드리지 않는다.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .change_proposal import ChangeProposal, is_hard_blocked

logger = logging.getLogger(__name__)


# 샌드박스 실행 timeout (초). 무한루프 방지를 위해 강제 종료.
SANDBOX_TIMEOUT_S = 60

# 샌드박스 worktree 베이스 디렉터리. macOS/Linux 의 /tmp 사용.
SANDBOX_BASE = Path("/tmp")


@dataclass
class SandboxResult:
    """샌드박스 테스트 실행 결과."""

    passed: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_s: float
    error: Optional[str] = None


def _find_repo_root() -> Optional[Path]:
    """현재 git 저장소 루트를 탐색한다."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception as e:
        logger.error(f"repo root 탐색 실패: {e}")
    return None


class SandboxRunner:
    """git worktree 기반 격리 테스트 실행기."""

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or _find_repo_root()
        if self.repo_root is None:
            raise RuntimeError("git 저장소 루트를 찾을 수 없다")

    def run_in_sandbox(
        self,
        proposal: ChangeProposal,
        test_command: str = "pytest",
    ) -> SandboxResult:
        """제안을 격리 worktree 에 적용하고 테스트를 실행한다.

        ALWAYS cleanup: 어떤 경로로 빠져나가도 worktree 는 삭제된다.
        """
        # 방어선 한 번 더 — sandbox 도 hard-block 검사
        if is_hard_blocked(proposal.file_path):
            return SandboxResult(
                passed=False,
                stdout="",
                stderr="hard-blocked path",
                exit_code=-1,
                duration_s=0.0,
                error="hard-blocked path rejected at sandbox layer",
            )

        sandbox_id = uuid.uuid4().hex[:12]
        sandbox_dir = SANDBOX_BASE / f"hwarang-sandbox-{sandbox_id}"

        start = time.monotonic()
        worktree_created = False
        try:
            # 1) worktree 생성
            create = subprocess.run(
                ["git", "worktree", "add", str(sandbox_dir), "HEAD"],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if create.returncode != 0:
                return SandboxResult(
                    passed=False,
                    stdout=create.stdout,
                    stderr=create.stderr,
                    exit_code=create.returncode,
                    duration_s=time.monotonic() - start,
                    error="worktree 생성 실패",
                )
            worktree_created = True

            # 2) 변경 적용
            target = self._resolve_target(sandbox_dir, proposal.file_path)
            if target is None:
                return SandboxResult(
                    passed=False,
                    stdout="",
                    stderr="target path resolution failed",
                    exit_code=-1,
                    duration_s=time.monotonic() - start,
                    error="대상 파일 경로 해석 실패",
                )
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(proposal.proposed_code, encoding="utf-8")
            except Exception as e:
                return SandboxResult(
                    passed=False,
                    stdout="",
                    stderr=str(e),
                    exit_code=-1,
                    duration_s=time.monotonic() - start,
                    error=f"파일 쓰기 실패: {e}",
                )

            # 3) 테스트 실행 (subprocess + timeout)
            try:
                env = os.environ.copy()
                env["HWARANG_SANDBOX"] = "1"  # 자식 프로세스가 인식할 수 있게
                # shell=True 는 위험하지만 임의의 test_command 를 받기 위해 필요.
                # SANDBOX_TIMEOUT_S 로 강제 종료, 격리된 worktree 에서만 실행.
                result = subprocess.run(
                    test_command,
                    shell=True,
                    cwd=str(sandbox_dir),
                    capture_output=True,
                    text=True,
                    timeout=SANDBOX_TIMEOUT_S,
                    env=env,
                )
                duration = time.monotonic() - start
                return SandboxResult(
                    passed=(result.returncode == 0),
                    stdout=result.stdout[-8000:],
                    stderr=result.stderr[-8000:],
                    exit_code=result.returncode,
                    duration_s=duration,
                )
            except subprocess.TimeoutExpired as e:
                return SandboxResult(
                    passed=False,
                    stdout=(e.stdout or b"").decode("utf-8", errors="replace") if isinstance(e.stdout, (bytes, bytearray)) else (e.stdout or ""),
                    stderr=f"timeout after {SANDBOX_TIMEOUT_S}s",
                    exit_code=-1,
                    duration_s=time.monotonic() - start,
                    error="테스트 timeout — 자동 거부",
                )
            except Exception as e:
                return SandboxResult(
                    passed=False,
                    stdout="",
                    stderr=str(e),
                    exit_code=-1,
                    duration_s=time.monotonic() - start,
                    error=f"테스트 실행 예외: {e}",
                )
        finally:
            # 4) 정리 — 어떤 경우에도 worktree 제거
            if worktree_created:
                self._cleanup(sandbox_dir)

    def _resolve_target(self, sandbox_dir: Path, file_path: str) -> Optional[Path]:
        """제안 대상 경로를 sandbox 내부의 안전한 경로로 매핑.

        sandbox 외부로 탈출 시도 (e.g. ../../etc/passwd) 는 거부.
        """
        try:
            p = Path(file_path)
            if p.is_absolute():
                # 절대 경로면 repo_root 기준 상대 경로로 변환 시도
                try:
                    rel = p.resolve().relative_to(self.repo_root.resolve())
                except ValueError:
                    logger.warning(f"sandbox 외부 경로 거부: {file_path}")
                    return None
            else:
                rel = p
            target = (sandbox_dir / rel).resolve()
            sandbox_resolved = sandbox_dir.resolve()
            if not str(target).startswith(str(sandbox_resolved)):
                logger.warning(f"sandbox 탈출 시도 거부: {file_path}")
                return None
            return target
        except Exception as e:
            logger.warning(f"경로 해석 실패 {file_path}: {e}")
            return None

    def _cleanup(self, sandbox_dir: Path) -> None:
        """worktree 제거. git 명령이 실패해도 디렉터리는 강제 삭제."""
        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(sandbox_dir)],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as e:
            logger.warning(f"git worktree remove 실패: {e}")
        # 디렉터리가 남아있으면 강제 삭제
        try:
            if sandbox_dir.exists():
                shutil.rmtree(sandbox_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"sandbox 디렉터리 강제 삭제 실패: {e}")
