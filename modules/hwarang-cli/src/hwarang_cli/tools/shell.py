"""Shell command execution tool."""

from __future__ import annotations

import asyncio
import os

from hwarang_cli.tools.base import BaseTool, ToolResult


class ShellTool(BaseTool):
    name = "run_command"
    description = "Execute a shell command and return its output."
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "cwd": {"type": "string", "description": "Working directory for the command"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
        },
        "required": ["command"],
    }

    # Commands that are never allowed
    BLOCKED_COMMANDS = {"rm -rf /", "mkfs", "dd if=", ":(){:|:&};:"}

    async def execute(
        self,
        command: str,
        cwd: str = "",
        timeout: int = 30,
    ) -> ToolResult:
        # Safety check
        for blocked in self.BLOCKED_COMMANDS:
            if blocked in command:
                return ToolResult(
                    output="", success=False, error=f"Command blocked for safety: {command}"
                )

        try:
            work_dir = cwd or os.getcwd()

            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            output_parts = []
            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))
            if stderr:
                output_parts.append(f"STDERR:\n{stderr.decode('utf-8', errors='replace')}")

            output = "\n".join(output_parts)

            # Truncate very long output
            if len(output) > 10000:
                output = output[:10000] + f"\n... (truncated, {len(output)} total chars)"

            return ToolResult(
                output=output or "(no output)",
                success=proc.returncode == 0,
                error=f"Exit code: {proc.returncode}" if proc.returncode != 0 else None,
            )

        except asyncio.TimeoutError:
            return ToolResult(
                output="", success=False, error=f"Command timed out after {timeout}s"
            )
        except Exception as e:
            return ToolResult(output="", success=False, error=str(e))
