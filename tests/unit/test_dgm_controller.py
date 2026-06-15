"""
Unit tests for DGMController initialization and helper methods.
"""

import pytest
import yaml
from pathlib import Path


def _minimal_config(tmp_path: Path) -> dict:
    bench_dir = tmp_path / "benchmarks"
    bench_dir.mkdir()
    (bench_dir / "dummy.yaml").write_text(yaml.dump({
        "name": "dummy",
        "description": "dummy",
        "task_prompt": "dummy",
        "test_cases": [
            {"function_name": "f", "inputs": ["1"], "expected_outputs": ["1"]}
        ],
        "timeout": 5,
        "scoring_method": "pass_fail",
    }))
    for d in ("archive", "results", "workspace"):
        (tmp_path / d).mkdir()
    initial = tmp_path / "agent.py"
    # Must use sync def — validator only recognises ast.FunctionDef (production bug).
    initial.write_text(
        'class Agent:\n'
        '    def __init__(self, config): self.fm_interface = None; self.tools = []\n'
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
        "archive": {"path": str(tmp_path / "archive")},
        "parent_selection": {"lambda": 10, "alpha_0": 0.5},
        "evaluation": {
            "benchmarks_dir": str(bench_dir),
            "results_dir": str(tmp_path / "results"),
        },
        "agents": {
            "workspace_dir": str(tmp_path / "workspace"),
            "initial_agent_path": str(initial),
            "max_steps": 1,
        },
        "benchmarks": {"enabled": ["dummy"]},
        "logging": {"level": "WARNING"},
    }


class TestDGMControllerInit:

    def test_init_from_dict(self, tmp_path):
        from dgm_controller import DGMController
        cfg = _minimal_config(tmp_path)
        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))
        assert ctrl.archive is not None
        assert ctrl.parent_selector is not None
        assert ctrl.benchmark_runner is not None
        assert ctrl.validator is not None
        assert ctrl.generation == 0

    def test_archive_dir_created_on_init(self, tmp_path):
        from dgm_controller import DGMController
        cfg = _minimal_config(tmp_path)
        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))
        assert Path(cfg["archive"]["path"]).exists()

    def test_results_dir_created_on_init(self, tmp_path):
        from dgm_controller import DGMController
        cfg = _minimal_config(tmp_path)
        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))
        assert Path(cfg["evaluation"]["results_dir"]).exists()

    def test_should_stop_false_initially(self, tmp_path):
        from dgm_controller import DGMController
        cfg = _minimal_config(tmp_path)
        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))
        assert ctrl._should_stop() is False

    def test_get_or_create_initial_agent(self, tmp_path):
        from dgm_controller import DGMController
        cfg = _minimal_config(tmp_path)
        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))
        agent_id = ctrl.get_or_create_initial_agent()
        assert agent_id == "agent_0"
        agent_path = Path(ctrl.workspace) / "agents" / agent_id
        assert agent_path.exists()
        assert (agent_path / "agent.py").exists()

    def test_get_or_create_initial_agent_idempotent(self, tmp_path):
        from dgm_controller import DGMController
        cfg = _minimal_config(tmp_path)
        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))
        id1 = ctrl.get_or_create_initial_agent()
        id2 = ctrl.get_or_create_initial_agent()
        assert id1 == id2

    def test_create_modification_task_returns_task(self, tmp_path):
        from dgm_controller import DGMController
        from archive.agent_archive import ArchivedAgent
        cfg = _minimal_config(tmp_path)
        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))

        mock_parent = ArchivedAgent(
            agent_id="parent_001",
            parent_id=None,
            generation=0,
            source_path=str(tmp_path),
            created_at="2025-01-01T00:00:00",
            benchmark_scores={"dummy": 0.7},
            average_score=0.7,
            is_valid=True,
            metadata={},
        )
        task = ctrl._create_modification_task(mock_parent)
        from agent.agent import Task
        assert isinstance(task, Task)
        assert "0.700" in task.description or "0.7" in task.description

    def test_env_var_expansion(self, tmp_path, monkeypatch):
        """${VAR} in config values should be expanded from environment."""
        from dgm_controller import DGMController
        monkeypatch.setenv("MY_TEST_VAR", "expanded_value")
        cfg = _minimal_config(tmp_path)
        cfg["custom_setting"] = "${MY_TEST_VAR}"
        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))
        assert ctrl.config["custom_setting"] == "expanded_value"

    def test_redacts_sensitive_values_before_logging(self, tmp_path):
        from dgm_controller import DGMController
        cfg = _minimal_config(tmp_path)
        cfg["nested"] = {
            "api_token": "tok_live",
            "items": [{"password": "pw_live"}, {"safe": "visible"}],
        }

        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))
        redacted = ctrl._redact_sensitive_values(ctrl.config)

        assert redacted["fm_providers"]["anthropic"]["api_key"] == "[REDACTED]"
        assert redacted["fm_providers"]["anthropic"]["max_tokens"] == 128
        assert redacted["nested"]["api_token"] == "[REDACTED]"
        assert redacted["nested"]["items"][0]["password"] == "[REDACTED]"
        assert redacted["nested"]["items"][1]["safe"] == "visible"

    def test_init_wires_sandbox_manager_when_enabled(self, tmp_path, monkeypatch):
        from dgm_controller import DGMController

        class FakeSandboxManager:
            def __init__(self, config):
                self.config = config

        monkeypatch.setattr("dgm_controller.SandboxManager", FakeSandboxManager)
        cfg = _minimal_config(tmp_path)
        cfg["evaluation"]["use_sandbox"] = True
        cfg["sandbox"] = {"image_name": "custom-sandbox"}

        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))

        assert isinstance(ctrl.sandbox_manager, FakeSandboxManager)
        assert ctrl.sandbox_manager.config.image_name == "custom-sandbox"
        assert ctrl.use_sandbox is True
        assert ctrl.benchmark_runner.sandbox_manager is ctrl.sandbox_manager
        assert ctrl.benchmark_runner.use_sandbox is True
        assert ctrl.validator.sandbox_manager is ctrl.sandbox_manager
        assert ctrl.validator.use_sandbox is True
