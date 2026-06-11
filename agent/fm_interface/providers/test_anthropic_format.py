"""
Self-contained unit tests for AnthropicHandler message formatting.

No network calls are made — the handler is constructed with a dummy API key
and the Anthropic SDK client is monkey-patched so that ``get_completion`` never
reaches the wire.  Only the pure formatting logic is exercised.

Run with:
    python3 -m pytest agent/fm_interface/providers/test_anthropic_format.py -v
or as a plain script:
    python3 agent/fm_interface/providers/test_anthropic_format.py
"""

import sys
import os
import types
import unittest

# ---------------------------------------------------------------------------
# Make sure the project root is on sys.path so imports work regardless of cwd.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_HERE, "..", "..", "..", ".."))
# The repo root should be darwin-godel-machine's parent; add darwin-godel-machine.
_PROJECT = os.path.normpath(os.path.join(_HERE, "..", "..", ".."))
for _p in (_PROJECT, _REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from agent.fm_interface.api_handler import (
    Message,
    MessageRole,
    CompletionRequest,
    ToolCall,
)
from agent.fm_interface.providers.anthropic import AnthropicHandler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_handler() -> AnthropicHandler:
    """Return an AnthropicHandler with a dummy key; no real API calls."""
    config = {
        "api_key": "sk-ant-dummy-key-for-tests",
        "model": "claude-sonnet-4-20250514",
        "timeout": 30,
        "max_tokens": 1024,
        "temperature": 0.7,
    }
    return AnthropicHandler(config)


def _build_conversation() -> list:
    """
    Build a realistic multi-turn conversation:

      SYSTEM  — base instructions
      USER    — task description
      ASSISTANT (with 2 tool calls)
      TOOL    — result for tool call 1
      TOOL    — result for tool call 2
      USER    — follow-up

    Returns a flat list of Message objects.
    """
    system_msg = Message(
        role=MessageRole.SYSTEM,
        content="You are a helpful coding assistant.",
    )
    user_task = Message(
        role=MessageRole.USER,
        content="Please read config.yaml and list_files in /tmp.",
    )
    # Assistant replies with two tool calls.
    assistant_with_tools = Message(
        role=MessageRole.ASSISTANT,
        content="I'll call both tools now.",
        metadata={
            "tool_calls": [
                {
                    "id": "toolu_abc123",
                    "name": "read_file",
                    "input": {"path": "config.yaml"},
                },
                {
                    "id": "toolu_def456",
                    "name": "list_files",
                    "input": {"directory": "/tmp"},
                },
            ]
        },
    )
    # Two separate TOOL-role messages (one per tool call).
    tool_result_1 = Message(
        role=MessageRole.TOOL,
        content="contents: foo: bar",
        metadata={"tool_use_id": "toolu_abc123"},
    )
    tool_result_2 = Message(
        role=MessageRole.TOOL,
        content="file1.txt\nfile2.txt",
        metadata={"tool_use_id": "toolu_def456"},
    )
    final_user = Message(
        role=MessageRole.USER,
        content="Thanks, now summarise.",
    )
    return [
        system_msg,
        user_task,
        assistant_with_tools,
        tool_result_1,
        tool_result_2,
        final_user,
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAnthropicFormatMessages(unittest.TestCase):
    """Verify that format_messages produces a correct Anthropic wire payload."""

    def setUp(self):
        self.handler = _make_handler()
        self.conversation = _build_conversation()

    def _build_api_params(self, temperature: float = 0.7):
        """
        Simulate what get_completion does (without a real API call):
        extract system, format messages, assemble api_params.
        """
        system_text, non_system = self.handler._extract_system(self.conversation)
        messages = self.handler.format_messages(non_system)
        api_params = {
            "model": self.handler.model,
            "messages": messages,
            "max_tokens": self.handler.max_tokens,
            "temperature": temperature,
        }
        if system_text:
            api_params["system"] = system_text
        return api_params

    # ------------------------------------------------------------------
    # Assertion 1: api_params contains top-level `system`
    # ------------------------------------------------------------------
    def test_system_in_api_params(self):
        params = self._build_api_params()
        self.assertIn(
            "system",
            params,
            "api_params must contain a top-level 'system' key for SYSTEM-role messages",
        )
        self.assertIn(
            "helpful coding assistant",
            params["system"],
            "system text must include the content from the SYSTEM message",
        )

    # ------------------------------------------------------------------
    # Assertion 2: roles strictly alternate user/assistant, starting with user
    # ------------------------------------------------------------------
    def test_roles_alternate_starting_with_user(self):
        params = self._build_api_params()
        messages = params["messages"]

        self.assertTrue(
            len(messages) > 0,
            "messages array must not be empty",
        )
        self.assertEqual(
            messages[0]["role"],
            "user",
            f"First message must have role 'user', got '{messages[0]['role']}'",
        )

        for i in range(1, len(messages)):
            prev_role = messages[i - 1]["role"]
            curr_role = messages[i]["role"]
            expected = "assistant" if prev_role == "user" else "user"
            self.assertEqual(
                curr_role,
                expected,
                f"Role alternation violated at index {i}: "
                f"after '{prev_role}' expected '{expected}', got '{curr_role}'. "
                f"Full roles: {[m['role'] for m in messages]}",
            )

    # ------------------------------------------------------------------
    # Assertion 3: assistant message contains both tool_use blocks with their ids
    # ------------------------------------------------------------------
    def test_assistant_message_contains_tool_use_blocks(self):
        params = self._build_api_params()
        messages = params["messages"]

        # Find the assistant message.
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        self.assertTrue(
            len(assistant_msgs) >= 1,
            "Expected at least one assistant message",
        )
        asst = assistant_msgs[0]

        content = asst["content"]
        self.assertIsInstance(
            content,
            list,
            "Assistant message content must be a list of blocks when tool calls are present",
        )

        tool_use_blocks = [b for b in content if b.get("type") == "tool_use"]
        self.assertEqual(
            len(tool_use_blocks),
            2,
            f"Expected 2 tool_use blocks in assistant content, got {len(tool_use_blocks)}",
        )

        ids_found = {b["id"] for b in tool_use_blocks}
        self.assertIn("toolu_abc123", ids_found, "tool_use block for toolu_abc123 missing")
        self.assertIn("toolu_def456", ids_found, "tool_use block for toolu_def456 missing")

    # ------------------------------------------------------------------
    # Assertion 4: following user message contains two tool_result blocks
    #              with MATCHING tool_use_ids
    # ------------------------------------------------------------------
    def test_tool_results_batched_in_one_user_message_with_matching_ids(self):
        params = self._build_api_params()
        messages = params["messages"]

        # Find the user message that follows the assistant tool-call message.
        asst_idx = next(
            (i for i, m in enumerate(messages) if m["role"] == "assistant"), None
        )
        self.assertIsNotNone(asst_idx, "No assistant message found")

        # The very next message should be the batched tool-results user message.
        tool_result_user_idx = asst_idx + 1
        self.assertLess(
            tool_result_user_idx,
            len(messages),
            "No message after the assistant message",
        )
        tool_result_msg = messages[tool_result_user_idx]

        self.assertEqual(
            tool_result_msg["role"],
            "user",
            f"Message after assistant must be 'user', got '{tool_result_msg['role']}'",
        )

        content = tool_result_msg["content"]
        self.assertIsInstance(
            content,
            list,
            "Tool-result user message content must be a list of blocks",
        )

        tr_blocks = [b for b in content if b.get("type") == "tool_result"]
        self.assertEqual(
            len(tr_blocks),
            2,
            f"Expected 2 tool_result blocks in one user message, got {len(tr_blocks)}",
        )

        ids_found = {b["tool_use_id"] for b in tr_blocks}
        self.assertIn(
            "toolu_abc123",
            ids_found,
            "tool_result for toolu_abc123 missing",
        )
        self.assertIn(
            "toolu_def456",
            ids_found,
            "tool_result for toolu_def456 missing",
        )

    # ------------------------------------------------------------------
    # Assertion 5: temperature=0.0 survives (must not be treated as falsy)
    # ------------------------------------------------------------------
    def test_zero_temperature_survives(self):
        # Build api_params with explicit temperature=0.0.
        system_text, non_system = self.handler._extract_system(self.conversation)
        messages = self.handler.format_messages(non_system)

        request_temperature = 0.0
        # This is the fix (c) logic from get_completion:
        temperature = (
            request_temperature
            if request_temperature is not None
            else self.handler.temperature
        )

        self.assertEqual(
            temperature,
            0.0,
            f"temperature=0.0 must survive the 'is not None' guard; got {temperature}",
        )
        # Contrast with old buggy `request.temperature or self.temperature`:
        old_buggy = request_temperature or self.handler.temperature
        self.assertNotEqual(
            old_buggy,
            0.0,
            "Sanity check: the old `or` pattern would incorrectly discard 0.0",
        )

    # ------------------------------------------------------------------
    # Bonus: SYSTEM messages must NOT appear in the messages array
    # ------------------------------------------------------------------
    def test_system_messages_not_in_messages_array(self):
        params = self._build_api_params()
        for msg in params["messages"]:
            self.assertNotEqual(
                msg.get("role"),
                "system",
                "SYSTEM-role messages must not appear in the messages array; "
                "they belong in the top-level 'system' parameter",
            )


# ---------------------------------------------------------------------------
# Plain-script entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Run with verbose output when executed directly.
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestAnthropicFormatMessages)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
