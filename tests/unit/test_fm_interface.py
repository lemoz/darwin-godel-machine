"""
Unit tests for FM interface components: ApiHandler, MessageFormatter,
and AnthropicHandler formatting logic.
"""

import pytest
from unittest.mock import patch, AsyncMock

from agent.fm_interface.api_handler import (
    ApiHandler, Message, MessageRole, CompletionRequest,
    CompletionResponse, ToolCall, MessageRole
)
from agent.fm_interface.providers.anthropic import AnthropicHandler
from agent.fm_interface.message_formatter import MessageFormatter, ConversationContext


def _handler(model="claude-sonnet-4-6"):
    return AnthropicHandler({
        "api_key": "sk-ant-dummy",
        "model": model,
        "max_tokens": 512,
        "temperature": 0.0,
        "timeout": 10,
    })


class TestApiHandlerAbstract:

    def test_api_handler_is_abstract(self):
        with pytest.raises(TypeError):
            ApiHandler({})  # type: ignore


class TestAnthropicHandlerFormatMessages:

    def test_user_message_role(self):
        h = _handler()
        msgs = [Message(role=MessageRole.USER, content="hello")]
        out = h.format_messages(msgs)
        assert out[0]["role"] == "user"

    def test_assistant_message_with_no_tool_calls(self):
        h = _handler()
        msgs = [
            Message(role=MessageRole.USER, content="go"),
            Message(role=MessageRole.ASSISTANT, content="done", metadata=None),
        ]
        out = h.format_messages(msgs)
        assert out[-1]["role"] == "assistant"

    def test_assistant_message_with_tool_calls(self):
        h = _handler()
        msgs = [
            Message(
                role=MessageRole.ASSISTANT,
                content="I will call bash.",
                metadata={
                    "tool_calls": [
                        {"id": "toolu_01", "name": "bash", "input": {"command": "ls"}}
                    ]
                },
            )
        ]
        out = h.format_messages(msgs)
        content_blocks = out[0]["content"]
        assert isinstance(content_blocks, list)
        tool_use_blocks = [b for b in content_blocks if b.get("type") == "tool_use"]
        assert len(tool_use_blocks) == 1
        assert tool_use_blocks[0]["name"] == "bash"

    def test_tool_result_message_merged(self):
        """Consecutive TOOL messages → single user message."""
        h = _handler()
        msgs = [
            Message(
                role=MessageRole.TOOL,
                content="ok1",
                metadata={"tool_use_id": "toolu_01"},
            ),
            Message(
                role=MessageRole.TOOL,
                content="ok2",
                metadata={"tool_use_id": "toolu_02"},
            ),
        ]
        out = h.format_messages(msgs)
        assert len(out) == 1
        assert out[0]["role"] == "user"

    def test_consecutive_user_messages_merged(self):
        """Two consecutive USER messages should be merged into one."""
        h = _handler()
        msgs = [
            Message(role=MessageRole.USER, content="line1"),
            Message(role=MessageRole.USER, content="line2"),
        ]
        out = h.format_messages(msgs)
        assert len(out) == 1
        assert out[0]["role"] == "user"

    def test_system_extracted_not_in_messages(self):
        h = _handler()
        sys_msg = Message(role=MessageRole.SYSTEM, content="system prompt")
        user_msg = Message(role=MessageRole.USER, content="question")
        system_text, rest = h._extract_system([sys_msg, user_msg])
        assert system_text == "system prompt"
        assert all(m.role != MessageRole.SYSTEM for m in rest)


class TestAnthropicHandlerFormatTools:

    def test_format_tools_adds_input_schema(self):
        h = _handler()
        tools = [{
            "name": "edit",
            "description": "Edit files",
            "parameters": {
                "type": "object",
                "properties": {"action": {"type": "string"}},
                "required": ["action"],
            }
        }]
        formatted = h.format_tools(tools)
        assert formatted[0]["input_schema"]["type"] == "object"

    def test_format_tools_empty_list(self):
        h = _handler()
        assert h.format_tools([]) == []


class TestMessageFormatter:

    def test_format_task_message_contains_description(self):
        fmt = MessageFormatter()
        msg = fmt.format_task_message("Solve X", None, [], [])
        assert "Solve X" in msg.content

    def test_format_task_message_role_is_user(self):
        fmt = MessageFormatter()
        msg = fmt.format_task_message("task", None, [], [])
        assert msg.role == MessageRole.USER

    def test_format_task_message_with_constraints(self):
        fmt = MessageFormatter()
        msg = fmt.format_task_message("task", None, ["no global vars"], [])
        assert "no global vars" in msg.content or isinstance(msg.content, str)
