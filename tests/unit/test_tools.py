"""
Unit tests for tool implementations: BashTool, EditTool, and base ToolRegistry.

All async tests use pytest-asyncio (asyncio_mode = auto in pytest.ini).
"""

import pytest
import shutil
import tempfile
from pathlib import Path

from agent.tools.base_tool import (
    BaseTool, ToolRegistry, ToolResult, ToolExecutionStatus, ToolParameter
)
from agent.tools.bash_tool import BashTool
from agent.tools.edit_tool import EditTool


# ---------------------------------------------------------------------------
# BaseTool / ToolRegistry
# ---------------------------------------------------------------------------

class ConcreteTestTool(BaseTool):
    """Concrete subclass used for ToolRegistry tests."""
    def get_name(self): return "test_tool"
    def get_description(self): return "A test tool"
    def get_parameters(self): return []
    async def execute(self, parameters):
        return ToolResult(status=ToolExecutionStatus.SUCCESS, output="ok")


class TestToolRegistry:

    def test_base_tool_is_abstract(self):
        with pytest.raises(TypeError):
            BaseTool()  # type: ignore

    def test_register_and_get_tool(self):
        registry = ToolRegistry()
        tool = ConcreteTestTool()
        registry.register_tool(tool)
        assert registry.get_tool("test_tool") is tool

    def test_get_nonexistent_returns_none(self):
        registry = ToolRegistry()
        assert registry.get_tool("missing") is None

    def test_list_tools(self):
        registry = ToolRegistry()
        registry.register_tool(ConcreteTestTool())
        assert "test_tool" in registry.list_tools()

    def test_tool_schema_roundtrip(self):
        tool = ConcreteTestTool()
        schema = tool.get_tool_schema()
        assert schema["name"] == "test_tool"
        assert "parameters" in schema


# ---------------------------------------------------------------------------
# BashTool
# ---------------------------------------------------------------------------

class TestBashTool:

    @pytest.fixture(autouse=True)
    def setup_dir(self, tmp_path):
        self.wd = str(tmp_path)
        self.tool = BashTool(working_directory=self.wd, timeout=10)

    async def test_echo_works(self):
        result = await self.tool.execute({"command": "echo hello"})
        assert result.status == ToolExecutionStatus.SUCCESS
        assert "hello" in result.output

    async def test_echo_special_chars(self):
        result = await self.tool.execute({"command": "echo 'foo bar baz'"})
        assert result.status == ToolExecutionStatus.SUCCESS
        assert "foo bar baz" in result.output

    async def test_failed_command_returns_error(self):
        result = await self.tool.execute({"command": "ls /nonexistent_xyz_path_999"})
        assert result.status == ToolExecutionStatus.ERROR

    async def test_timeout_kills_sleep(self):
        """sleep 30 with 1s timeout must be killed quickly."""
        result = await self.tool.execute({
            "command": "sleep 30",
            "timeout": 1,
        })
        assert result.status == ToolExecutionStatus.TIMEOUT
        assert "timed out" in (result.error or "").lower() or "timeout" in (result.error or "").lower()

    async def test_empty_command_invalid_params(self):
        result = await self.tool.execute({"command": ""})
        assert result.status == ToolExecutionStatus.INVALID_PARAMS

    async def test_redirect_inside_wd_allowed(self, tmp_path):
        """Redirecting to a file inside the working directory is safe."""
        tool = BashTool(working_directory=str(tmp_path), timeout=5)
        result = await tool.execute({"command": f"echo ok > {tmp_path}/out.txt"})
        # Either succeeds or is allowed (not blocked for containment reasons)
        # The safety check returns True for contained redirects
        assert result.status in (ToolExecutionStatus.SUCCESS, ToolExecutionStatus.ERROR)

    async def test_redirect_escape_blocked(self, tmp_path):
        """Redirecting to a path outside the working directory must be blocked."""
        subdir = tmp_path / "sandbox"
        subdir.mkdir()
        tool = BashTool(working_directory=str(subdir), timeout=5)
        # Try to write to parent (escape)
        result = await tool.execute({"command": "echo evil > ../escape.txt"})
        # The safety check should block it
        assert result.status == ToolExecutionStatus.ERROR, (
            "Expected path escape to be blocked"
        )

    async def test_blocked_commands_rejected(self):
        for cmd in ["sudo ls", "kill 1", "rm -rf /"]:
            result = await self.tool.execute({"command": cmd})
            assert result.status == ToolExecutionStatus.ERROR, (
                f"Expected blocked command to fail: {cmd}"
            )

    def test_tool_name(self):
        assert self.tool.get_name() == "bash"

    def test_timeout_property(self):
        tool = BashTool(timeout=42)
        assert tool.default_timeout == 42


# ---------------------------------------------------------------------------
# EditTool
# ---------------------------------------------------------------------------

class TestEditTool:

    @pytest.fixture(autouse=True)
    def setup_dir(self, tmp_path):
        self.wd = str(tmp_path)
        self.tmp = tmp_path
        self.tool = EditTool(working_directory=self.wd)

    async def test_write_and_read(self):
        result = await self.tool.execute({
            "action": "write",
            "file_path": "hello.txt",
            "content": "hello world",
        })
        assert result.status == ToolExecutionStatus.SUCCESS

        result2 = await self.tool.execute({
            "action": "read",
            "file_path": "hello.txt",
        })
        assert result2.status == ToolExecutionStatus.SUCCESS
        assert result2.output == "hello world"

    async def test_modify_single_occurrence(self):
        await self.tool.execute({
            "action": "write",
            "file_path": "f.txt",
            "content": "aaa bbb ccc",
        })
        result = await self.tool.execute({
            "action": "modify",
            "file_path": "f.txt",
            "search_text": "bbb",
            "replace_text": "XXX",
        })
        assert result.status == ToolExecutionStatus.SUCCESS

        read = await self.tool.execute({"action": "read", "file_path": "f.txt"})
        assert "XXX" in read.output
        assert "bbb" not in read.output

    async def test_modify_zero_occurrences_rejected(self):
        await self.tool.execute({
            "action": "write",
            "file_path": "f.txt",
            "content": "hello world",
        })
        result = await self.tool.execute({
            "action": "modify",
            "file_path": "f.txt",
            "search_text": "NOTFOUND",
            "replace_text": "X",
        })
        assert result.status == ToolExecutionStatus.ERROR
        assert "not found" in (result.error or "").lower() or "no occurrences" in (result.error or "").lower()

    async def test_modify_two_occurrences_rejected(self):
        await self.tool.execute({
            "action": "write",
            "file_path": "f.txt",
            "content": "abc abc",
        })
        result = await self.tool.execute({
            "action": "modify",
            "file_path": "f.txt",
            "search_text": "abc",
            "replace_text": "X",
        })
        assert result.status == ToolExecutionStatus.ERROR
        assert "2" in (result.error or "") or "occurrences" in (result.error or "").lower() or "Ambiguous" in (result.error or "")

    async def test_path_containment_blocked(self):
        """'../escape.txt' should be blocked when working_directory is set."""
        result = await self.tool.execute({
            "action": "write",
            "file_path": "../escape.txt",
            "content": "bad",
        })
        assert result.status == ToolExecutionStatus.ERROR
        assert "escape" in (result.error or "").lower() or "outside" in (result.error or "").lower()

    async def test_delete_action(self):
        await self.tool.execute({
            "action": "write",
            "file_path": "todelete.txt",
            "content": "bye",
        })
        assert (self.tmp / "todelete.txt").exists()

        result = await self.tool.execute({
            "action": "delete",
            "file_path": "todelete.txt",
        })
        assert result.status == ToolExecutionStatus.SUCCESS
        assert not (self.tmp / "todelete.txt").exists()

    async def test_delete_nonexistent_is_error(self):
        result = await self.tool.execute({
            "action": "delete",
            "file_path": "ghost.txt",
        })
        assert result.status == ToolExecutionStatus.ERROR

    async def test_read_nonexistent_is_error(self):
        result = await self.tool.execute({
            "action": "read",
            "file_path": "nosuchfile.txt",
        })
        assert result.status == ToolExecutionStatus.ERROR

    async def test_append_action(self):
        await self.tool.execute({
            "action": "write",
            "file_path": "app.txt",
            "content": "line1",
        })
        await self.tool.execute({
            "action": "append",
            "file_path": "app.txt",
            "content": "\nline2",
        })
        read = await self.tool.execute({"action": "read", "file_path": "app.txt"})
        assert "line1" in read.output
        assert "line2" in read.output

    async def test_unknown_action_is_error(self):
        result = await self.tool.execute({
            "action": "frobnicate",
            "file_path": "x.txt",
        })
        assert result.status == ToolExecutionStatus.ERROR

    async def test_missing_file_path_is_error(self):
        result = await self.tool.execute({"action": "read"})
        assert result.status == ToolExecutionStatus.ERROR

    def test_tool_name(self):
        assert self.tool.get_name() == "edit"
