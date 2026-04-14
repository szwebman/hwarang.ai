"""File read tool."""

from __future__ import annotations

from pathlib import Path

from hwarang_cli.tools.base import BaseTool, ToolResult


class FileReadTool(BaseTool):
    name = "read_file"
    description = "Read the contents of a file at the given path."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative file path"},
            "offset": {"type": "integer", "description": "Line number to start reading from (0-based)"},
            "limit": {"type": "integer", "description": "Maximum number of lines to read"},
        },
        "required": ["path"],
    }

    async def execute(self, path: str, offset: int = 0, limit: int = 500) -> ToolResult:
        try:
            file_path = Path(path).resolve()
            if not file_path.exists():
                return ToolResult(output="", success=False, error=f"File not found: {path}")
            if not file_path.is_file():
                return ToolResult(output="", success=False, error=f"Not a file: {path}")

            with open(file_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            selected = lines[offset : offset + limit]
            numbered = [f"{offset + i + 1:4d} | {line}" for i, line in enumerate(selected)]

            output = f"File: {file_path} ({len(lines)} lines)\n" + "".join(numbered)
            return ToolResult(output=output)
        except Exception as e:
            return ToolResult(output="", success=False, error=str(e))
