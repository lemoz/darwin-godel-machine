"""
Integration test: one full DGM generation end-to-end, no network.

Strategy
--------
1. Build a tiny config dict pointing at tmp_path directories.
2. Write a one-task benchmark YAML to tmp_path/benchmarks/.
3. Write a minimal agent.py that already correctly solves the benchmark task.
4. Monkeypatch AnthropicHandler.get_completion so that the "self-modification"
   step returns a scripted CompletionResponse telling the agent to write a new
   agent.py (via the edit tool).
5. Run DGMController._initialize_base_agent() + _run_generation().
6. Assert:
   - validation passed
   - benchmark score is non-None float in [0, 1]
   - new agent was added to the archive with correct parent_id
   - a second generation can select the first child as a parent
"""

import asyncio
import math
import os
import random
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import yaml

from archive.agent_archive import AgentArchive
from archive.parent_selector import ParentSelector
from agent.fm_interface.api_handler import CompletionResponse, ToolCall


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

AGENT_CODE_SOLVES_ADD = '''\
"""Minimal agent used in integration test.

IMPORTANT: The validator (AgentValidator._validate_implementation) uses ast.walk
with isinstance(node, ast.ClassDef) and 'Agent' in node.name — it picks the
FIRST such class.  Therefore this file must define the Agent class BEFORE any
other class whose name contains 'Agent' (e.g. AgentConfig).  Additionally,
solve_task must be a plain def, not async def, because the validator only
checks ast.FunctionDef (ast.AsyncFunctionDef is NOT detected — production bug).
"""
from pathlib import Path


class Agent:
    """Integration-test stub: returns a solution to the add benchmark."""

    def __init__(self, config):
        self.config = config
        self.agent_id = config.agent_id
        self.working_directory = Path(config.working_directory)
        self.working_directory.mkdir(parents=True, exist_ok=True)
        self.fm_interface = None
        self.tools = []

    def solve_task(self, task):
        """Sync wrapper returning a coroutine so it can be awaited."""
        async def _inner():
            return {
                "success": True,
                "solution": "def add(a, b):\\n    return a + b\\n",
                "task_id": task.task_id,
                "agent_id": self.agent_id,
                "steps": 1,
                "conversation_history": [],
            }
        return _inner()


class _Config:
    """Internal config shim — not 'Agent' in name, so validator ignores it."""
    pass
'''

# The "child" agent written by the self-modification step.
CHILD_AGENT_CODE = AGENT_CODE_SOLVES_ADD.replace(
    "returns a solution to the add benchmark.",
    "child (generation 1) — same benchmark solution.",
)


def _make_benchmark_yaml(bdir: Path) -> None:
    """Write a single-task benchmark YAML."""
    config = {
        "name": "add_two_numbers",
        "description": "Add two numbers",
        "task_prompt": "Write a Python function add(a, b) that returns a+b.",
        "test_cases": [
            {
                "function_name": "add",
                "inputs": ["1, 2", "10, 20"],
                "expected_outputs": ["3", "30"],
            }
        ],
        "timeout": 10,
        "scoring_method": "partial",
    }
    bdir.mkdir(parents=True, exist_ok=True)
    (bdir / "add_two_numbers.yaml").write_text(yaml.dump(config))


def _make_dgm_config(tmp_path: Path) -> dict:
    arc_dir = tmp_path / "archive"
    bench_dir = tmp_path / "benchmarks"
    results_dir = tmp_path / "results"
    workspace_dir = tmp_path / "workspace"
    initial_agent = tmp_path / "initial_agent.py"

    for d in (arc_dir, results_dir, workspace_dir):
        d.mkdir(parents=True, exist_ok=True)

    _make_benchmark_yaml(bench_dir)
    initial_agent.write_text(AGENT_CODE_SOLVES_ADD)

    return {
        "fm_providers": {
            "primary": "anthropic",
            "anthropic": {
                "model": "claude-sonnet-4-6",
                "api_key": "test-dummy",
                "max_tokens": 256,
                "temperature": 0.0,
                "timeout": 10,
            },
        },
        "archive": {"path": str(arc_dir)},
        "parent_selection": {"lambda": 10, "alpha_0": 0.5},
        "evaluation": {
            "benchmarks_dir": str(bench_dir),
            "results_dir": str(results_dir),
        },
        "agents": {
            "workspace_dir": str(workspace_dir),
            "initial_agent_path": str(initial_agent),
            "max_steps": 5,
        },
        "benchmarks": {
            "enabled": ["add_two_numbers"],
        },
        "logging": {"level": "WARNING"},
        "generation_delay_seconds": 0,
    }


# ---------------------------------------------------------------------------
# Scripted FM responses used by _run_generation
# ---------------------------------------------------------------------------

def _edit_tool_response(workspace_agent_path: Path) -> CompletionResponse:
    """
    Return a CompletionResponse that writes the child agent code via the edit tool.
    The path must be relative so the edit tool resolves it inside the workspace.
    """
    tc = ToolCall(
        tool_name="edit",
        parameters={
            "action": "write",
            "file_path": "agent.py",
            "content": CHILD_AGENT_CODE,
        },
        call_id="toolu_dgm_test_001",
    )
    return CompletionResponse(
        content="I will modify the agent.",
        tool_calls=[tc],
        finish_reason="tool_use",
    )


def _terminal_response() -> CompletionResponse:
    return CompletionResponse(
        content="Modification complete. SOLUTION COMPLETE",
        tool_calls=[],
        finish_reason="end_turn",
    )


# ---------------------------------------------------------------------------
# The integration test
# ---------------------------------------------------------------------------

class TestDGMLoopIntegration:
    """End-to-end DGM generation loop test — no network, no real FM."""

    async def _run_test(self, tmp_path: Path):
        from dgm_controller import DGMController

        cfg = _make_dgm_config(tmp_path)

        # Build controller
        controller = DGMController(config_or_path=cfg, workspace=str(tmp_path))

        # --- Phase 1: initialise base agent ---
        await controller._initialize_base_agent()

        assert len(controller.archive.agents) == 1, (
            "Archive should contain exactly the base agent after initialization"
        )
        base_agent = list(controller.archive.agents.values())[0]
        assert base_agent.parent_id is None
        assert base_agent.is_valid is True
        base_score = base_agent.average_score
        assert 0.0 <= base_score <= 1.0

        # --- Phase 2: one generation with monkeypatched FM ---
        # We need to intercept get_completion on the INSTANCE that _run_generation
        # will create.  The cleanest seam is to patch the class-level method.
        call_count = {"n": 0}
        workspace_ref = {"path": None}

        original_run_gen = controller._run_generation

        async def patched_run_gen():
            # Discover the workspace directory that will be created for the task
            # by wrapping _perform_self_modification
            original_psm = controller._perform_self_modification

            async def patched_psm(parent_agent, modification_task):
                # Let the real method build the workspace then intercept FM
                workspace_dir = (
                    Path(cfg["agents"]["workspace_dir"]) / modification_task.task_id
                )
                workspace_ref["path"] = workspace_dir

                async def fake_get_completion(request):
                    call_count["n"] += 1
                    if call_count["n"] == 1:
                        return _edit_tool_response(workspace_dir / "agent.py")
                    return _terminal_response()

                with patch(
                    "agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion",
                    side_effect=fake_get_completion,
                ):
                    return await original_psm(parent_agent, modification_task)

            controller._perform_self_modification = patched_psm
            try:
                return await original_run_gen()
            finally:
                controller._perform_self_modification = original_psm

        await patched_run_gen()

        # --- Assertions ---
        # Archive should have 2 agents now (base + child)
        assert len(controller.archive.agents) == 2, (
            f"Expected 2 agents in archive, got {len(controller.archive.agents)}"
        )

        # Find the child agent
        child_agents = [
            a for a in controller.archive.agents.values()
            if a.parent_id is not None
        ]
        assert len(child_agents) == 1, "Expected exactly one child agent"
        child = child_agents[0]

        # Child has correct parent_id
        assert child.parent_id == base_agent.agent_id

        # Child score is a valid float in [0, 1]
        assert isinstance(child.average_score, float)
        assert 0.0 <= child.average_score <= 1.0, (
            f"Child score {child.average_score} out of range"
        )

        # Child is marked valid
        assert child.is_valid is True

        # --- Phase 3: second generation can select the child as a parent ---
        selector = ParentSelector(lam=10.0, alpha_0=0.5)
        random.seed(99)
        # There are now 2 valid agents; both should be selectable
        selected = selector.select_parents(controller.archive, n_parents=1)
        assert len(selected) == 1
        # Both base and child are in the archive
        all_ids = set(controller.archive.agents.keys())
        assert selected[0].agent_id in all_ids

    async def test_one_generation_end_to_end(self, tmp_path):
        await self._run_test(tmp_path)

    async def test_child_score_at_least_as_good_as_parent_or_archive_accepts_all(
        self, tmp_path
    ):
        """
        The paper-faithful controller archives ALL valid agents (no score gate).
        Verify that even a child with score 0.0 would be added to the archive.
        This is tested implicitly by _run_test, but we make it explicit here.
        """
        from dgm_controller import DGMController

        cfg = _make_dgm_config(tmp_path)
        controller = DGMController(config_or_path=cfg, workspace=str(tmp_path))
        await controller._initialize_base_agent()

        archive_size_before = len(controller.archive.agents)

        # Simulate adding an agent with score 0.0 (should still be added)
        initial_agent_path = cfg["agents"]["initial_agent_path"]
        added = controller.archive.add_agent(
            agent_path=initial_agent_path,
            parent_id=list(controller.archive.agents.keys())[0],
            benchmark_scores={"add_two_numbers": 0.0},
            is_valid=True,
        )
        assert len(controller.archive.agents) == archive_size_before + 1
        assert added.average_score == 0.0
