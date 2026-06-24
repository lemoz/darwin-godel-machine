from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import asyncio
import pytest

from agent.fm_interface.api_handler import (
    ApiError,
    CompletionRequest,
    Message,
    MessageRole,
)
from agent.fm_interface.providers.openai_compatible import OpenAICompatibleHandler


def _handler(**overrides):
    config = {
        "api_key": "sk-test-dummy",
        "base_url": "https://example.com/v1",
        "model": "test/model",
        "max_tokens": 256,
        "temperature": 0.1,
        "timeout": 10,
    }
    config.update(overrides)
    return OpenAICompatibleHandler(config)


def test_format_messages_preserves_openai_tool_call_shape():
    h = _handler()

    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="do work"),
        Message(
            role=MessageRole.ASSISTANT,
            content="calling bash",
            metadata={
                "tool_calls": [
                    {
                        "id": "call_123",
                        "name": "bash",
                        "input": {"command": "ls"},
                    }
                ]
            },
        ),
        Message(
            role=MessageRole.TOOL,
            content="ok",
            metadata={"tool_use_id": "call_123"},
        ),
    ]

    formatted = h.format_messages(messages)

    assert formatted[0] == {"role": "system", "content": "system"}
    assert formatted[1] == {"role": "user", "content": "do work"}
    assert formatted[2]["role"] == "assistant"
    assert formatted[2]["tool_calls"][0]["id"] == "call_123"
    assert formatted[2]["tool_calls"][0]["type"] == "function"
    assert formatted[2]["tool_calls"][0]["function"]["name"] == "bash"
    assert formatted[2]["tool_calls"][0]["function"]["arguments"] == '{"command": "ls"}'
    assert formatted[3] == {
        "role": "tool",
        "tool_call_id": "call_123",
        "content": "ok",
    }


def test_format_tools_uses_function_schema():
    h = _handler()

    formatted = h.format_tools(
        [
            {
                "name": "edit",
                "description": "Edit files",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            }
        ]
    )

    assert formatted == [
        {
            "type": "function",
            "function": {
                "name": "edit",
                "description": "Edit files",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }
    ]


def test_parse_response_extracts_content_tool_calls_and_usage():
    h = _handler()
    response = SimpleNamespace(
        model="test/model",
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content="I will run a command.",
                    tool_calls=[
                        SimpleNamespace(
                            id="call_abc",
                            function=SimpleNamespace(
                                name="bash",
                                arguments='{"command": "pwd"}',
                            ),
                        )
                    ],
                ),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=11,
            completion_tokens=7,
            total_tokens=18,
        ),
    )

    parsed = h.parse_response(response)

    assert parsed.content == "I will run a command."
    assert parsed.model == "test/model"
    assert parsed.finish_reason == "tool_calls"
    assert parsed.usage == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }
    assert len(parsed.tool_calls) == 1
    assert parsed.tool_calls[0].tool_name == "bash"
    assert parsed.tool_calls[0].parameters == {"command": "pwd"}
    assert parsed.tool_calls[0].call_id == "call_abc"


def test_parse_response_keeps_invalid_tool_arguments_as_raw_text():
    h = _handler()
    response = {
        "model": "test/model",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_bad",
                            "function": {
                                "name": "bash",
                                "arguments": "not-json",
                            },
                        }
                    ],
                },
            }
        ],
    }

    parsed = h.parse_response(response)

    assert parsed.content == ""
    assert parsed.tool_calls[0].parameters == {"arguments": "not-json"}


async def test_get_completion_preserves_zero_temperature_and_extra_body():
    h = _handler(extra_body={"reasoning": {"enabled": True}})
    fake_response = {
        "model": "test/model",
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
    }

    with patch.object(
        h.client.chat.completions,
        "create",
        new_callable=AsyncMock,
        return_value=fake_response,
    ) as mock_create:
        request = CompletionRequest(
            messages=[Message(role=MessageRole.USER, content="hi")],
            max_tokens=12,
            temperature=0.0,
        )
        parsed = await h.get_completion(request)

    assert parsed.content == "ok"
    mock_create.assert_awaited_once()
    kwargs = mock_create.await_args.kwargs
    assert kwargs["temperature"] == 0.0
    assert kwargs["max_tokens"] == 12
    assert kwargs["extra_body"] == {"reasoning": {"enabled": True}}


async def test_get_completion_enforces_outer_timeout():
    h = _handler(timeout=0.01)

    async def slow_create(**kwargs):
        await asyncio.sleep(1)

    with patch.object(h.client.chat.completions, "create", side_effect=slow_create):
        request = CompletionRequest(
            messages=[Message(role=MessageRole.USER, content="hi")],
        )
        with pytest.raises(ApiError, match="timed out after"):
            await h.get_completion(request)


def test_validate_config_rejects_bad_base_url():
    with pytest.raises(ValueError, match="base_url"):
        _handler(base_url="not-a-url")


def test_parse_response_requires_choices():
    h = _handler()

    with pytest.raises(ApiError, match="choices"):
        h.parse_response({"choices": []})
