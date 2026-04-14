"""Execution policy for sandboxed operations."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExecutionPolicy:
    """Defines what is allowed in the sandbox."""

    # Paths that can be used as working directory
    allowed_paths: list[str] = field(default_factory=lambda: [os.getcwd()])

    # Commands that are explicitly blocked
    blocked_commands: list[str] = field(default_factory=lambda: [
        "rm -rf /",
        "rm -rf /*",
        "mkfs",
        "dd if=/dev",
        ":(){:|:&};:",
        "chmod -R 777 /",
        "curl.*|.*sh",
        "wget.*|.*sh",
    ])

    # Environment variables allowed to pass through
    allowed_env_vars: list[str] = field(default_factory=lambda: [
        "PATH", "HOME", "USER", "LANG", "SHELL",
        "PYTHONPATH", "NODE_PATH", "GOPATH",
        "TERM", "COLORTERM",
    ])

    # Maximum output size in bytes
    max_output_size: int = 100_000

    def is_path_allowed(self, path: str) -> bool:
        """Check if a path is allowed as a working directory."""
        resolved = str(Path(path).resolve())
        return any(
            resolved.startswith(str(Path(allowed).resolve()))
            for allowed in self.allowed_paths
        )

    def is_command_allowed(self, command: str) -> bool:
        """Check if a shell command is allowed."""
        for blocked in self.blocked_commands:
            if blocked in command:
                return False
            # Also check as regex pattern
            try:
                if re.search(blocked, command):
                    return False
            except re.error:
                pass
        return True
