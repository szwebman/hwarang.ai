"""Tests for CLI tools."""

import pytest

from hwarang_cli.tools.file_read import FileReadTool
from hwarang_cli.tools.file_write import FileWriteTool
from hwarang_cli.tools.file_search import FileSearchTool
from hwarang_cli.tools.shell import ShellTool


class TestFileReadTool:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n")

        tool = FileReadTool()
        result = await tool.execute(path=str(test_file))
        assert result.success
        assert "line1" in result.output
        assert "line2" in result.output

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self):
        tool = FileReadTool()
        result = await tool.execute(path="/nonexistent/file.txt")
        assert not result.success
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_read_with_offset_and_limit(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("\n".join(f"line{i}" for i in range(100)))

        tool = FileReadTool()
        result = await tool.execute(path=str(test_file), offset=10, limit=5)
        assert result.success
        assert "line10" in result.output

    def test_openai_tool_format(self):
        tool = FileReadTool()
        definition = tool.to_openai_tool()
        assert definition["type"] == "function"
        assert definition["function"]["name"] == "read_file"
        assert "parameters" in definition["function"]


class TestFileWriteTool:
    @pytest.mark.asyncio
    async def test_write_new_file(self, tmp_path):
        tool = FileWriteTool()
        file_path = str(tmp_path / "new.txt")
        result = await tool.execute(path=file_path, content="hello world")
        assert result.success
        assert (tmp_path / "new.txt").read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_append_to_file(self, tmp_path):
        test_file = tmp_path / "append.txt"
        test_file.write_text("first\n")

        tool = FileWriteTool()
        result = await tool.execute(path=str(test_file), content="second\n", mode="append")
        assert result.success
        assert test_file.read_text() == "first\nsecond\n"

    @pytest.mark.asyncio
    async def test_replace_in_file(self, tmp_path):
        test_file = tmp_path / "replace.txt"
        test_file.write_text("hello world")

        tool = FileWriteTool()
        result = await tool.execute(
            path=str(test_file),
            content="universe",
            mode="replace",
            old_string="world",
        )
        assert result.success
        assert test_file.read_text() == "hello universe"

    @pytest.mark.asyncio
    async def test_creates_parent_dirs(self, tmp_path):
        tool = FileWriteTool()
        file_path = str(tmp_path / "a" / "b" / "c.txt")
        result = await tool.execute(path=file_path, content="deep")
        assert result.success


class TestFileSearchTool:
    @pytest.mark.asyncio
    async def test_glob_search(self, tmp_path):
        (tmp_path / "test.py").write_text("# python")
        (tmp_path / "test.js").write_text("// js")

        tool = FileSearchTool()
        result = await tool.execute(path=str(tmp_path), pattern="*.py")
        assert result.success
        assert "test.py" in result.output

    @pytest.mark.asyncio
    async def test_content_search(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello world\nfoo bar")
        (tmp_path / "b.txt").write_text("nothing here")

        tool = FileSearchTool()
        result = await tool.execute(path=str(tmp_path), content="hello")
        assert result.success
        assert "hello world" in result.output

    @pytest.mark.asyncio
    async def test_no_matches(self, tmp_path):
        tool = FileSearchTool()
        result = await tool.execute(path=str(tmp_path), pattern="*.xyz")
        assert "No matches" in result.output


class TestShellTool:
    @pytest.mark.asyncio
    async def test_echo_command(self):
        tool = ShellTool()
        result = await tool.execute(command="echo hello")
        assert result.success
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_failed_command(self):
        tool = ShellTool()
        result = await tool.execute(command="false")
        assert not result.success

    @pytest.mark.asyncio
    async def test_blocked_command(self):
        tool = ShellTool()
        result = await tool.execute(command="rm -rf /")
        assert not result.success
        assert "blocked" in result.error.lower()

    @pytest.mark.asyncio
    async def test_timeout(self):
        tool = ShellTool()
        result = await tool.execute(command="sleep 10", timeout=1)
        assert not result.success
        assert "timed out" in result.error.lower()
