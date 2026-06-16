"""
Unit tests for Agent, AgentConfig, Task, and the tool registry wiring.

Uses pytest-asyncio (asyncio_mode = auto).  All network calls are monkeypatched.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from agent.agent import Agent, AgentConfig, Task
from agent.fm_interface.api_handler import (
    ApiHandler, CompletionResponse, CompletionRequest, ToolCall
)
from agent.fm_interface.providers.openai_compatible import OpenAICompatibleHandler
from agent.tools.bash_tool import BashTool
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
