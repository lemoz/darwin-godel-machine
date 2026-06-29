"""
Unit tests for DGMController initialization and helper methods.
"""

import json
import pytest
import yaml
from pathlib import Path
from types import SimpleNamespace


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

    def test_init_loads_only_enabled_benchmarks(self, tmp_path):
        from dgm_controller import DGMController
        cfg = _minimal_config(tmp_path)
        extra = Path(cfg["evaluation"]["benchmarks_dir"]) / "unused.yaml"
        extra.write_text(yaml.dump({
            "name": "unused",
            "description": "unused",
            "task_prompt": "unused",
            "test_cases": [
                {"function_name": "f", "inputs": ["1"], "expected_outputs": ["1"]}
            ],
            "timeout": 5,
            "scoring_method": "pass_fail",
        }))

        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))

        assert set(ctrl.benchmark_runner.benchmarks) == {"dummy"}

    def test_should_stop_false_initially(self, tmp_path):
        from dgm_controller import DGMController
        cfg = _minimal_config(tmp_path)
        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))
        assert ctrl._should_stop() is False

    def test_should_stop_after_configured_consecutive_noops(self, tmp_path):
        from dgm_controller import DGMController
        cfg = _minimal_config(tmp_path)
        cfg["self_modification"] = {"max_consecutive_noop_mutations": 3}
        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))

        ctrl.consecutive_noop_mutations = 2
        assert ctrl._should_stop() is False

        ctrl.consecutive_noop_mutations = 3
        assert ctrl._should_stop() is True

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
        cfg["self_modification"] = {"max_steps": 7}
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
        assert "Self-modification turn budget: 7" in task.description
        assert "No-op attempts" in task.description
        assert "Do not use shell command chaining" in task.description
        assert "first source write" in task.description

    def test_parent_selection_non_regression_config_is_wired(self, tmp_path):
        from dgm_controller import DGMController

        cfg = _minimal_config(tmp_path)
        cfg["parent_selection"]["require_non_regression"] = True
        cfg["parent_selection"]["regression_tolerance"] = 0.01
        cfg["parent_selection"]["elite_selection_probability"] = 0.25

        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))

        assert ctrl.parent_selector.require_non_regression is True
        assert ctrl.parent_selector.regression_tolerance == pytest.approx(0.01)
        assert ctrl.parent_selector.elite_selection_probability == pytest.approx(0.25)

    def test_build_score_delta_metadata_marks_regressions(self, tmp_path):
        from archive.agent_archive import ArchivedAgent
        from dgm_controller import DGMController

        cfg = _minimal_config(tmp_path)
        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))
        parent = ArchivedAgent(
            agent_id="parent_001",
            parent_id=None,
            generation=0,
            source_path=str(tmp_path),
            created_at="2025-01-01T00:00:00",
            benchmark_scores={"a": 1.0, "b": 0.0},
            average_score=0.5,
            is_valid=True,
            metadata={},
        )

        metadata = ctrl._build_score_delta_metadata(
            parent,
            {"a": 0.0, "b": 1.0},
        )

        assert metadata["average_delta"] == pytest.approx(0.0)
        assert metadata["benchmark_improvements"] == {"b": 1.0}
        assert metadata["benchmark_regressions"] == {"a": -1.0}
        assert metadata["has_benchmark_regression"] is True
        assert metadata["selection_non_regression_eligible"] is False

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

    def test_init_disables_sandbox_when_manager_not_ready(self, tmp_path, monkeypatch):
        from dgm_controller import DGMController

        class NotReadySandboxManager:
            def __init__(self, config):
                self.config = config

            def is_sandbox_ready(self):
                return False

        monkeypatch.setattr("dgm_controller.SandboxManager", NotReadySandboxManager)
        cfg = _minimal_config(tmp_path)
        cfg["evaluation"]["use_sandbox"] = True

        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))

        assert ctrl.sandbox_manager is None
        assert ctrl.use_sandbox is False
        assert ctrl.benchmark_runner.sandbox_manager is None
        assert ctrl.benchmark_runner.use_sandbox is False
        assert ctrl.validator.sandbox_manager is None
        assert ctrl.validator.use_sandbox is False

    async def test_self_modification_solution_write_uses_sandbox_edit_tool(
        self,
        tmp_path,
        monkeypatch,
    ):
        from archive.agent_archive import ArchivedAgent
        from agent.agent import Task
        from dgm_controller import DGMController
        from sandbox.sandbox_manager import SandboxResult

        class FakeSandboxManager:
            instances = []

            def __init__(self, config):
                self.config = config
                self.calls = []
                self.instances.append(self)

            def is_sandbox_ready(self):
                return True

            async def execute_in_sandbox(
                self,
                command,
                agent_code_path=None,
                workspace_path=None,
                timeout=None,
            ):
                params_path = Path(workspace_path) / ".dgm_edit_tool_params.json"
                params = json.loads(params_path.read_text(encoding="utf-8"))
                Path(workspace_path, params["file_path"]).write_text(
                    params["content"],
                    encoding="utf-8",
                )
                self.calls.append({
                    "command": command,
                    "agent_code_path": agent_code_path,
                    "workspace_path": workspace_path,
                    "timeout": timeout,
                })
                return SandboxResult(
                    success=True,
                    output=json.dumps({
                        "status": "success",
                        "output": "wrote agent.py",
                        "error": "",
                    }),
                    exit_code=0,
                    execution_time=0.1,
                )

        solution = (
            "class Agent:\n"
            "    def __init__(self, config=None): pass\n"
            "    def solve_task(self, task): return 'done'\n"
        )

        class FakeAgent:
            def __init__(self, config):
                self.config = config

            async def solve_task(self, task):
                return {"success": True, "solution": solution}

        monkeypatch.setattr("dgm_controller.SandboxManager", FakeSandboxManager)
        monkeypatch.setattr("dgm_controller.Agent", FakeAgent)

        cfg = _minimal_config(tmp_path)
        cfg["evaluation"]["use_sandbox"] = True
        cfg["evaluation"]["timeout_seconds"] = 9
        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))

        parent_dir = tmp_path / "parent_agent"
        parent_dir.mkdir()
        (parent_dir / "agent.py").write_text(
            "class Agent:\n"
            "    def __init__(self, config=None): pass\n"
            "    def solve_task(self, task): return 'old'\n",
            encoding="utf-8",
        )
        parent = ArchivedAgent(
            agent_id="parent_001",
            parent_id=None,
            generation=0,
            source_path=str(parent_dir / "agent.py"),
            created_at="2026-06-15T00:00:00",
            benchmark_scores={"dummy": 0.0},
            average_score=0.0,
            is_valid=True,
            metadata={},
        )
        task = Task(task_id="self_modify_parent_001_0", description="modify")

        result_path = await ctrl._perform_self_modification(parent, task)

        assert result_path is not None
        result_file = Path(result_path)
        assert result_file.read_text(encoding="utf-8") == solution
        assert not (result_file.parent / ".dgm_edit_tool_params.json").exists()
        sandbox_manager = FakeSandboxManager.instances[0]
        assert len(sandbox_manager.calls) == 1
        assert sandbox_manager.calls[0]["timeout"] == 9
        assert sandbox_manager.calls[0]["workspace_path"] != str(result_file.parent)
        mutation = ctrl._mutation_metadata_by_agent_path[str(result_file.resolve())]
        assert mutation["mutation_status"] == "changed"
        assert mutation["changed_code_files"] == ["agent.py"]
        assert (result_file.parent / ".dgm_metadata" / "mutation.json").exists()
        assert (result_file.parent / ".dgm_metadata" / "mutation.patch").exists()

    async def test_self_modification_noop_records_mutation_metadata(
        self,
        tmp_path,
        monkeypatch,
    ):
        from archive.agent_archive import ArchivedAgent
        from agent.agent import Task
        from dgm_controller import DGMController

        class NoopAgent:
            def __init__(self, config):
                self.config = config

            async def solve_task(self, task):
                return {"success": True, "solution": ""}

        monkeypatch.setattr("dgm_controller.Agent", NoopAgent)

        cfg = _minimal_config(tmp_path)
        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))

        parent_dir = tmp_path / "parent_agent"
        parent_dir.mkdir()
        (parent_dir / "agent.py").write_text(
            "class Agent:\n"
            "    def __init__(self, config=None): pass\n"
            "    def solve_task(self, task): return 'old'\n",
            encoding="utf-8",
        )
        parent = ArchivedAgent(
            agent_id="parent_001",
            parent_id=None,
            generation=0,
            source_path=str(parent_dir / "agent.py"),
            created_at="2026-06-15T00:00:00",
            benchmark_scores={"dummy": 0.0},
            average_score=0.0,
            is_valid=True,
            metadata={},
        )

        result_path = await ctrl._perform_self_modification(
            parent,
            Task(task_id="self_modify_parent_001_0", description="modify"),
        )

        assert result_path is not None
        result_file = Path(result_path)
        mutation = ctrl._mutation_metadata_by_agent_path[str(result_file.resolve())]
        assert mutation["mutation_status"] == "noop"
        assert mutation["has_code_changes"] is False
        assert mutation["changed_code_files"] == []
        assert mutation["changed_files"] == []
        archived_metadata = result_file.parent / ".dgm_metadata" / "mutation.json"
        assert json.loads(archived_metadata.read_text(encoding="utf-8"))[
            "mutation_status"
        ] == "noop"

    async def test_self_modification_uses_self_modification_step_budget(
        self,
        tmp_path,
        monkeypatch,
    ):
        from archive.agent_archive import ArchivedAgent
        from agent.agent import Task
        from dgm_controller import DGMController

        captured = {}

        class CapturingAgent:
            def __init__(self, config):
                captured["max_iterations"] = config.max_iterations

            async def solve_task(self, task):
                return {"success": True, "solution": ""}

        monkeypatch.setattr("dgm_controller.Agent", CapturingAgent)

        cfg = _minimal_config(tmp_path)
        cfg["agents"]["max_steps"] = 1
        cfg["self_modification"] = {"max_steps": 7}
        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))

        parent_dir = tmp_path / "parent_agent"
        parent_dir.mkdir()
        (parent_dir / "agent.py").write_text(
            "class Agent:\n"
            "    def __init__(self, config=None): pass\n"
            "    def solve_task(self, task): return 'old'\n",
            encoding="utf-8",
        )
        parent = ArchivedAgent(
            agent_id="parent_001",
            parent_id=None,
            generation=0,
            source_path=str(parent_dir / "agent.py"),
            created_at="2026-06-15T00:00:00",
            benchmark_scores={"dummy": 0.0},
            average_score=0.0,
            is_valid=True,
            metadata={},
        )

        result_path = await ctrl._perform_self_modification(
            parent,
            Task(task_id="self_modify_parent_001_0", description="modify"),
        )

        assert result_path is not None
        assert captured["max_iterations"] == 7

    async def test_run_generation_archives_noop_without_evaluation(
        self,
        tmp_path,
        monkeypatch,
    ):
        from dgm_controller import DGMController

        cfg = _minimal_config(tmp_path)
        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))

        parent_dir = tmp_path / "parent_agent"
        parent_dir.mkdir()
        parent_file = parent_dir / "agent.py"
        parent_file.write_text(
            "class Agent:\n"
            "    def __init__(self, config=None): pass\n"
            "    def solve_task(self, task): return 'old'\n",
            encoding="utf-8",
        )
        parent = ctrl.archive.add_agent(
            agent_path=str(parent_file),
            benchmark_scores={"dummy": 1.0},
            is_valid=True,
        )

        child_dir = tmp_path / "workspace" / "noop_child"
        child_dir.mkdir(parents=True)
        child_file = child_dir / "agent.py"
        child_file.write_text(parent_file.read_text(encoding="utf-8"), encoding="utf-8")
        mutation = {
            "schema_version": 1,
            "task_id": "self_modify_parent_001_1",
            "parent_agent_id": parent.agent_id,
            "mutation_status": "noop",
            "has_code_changes": False,
            "changed_files": [],
            "changed_code_files": [],
        }
        ctrl._mutation_metadata_by_agent_path[str(child_file.resolve())] = mutation

        async def fake_perform_self_modification(parent_agent, modification_task):
            return str(child_file)

        async def fail_validate(agent_path):
            raise AssertionError("noop child should not be validated")

        async def fail_evaluate(agent_path):
            raise AssertionError("noop child should not be evaluated")

        monkeypatch.setattr(
            ctrl,
            "_perform_self_modification",
            fake_perform_self_modification,
        )
        monkeypatch.setattr(ctrl.validator, "validate_agent", fail_validate)
        monkeypatch.setattr(ctrl, "_evaluate_agent", fail_evaluate)

        await ctrl._run_generation()

        children = [
            agent for agent in ctrl.archive.agents.values()
            if agent.parent_id == parent.agent_id
        ]
        assert len(children) == 1
        child = children[0]
        assert child.is_valid is False
        assert child.benchmark_scores == {}
        assert child.metadata["mutation"]["mutation_status"] == "noop"
        assert ctrl.consecutive_noop_mutations == 1

    async def test_evaluate_agent_passes_sandbox_config_to_loaded_agent(
        self,
        tmp_path,
        monkeypatch,
    ):
        from dgm_controller import DGMController

        class FakeSandboxManager:
            def __init__(self, config):
                self.config = config

            def is_sandbox_ready(self):
                return True

        monkeypatch.setattr("dgm_controller.SandboxManager", FakeSandboxManager)
        cfg = _minimal_config(tmp_path)
        cfg["evaluation"]["use_sandbox"] = True
        ctrl = DGMController(config_or_path=cfg, workspace=str(tmp_path))

        agent_file = tmp_path / "candidate_agent.py"
        agent_file.write_text(
            "class Agent:\n"
            "    def __init__(self, config): self.config = config\n"
            "    def solve_task(self, task): return {'success': True, 'solution': ''}\n",
            encoding="utf-8",
        )

        captured = {}

        class LoadedAgent:
            def __init__(self, config):
                captured["config"] = config
                self.config = config
                self.agent_id = config.agent_id

            async def close(self):
                captured["closed"] = True

        ctrl.agent_loader.load_from_path = lambda _path: LoadedAgent

        async def fake_run_benchmark(agent, benchmark_name, verbose=False):
            captured["agent"] = agent
            captured["benchmark_name"] = benchmark_name
            captured["verbose"] = verbose
            Path(agent.config.working_directory, "solution.py").write_text(
                "generated scratch solution\n",
                encoding="utf-8",
            )
            return SimpleNamespace(score=0.75)

        ctrl.benchmark_runner.run_benchmark = fake_run_benchmark

        scores = await ctrl._evaluate_agent(str(agent_file))

        assert scores == {"dummy": 0.75}
        assert captured["config"].sandbox_manager is ctrl.sandbox_manager
        assert captured["config"].use_sandbox is True
        assert captured["config"].working_directory != str(agent_file.parent)
        assert "dgm-benchmark-" in Path(captured["config"].working_directory).name
        assert not (agent_file.parent / "solution.py").exists()
        assert not Path(captured["config"].working_directory).exists()
        assert captured["agent"].config is captured["config"]
        assert captured["benchmark_name"] == "dummy"
        assert captured["verbose"] is False
        assert captured["closed"] is True
