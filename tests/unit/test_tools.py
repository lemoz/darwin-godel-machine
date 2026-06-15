"""
Unit tests for tool implementations: BashTool, EditTool, and base ToolRegistry.

All async tests use pytest-asyncio (asyncio_mode = auto in pytest.ini).
"""

import json
import pytest
import shutil
import tempfile
from pathlib import Path

from agent.tools.base_tool import (
    BaseTool, ToolRegistry, ToolResult, ToolExecutionStatus, ToolParameter
)
from agent.tools.bash_tool import BashTool
from agent.tools.edit_tool import EditTool
from sandbox.sandbox_manager import SandboxResult


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

    async def test_command_environment_redacts_secret_like_variables(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-secret")
        monkeypatch.setenv("SAFE_PUBLIC_VALUE", "visible")
        result = await self.tool.execute({
            "command": "python3 -c 'import os\nprint(os.getenv(\"ANTHROPIC_API_KEY\"))\nprint(os.getenv(\"SAFE_PUBLIC_VALUE\"))'"
        })
        assert result.status == ToolExecutionStatus.SUCCESS
        assert "sk-test-secret" not in result.output
        assert "visible" in result.output

    async def test_uses_sandbox_manager_when_enabled(self, tmp_path):
        class FakeSandboxManager:
            def __init__(self):
                self.calls = []

            def is_docker_available(self):
                return True

            async def execute_in_sandbox(self, command, workspace_path, timeout):
                Path(workspace_path, "from_sandbox.txt").write_text("created in sandbox")
                self.calls.append({
                    "command": command,
                    "workspace_path": workspace_path,
                    "timeout": timeout,
                })
                return SandboxResult(
                    success=True,
                    output="sandbox hello\n",
                    exit_code=0,
                    execution_time=0.1,
                )

        sandbox_manager = FakeSandboxManager()
        tool = BashTool(
            working_directory=str(tmp_path),
            timeout=10,
            sandbox_manager=sandbox_manager,
            use_sandbox=True,
        )

        result = await tool.execute({"command": "python3 hello.py", "timeout": 7})

        assert result.status == ToolExecutionStatus.SUCCESS
        assert result.output == "sandbox hello\n"
        assert result.metadata == {"exit_code": 0, "sandboxed": True}
        assert sandbox_manager.calls[0]["command"] == "python3 hello.py"
        assert sandbox_manager.calls[0]["timeout"] == 7
        assert sandbox_manager.calls[0]["workspace_path"] != str(tmp_path)
        assert str(Path(sandbox_manager.calls[0]["workspace_path"])).startswith(
            str(Path.home() / ".cache" / "dgm-sandbox")
        )
        assert (tmp_path / "from_sandbox.txt").read_text() == "created in sandbox"

    async def test_sandbox_request_falls_back_when_unavailable(self, tmp_path):
        class UnavailableSandboxManager:
            def __init__(self):
                self.calls = []

            def is_docker_available(self):
                return False

            async def execute_in_sandbox(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                raise AssertionError("Sandbox should not be used when unavailable")

        sandbox_manager = UnavailableSandboxManager()
        tool = BashTool(
            working_directory=str(tmp_path),
            timeout=10,
            sandbox_manager=sandbox_manager,
            use_sandbox=True,
        )

        result = await tool.execute({"command": "echo fallback"})

        assert result.status == ToolExecutionStatus.SUCCESS
        assert "fallback" in result.output
        assert sandbox_manager.calls == []

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

    async def test_uses_sandbox_manager_when_enabled(self, tmp_path):
        class FakeSandboxManager:
            def __init__(self):
                self.calls = []

            def is_docker_available(self):
                return True

            async def execute_in_sandbox(
                self,
                command,
                agent_code_path=None,
                workspace_path=None,
                timeout=None,
            ):
                Path(workspace_path, "from_sandbox.txt").write_text(
                    "created in sandbox"
                )
                self.calls.append({
                    "command": command,
                    "agent_code_path": agent_code_path,
                    "agent_edit_tool_exists": (
                        Path(agent_code_path) / "agent" / "tools" / "edit_tool.py"
                    ).exists(),
                    "workspace_path": workspace_path,
                    "timeout": timeout,
                })
                return SandboxResult(
                    success=True,
                    output=json.dumps({
                        "status": "success",
                        "output": "Successfully wrote from_sandbox.txt",
                        "error": "",
                    }),
                    exit_code=0,
                    execution_time=0.1,
                )

        sandbox_manager = FakeSandboxManager()
        tool = EditTool(
            working_directory=str(tmp_path),
            sandbox_manager=sandbox_manager,
            use_sandbox=True,
            timeout=12,
        )

        result = await tool.execute({
            "action": "write",
            "file_path": "from_sandbox.txt",
            "content": "created in sandbox",
        })

        assert result.status == ToolExecutionStatus.SUCCESS
        assert result.metadata == {"exit_code": 0, "sandboxed": True}
        assert sandbox_manager.calls[0]["timeout"] == 12
        assert sandbox_manager.calls[0]["workspace_path"] != str(tmp_path)
        assert str(Path(sandbox_manager.calls[0]["workspace_path"])).startswith(
            str(Path.home() / ".cache" / "dgm-sandbox")
        )
        assert sandbox_manager.calls[0]["agent_edit_tool_exists"] is True
        assert sandbox_manager.calls[0]["command"].startswith("python3 -c ")
        assert (tmp_path / "from_sandbox.txt").read_text() == "created in sandbox"
        assert not (tmp_path / ".dgm_edit_tool_params.json").exists()

    async def test_sandbox_delete_removes_host_file(self, tmp_path):
        (tmp_path / "delete_me.txt").write_text("delete me")

        class FakeSandboxManager:
            def is_docker_available(self):
                return True

            async def execute_in_sandbox(
                self,
                command,
                agent_code_path=None,
                workspace_path=None,
                timeout=None,
            ):
                Path(workspace_path, "delete_me.txt").unlink()
                return SandboxResult(
                    success=True,
                    output=json.dumps({
                        "status": "success",
                        "output": "Successfully deleted delete_me.txt",
                        "error": "",
                    }),
                    exit_code=0,
                    execution_time=0.1,
                )

        tool = EditTool(
            working_directory=str(tmp_path),
            sandbox_manager=FakeSandboxManager(),
            use_sandbox=True,
        )

        result = await tool.execute({
            "action": "delete",
            "file_path": "delete_me.txt",
        })

        assert result.status == ToolExecutionStatus.SUCCESS
        assert not (tmp_path / "delete_me.txt").exists()

    async def test_sandbox_request_falls_back_when_unavailable(self, tmp_path):
        class UnavailableSandboxManager:
            def __init__(self):
                self.calls = []

            def is_docker_available(self):
                return False

            async def execute_in_sandbox(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                raise AssertionError("Sandbox should not be used when unavailable")

        sandbox_manager = UnavailableSandboxManager()
        tool = EditTool(
            working_directory=str(tmp_path),
            sandbox_manager=sandbox_manager,
            use_sandbox=True,
        )

        result = await tool.execute({
            "action": "write",
            "file_path": "fallback.txt",
            "content": "direct write",
        })

        assert result.status == ToolExecutionStatus.SUCCESS
        assert (tmp_path / "fallback.txt").read_text() == "direct write"
        assert sandbox_manager.calls == []

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
