"""
Tests for the Agent._extract_code_solution helper.
"""

import pytest
from agent.agent import Agent, AgentConfig

# We test the private method directly by constructing a minimal agent
# (no FM call is made during __init__ except building the handler).


def _make_agent(tmp_path):
    cfg = AgentConfig(
        agent_id="test",
        fm_provider="anthropic",
        fm_config={
            "model": "claude-sonnet-4-6",
            "api_key": "dummy",
            "max_tokens": 128,
        },
        working_directory=str(tmp_path),
    )
    return Agent(cfg)


class TestExtractCodeSolution:

    def test_extracts_python_code_block(self, tmp_path):
        agent = _make_agent(tmp_path)
        response = "Here is the solution:\n```python\ndef add(a, b):\n    return a + b\n```"
        code = agent._extract_code_solution(response)
        assert "def add" in code

    def test_extracts_plain_code_block(self, tmp_path):
        agent = _make_agent(tmp_path)
        response = "Solution:\n```\ndef f(): pass\n```"
        code = agent._extract_code_solution(response)
        assert "def f" in code

    def test_extracts_last_block_when_multiple(self, tmp_path):
        agent = _make_agent(tmp_path)
        response = (
            "```python\ndef helper(): pass\n```\n"
            "Final:\n```python\ndef solution(): return 42\n```"
        )
        code = agent._extract_code_solution(response)
        assert "solution" in code

    def test_no_code_block_returns_string(self, tmp_path):
        agent = _make_agent(tmp_path)
        # No markdown block; should return something (possibly empty)
        response = "I could not solve this problem."
        code = agent._extract_code_solution(response)
        assert isinstance(code, str)

    def test_empty_response_returns_string(self, tmp_path):
        agent = _make_agent(tmp_path)
        code = agent._extract_code_solution("")
        assert isinstance(code, str)
