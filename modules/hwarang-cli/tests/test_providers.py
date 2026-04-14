"""Tests for LLM provider abstractions."""

import pytest

from hwarang_cli.providers.base import LLMProvider, LLMResponse, ToolCall


class TestLLMResponse:
    def test_basic_response(self):
        resp = LLMResponse(content="Hello!", finish_reason="stop")
        assert resp.content == "Hello!"
        assert resp.tool_calls is None

    def test_tool_call_response(self):
        resp = LLMResponse(
            tool_calls=[
                ToolCall(id="call_1", name="read_file", arguments='{"path": "/tmp/test.txt"}')
            ],
            finish_reason="tool_calls",
        )
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "read_file"


class TestToolRegistry:
    def test_register_defaults(self, tool_registry):
        assert "read_file" in tool_registry.tool_names
        assert "write_file" in tool_registry.tool_names
        assert "search_files" in tool_registry.tool_names
        assert "run_command" in tool_registry.tool_names

    def test_get_tool_definitions(self, tool_registry):
        definitions = tool_registry.get_tool_definitions()
        assert len(definitions) >= 4
        for d in definitions:
            assert d["type"] == "function"
            assert "name" in d["function"]
            assert "description" in d["function"]
            assert "parameters" in d["function"]

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, tool_registry):
        result = await tool_registry.execute("nonexistent_tool", "{}")
        assert not result.success
        assert "Unknown tool" in result.error
