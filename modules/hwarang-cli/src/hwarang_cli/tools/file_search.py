"""File search tool - glob and grep."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from hwarang_cli.tools.base import BaseTool, ToolResult


class FileSearchTool(BaseTool):
    name = "search_files"
    description = "Search for files by name pattern (glob) or content (grep)."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory to search in", "default": "."},
            "pattern": {"type": "string", "description": "Glob pattern for file names (e.g. '**/*.py')"},
            "content": {"type": "string", "description": "Regex pattern to search in file contents"},
            "max_results": {"type": "integer", "description": "Maximum results to return", "default": 50},
        },
        "required": [],
    }

    async def execute(
        self,
        path: str = ".",
        pattern: str = "",
        content: str = "",
        max_results: int = 50,
    ) -> ToolResult:
        try:
            search_dir = Path(path).resolve()
            if not search_dir.is_dir():
                return ToolResult(output="", success=False, error=f"Not a directory: {path}")

            results: list[str] = []

            if pattern:
                # Glob search
                for match in search_dir.rglob(pattern):
                    if len(results) >= max_results:
                        break
                    if match.is_file():
                        results.append(str(match))

            elif content:
                # Content grep
                regex = re.compile(content)
                for file_path in search_dir.rglob("*"):
                    if len(results) >= max_results:
                        break
                    if not file_path.is_file():
                        continue
                    # Skip binary files and hidden dirs
                    if any(p.startswith(".") for p in file_path.parts):
                        continue
                    try:
                        text = file_path.read_text(encoding="utf-8", errors="ignore")
                        for i, line in enumerate(text.splitlines(), 1):
                            if regex.search(line):
                                results.append(f"{file_path}:{i}: {line.strip()}")
                                if len(results) >= max_results:
                                    break
                    except (OSError, UnicodeDecodeError):
                        continue

            if not results:
                return ToolResult(output="No matches found.")

            output = f"Found {len(results)} result(s):\n" + "\n".join(results)
            return ToolResult(output=output)

        except Exception as e:
            return ToolResult(output="", success=False, error=str(e))
