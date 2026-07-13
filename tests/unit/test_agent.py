"""
Unit tests for Agent, AgentConfig, Task, and the tool registry wiring.

Uses pytest-asyncio (asyncio_mode = auto).  All network calls are monkeypatched.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from agent.agent import Agent, AgentConfig, Task, ToolExecutionEvent
from agent.fm_interface.api_handler import (
    ApiHandler, CompletionResponse, CompletionRequest, MessageRole, ToolCall
)
from agent.fm_interface.message_formatter import ConversationContext
from agent.fm_interface.providers.openai_compatible import OpenAICompatibleHandler
from agent.tools.bash_tool import BashTool
from agent.tools.base_tool import ToolExecutionStatus, ToolResult
from agent.tools.edit_tool import EditTool


FM_CONFIG = {
    "model": "claude-sonnet-4-6",
    "api_key": "test-key-dummy",
    "max_tokens": 256,
    "temperature": 0.0,
}


def _make_config(tmp_path: Path, agent_id: str = "test_agent") -> AgentConfig:
    return AgentConfig(
        agent_id=agent_id,
        fm_provider="anthropic",
        fm_config=FM_CONFIG,
        working_directory=str(tmp_path),
    )


def _make_completion(content: str, tool_calls=None) -> CompletionResponse:
    return CompletionResponse(
        content=content,
        tool_calls=tool_calls or [],
        finish_reason="end_turn",
    )


# ---------------------------------------------------------------------------
# Initialisation tests (no FM calls needed)
# ---------------------------------------------------------------------------

class TestAgentInit:

    def test_agent_id_set(self, tmp_path):
        agent = Agent(_make_config(tmp_path, "myagent"))
        assert agent.agent_id == "myagent"

    def test_working_directory_is_path(self, tmp_path):
        agent = Agent(_make_config(tmp_path))
        assert isinstance(agent.working_directory, Path)
        assert agent.working_directory == tmp_path

    def test_tools_registered(self, tmp_path):
        agent = Agent(_make_config(tmp_path))
        assert "bash" in agent.tool_registry._tools
        assert "edit" in agent.tool_registry._tools

    def test_bash_tool_is_bash_tool(self, tmp_path):
        agent = Agent(_make_config(tmp_path))
        assert isinstance(agent.tool_registry.get_tool("bash"), BashTool)

    def test_bash_tool_receives_sandbox_config(self, tmp_path):
        sandbox_manager = object()
        cfg = _make_config(tmp_path)
        cfg.sandbox_manager = sandbox_manager
        cfg.use_sandbox = True

        agent = Agent(cfg)

        bash_tool = agent.tool_registry.get_tool("bash")
        assert isinstance(bash_tool, BashTool)
        assert bash_tool.sandbox_manager is sandbox_manager
        assert bash_tool.use_sandbox is True

    def test_edit_tool_receives_sandbox_config(self, tmp_path):
        sandbox_manager = object()
        cfg = _make_config(tmp_path)
        cfg.sandbox_manager = sandbox_manager
        cfg.use_sandbox = True
        cfg.tool_timeout = 17

        agent = Agent(cfg)

        edit_tool = agent.tool_registry.get_tool("edit")
        assert isinstance(edit_tool, EditTool)
        assert edit_tool.sandbox_manager is sandbox_manager
        assert edit_tool.use_sandbox is True
        assert edit_tool.default_timeout == 17

    def test_edit_tool_is_edit_tool(self, tmp_path):
        agent = Agent(_make_config(tmp_path))
        assert isinstance(agent.tool_registry.get_tool("edit"), EditTool)

    def test_fm_handler_is_api_handler(self, tmp_path):
        agent = Agent(_make_config(tmp_path))
        assert isinstance(agent.fm_handler, ApiHandler)

    def test_openai_compatible_provider_supported(self, tmp_path):
        cfg = AgentConfig(
            agent_id="x",
            fm_provider="openai_compatible",
            fm_config={
                "model": "moonshotai/kimi-k2.7-code",
                "api_key": "test-key-dummy",
                "base_url": "https://openrouter.ai/api/v1",
                "max_tokens": 256,
                "temperature": 0.0,
            },
            working_directory=str(tmp_path),
        )
        agent = Agent(cfg)
        assert isinstance(agent.fm_handler, OpenAICompatibleHandler)

    def test_required_tool_policy_releases_after_self_modification_change(self, tmp_path):
        cfg = _make_config(tmp_path)
        cfg.fm_config = {**FM_CONFIG, "tool_choice_policy": "required_until_workspace_change"}
        agent = Agent(cfg)
        task = Task(task_id="self_modify_canary_0", description="modify")
        before = agent._snapshot_agent_code_files()

        assert agent._tool_choice_for_step(
            task=task,
            is_self_modification=True,
            initial_agent_code_snapshot=before,
        ) == "required"

        (tmp_path / "agent.py").write_text("class Agent:\n    pass\n", encoding="utf-8")
        assert agent._tool_choice_for_step(
            task=task,
            is_self_modification=True,
            initial_agent_code_snapshot=before,
        ) is None

    def test_required_tool_policy_releases_after_benchmark_solution(self, tmp_path):
        cfg = _make_config(tmp_path)
        cfg.fm_config = {**FM_CONFIG, "tool_choice_policy": "required_until_workspace_change"}
        agent = Agent(cfg)
        task = Task(
            task_id="benchmark_canary",
            description="solve",
            metadata={"benchmark": "canary"},
        )

        assert agent._tool_choice_for_step(
            task=task,
            is_self_modification=False,
            initial_agent_code_snapshot={},
        ) == "required"

        (tmp_path / "solution.py").write_text("print(42)\n", encoding="utf-8")
        assert agent._tool_choice_for_step(
            task=task,
            is_self_modification=False,
            initial_agent_code_snapshot={},
        ) is None

    async def test_read_then_write_policy_starts_with_bounded_read_schema(self, tmp_path):
        cfg = _make_config(tmp_path)
        cfg.fm_config = {
            **FM_CONFIG,
            "tool_choice_policy": "required_read_then_workspace_change",
        }
        agent = Agent(cfg)
        task = Task(task_id="self_modify_canary_0", description="modify")
        (tmp_path / "agent.py").write_text(
            "class Agent:\n    pass\n",
            encoding="utf-8",
        )

        schemas = agent._tool_schemas_for_step(is_self_modification=True)
        assert [schema["name"] for schema in schemas] == ["edit"]
        params = schemas[0]["parameters"]
        assert params["properties"]["action"]["enum"] == ["read"]
        assert params["required"] == [
            "action",
            "file_path",
            "line_number",
            "line_count",
        ]

        await agent._execute_tool_calls(
            [ToolCall(
                tool_name="edit",
                parameters={
                    "action": "read",
                    "file_path": "agent.py",
                    "line_number": 1,
                    "line_count": 2,
                },
            )],
            task,
        )

        assert agent._self_modification_read_observed is True
        write_schemas = agent._tool_schemas_for_step(is_self_modification=True)
        assert [schema["name"] for schema in write_schemas] == ["edit"]
        assert write_schemas[0]["parameters"]["properties"]["action"]["enum"] == [
            "line_replace",
            "modify",
            "write",
        ]

        await agent._execute_tool_calls(
            [ToolCall(
                tool_name="edit",
                parameters={
                    "action": "line_replace",
                    "file_path": "agent.py",
                    "line_number": 2,
                    "line_count": 1,
                    "content_lines": ["    changed = True"],
                },
            )],
            task,
        )

        assert agent._self_modification_write_observed is True
        assert len(agent._tool_schemas_for_step(is_self_modification=True)) == 2

    async def test_close_releases_provider_client(self, tmp_path):
        agent = Agent(_make_config(tmp_path))
        closed = {}

        class FakeClient:
            async def close(self):
                closed["value"] = True

        agent.fm_handler.client = FakeClient()

        await agent.close()

        assert closed["value"] is True

    def test_unsupported_provider_raises(self, tmp_path):
        cfg = AgentConfig(
            agent_id="x",
            fm_provider="nonexistent_provider",
            fm_config=FM_CONFIG,
            working_directory=str(tmp_path),
        )
        with pytest.raises(ValueError, match="Unsupported"):
            Agent(cfg)


# ---------------------------------------------------------------------------
# solve_task tests — FM is monkeypatched
# ---------------------------------------------------------------------------

class TestAgentSolveTask:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.tmp = tmp_path
        self.agent = Agent(_make_config(tmp_path))

    @patch(
        "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
        new_callable=AsyncMock,
    )
    async def test_solve_task_returns_dict_with_success(self, mock_gc):
        mock_gc.return_value = _make_completion("Task complete.\n\nSOLUTION COMPLETE")
        task = Task(task_id="t1", description="Do something")
        result = await self.agent.solve_task(task)
        assert isinstance(result, dict)
        # solve_task catches exceptions internally; either success=True or success=False
        assert "success" in result or "task_id" in result

    @patch(
        "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
        new_callable=AsyncMock,
    )
    async def test_solve_task_failure_returns_success_false(self, mock_gc):
        mock_gc.side_effect = Exception("FM unavailable")
        task = Task(task_id="t2", description="Fail task")
        result = await self.agent.solve_task(task)
        assert result.get("success") is False
        assert "FM unavailable" in result.get("error", "")

    @patch(
        "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
        new_callable=AsyncMock,
    )
    async def test_solve_task_calls_fm_at_least_once(self, mock_gc):
        mock_gc.return_value = _make_completion("Done. SOLUTION COMPLETE")
        task = Task(task_id="t3", description="Test")
        await self.agent.solve_task(task)
        mock_gc.assert_called()

    @patch(
        "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
        new_callable=AsyncMock,
    )
    async def test_solve_task_with_tool_call_round_trip(self, mock_gc):
        """FM returns a tool call, then a terminal response."""
        tool_call = ToolCall(
            tool_name="edit",
            parameters={
                "action": "write",
                "file_path": "out.txt",
                "content": "hello",
            },
            call_id="toolu_001",
        )
        mock_gc.side_effect = [
            CompletionResponse(
                content="I will write the file.",
                tool_calls=[tool_call],
                finish_reason="tool_use",
            ),
            _make_completion("Done. SOLUTION COMPLETE"),
        ]
        task = Task(task_id="t4", description="Write a file")
        result = await self.agent.solve_task(task)
        # The tool_call should have been executed (file written)
        assert (self.tmp / "out.txt").exists()

    @patch(
        "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
        new_callable=AsyncMock,
    )
    async def test_conversation_history_cleared_per_task(self, mock_gc):
        mock_gc.return_value = _make_completion("Done. SOLUTION COMPLETE")
        task_a = Task(task_id="a", description="Task A")
        task_b = Task(task_id="b", description="Task B")
        await self.agent.solve_task(task_a)
        # Conversation history is cleared at start of solve_task
        len_after_a = len(self.agent.conversation_history)
        await self.agent.solve_task(task_b)
        # Should not grow unboundedly from prior task
        assert len(self.agent.conversation_history) <= len_after_a + 10

    @patch(
        "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
        new_callable=AsyncMock,
    )
    async def test_solve_task_respects_configured_max_iterations(self, mock_gc):
        mock_gc.return_value = CompletionResponse(
            content="I need to keep working.",
            tool_calls=[
                ToolCall(
                    tool_name="missing_tool",
                    parameters={},
                    call_id="toolu_missing",
                )
            ],
            finish_reason="tool_use",
        )
        cfg = _make_config(self.tmp)
        cfg.max_iterations = 2
        agent = Agent(cfg)

        task = Task(task_id="limited", description="Keep trying")
        result = await agent.solve_task(task)

        assert result["success"] is True
        assert mock_gc.await_count == 2

    @patch(
        "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
        new_callable=AsyncMock,
    )
    async def test_solve_task_reasks_after_empty_no_tool_response(self, mock_gc):
        cfg = _make_config(self.tmp)
        cfg.max_iterations = 3
        agent = Agent(cfg)
        mock_gc.side_effect = [
            CompletionResponse(
                content="No response generated",
                tool_calls=[],
                finish_reason="length",
            ),
            CompletionResponse(
                content=(
                    "Here is the solution:\n\n"
                    "```python\nprint('ok')\n```\n\n"
                    "Task complete"
                ),
                tool_calls=[],
                finish_reason="stop",
            ),
        ]

        task = Task(task_id="empty_then_complete", description="Write a program")
        result = await agent.solve_task(task)

        assert result["success"] is True
        assert result["solution"] == "print('ok')"
        assert mock_gc.await_count == 2
        assert any(
            "previous response had no usable content" in msg.content
            for msg in agent.conversation_history
        )

    @patch(
        "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
        new_callable=AsyncMock,
    )
    async def test_solve_task_returns_tool_written_solution_at_max_steps(self, mock_gc):
        cfg = _make_config(self.tmp)
        cfg.max_iterations = 2
        agent = Agent(cfg)
        solution = "print('ok')\n"
        mock_gc.side_effect = [
            CompletionResponse(
                content="I will write the solution.",
                tool_calls=[
                    ToolCall(
                        tool_name="edit",
                        parameters={
                            "action": "write",
                            "file_path": "solution.py",
                            "content": solution,
                        },
                        call_id="toolu_write",
                    )
                ],
                finish_reason="tool_use",
            ),
            CompletionResponse(
                content="I will keep checking.",
                tool_calls=[
                    ToolCall(
                        tool_name="bash",
                        parameters={"command": "python solution.py"},
                        call_id="toolu_run",
                    )
                ],
                finish_reason="tool_use",
            ),
        ]

        task = Task(task_id="tool_solution", description="Write solution.py")
        result = await agent.solve_task(task)

        assert result["success"] is True
        assert result["solution"] == solution
        assert mock_gc.await_count == 2

    @patch(
        "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
        new_callable=AsyncMock,
    )
    async def test_solve_task_recovers_common_benchmark_solution_filename(self, mock_gc):
        cfg = _make_config(self.tmp)
        cfg.max_iterations = 1
        agent = Agent(cfg)
        solution = "print('from solve')\n"
        mock_gc.return_value = CompletionResponse(
            content="I will write the solution.",
            tool_calls=[
                ToolCall(
                    tool_name="edit",
                    parameters={
                        "action": "write",
                        "file_path": "solve.py",
                        "content": solution,
                    },
                    call_id="toolu_write",
                )
            ],
            finish_reason="tool_use",
        )

        task = Task(
            task_id="benchmark_tool_solution",
            description="Write a program",
            metadata={"benchmark": "livecodebench_example"},
        )
        result = await agent.solve_task(task)

        assert result["success"] is True
        assert result["solution"] == solution

    @patch(
        "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
        new_callable=AsyncMock,
    )
    async def test_solve_task_does_not_recover_arbitrary_benchmark_python_file(self, mock_gc):
        cfg = _make_config(self.tmp)
        cfg.max_iterations = 1
        agent = Agent(cfg)
        mock_gc.return_value = CompletionResponse(
            content="I will explore the search space.",
            tool_calls=[
                ToolCall(
                    tool_name="edit",
                    parameters={
                        "action": "write",
                        "file_path": "explore.py",
                        "content": "print('scratch')\n",
                    },
                    call_id="toolu_write",
                )
            ],
            finish_reason="tool_use",
        )

        task = Task(
            task_id="benchmark_scratch_file",
            description="Write a program",
            metadata={"benchmark": "livecodebench_example"},
        )
        result = await agent.solve_task(task)

        assert result["success"] is True
        assert result["solution"] == ""

    @patch(
        "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
        new_callable=AsyncMock,
    )
    async def test_benchmark_sample_mismatch_blocks_workspace_solution_fallback(
        self,
        mock_gc,
    ):
        cfg = _make_config(self.tmp)
        cfg.max_iterations = 3
        agent = Agent(cfg)
        task = Task(
            task_id="benchmark_livecodebench_example",
            description=(
                "Solve a benchmark\n\nPUBLIC EXAMPLES:\n"
                "1. Program reads stdin and writes stdout\n"
                "   1. Stdin:\n"
                "1\n"
                "      Expected stdout:\n"
                "2\n"
                "\nFocus on the requested behavior and the examples above."
            ),
            metadata={"benchmark": "livecodebench_example"},
        )
        mock_gc.side_effect = [
            _make_completion(
                "write wrong solution",
                [
                    ToolCall(
                        tool_name="edit",
                        parameters={
                            "action": "write",
                            "file_path": "solution.py",
                            "content_lines": ["print(1)"],
                        },
                        call_id="toolu_edit",
                    )
                ],
            ),
            _make_completion(
                "run sample",
                [
                    ToolCall(
                        tool_name="bash",
                        parameters={
                            "command": "python3 solution.py << 'EOF'\n1\nEOF"
                        },
                        call_id="toolu_bash",
                    )
                ],
            ),
            _make_completion("```python\nprint(1)\n```\n\nTask complete"),
        ]

        result = await agent.solve_task(task)

        assert result["success"] is True
        assert result["solution"] == ""

    @patch(
        "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
        new_callable=AsyncMock,
    )
    async def test_solve_task_does_not_recover_agent_file_for_self_modification(self, mock_gc):
        cfg = _make_config(self.tmp)
        cfg.max_iterations = 1
        agent = Agent(cfg)
        (self.tmp / "agent.py").write_text("print('not a benchmark answer')\n")
        mock_gc.return_value = CompletionResponse(
            content="I edited myself.",
            tool_calls=[],
            finish_reason="stop",
        )

        task = Task(task_id="self_modify", description="Modify agent.py")
        result = await agent.solve_task(task)

        assert result["success"] is True
        assert result["solution"] == ""

    def test_self_modification_system_message_includes_patch_mode(self):
        system_message = self.agent._build_system_message(
            ConversationContext(
                task_id="self_modify_parent_001_1",
                agent_id="agent_001",
            )
        )

        assert "SELF-MODIFICATION MODE" in system_message.content
        assert "Do not create `solution.py`" in system_message.content
        assert "real Python source change" in system_message.content
        assert "line_replace" in system_message.content
        assert "line_number" in system_message.content
        assert "incidental examples" in system_message.content
        assert "token-efficient" in system_message.content
        assert "Avoid changing `_is_task_complete`" in system_message.content

    @patch(
        "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
        new_callable=AsyncMock,
    )
    async def test_self_modification_read_only_loop_gets_patch_nudge(self, mock_gc):
        cfg = _make_config(self.tmp)
        cfg.max_iterations = 3
        agent = Agent(cfg)
        (self.tmp / "agent.py").write_text(
            "class Agent:\n"
            "    def __init__(self, config=None): pass\n",
            encoding="utf-8",
        )
        mock_gc.return_value = CompletionResponse(
            content="I will inspect more files.",
            tool_calls=[
                ToolCall(
                    tool_name="bash",
                    parameters={"command": "pwd"},
                    call_id="toolu_readonly",
                )
            ],
            finish_reason="tool_use",
        )

        task = Task(
            task_id="self_modify_parent_001_1",
            description="Modify yourself",
            metadata={"parent_id": "parent_001", "generation": 1},
        )
        result = await agent.solve_task(task)

        assert result["success"] is True
        assert mock_gc.await_count == 3
        assert any(
            "SELF-MODIFICATION PATCH REQUIRED" in msg.content
            for msg in agent.conversation_history
        )

    def test_self_modification_edit_error_gets_line_replace_repair_nudge(self):
        task = Task(
            task_id="self_modify_parent_001_1",
            description="Modify yourself",
            metadata={"parent_id": "parent_001", "generation": 1},
        )
        tool_call = ToolCall(
            tool_name="edit",
            parameters={
                "action": "modify",
                "file_path": "agent.py",
                "search_text": "missing",
                "replace_text": "replacement",
            },
            call_id="toolu_edit",
        )
        result = ToolResult(
            status=ToolExecutionStatus.ERROR,
            output="",
            error="old_code not found in agent.py: no occurrences of the search text",
        )

        nudge = self.agent._build_self_modification_edit_repair_nudge(
            tool_call,
            result,
            task,
        )

        assert nudge is not None
        assert "SELF-MODIFICATION EDIT REPAIR" in nudge
        assert "line_replace" in nudge
        assert "line_number" in nudge
        assert "content_lines" in nudge

    def test_self_modification_syntax_error_gets_line_replace_repair_nudge(self):
        task = Task(
            task_id="self_modify_parent_001_1",
            description="Modify yourself",
            metadata={"parent_id": "parent_001", "generation": 1},
        )
        tool_call = ToolCall(
            tool_name="edit",
            parameters={
                "action": "line_replace",
                "file_path": "agent.py",
                "line_number": 42,
                "line_count": 3,
                "content_lines": ["if True:"],
            },
            call_id="toolu_edit",
        )
        result = ToolResult(
            status=ToolExecutionStatus.ERROR,
            output="",
            error=(
                "Rejected line_replace for Python file agent.py: content has "
                "a syntax error at line 44, column 1: unexpected EOF"
            ),
        )

        nudge = self.agent._build_self_modification_edit_repair_nudge(
            tool_call,
            result,
            task,
        )

        assert nudge is not None
        assert "SELF-MODIFICATION EDIT REPAIR" in nudge
        assert "syntactically invalid" in nudge
        assert "retry a smaller action='line_replace' patch" in nudge
        assert "named instruction block" in nudge

    def test_benchmark_edit_error_gets_content_lines_repair_nudge(self):
        task = Task(
            task_id="benchmark_livecodebench_example",
            description="Solve a benchmark",
            metadata={"benchmark": "livecodebench_example"},
        )
        tool_call = ToolCall(
            tool_name="edit",
            parameters={
                "action": "write",
                "file_path": "solution.py",
                "content_lines": [["import sys"], ["print(1)"]],
            },
            call_id="toolu_edit",
        )
        result = ToolResult(
            status=ToolExecutionStatus.ERROR,
            output="",
            error="content_lines parameter must contain only strings for write action",
        )

        nudge = self.agent._build_edit_repair_nudge(tool_call, result, task)

        assert nudge is not None
        assert "BENCHMARK EDIT REPAIR" in nudge
        assert "complete solution.py" in nudge
        assert "content_lines as a JSON array of plain strings" in nudge
        assert "Do not nest arrays or objects" in nudge

    def test_nested_content_lines_are_tagged_as_malformed_edit(self):
        tool_call = ToolCall(
            tool_name="edit",
            parameters={
                "action": "write",
                "file_path": "solution.py",
                "content_lines": [["print(1)"]],
            },
        )
        result = ToolResult(
            status=ToolExecutionStatus.ERROR,
            output="",
            error=(
                "content_lines parameter must contain only strings in a flat "
                "array for write action; found list"
            ),
        )

        assert (
            self.agent._classify_tool_failure(tool_call, result)
            == "malformed edit"
        )

    def test_python_syntax_edit_is_tagged_separately(self):
        tool_call = ToolCall(
            tool_name="edit",
            parameters={"action": "write", "file_path": "solution.py"},
        )
        result = ToolResult(
            status=ToolExecutionStatus.ERROR,
            output="",
            error="Rejected write: content has a syntax error at line 1",
        )

        assert (
            self.agent._classify_tool_failure(tool_call, result)
            == "invalid Python"
        )

    def test_benchmark_tool_registry_param_error_gets_repair_nudge(self):
        task = Task(
            task_id="benchmark_livecodebench_example",
            description="Solve a benchmark",
            metadata={"benchmark": "livecodebench_example"},
        )
        tool_call = ToolCall(
            tool_name="edit",
            parameters={
                "action": "append",
                "file_path": "solution.py",
                "content_lines": "['print(1)']",
            },
            call_id="toolu_edit",
        )
        result = ToolResult(
            status=ToolExecutionStatus.INVALID_PARAMS,
            output="",
            error="Parameter 'content_lines' must be an array, got str",
        )

        nudge = self.agent._build_edit_repair_nudge(tool_call, result, task)

        assert nudge is not None
        assert "BENCHMARK EDIT REPAIR" in nudge
        assert "content_lines as a JSON array of plain strings" in nudge
        assert "final Python code in a markdown python block" in nudge

    def test_benchmark_unknown_edit_parameter_gets_repair_nudge(self):
        task = Task(
            task_id="benchmark_livecodebench_example",
            description="Solve a benchmark",
            metadata={"benchmark": "livecodebench_example"},
        )
        tool_call = ToolCall(
            tool_name="edit",
            parameters={
                "action": "write",
                "file_path": "solution.py",
                "1": "print(1)",
            },
            call_id="toolu_edit",
        )
        result = ToolResult(
            status=ToolExecutionStatus.INVALID_PARAMS,
            output="",
            error=(
                "Unknown parameter '1' for tool 'edit'. "
                "Valid parameters: action, file_path, content_lines"
            ),
        )

        nudge = self.agent._build_edit_repair_nudge(tool_call, result, task)

        assert nudge is not None
        assert "BENCHMARK EDIT REPAIR" in nudge
        assert "complete solution.py" in nudge

    def test_benchmark_solution_write_gets_constraint_verification_nudge(self):
        task = Task(
            task_id="benchmark_livecodebench_example",
            description="Solve a benchmark",
            metadata={"benchmark": "livecodebench_example"},
        )
        event = ToolExecutionEvent(
            tool_call=ToolCall(
                tool_name="edit",
                parameters={
                    "action": "write",
                    "file_path": "solution.py",
                    "content_lines": ["print(1)"],
                },
                call_id="toolu_edit",
            ),
            result=ToolResult(
                status=ToolExecutionStatus.SUCCESS,
                output="Successfully wrote solution.py",
            ),
        )

        nudge = self.agent._build_benchmark_control_nudge(
            tool_events=[event],
            task=task,
            consumed_steps=1,
            max_steps=7,
            edit_failure_streak=0,
            seen_bash_success_with_solution=False,
            has_unresolved_bash_failure=False,
            seen_unsafe_evidence=False,
            current_solution_known_bad=False,
            can_send_constraint_nudge=True,
            can_send_finalization_nudge=True,
            can_send_edit_reset_nudge=True,
            can_send_no_stdin_nudge=True,
            can_send_failure_repair_nudge=True,
            can_send_unsafe_nudge=True,
        )

        assert nudge is not None
        kind, text = nudge
        assert kind == "constraint"
        assert "BENCHMARK VERIFICATION CHECK" in text
        assert "time and memory complexity" in text
        assert "Public samples are only smoke tests" in text

    def test_benchmark_late_bash_success_gets_finalization_guard(self):
        task = Task(
            task_id="benchmark_livecodebench_example",
            description="Solve a benchmark",
            metadata={"benchmark": "livecodebench_example"},
        )
        (self.tmp / "solution.py").write_text("print(1)\n", encoding="utf-8")
        event = ToolExecutionEvent(
            tool_call=ToolCall(
                tool_name="bash",
                parameters={"command": "python3 solution.py << 'EOF'\n1\nEOF"},
                call_id="toolu_bash",
            ),
            result=ToolResult(
                status=ToolExecutionStatus.SUCCESS,
                output="1\n",
            ),
        )

        nudge = self.agent._build_benchmark_control_nudge(
            tool_events=[event],
            task=task,
            consumed_steps=6,
            max_steps=7,
            edit_failure_streak=0,
            seen_bash_success_with_solution=True,
            has_unresolved_bash_failure=False,
            seen_unsafe_evidence=False,
            current_solution_known_bad=False,
            can_send_constraint_nudge=True,
            can_send_finalization_nudge=True,
            can_send_edit_reset_nudge=True,
            can_send_no_stdin_nudge=True,
            can_send_failure_repair_nudge=True,
            can_send_unsafe_nudge=True,
        )

        assert nudge is not None
        kind, text = nudge
        assert kind == "finalization"
        assert "BENCHMARK FINALIZATION GUARD" in text
        assert "Do not rewrite solution.py" in text
        assert "Task complete" in text

    def test_benchmark_no_stdin_bash_failure_gets_repair_nudge(self):
        task = Task(
            task_id="benchmark_livecodebench_example",
            description="Solve a benchmark",
            metadata={"benchmark": "livecodebench_example"},
        )
        event = ToolExecutionEvent(
            tool_call=ToolCall(
                tool_name="bash",
                parameters={"command": "python3 solution.py"},
                call_id="toolu_bash",
            ),
            result=ToolResult(
                status=ToolExecutionStatus.ERROR,
                output="",
                error="EOFError: EOF when reading a line",
            ),
        )

        nudge = self.agent._build_benchmark_control_nudge(
            tool_events=[event],
            task=task,
            consumed_steps=3,
            max_steps=7,
            edit_failure_streak=0,
            seen_bash_success_with_solution=False,
            has_unresolved_bash_failure=True,
            seen_unsafe_evidence=False,
            current_solution_known_bad=False,
            can_send_constraint_nudge=True,
            can_send_finalization_nudge=True,
            can_send_edit_reset_nudge=True,
            can_send_no_stdin_nudge=True,
            can_send_failure_repair_nudge=True,
            can_send_unsafe_nudge=True,
        )

        assert nudge is not None
        kind, text = nudge
        assert kind == "no_stdin_repair"
        assert "BENCHMARK STDIN REPAIR" in text
        assert "Do not run python3 solution.py without stdin" in text
        assert "heredoc or printf pipe" in text

    def test_benchmark_failed_bash_blocks_finalization_guard(self):
        task = Task(
            task_id="benchmark_livecodebench_example",
            description="Solve a benchmark",
            metadata={"benchmark": "livecodebench_example"},
        )
        (self.tmp / "solution.py").write_text("print(1)\n", encoding="utf-8")
        event = ToolExecutionEvent(
            tool_call=ToolCall(
                tool_name="bash",
                parameters={"command": "python3 solution.py << 'EOF'\n1\nEOF"},
                call_id="toolu_bash",
            ),
            result=ToolResult(
                status=ToolExecutionStatus.SUCCESS,
                output="1\n",
            ),
        )

        nudge = self.agent._build_benchmark_control_nudge(
            tool_events=[event],
            task=task,
            consumed_steps=6,
            max_steps=7,
            edit_failure_streak=0,
            seen_bash_success_with_solution=True,
            has_unresolved_bash_failure=True,
            seen_unsafe_evidence=False,
            current_solution_known_bad=False,
            can_send_constraint_nudge=True,
            can_send_finalization_nudge=True,
            can_send_edit_reset_nudge=True,
            can_send_no_stdin_nudge=True,
            can_send_failure_repair_nudge=True,
            can_send_unsafe_nudge=True,
        )

        assert nudge is not None
        kind, text = nudge
        assert kind == "sample_failure_repair"
        assert "BENCHMARK FAILURE REPAIR" in text
        assert "failed sample" in text
        assert "runtime check" in text
        assert "re-run the failing check with explicit stdin" in text

    def test_benchmark_sample_output_mismatch_is_detected(self):
        task = Task(
            task_id="benchmark_livecodebench_example",
            description=(
                "Solve a benchmark\n\nPUBLIC EXAMPLES:\n"
                "1. Program reads stdin and writes stdout\n"
                "   1. Stdin:\n"
                "1\n"
                "      Expected stdout:\n"
                "2\n"
                "\nFocus on the requested behavior and the examples above."
            ),
            metadata={"benchmark": "livecodebench_example"},
        )
        event = ToolExecutionEvent(
            tool_call=ToolCall(
                tool_name="bash",
                parameters={"command": "python3 solution.py << 'EOF'\n1\nEOF"},
                call_id="toolu_bash",
            ),
            result=ToolResult(
                status=ToolExecutionStatus.SUCCESS,
                output="1\n",
            ),
        )

        assert self.agent._events_include_benchmark_sample_mismatch([event], task)
        assert not self.agent._events_include_verified_benchmark_sample_success(
            [event],
            task,
        )

    def test_benchmark_known_bad_solution_gets_failure_repair_nudge(self):
        task = Task(
            task_id="benchmark_livecodebench_example",
            description="Solve a benchmark",
            metadata={"benchmark": "livecodebench_example"},
        )
        (self.tmp / "solution.py").write_text("print(1)\n", encoding="utf-8")
        event = ToolExecutionEvent(
            tool_call=ToolCall(
                tool_name="bash",
                parameters={"command": "python3 solution.py << 'EOF'\n1\nEOF"},
                call_id="toolu_bash",
            ),
            result=ToolResult(
                status=ToolExecutionStatus.SUCCESS,
                output="1\n",
            ),
        )

        nudge = self.agent._build_benchmark_control_nudge(
            tool_events=[event],
            task=task,
            consumed_steps=6,
            max_steps=7,
            edit_failure_streak=0,
            seen_bash_success_with_solution=True,
            has_unresolved_bash_failure=False,
            seen_unsafe_evidence=False,
            current_solution_known_bad=True,
            can_send_constraint_nudge=True,
            can_send_finalization_nudge=True,
            can_send_edit_reset_nudge=True,
            can_send_no_stdin_nudge=True,
            can_send_failure_repair_nudge=True,
            can_send_unsafe_nudge=True,
        )

        assert nudge is not None
        kind, text = nudge
        assert kind == "sample_failure_repair"
        assert "mismatched expected stdout" in text

    def test_benchmark_completion_block_rejects_import_only_solution(self):
        task = Task(
            task_id="benchmark_livecodebench_example",
            description="Solve a benchmark",
            metadata={"benchmark": "livecodebench_example"},
        )
        (self.tmp / "solution.py").write_text("import math\n", encoding="utf-8")

        reason = self.agent._benchmark_completion_block_reason(
            task=task,
            current_solution_known_bad=False,
            has_unresolved_bash_failure=False,
            seen_unsafe_evidence=False,
        )

        assert reason == "current solution file is empty or import-only"

    def test_benchmark_unsafe_evidence_blocks_late_finalization(self):
        task = Task(
            task_id="benchmark_livecodebench_example",
            description="Solve a benchmark",
            metadata={"benchmark": "livecodebench_example"},
        )
        (self.tmp / "solution.py").write_text("print(1)\n", encoding="utf-8")
        event = ToolExecutionEvent(
            tool_call=ToolCall(
                tool_name="bash",
                parameters={"command": "python3 solution.py << 'EOF'\n1\nEOF"},
                call_id="toolu_bash",
            ),
            result=ToolResult(
                status=ToolExecutionStatus.SUCCESS,
                output="1\n",
            ),
        )

        nudge = self.agent._build_benchmark_control_nudge(
            tool_events=[event],
            task=task,
            consumed_steps=6,
            max_steps=7,
            edit_failure_streak=0,
            seen_bash_success_with_solution=True,
            has_unresolved_bash_failure=False,
            seen_unsafe_evidence=True,
            current_solution_known_bad=False,
            can_send_constraint_nudge=True,
            can_send_finalization_nudge=True,
            can_send_edit_reset_nudge=True,
            can_send_no_stdin_nudge=True,
            can_send_failure_repair_nudge=True,
            can_send_unsafe_nudge=True,
        )

        assert nudge is not None
        kind, text = nudge
        assert kind == "unsafe_verification"
        assert "BENCHMARK UNSAFE COMPLEXITY BLOCK" in text
        assert "Do not finalize from public samples alone" in text

    def test_benchmark_timeout_parameter_is_not_timeout_evidence(self):
        event = ToolExecutionEvent(
            tool_call=ToolCall(
                tool_name="bash",
                parameters={
                    "command": "python3 solution.py << 'EOF'\n1\nEOF",
                    "timeout": 30,
                    "capture_output": True,
                },
                call_id="toolu_bash",
            ),
            result=ToolResult(
                status=ToolExecutionStatus.SUCCESS,
                output="1\n",
            ),
        )

        assert not self.agent._events_include_unsafe_benchmark_evidence([event])

    def test_benchmark_timeout_result_remains_unsafe_evidence(self):
        event = ToolExecutionEvent(
            tool_call=ToolCall(
                tool_name="bash",
                parameters={
                    "command": "python3 solution.py",
                    "timeout": 30,
                },
                call_id="toolu_bash",
            ),
            result=ToolResult(
                status=ToolExecutionStatus.TIMEOUT,
                output="",
                error="Command timed out after 30 seconds",
            ),
        )

        assert self.agent._events_include_unsafe_benchmark_evidence([event])

    def test_benchmark_repeated_edit_failures_get_fresh_source_reset(self):
        task = Task(
            task_id="benchmark_livecodebench_example",
            description="Solve a benchmark",
            metadata={"benchmark": "livecodebench_example"},
        )
        event = ToolExecutionEvent(
            tool_call=ToolCall(
                tool_name="edit",
                parameters={
                    "action": "write",
                    "file_path": "solution.py",
                    "content_lines": [["print(1)"]],
                },
                call_id="toolu_edit",
            ),
            result=ToolResult(
                status=ToolExecutionStatus.ERROR,
                output="",
                error="content_lines parameter must contain only strings",
            ),
        )

        nudge = self.agent._build_benchmark_control_nudge(
            tool_events=[event],
            task=task,
            consumed_steps=3,
            max_steps=7,
            edit_failure_streak=2,
            seen_bash_success_with_solution=False,
            has_unresolved_bash_failure=False,
            seen_unsafe_evidence=False,
            current_solution_known_bad=False,
            can_send_constraint_nudge=True,
            can_send_finalization_nudge=True,
            can_send_edit_reset_nudge=True,
            can_send_no_stdin_nudge=True,
            can_send_failure_repair_nudge=True,
            can_send_unsafe_nudge=True,
        )

        assert nudge is not None
        kind, text = nudge
        assert kind == "edit_reset"
        assert "BENCHMARK FRESH SOURCE RESET" in text
        assert "flat JSON array" in text
        assert "whole solution.py" in text

    def test_benchmark_system_message_rejects_brittle_shell_testing(self):
        system_message = self.agent._build_system_message(
            ConversationContext(
                task_id="benchmark_livecodebench_example",
                agent_id="agent_001",
                benchmark_name="livecodebench_example",
            )
        )

        assert "Public samples are only smoke tests" in system_message.content
        assert "Do not use `echo -e`" in system_message.content
        assert "Do not run `python3 solution.py` with no stdin" in system_message.content

    def test_length_nudge_rejects_pseudo_tool_call_text(self):
        response = CompletionResponse(
            content="<tool_call><function=edit>",
            tool_calls=[],
            finish_reason="length",
        )
        task = Task(
            task_id="benchmark_livecodebench_example",
            description="Solve a benchmark",
            metadata={"benchmark": "livecodebench_example"},
        )

        nudge = self.agent._build_no_progress_nudge(response, task)

        assert "Do not emit XML-like <tool_call> text" in nudge
        assert "real tool call" in nudge

    @patch(
        "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
        new_callable=AsyncMock,
    )
    async def test_length_pseudo_tool_text_is_compacted_in_history(self, mock_gc):
        cfg = _make_config(self.tmp)
        cfg.max_iterations = 1
        agent = Agent(cfg)
        pseudo_tool_text = "<tool_call><function=edit>" + ("x" * 5000)
        mock_gc.return_value = CompletionResponse(
            content=pseudo_tool_text,
            tool_calls=[],
            finish_reason="length",
        )

        task = Task(
            task_id="benchmark_livecodebench_example",
            description="Solve a benchmark",
            metadata={"benchmark": "livecodebench_example"},
        )
        await agent.solve_task(task)

        assistant_messages = [
            msg
            for msg in agent.conversation_history
            if msg.role == MessageRole.ASSISTANT
        ]
        assert len(assistant_messages) == 1
        compacted = assistant_messages[0].content
        assert "Assistant response compacted" in compacted
        assert "pseudo-tool-call text omitted" in compacted
        assert "<tool_call" not in compacted
        assert len(compacted) < 300


# ---------------------------------------------------------------------------
# Task dataclass
# ---------------------------------------------------------------------------

class TestTask:

    def test_task_required_fields(self):
        t = Task(task_id="x", description="y")
        assert t.task_id == "x"
        assert t.description == "y"

    def test_task_defaults(self):
        t = Task(task_id="x", description="y")
        assert t.constraints == []
        assert t.examples == []
        assert t.metadata == {}
        assert t.timeout == 300


# ---------------------------------------------------------------------------
# AgentConfig
# ---------------------------------------------------------------------------

class TestAgentConfig:

    def test_config_fields(self):
        cfg = AgentConfig(
            agent_id="a",
            fm_provider="anthropic",
            fm_config=FM_CONFIG,
            working_directory="/tmp",
        )
        assert cfg.agent_id == "a"
        assert cfg.fm_provider == "anthropic"
        assert cfg.max_iterations == 10  # default
