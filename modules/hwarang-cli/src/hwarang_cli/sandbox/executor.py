"""Sandboxed code execution."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from hwarang_cli.sandbox.policy import ExecutionPolicy


@dataclass
class ExecutionResult:
    """Result of sandboxed code execution."""

    stdout: str
    stderr: str
    return_code: int
    timed_out: bool = False

    @property
    def success(self) -> bool:
        return self.return_code == 0 and not self.timed_out


class SandboxExecutor:
    """Execute code in a restricted subprocess.

    Security measures:
    - Runs in a subprocess (not in the current process)
    - Timeout enforcement
    - Working directory restrictions
    - Environment variable filtering
    """

    def __init__(self, policy: ExecutionPolicy | None = None):
        self.policy = policy or ExecutionPolicy()

    async def execute_python(
        self,
        code: str,
        timeout: int = 30,
        cwd: str | None = None,
    ) -> ExecutionResult:
        """Execute Python code in a sandboxed subprocess.

        Args:
            code: Python source code to execute.
            timeout: Maximum execution time in seconds.
            cwd: Working directory. Must be in the policy's allowed paths.

        Returns:
            ExecutionResult with stdout, stderr, and return code.
        """
        work_dir = cwd or os.getcwd()

        # Check policy
        if not self.policy.is_path_allowed(work_dir):
            return ExecutionResult(
                stdout="",
                stderr=f"Working directory not allowed: {work_dir}",
                return_code=1,
            )

        # Write code to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=work_dir
        ) as f:
            f.write(code)
            script_path = f.name

        try:
            # Build safe environment
            env = self._build_safe_env()

            proc = await asyncio.create_subprocess_exec(
                sys.executable, script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                return ExecutionResult(
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    return_code=proc.returncode or 0,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ExecutionResult(
                    stdout="",
                    stderr=f"Execution timed out after {timeout}s",
                    return_code=-1,
                    timed_out=True,
                )

        finally:
            # Clean up temp file
            try:
                os.unlink(script_path)
            except OSError:
                pass

    async def execute_shell(
        self,
        command: str,
        timeout: int = 30,
        cwd: str | None = None,
    ) -> ExecutionResult:
        """Execute a shell command in a sandboxed subprocess."""
        work_dir = cwd or os.getcwd()

        if not self.policy.is_command_allowed(command):
            return ExecutionResult(
                stdout="",
                stderr=f"Command not allowed by policy: {command}",
                return_code=1,
            )

        env = self._build_safe_env()

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
            env=env,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return ExecutionResult(
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                return_code=proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ExecutionResult(
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                return_code=-1,
                timed_out=True,
            )

    def _build_safe_env(self) -> dict[str, str]:
        """Build a safe environment for subprocess execution."""
        # Start with minimal environment
        safe_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LANG": "en_US.UTF-8",
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        }

        # Add allowed environment variables from policy
        for var in self.policy.allowed_env_vars:
            if var in os.environ:
                safe_env[var] = os.environ[var]

        return safe_env
