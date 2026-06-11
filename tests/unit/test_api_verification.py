"""
Tests for API handler validation logic (no real network calls).
"""

import pytest
from agent.fm_interface.providers.anthropic import AnthropicHandler
from agent.fm_interface.api_handler import ApiError


class TestAnthropicHandlerValidation:

    def _handler(self, model="claude-sonnet-4-6"):
        return AnthropicHandler({
            "api_key": "sk-ant-test-dummy",
            "model": model,
            "max_tokens": 128,
            "temperature": 0.0,
            "timeout": 10,
        })

    def test_valid_model_does_not_raise(self):
        # Should not raise
        h = self._handler("claude-sonnet-4-6")
        assert h.model == "claude-sonnet-4-6"

    def test_non_claude_model_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid Anthropic model"):
            AnthropicHandler({
                "api_key": "sk-ant-dummy",
                "model": "gpt-4",
                "max_tokens": 128,
            })

    def test_deprecated_model_emits_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            h = AnthropicHandler({
                "api_key": "sk-ant-dummy",
                "model": "claude-3-sonnet-20240229",
                "max_tokens": 128,
            })
        # Should have logged a deprecation warning
        assert any("deprecated" in r.message.lower() for r in caplog.records)
