"""
Tests for FM provider handler construction and format methods.

No real API calls — all network is monkeypatched.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from agent.fm_interface.api_handler import (
    Message, MessageRole, CompletionRequest, CompletionResponse, ToolCall
)
from agent.fm_interface.providers.anthropic import AnthropicHandler
from agent.fm_interface.message_formatter import MessageFormatter


def _make_handler(model="claude-sonnet-4-6"):
    return AnthropicHandler({
        "api_key": "sk-ant-test-dummy",
        "model": model,
        "max_tokens": 256,
        "temperature": 0.1,
        "timeout": 10,
    })


class TestAnthropicHandlerFormat:

    def test_format_tools_standard_schema(self):
        h = _make_handler()
        tools = [
            {
                "name": "bash",
                "description": "Run bash",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            }
        ]
        formatted = h.format_tools(tools)
        assert len(formatted) == 1
        assert formatted[0]["name"] == "bash"
        assert "input_schema" in formatted[0]
        assert formatted[0]["input_schema"]["type"] == "object"

    def test_format_messages_user_role(self):
        h = _make_handler()
        msgs = [Message(role=MessageRole.USER, content="hello")]
        formatted = h.format_messages(msgs)
        assert formatted[0]["role"] == "user"
        assert "hello" in formatted[0]["content"]

    def test_format_messages_tool_results_merged(self):
        """Two consecutive TOOL messages should be merged into one user message."""
        h = _make_handler()
        msgs = [
            Message(
                role=MessageRole.TOOL,
                content="result1",
                metadata={"tool_use_id": "toolu_001"},
            ),
            Message(
                role=MessageRole.TOOL,
                content="result2",
                metadata={"tool_use_id": "toolu_002"},
            ),
        ]
        formatted = h.format_messages(msgs)
        assert len(formatted) == 1
        assert formatted[0]["role"] == "user"
        content = formatted[0]["content"]
        assert isinstance(content, list)
        tool_ids = [b["tool_use_id"] for b in content if b.get("type") == "tool_result"]
        assert "toolu_001" in tool_ids
        assert "toolu_002" in tool_ids

    def test_format_messages_system_extracted(self):
        """SYSTEM messages should be separated, not in the messages array."""
        h = _make_handler()
        sys_msg = Message(role=MessageRole.SYSTEM, content="You are a helper.")
        user_msg = Message(role=MessageRole.USER, content="Hi")
        system_text, rest = h._extract_system([sys_msg, user_msg])
        assert "helper" in (system_text or "")
        assert len(rest) == 1
        assert rest[0].role == MessageRole.USER

    async def test_get_completion_raises_api_error_on_failure(self):
        """A failed API call should raise ApiError (not leak the raw exception)."""
        from agent.fm_interface.api_handler import ApiError

        h = _make_handler()
        with patch.object(h.client.messages, "create", side_effect=Exception("boom")):
            request = CompletionRequest(
                messages=[Message(role=MessageRole.USER, content="hi")],
                max_tokens=10,
            )
            with pytest.raises(ApiError):
                await h.get_completion(request)

    def test_validate_config_missing_key_raises(self):
        with pytest.raises(ValueError):
            AnthropicHandler({
                "model": "claude-sonnet-4-6",
                # no api_key
            })


class TestMessageFormatter:

    def test_format_task_message_returns_message(self):
        fmt = MessageFormatter()
        msg = fmt.format_task_message(
            task_description="do the thing",
            test_description=None,
            constraints=[],
            examples=[],
        )
        assert msg.role == MessageRole.USER
        assert "do the thing" in msg.content
