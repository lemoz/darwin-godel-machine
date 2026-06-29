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

import evaluation.benchmark_runner as benchmark_runner_module
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


def _make_stdin_task(tmp_path: Path, name: str = "stdin_sum_task") -> BenchmarkTask:
    """Write a stdin/stdout benchmark config and return a BenchmarkTask."""
    config = {
        "name": name,
        "description": "Sum numbers from stdin",
        "task_prompt": "Read integers from stdin and print their sum.",
        "test_cases": [
            {
                "testtype": "stdin",
                "inputs": ["3\n1 2 3\n", "2\n4 5\n"],
                "expected_outputs": ["6\n", "9\n"],
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


def test_runner_loads_only_enabled_benchmarks(tmp_path):
    bdir = tmp_path / "benchmarks"
    bdir.mkdir()
    for name in ("keep_task", "skip_task"):
        config = {
            "name": name,
            "description": name,
            "task_prompt": name,
            "test_cases": [
                {
                    "function_name": "f",
                    "inputs": ["1"],
                    "expected_outputs": ["1"],
                }
            ],
            "timeout": 10,
            "scoring_method": "pass_fail",
        }
        (bdir / f"{name}.yaml").write_text(yaml.dump(config))

    runner = BenchmarkRunner(
        benchmarks_dir=str(bdir),
        use_sandbox=False,
        enabled_benchmarks=["keep_task"],
    )

    assert set(runner.benchmarks) == {"keep_task"}


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

    def test_stdin_solution_script_produces_success_json(self, tmp_path):
        import subprocess, json
        solution_file = str(tmp_path / "stdin_correct.py")
        Path(solution_file).write_text(
            "import sys\n"
            "def main():\n"
            "    data = list(map(int, sys.stdin.read().split()))\n"
            "    print(sum(data[1:]))\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )
        script = BenchmarkRunner._build_stdin_test_script(
            solution_file, "3\n1 2 3\n", "6\n", 0, 10
        )
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout.strip().split("\n")[-1])
        assert data["success"] is True

    def test_stdin_solution_script_limits_child_process_memory(self, tmp_path):
        solution_file = str(tmp_path / "stdin_correct.py")
        Path(solution_file).write_text("print('ok')\n")

        script = BenchmarkRunner._build_stdin_test_script(
            solution_file,
            "ignored\n",
            "ok\n",
            0,
            10,
        )

        assert "_limit_child_process_resources" in script
        assert "preexec_fn=_limit_child_process_resources" in script
        assert "_limit_child_process_by_pid" in script
        assert "_read_child_memory_bytes" in script

    def test_stdin_solution_script_rejects_oversized_stdout(self, tmp_path, monkeypatch):
        import subprocess, json

        monkeypatch.setattr(
            benchmark_runner_module,
            "_STDIN_OUTPUT_CAPTURE_LIMIT_BYTES",
            128,
        )
        solution_file = str(tmp_path / "stdin_too_loud.py")
        Path(solution_file).write_text("print('x' * 1024)\n")

        script = BenchmarkRunner._build_stdin_test_script(
            solution_file,
            "ignored\n",
            "ok\n",
            0,
            10,
        )
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True,
            text=True,
            timeout=10,
        )

        data = json.loads(result.stdout.strip().split("\n")[-1])
        assert data["success"] is False
        assert "Output too large" in data["error"]


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

    async def test_stdin_solution_all_pass(self, tmp_path):
        task = _make_stdin_task(tmp_path)
        runner = _make_runner(tmp_path, task)
        solution = (
            "import sys\n"
            "def main():\n"
            "    data = list(map(int, sys.stdin.read().split()))\n"
            "    print(sum(data[1:]))\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )
        result = await runner._run_test_case(solution, task.test_cases[0], task)
        assert result["success"] is True
        assert result["passed"] == result["total"] == 2

    async def test_stdin_wrong_solution_fails(self, tmp_path):
        task = _make_stdin_task(tmp_path)
        runner = _make_runner(tmp_path, task)
        solution = (
            "import sys\n"
            "data = list(map(int, sys.stdin.read().split()))\n"
            "print(sum(data))\n"
        )
        result = await runner._run_test_case(solution, task.test_cases[0], task)
        assert result["success"] is False
        assert result["passed"] == 0
        assert result["total"] == 2
        assert any(
            "Wrong answer" in (item.get("error") or "")
            for item in result["individual_results"]
        )

    async def test_pass_fail_stdin_short_circuits_after_first_failure(self, tmp_path):
        task = BenchmarkTask(
            name="stdin_pass_fail",
            description="Print exact output",
            task_prompt="Read stdin and print the expected output.",
            test_cases=[{
                "testtype": "stdin",
                "inputs": ["first\n", "second\n"],
                "expected_outputs": ["expected\n", "expected\n"],
            }],
            timeout=10,
            validation_code="",
            scoring_method="pass_fail",
        )
        runner = _make_runner(tmp_path, task)

        result = await runner._run_test_case(
            "print('wrong')\n",
            task.test_cases[0],
            task,
        )

        assert result["success"] is False
        assert result["passed"] == 0
        assert result["total"] == 1
        assert result["short_circuited"] is True

    async def test_stdin_subset_dp_resource_guard_short_circuits(self, tmp_path):
        task = BenchmarkTask(
            name="stdin_subset_dp_guard",
            description="Avoid memory-heavy subset DP",
            task_prompt="Solve from stdin.",
            test_cases=[{
                "testtype": "stdin",
                "inputs": ["12\n" + " ".join(str(i) for i in range(12)) + "\n"],
                "expected_outputs": ["1\n"],
            }],
            timeout=10,
            validation_code="",
            scoring_method="pass_fail",
        )
        runner = _make_runner(tmp_path, task)
        solution = """
def solve():
    N = 12
    M = 1 << N
    dp = [set() for _ in range(M)]
    for mask in range(1, M):
        sub = mask
        while sub:
            if sub & 1:
                dp[mask].update(x for x in dp[mask ^ sub])
            sub = (sub - 1) & mask
    print(len(dp[-1]))

solve()
"""

        result = await runner._run_test_case(solution, task.test_cases[0], task)

        assert result["success"] is False
        assert result["passed"] == 0
        assert result["total"] == 1
        assert result["short_circuited"] is True
        assert "Resource guard rejected solution" in result["individual_results"][0]["error"]

    async def test_stdin_decimal_output_matching(self, tmp_path):
        task = BenchmarkTask(
            name="stdin_decimal",
            description="Print decimals",
            task_prompt="Print numeric values.",
            test_cases=[{
                "testtype": "stdin",
                "inputs": ["ignored\n"],
                "expected_outputs": ["1.00 2\n"],
            }],
            timeout=10,
            validation_code="",
            scoring_method="partial",
        )
        runner = _make_runner(tmp_path, task)
        solution = "print('1.0 2.00')\n"
        result = await runner._run_test_case(solution, task.test_cases[0], task)
        assert result["success"] is True

    async def test_stdin_ignores_invalid_function_name(self, tmp_path):
        task = _make_stdin_task(tmp_path)
        runner = _make_runner(tmp_path, task)
        test_case = {
            "testtype": "stdin",
            "function_name": "not; a; function",
            "inputs": ["1\n7\n"],
            "expected_outputs": ["7\n"],
        }
        solution = (
            "import sys\n"
            "data = list(map(int, sys.stdin.read().split()))\n"
            "print(data[-1])\n"
        )
        result = await runner._run_test_case(solution, test_case, task)
        assert result["success"] is True

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

    async def test_direct_subprocess_uses_resource_limits(self, tmp_path, monkeypatch):
        task = _make_stdin_task(tmp_path)
        runner = _make_runner(tmp_path, task)
        captured = {}
        original_create = asyncio.create_subprocess_exec

        async def wrapped_create(*args, **kwargs):
            captured["preexec_fn"] = kwargs.get("preexec_fn")
            return await original_create(*args, **kwargs)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", wrapped_create)

        result = await runner._run_test_case(
            "import sys\nprint(sum(map(int, sys.stdin.read().split()[1:])))\n",
            task.test_cases[0],
            task,
        )

        assert result["success"] is True
        assert captured["preexec_fn"] is not None
        assert captured["preexec_fn"].__name__ == "_apply_test_process_resource_limits"

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

    async def test_stdin_uses_sandbox_manager_when_available(self, tmp_path):
        task = _make_stdin_task(tmp_path)

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
                    output='{"success": true, "actual_output": "6", "expected_output": "6", "error": null, "exit_code": 0}\n',
                    exit_code=0,
                )

        fake_sandbox = FakeSandboxManager()
        runner = _make_runner(tmp_path, task)
        runner.use_sandbox = True
        runner.sandbox_manager = fake_sandbox

        result = await runner._run_test_case(
            "print(6)\n",
            task.test_cases[0],
            task,
        )

        assert result["success"] is True
        assert result["passed"] == result["total"] == 2
        assert len(fake_sandbox.calls) == 2
        assert all(call["timeout"] == task.timeout + 2 for call in fake_sandbox.calls)

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

BROKEN_PROMPT_AGENT = '''\
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

@dataclass
class AgentConfig:
    agent_id: str
    fm_provider: str
    fm_config: Dict[str, Any]
    working_directory: str
    tool_timeout: int = 30
    max_iterations: int = 10
    use_sandbox: bool = False
    retain_conversation_history: bool = True

@dataclass
class ConversationContext:
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    iteration: Optional[int] = None
    benchmark_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class Message:
    def __init__(self, content):
        self.content = content

class Agent:
    def __init__(self, config):
        self.config = config
        self.fm_interface = None
        self.tools = []

    def solve_task(self, task):
        return "done"

    def _build_system_message(self, context):
        return Message(base_instructions)
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

    async def test_prompt_build_failure_fails_validation(self, tmp_path):
        f = tmp_path / "agent.py"
        f.write_text(BROKEN_PROMPT_AGENT)
        validator = AgentValidator()
        result = await validator.validate_agent(str(f))
        assert result["valid"] is False
        assert any("prompt-build smoke failed" in e for e in result["errors"])

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
