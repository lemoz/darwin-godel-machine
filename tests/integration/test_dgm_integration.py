"""
Basic integration test: DGMController can be instantiated with a minimal config dict.
(The heavy end-to-end loop is in test_dgm_loop.py.)
"""

import pytest
import yaml
from pathlib import Path


def _make_minimal_config(tmp_path: Path) -> dict:
    bench_dir = tmp_path / "benchmarks"
    bench_dir.mkdir()
    # Write a valid (but trivially simple) benchmark
    cfg = {
        "name": "dummy",
        "description": "dummy",
        "task_prompt": "dummy",
        "test_cases": [
            {"function_name": "f", "inputs": ["1"], "expected_outputs": ["1"]}
        ],
        "timeout": 5,
        "scoring_method": "pass_fail",
    }
    (bench_dir / "dummy.yaml").write_text(yaml.dump(cfg))

    arc_dir = tmp_path / "archive"
    results_dir = tmp_path / "results"
    workspace_dir = tmp_path / "workspace"
    for d in (arc_dir, results_dir, workspace_dir):
        d.mkdir()

    initial = tmp_path / "agent.py"
    # Must use sync def — validator only recognises ast.FunctionDef (production bug).
    initial.write_text(
        'class Agent:\n'
        '    def __init__(self, config): pass\n'
        '    def solve_task(self, task):\n'
        '        async def _r(): return {"success": True, "solution": ""}\n'
        '        return _r()\n'
    )

    return {
        "fm_providers": {
            "primary": "anthropic",
            "anthropic": {
                "model": "claude-sonnet-4-6",
                "api_key": "test-dummy",
                "max_tokens": 128,
                "temperature": 0.0,
                "timeout": 5,
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
            "initial_agent_path": str(initial),
            "max_steps": 1,
        },
        "benchmarks": {"enabled": ["dummy"]},
        "logging": {"level": "WARNING"},
    }


class TestDGMControllerInit:

    def test_controller_init_from_dict(self, tmp_path):
        """DGMController can be constructed from a config dict without raising."""
        from dgm_controller import DGMController
        cfg = _make_minimal_config(tmp_path)
        controller = DGMController(config_or_path=cfg, workspace=str(tmp_path))
        assert controller is not None
        assert controller.archive is not None
        assert controller.parent_selector is not None
        assert controller.benchmark_runner is not None
        assert controller.validator is not None

    def test_archive_dir_created(self, tmp_path):
        from dgm_controller import DGMController
        cfg = _make_minimal_config(tmp_path)
        controller = DGMController(config_or_path=cfg, workspace=str(tmp_path))
        assert Path(cfg["archive"]["path"]).exists()

    def test_initial_archive_is_empty(self, tmp_path):
        from dgm_controller import DGMController
        cfg = _make_minimal_config(tmp_path)
        controller = DGMController(config_or_path=cfg, workspace=str(tmp_path))
        assert len(controller.archive.agents) == 0
