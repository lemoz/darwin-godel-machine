"""
Integration tests for benchmark evaluation pipeline.

Tests BenchmarkRunner + BenchmarkScorer together against hand-written solutions.
No network, no Agent FM calls.
"""

import asyncio
import pytest
import yaml
from pathlib import Path

from evaluation.benchmark_runner import BenchmarkRunner, BenchmarkTask
from evaluation.scorer import BenchmarkScorer


def _write_benchmark(bdir: Path, name: str, test_cases: list,
                     scoring_method: str = "partial", timeout: int = 10) -> Path:
    cfg = {
        "name": name,
        "description": f"Benchmark {name}",
        "task_prompt": f"Implement {name}",
        "test_cases": test_cases,
        "timeout": timeout,
        "scoring_method": scoring_method,
    }
    p = bdir / f"{name}.yaml"
    p.write_text(yaml.dump(cfg))
    return p


class TestBenchmarkEvaluationPipeline:

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.bdir = tmp_path / "benchmarks"
        self.bdir.mkdir()
        _write_benchmark(self.bdir, "add", [
            {
                "function_name": "add",
                "inputs": ["1, 2", "5, 5", "100, 200"],
                "expected_outputs": ["3", "10", "300"],
            }
        ])
        self.runner = BenchmarkRunner(
            benchmarks_dir=str(self.bdir),
            use_sandbox=False,
        )

    async def test_runner_loads_benchmark(self):
        assert "add" in self.runner.benchmarks

    async def test_run_test_case_correct_solution(self):
        task = self.runner.benchmarks["add"]
        solution = "def add(a, b):\n    return a + b\n"
        result = await self.runner._run_test_case(solution, task.test_cases[0], task)
        assert result["success"] is True
        assert result["passed"] == 3

    async def test_run_test_case_wrong_solution(self):
        task = self.runner.benchmarks["add"]
        solution = "def add(a, b):\n    return a - b\n"
        result = await self.runner._run_test_case(solution, task.test_cases[0], task)
        assert result["success"] is False

    async def test_calculate_score_pass_fail_all_pass(self):
        tc = [{
            "individual_results": [{"success": True, "actual_output": "3",
                                     "expected_output": "3", "error": None}],
            "passed": 1, "total": 1,
        }]
        task2 = BenchmarkTask(
            name="add2", description="", task_prompt="",
            test_cases=[], timeout=10,
            validation_code="", scoring_method="pass_fail",
        )
        score = self.runner._calculate_score({"test_results": tc}, task2)
        assert score == pytest.approx(1.0)

    async def test_calculate_score_partial(self):
        tc = [
            {"individual_results": [{"success": True, "actual_output": "3",
                                      "expected_output": "3", "error": None}],
             "passed": 1, "total": 1},
            {"individual_results": [{"success": False, "actual_output": "0",
                                      "expected_output": "10", "error": None}],
             "passed": 0, "total": 1},
        ]
        task = BenchmarkTask(
            name="add3", description="", task_prompt="",
            test_cases=[], timeout=10,
            validation_code="", scoring_method="partial",
        )
        score = self.runner._calculate_score({"test_results": tc}, task)
        assert 0.0 < score < 1.0

    async def test_scorer_integrates_with_runner_output(self):
        """Full pipeline: runner output -> scorer -> score in [0, 1]."""
        task = self.runner.benchmarks["add"]
        solution = "def add(a, b):\n    return a + b\n"
        runner_result = await self.runner._run_test_case(
            solution, task.test_cases[0], task
        )
        scorer = BenchmarkScorer()
        bench_cfg = {"scoring": {"method": "partial"}}
        out = scorer.score_benchmark(bench_cfg, [runner_result])
        assert 0.0 <= out["total_score"] <= 1.0

    async def test_get_average_score(self):
        from evaluation.benchmark_runner import BenchmarkResult
        results = {
            "a": BenchmarkResult("a", "agent", True, 0.8, 0.1, []),
            "b": BenchmarkResult("b", "agent", True, 0.6, 0.1, []),
        }
        avg = self.runner.get_average_score(results)
        assert avg == pytest.approx(0.7)

    async def test_prompt_test_cases_are_public_examples_only(self, tmp_path):
        bdir = tmp_path / "hidden_benchmarks"
        bdir.mkdir()
        cfg = {
            "name": "hidden_add",
            "description": "Add two numbers",
            "task_prompt": "Implement add(a, b).",
            "prompt_test_cases": [
                {
                    "function_name": "add",
                    "inputs": ["1, 2"],
                    "expected_outputs": ["3"],
                }
            ],
            "test_cases": [
                {
                    "function_name": "add",
                    "inputs": ["10, 20"],
                    "expected_outputs": ["30"],
                }
            ],
            "timeout": 10,
            "scoring_method": "partial",
        }
        (bdir / "hidden_add.yaml").write_text(yaml.safe_dump(cfg))
        runner = BenchmarkRunner(benchmarks_dir=str(bdir), use_sandbox=False)
        captured = {}

        class CapturingAgent:
            agent_id = "agent"

            async def solve_task(self, task):
                captured["description"] = task.description
                return {"solution": "def add(a, b):\n    return a + b\n"}

        result = await runner.run_benchmark(CapturingAgent(), "hidden_add")

        assert result.score == pytest.approx(1.0)
        assert "PUBLIC EXAMPLES" in captured["description"]
        assert "1, 2" in captured["description"]
        assert "10, 20" not in captured["description"]


async def test_humaneval_style_reference_solution_passes():
    """The shipped HumanEval-style pack must be verified without API calls."""
    project_root = Path(__file__).resolve().parents[2]
    runner = BenchmarkRunner(
        benchmarks_dir=str(project_root / "config" / "benchmarks"),
        use_sandbox=False,
    )
    task = runner.benchmarks["humaneval_style"]
    reference_solution = (
        project_root / "tests" / "fixtures" / "reference_solutions" / "humaneval_style.py"
    ).read_text()

    test_results = []
    for test_case in task.test_cases:
        result = await runner._run_test_case(reference_solution, test_case, task)
        test_results.append(result)

    assert len(task.test_cases) == 4
    assert all(result["success"] for result in test_results)
    assert runner._calculate_score({"test_results": test_results}, task) == pytest.approx(1.0)
