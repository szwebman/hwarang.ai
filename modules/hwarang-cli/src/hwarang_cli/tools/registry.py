"""Tool registry for discovering and executing tools."""

from __future__ import annotations

import json
import logging

from hwarang_cli.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for managing available tools."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def get_tool_definitions(self) -> list[dict]:
        """Get all tools in OpenAI function-calling format."""
        return [tool.to_openai_tool() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: str) -> ToolResult:
        """Execute a tool by name with JSON arguments."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                output="",
                success=False,
                error=f"Unknown tool: {name}",
            )

        try:
            kwargs = json.loads(arguments) if arguments else {}
            result = await tool.execute(**kwargs)
            logger.debug(f"Tool {name} executed: success={result.success}")
            return result
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return ToolResult(output="", success=False, error=str(e))

    def register_defaults(self) -> None:
        """Register all built-in tools."""
        from hwarang_cli.tools.file_read import FileReadTool
        from hwarang_cli.tools.file_write import FileWriteTool
        from hwarang_cli.tools.file_search import FileSearchTool
        from hwarang_cli.tools.shell import ShellTool

        self.register(FileReadTool())
        self.register(FileWriteTool())
        self.register(FileSearchTool())
        self.register(ShellTool())

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())
