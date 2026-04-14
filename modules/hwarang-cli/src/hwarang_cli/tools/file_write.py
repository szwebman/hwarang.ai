"""File write/edit tool."""

from __future__ import annotations

from pathlib import Path

from hwarang_cli.tools.base import BaseTool, ToolResult


class FileWriteTool(BaseTool):
    name = "write_file"
    description = "Write or edit content in a file. Can create new files or replace existing content."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to write to"},
            "content": {"type": "string", "description": "Content to write"},
            "mode": {
                "type": "string",
                "enum": ["write", "append", "replace"],
                "description": "Write mode: 'write' overwrites, 'append' adds to end, 'replace' does string replacement",
            },
            "old_string": {"type": "string", "description": "String to replace (only for mode='replace')"},
        },
        "required": ["path", "content"],
    }

    async def execute(
        self,
        path: str,
        content: str,
        mode: str = "write",
        old_string: str = "",
    ) -> ToolResult:
        try:
            file_path = Path(path).resolve()

            # Create parent directories
            file_path.parent.mkdir(parents=True, exist_ok=True)

            if mode == "append":
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(content)
                return ToolResult(output=f"Appended to {file_path}")

            elif mode == "replace":
                if not file_path.exists():
                    return ToolResult(output="", success=False, error="File not found for replace")
                existing = file_path.read_text(encoding="utf-8")
                if old_string not in existing:
                    return ToolResult(
                        output="", success=False, error="old_string not found in file"
                    )
                new_content = existing.replace(old_string, content, 1)
                file_path.write_text(new_content, encoding="utf-8")
                return ToolResult(output=f"Replaced in {file_path}")

            else:  # write
                file_path.write_text(content, encoding="utf-8")
                return ToolResult(output=f"Wrote {len(content)} bytes to {file_path}")

        except Exception as e:
            return ToolResult(output="", success=False, error=str(e))
