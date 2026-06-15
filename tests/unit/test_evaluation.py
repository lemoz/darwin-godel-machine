"""
Unit tests for evaluation components: BenchmarkRunner internals, BenchmarkScorer,
and AgentValidator.

No network calls. BenchmarkRunner tests exercise _build_test_script and _run_test_case
directly with hand-written Python solutions in tmp_path.
"""

import asyncio
import pytest
import yaml
from pathlib import Path
from unittest.mock import MagicMock

from evaluation.benchmark_runner import BenchmarkRunner, BenchmarkTask, BenchmarkResult
from evaluation.scorer import (
    BenchmarkScorer, BinaryScorer, PartialCreditScorer,
    JsonScorer, FunctionOutputScorer
)
from evaluation.agent_validator import AgentValidator
from sandbox.sandbox_manager import SandboxManager, SandboxResult


# ---------------------------------------------------------------------------
# BenchmarkTask helpers
# ---------------------------------------------------------------------------

def _make_task(tmp_path: Path, name: str = "add_task") -> BenchmarkTask:
    """Write a YAML benchmark config and return a BenchmarkTask."""
    config = {
        "name": name,
        "description": "Add two numbers",
        "task_prompt": "Write a function add(a, b) that returns a+b",
        "test_cases": [
            {
                "function_name": "add",
                "inputs": ["1, 2", "10, 20", "-1, 1"],
                "expected_outputs": ["3", "30", "0"],
            }
        ],
        "timeout": 10,
        "scoring_method": "partial",
    }
    p = tmp_path / f"{name}.yaml"
    p.write_text(yaml.dump(config))
    return BenchmarkTask.from_config(str(p))


def _make_runner(tmp_path: Path, task: BenchmarkTask) -> BenchmarkRunner:
    """Build a BenchmarkRunner whose benchmarks dir contains only task."""
    bdir = tmp_path / "benchmarks"
    bdir.mkdir(exist_ok=True)
    cfg = {
        "name": task.name,
        "description": task.description,
        "task_prompt": task.task_prompt,
        "test_cases": task.test_cases,
        "timeout": task.timeout,
        "scoring_method": task.scoring_method,
    }
    (bdir / f"{task.name}.yaml").write_text(yaml.dump(cfg))
    return BenchmarkRunner(benchmarks_dir=str(bdir), use_sandbox=False)


# ---------------------------------------------------------------------------
# BenchmarkRunner._build_test_script tests
# ---------------------------------------------------------------------------

class TestBuildTestScript:

    def test_correct_solution_returns_success(self, tmp_path):
        solution_file = str(tmp_path / "sol.py")
        Path(solution_file).write_text("def add(a, b): return a + b\n")
        script = BenchmarkRunner._build_test_script(
            solution_file, "add", "1, 2", "3", 0
        )
        assert "add" in script
        assert repr("1, 2") in script

    def test_wrong_solution_returns_failure(self, tmp_path):
        """Run the generated script for a wrong solution and check JSON output."""
        import subprocess, json
        solution_file = str(tmp_path / "wrong.py")
        Path(solution_file).write_text("def add(a, b): return a - b\n")
        script = BenchmarkRunner._build_test_script(
            solution_file, "add", "1, 2", "3", 0
        )
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout.strip().split("\n")[-1])
        assert data["success"] is False

    def test_correct_solution_script_produces_success_json(self, tmp_path):
        import subprocess, json
        solution_file = str(tmp_path / "correct.py")
        Path(solution_file).write_text("def add(a, b): return a + b\n")
        script = BenchmarkRunner._build_test_script(
            solution_file, "add", "1, 2", "3", 0
        )
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout.strip().split("\n")[-1])
        assert data["success"] is True


# ---------------------------------------------------------------------------
# BenchmarkRunner._run_test_case async tests
# ---------------------------------------------------------------------------

class TestRunTestCase:

    async def test_correct_solution_all_pass(self, tmp_path):
        task = _make_task(tmp_path)
        runner = _make_runner(tmp_path, task)
        solution = "def add(a, b):\n    return a + b\n"
        result = await runner._run_test_case(solution, task.test_cases[0], task)
        assert result["success"] is True
        assert result["passed"] == result["total"] == 3

    async def test_wrong_solution_all_fail(self, tmp_path):
        task = _make_task(tmp_path)
        runner = _make_runner(tmp_path, task)
        solution = "def add(a, b):\n    return a * b\n"  # wrong
        result = await runner._run_test_case(solution, task.test_cases[0], task)
        assert result["success"] is False
        assert result["passed"] < result["total"]

    async def test_invalid_function_name_blocked(self, tmp_path):
        """function_name with spaces/special chars should be rejected."""
        task = _make_task(tmp_path)
        runner = _make_runner(tmp_path, task)
        bad_test_case = {
            "function_name": "add; import os",
            "inputs": ["1, 2"],
            "expected_outputs": ["3"],
        }
        result = await runner._run_test_case("def add(a, b): return a+b", bad_test_case, task)
        assert result["success"] is False
        assert "Invalid function_name" in result.get("error", "")

    async def test_timeout_kills_slow_solution(self, tmp_path):
        task = _make_task(tmp_path)
        # Override timeout to 1 second
        task2 = BenchmarkTask(
            name=task.name,
            description=task.description,
            task_prompt=task.task_prompt,
            test_cases=[{
                "function_name": "add",
                "inputs": ["1, 2"],
                "expected_outputs": ["3"],
            }],
            timeout=1,
            validation_code="",
            scoring_method="partial",
        )
        runner = _make_runner(tmp_path, task2)
        # Solution that sleeps forever
        solution = "import time\ndef add(a, b):\n    time.sleep(30)\n    return a + b\n"
        result = await runner._run_test_case(solution, task2.test_cases[0], task2)
        assert result["success"] is False
        # at least one individual result should mention timeout
        errors = [
            r.get("error", "") for r in result.get("individual_results", [])
        ]
        assert any("Timeout" in (e or "") or "timeout" in (e or "") for e in errors), (
            f"Expected timeout error, got: {errors}"
        )

    async def test_uses_sandbox_manager_when_available(self, tmp_path):
        task = _make_task(tmp_path)

        class FakeConfig:
            working_dir = "/home/dgm_agent/workspace"

        class FakeSandboxManager:
            config = FakeConfig()

            def __init__(self):
                self.calls = []

            def is_docker_available(self):
                return True

            async def execute_in_sandbox(self, command, workspace_path, timeout, **kwargs):
                self.calls.append({
                    "command": command,
                    "workspace_path": workspace_path,
                    "timeout": timeout,
                    "kwargs": kwargs,
                })
                return SandboxResult(
                    success=True,
                    output='{"success": true, "actual_output": "3", "expected_output": "3", "error": null}\n',
                    exit_code=0,
                )

        fake_sandbox = FakeSandboxManager()
        runner = _make_runner(tmp_path, task)
        runner.use_sandbox = True
        runner.sandbox_manager = fake_sandbox

        result = await runner._run_test_case(
            "def add(a, b):\n    return a + b\n",
            task.test_cases[0],
            task,
        )

        assert result["success"] is True
        assert result["passed"] == result["total"] == 3
        assert len(fake_sandbox.calls) == 3
        assert all(call["command"].startswith("python test_case_") for call in fake_sandbox.calls)

    async def test_sandbox_request_falls_back_when_unavailable(self, tmp_path):
        task = _make_task(tmp_path)

        class UnavailableSandboxManager:
            def __init__(self):
                self.calls = []

            def is_docker_available(self):
                return False

            async def execute_in_sandbox(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                raise AssertionError("Sandbox should not be used when unavailable")

        sandbox_manager = UnavailableSandboxManager()
        runner = _make_runner(tmp_path, task)
        runner.use_sandbox = True
        runner.sandbox_manager = sandbox_manager

        result = await runner._run_test_case(
            "def add(a, b):\n    return a + b\n",
            task.test_cases[0],
            task,
        )

        assert result["success"] is True
        assert result["passed"] == result["total"] == 3
        assert sandbox_manager.calls == []

    async def test_sandbox_request_falls_back_when_not_ready_at_runtime(
        self,
        tmp_path,
    ):
        task = _make_task(tmp_path)

        class NotReadySandboxManager:
            def __init__(self):
                self.calls = []

            def is_sandbox_ready(self):
                return False

            async def execute_in_sandbox(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                raise AssertionError("Sandbox should not be used when not ready")

        sandbox_manager = NotReadySandboxManager()
        runner = _make_runner(tmp_path, task)
        runner.use_sandbox = True
        runner.sandbox_manager = sandbox_manager

        result = await runner._run_test_case(
            "def add(a, b):\n    return a + b\n",
            task.test_cases[0],
            task,
        )

        assert result["success"] is True
        assert result["passed"] == result["total"] == 3
        assert sandbox_manager.calls == []

    def test_constructor_disables_sandbox_when_manager_not_ready(self, tmp_path):
        task = _make_task(tmp_path)

        class NotReadySandboxManager:
            def is_sandbox_ready(self):
                return False

        bdir = tmp_path / "benchmarks"
        bdir.mkdir(exist_ok=True)
        cfg = {
            "name": task.name,
            "description": task.description,
            "task_prompt": task.task_prompt,
            "test_cases": task.test_cases,
            "timeout": task.timeout,
            "scoring_method": task.scoring_method,
        }
        (bdir / f"{task.name}.yaml").write_text(yaml.dump(cfg))

        runner = BenchmarkRunner(
            benchmarks_dir=str(bdir),
            sandbox_manager=NotReadySandboxManager(),
            use_sandbox=True,
        )

        assert runner.use_sandbox is False


class TestSandboxManager:

    def test_cpu_limit_to_nano_cpus(self):
        assert SandboxManager._cpu_limit_to_nano_cpus("1") == 1_000_000_000
        assert SandboxManager._cpu_limit_to_nano_cpus("0.5") == 500_000_000
        assert SandboxManager._cpu_limit_to_nano_cpus("bad") is None
        assert SandboxManager._cpu_limit_to_nano_cpus("0") is None

    def test_sandbox_ready_requires_docker_and_image(self, monkeypatch):
        manager = SandboxManager()

        monkeypatch.setattr(manager, "is_docker_available", lambda: False)
        assert manager.is_sandbox_ready() is False

        calls = []
        monkeypatch.setattr(manager, "is_docker_available", lambda: True)
        monkeypatch.setattr(manager, "ensure_sandbox_image", lambda: calls.append("ok"))
        assert manager.is_sandbox_ready() is True
        assert calls == ["ok"]

        def fail_image():
            raise RuntimeError("image unavailable")

        monkeypatch.setattr(manager, "ensure_sandbox_image", fail_image)
        assert manager.is_sandbox_ready() is False


# ---------------------------------------------------------------------------
# BenchmarkScorer tests
# ---------------------------------------------------------------------------

class TestBenchmarkScorer:

    def _make_runner_results(self, successes):
        """Build a result list in the runner format for simple pass/fail."""
        results = []
        for success in successes:
            results.append({
                "individual_results": [{
                    "success": success,
                    "actual_output": "3" if success else "0",
                    "expected_output": "3",
                    "error": None,
                }],
                "passed": 1 if success else 0,
                "total": 1,
            })
        return results

    def test_score_benchmark_empty_results(self):
        scorer = BenchmarkScorer()
        out = scorer.score_benchmark({"scoring": {"method": "binary"}}, [])
        assert out["total_score"] == 0.0
        assert out["passed_tests"] == 0
        assert out["total_tests"] == 0

    def test_score_benchmark_all_pass(self):
        scorer = BenchmarkScorer()
        results = self._make_runner_results([True, True, True])
        out = scorer.score_benchmark({"scoring": {"method": "binary"}}, results)
        assert out["total_score"] == pytest.approx(1.0)
        assert out["passed_tests"] == 3

    def test_score_benchmark_all_fail(self):
        scorer = BenchmarkScorer()
        results = self._make_runner_results([False, False])
        out = scorer.score_benchmark({}, results)
        assert out["total_score"] == pytest.approx(0.0)

    def test_score_benchmark_partial(self):
        scorer = BenchmarkScorer()
        results = self._make_runner_results([True, False, True, False])
        out = scorer.score_benchmark({"scoring": {"method": "partial"}}, results)
        assert out["total_score"] == pytest.approx(0.5)

    def test_score_benchmark_top_level_error(self):
        scorer = BenchmarkScorer()
        results = [{"error": "ImportError", "success": False}]
        out = scorer.score_benchmark({}, results)
        assert out["total_score"] == 0.0

    def test_binary_scorer_strict(self):
        scorer = BinaryScorer(strict=True)
        assert scorer.score("hello", "hello", {}) == 1.0
        assert scorer.score("hello ", "hello", {}) == 0.0

    def test_binary_scorer_non_strict(self):
        scorer = BinaryScorer(strict=False)
        assert scorer.score("hello ", " hello", {}) == 1.0

    def test_partial_credit_scorer_identical(self):
        scorer = PartialCreditScorer()
        assert scorer.score("abc", "abc", {}) == 1.0

    def test_json_scorer_partial_credit(self):
        scorer = JsonScorer(partial_credit=True)
        actual = '{"a": 1, "b": 2}'
        expected = '{"a": 1, "b": 99}'
        score = scorer.score(actual, expected, {})
        assert 0.0 < score < 1.0

    def test_json_scorer_perfect_match(self):
        scorer = JsonScorer()
        s = '{"x": 10}'
        assert scorer.score(s, s, {}) == 1.0

    def test_function_output_scorer_single(self):
        scorer = FunctionOutputScorer()
        assert scorer.score("3", "3", {}) == 1.0
        assert scorer.score("0", "3", {}) == 0.0

    def test_benchmark_scorer_selects_binary_by_default(self):
        scorer = BenchmarkScorer()
        s = scorer.get_scorer({})
        assert isinstance(s, BinaryScorer)


# ---------------------------------------------------------------------------
# AgentValidator tests
# ---------------------------------------------------------------------------

MINIMAL_AGENT = '''\
"""Minimal valid agent."""

class Agent:
    def __init__(self):
        self.fm_interface = None
        self.tools = []

    def solve_task(self, task):
        # NB: validator only recognises ast.FunctionDef, not ast.AsyncFunctionDef
        # (production bug: async solve_task is NOT detected by the validator).
        # Tests must use a sync stub to pass current validation.
        return "done"
'''

BROKEN_SYNTAX_AGENT = '''\
class Agent:
    def __init__(self
    # syntax error here
'''

NO_AGENT_CLASS = '''\
class Helper:
    def __init__(self):
        pass
'''


class TestAgentValidator:

    async def test_valid_agent_file_passes(self, tmp_path):
        f = tmp_path / "agent.py"
        f.write_text(MINIMAL_AGENT)
        validator = AgentValidator()
        result = await validator.validate_agent(str(f))
        assert result["valid"] is True, f"Errors: {result['errors']}"

    async def test_syntax_error_fails(self, tmp_path):
        f = tmp_path / "agent.py"
        f.write_text(BROKEN_SYNTAX_AGENT)
        validator = AgentValidator()
        result = await validator.validate_agent(str(f))
        assert result["valid"] is False
        assert any("Syntax" in e or "syntax" in e for e in result["errors"])

    async def test_no_agent_class_warns_but_passes(self, tmp_path):
        """
        Production note: validator treats a missing Agent class as a WARNING,
        not an error (valid=True). This is a known limitation — the validator
        only errors when required methods are missing from a found class.
        """
        f = tmp_path / "agent.py"
        f.write_text(NO_AGENT_CLASS)
        validator = AgentValidator()
        result = await validator.validate_agent(str(f))
        # Current production behaviour: no-Agent-class yields warnings only
        assert any("Agent" in w for w in result["warnings"])

    async def test_missing_file_fails(self, tmp_path):
        validator = AgentValidator()
        result = await validator.validate_agent(str(tmp_path / "ghost.py"))
        # _validate_structure will fail because suffix is .py but file doesn't exist
        # OR _validate_syntax will fail when trying to read it
        assert result["valid"] is False

    async def test_non_py_file_fails(self, tmp_path):
        f = tmp_path / "agent.txt"
        f.write_text("hello")
        validator = AgentValidator()
        result = await validator.validate_agent(str(f))
        assert result["valid"] is False

    async def test_validation_summary_is_string(self, tmp_path):
        f = tmp_path / "agent.py"
        f.write_text(MINIMAL_AGENT)
        validator = AgentValidator()
        result = await validator.validate_agent(str(f))
        summary = validator.get_validation_summary(result)
        assert isinstance(summary, str)
        assert "Agent Validation Summary" in summary

    async def test_runtime_load_uses_sandbox_when_enabled(self, tmp_path):
        f = tmp_path / "agent.py"
        f.write_text(
            'from pathlib import Path\n'
            'Path(__file__).with_name("host_import_marker.txt").write_text("bad")\n'
            'class Agent:\n'
            '    def __init__(self): pass\n'
            '    def solve_task(self, task): return "done"\n'
        )

        class FakeSandboxManager:
            def __init__(self):
                self.calls = []

            def is_docker_available(self):
                return True

            async def execute_in_sandbox(self, command, workspace_path, timeout):
                self.calls.append({
                    "command": command,
                    "workspace_path": workspace_path,
                    "timeout": timeout,
                    "agent_present": Path(workspace_path, "agent.py").exists(),
                    "marker_present": Path(
                        workspace_path,
                        "host_import_marker.txt",
                    ).exists(),
                })
                return SandboxResult(
                    success=True,
                    output=(
                        '{"valid": true, "errors": [], "warnings": [], '
                        '"checks_passed": ["Agent class loaded and verified successfully in sandbox"]}'
                    ),
                    exit_code=0,
                )

        sandbox_manager = FakeSandboxManager()
        validator = AgentValidator(
            sandbox_manager=sandbox_manager,
            use_sandbox=True,
            timeout=11,
        )

        result = await validator.validate_agent(str(f))

        assert result["valid"] is True, f"Errors: {result['errors']}"
        assert sandbox_manager.calls[0]["command"].startswith("python3 -c ")
        assert sandbox_manager.calls[0]["timeout"] == 11
        assert sandbox_manager.calls[0]["agent_present"] is True
        assert sandbox_manager.calls[0]["marker_present"] is False
        assert not (tmp_path / "host_import_marker.txt").exists()
        assert any("in sandbox" in check for check in result["checks_passed"])

    async def test_sandbox_runtime_load_falls_back_when_unavailable(self, tmp_path):
        f = tmp_path / "agent.py"
        f.write_text(MINIMAL_AGENT)

        class UnavailableSandboxManager:
            def __init__(self):
                self.calls = []

            def is_docker_available(self):
                return False

            async def execute_in_sandbox(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                raise AssertionError("Sandbox should not be used when unavailable")

        sandbox_manager = UnavailableSandboxManager()
        validator = AgentValidator(
            sandbox_manager=sandbox_manager,
            use_sandbox=True,
        )

        result = await validator.validate_agent(str(f))

        assert result["valid"] is True, f"Errors: {result['errors']}"
        assert sandbox_manager.calls == []
        assert any(
            "Agent class loaded and verified successfully" == check
            for check in result["checks_passed"]
        )

    async def test_sandbox_image_setup_failure_falls_back(self, tmp_path):
        f = tmp_path / "agent.py"
        f.write_text(MINIMAL_AGENT)

        class ImageUnavailableSandboxManager:
            def __init__(self):
                self.calls = []

            def is_docker_available(self):
                return True

            def ensure_sandbox_image(self):
                raise RuntimeError("image unavailable")

            async def execute_in_sandbox(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                raise AssertionError("Sandbox should not be used when image setup fails")

        sandbox_manager = ImageUnavailableSandboxManager()
        validator = AgentValidator(
            sandbox_manager=sandbox_manager,
            use_sandbox=True,
        )

        result = await validator.validate_agent(str(f))

        assert result["valid"] is True, f"Errors: {result['errors']}"
        assert sandbox_manager.calls == []
        assert any(
            "Agent class loaded and verified successfully" == check
            for check in result["checks_passed"]
        )
