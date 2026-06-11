"""
Integration tests for FM interface and tool usage.

test_anthropic_format.py (agent/fm_interface/providers/) already tests
message formatting in depth.  This file tests the Agent + tool integration
at a higher level, without network calls.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agent.agent import Agent, AgentConfig, Task
from agent.fm_interface.api_handler import CompletionResponse, ToolCall
from agent.tools.bash_tool import BashTool
from agent.tools.edit_tool import EditTool


FM_CONFIG = {
    "model": "claude-sonnet-4-6",
    "api_key": "test-key-dummy",
    "max_tokens": 128,
    "temperature": 0.0,
    "timeout": 10,
}


def _agent(tmp_path: Path) -> Agent:
    cfg = AgentConfig(
        agent_id="integ_agent",
        fm_provider="anthropic",
        fm_config=FM_CONFIG,
        working_directory=str(tmp_path),
    )
    return Agent(cfg)


class TestFMToolIntegration:

    async def test_edit_tool_write_via_agent_task(self, tmp_path):
        """
        FM returns a single edit-tool call to write a file, then declares done.
        Verify the file appears in the workspace.
        """
        agent = _agent(tmp_path)
        tc = ToolCall(
            tool_name="edit",
            parameters={
                "action": "write",
                "file_path": "result.py",
                "content": "x = 42\n",
            },
            call_id="toolu_001",
        )
        responses = [
            CompletionResponse(
                content="Writing result.py",
                tool_calls=[tc],
                finish_reason="tool_use",
            ),
            CompletionResponse(
                content="Done. SOLUTION COMPLETE",
                tool_calls=[],
                finish_reason="end_turn",
            ),
        ]
        with patch(
            "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
            new_callable=AsyncMock,
            side_effect=responses,
        ):
            task = Task(task_id="write_task", description="Write result.py")
            result = await agent.solve_task(task)

        assert (tmp_path / "result.py").exists()
        assert "42" in (tmp_path / "result.py").read_text()

    async def test_bash_tool_via_agent_task(self, tmp_path):
        """
        FM returns a bash tool call (echo), then declares done.
        """
        agent = _agent(tmp_path)
        tc = ToolCall(
            tool_name="bash",
            parameters={"command": "echo integration_ok"},
            call_id="toolu_bash_001",
        )
        responses = [
            CompletionResponse(
                content="Running bash.",
                tool_calls=[tc],
                finish_reason="tool_use",
            ),
            CompletionResponse(
                content="Done. SOLUTION COMPLETE",
                tool_calls=[],
                finish_reason="end_turn",
            ),
        ]
        with patch(
            "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
            new_callable=AsyncMock,
            side_effect=responses,
        ):
            task = Task(task_id="bash_task", description="Run echo")
            result = await agent.solve_task(task)

        # Result is returned (no exception)
        assert isinstance(result, dict)

    async def test_tool_registry_has_both_tools(self, tmp_path):
        agent = _agent(tmp_path)
        assert isinstance(agent.tool_registry.get_tool("bash"), BashTool)
        assert isinstance(agent.tool_registry.get_tool("edit"), EditTool)

    async def test_multiple_tool_calls_in_sequence(self, tmp_path):
        """Two consecutive tool calls before final answer."""
        agent = _agent(tmp_path)
        tc1 = ToolCall(
            tool_name="edit",
            parameters={"action": "write", "file_path": "step1.txt", "content": "a"},
            call_id="toolu_s1",
        )
        tc2 = ToolCall(
            tool_name="edit",
            parameters={"action": "write", "file_path": "step2.txt", "content": "b"},
            call_id="toolu_s2",
        )
        responses = [
            CompletionResponse("Step 1", tool_calls=[tc1], finish_reason="tool_use"),
            CompletionResponse("Step 2", tool_calls=[tc2], finish_reason="tool_use"),
            CompletionResponse("Done. SOLUTION COMPLETE", tool_calls=[], finish_reason="end_turn"),
        ]
        with patch(
            "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
            new_callable=AsyncMock,
            side_effect=responses,
        ):
            task = Task(task_id="seq_task", description="Write two files")
            await agent.solve_task(task)

        assert (tmp_path / "step1.txt").exists()
        assert (tmp_path / "step2.txt").exists()
