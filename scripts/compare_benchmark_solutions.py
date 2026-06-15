"""Compare two local solution files on a configured benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import warnings
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    module=r"agent\.fm_interface\.providers\.gemini",
)

from evaluation.benchmark_runner import BenchmarkRunner, BenchmarkTask


async def score_solution(
    runner: BenchmarkRunner,
    benchmark: BenchmarkTask,
    solution_path: Path,
    label: str,
) -> dict[str, Any]:
    """Run one solution file through every test case in a benchmark."""
    solution = solution_path.read_text()
    test_results = []

    for test_case in benchmark.test_cases:
        result = await runner._run_test_case(solution, test_case, benchmark)
        result["function_name"] = test_case.get("function_name", "solve")
        test_results.append(result)

    score = runner._calculate_score({"test_results": test_results}, benchmark)
    passed = sum(result.get("passed", 0) for result in test_results)
    total = sum(result.get("total", 0) for result in test_results)

    return {
        "label": label,
        "path": str(solution_path),
        "score": score,
        "passed": passed,
        "total": total,
        "test_cases": test_results,
    }


async def compare_solutions(
    *,
    benchmarks_dir: Path,
    benchmark_name: str,
    baseline_path: Path,
    candidate_path: Path,
    baseline_label: str = "baseline",
    candidate_label: str = "candidate",
) -> dict[str, Any]:
    """Compare baseline and candidate solution files on one benchmark."""
    runner = BenchmarkRunner(benchmarks_dir=str(benchmarks_dir), use_sandbox=False)
    if benchmark_name not in runner.benchmarks:
        known = ", ".join(sorted(runner.benchmarks)) or "(none loaded)"
        raise ValueError(f"Unknown benchmark {benchmark_name!r}. Known benchmarks: {known}")

    benchmark = runner.benchmarks[benchmark_name]
    baseline = await score_solution(runner, benchmark, baseline_path, baseline_label)
    candidate = await score_solution(runner, benchmark, candidate_path, candidate_label)

    return {
        "benchmark": benchmark_name,
        "benchmarks_dir": str(benchmarks_dir),
        "baseline": baseline,
        "candidate": candidate,
        "delta": candidate["score"] - baseline["score"],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare two local solution files on a DGM benchmark."
    )
    parser.add_argument("--benchmark", required=True, help="Benchmark name to run.")
    parser.add_argument(
        "--benchmarks-dir",
        default="config/benchmarks",
        help="Directory containing benchmark YAML files.",
    )
    parser.add_argument(
        "--baseline",
        required=True,
        help="Path to the weaker or previous solution file.",
    )
    parser.add_argument(
        "--candidate",
        required=True,
        help="Path to the improved or reference solution file.",
    )
    parser.add_argument(
        "--baseline-label",
        default="baseline",
        help="Label for the baseline solution in the report.",
    )
    parser.add_argument(
        "--candidate-label",
        default="candidate",
        help="Label for the candidate solution in the report.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the JSON report.",
    )
    return parser


async def _main_async(args: argparse.Namespace) -> dict[str, Any]:
    report = await compare_solutions(
        benchmarks_dir=Path(args.benchmarks_dir),
        benchmark_name=args.benchmark,
        baseline_path=Path(args.baseline),
        candidate_path=Path(args.candidate),
        baseline_label=args.baseline_label,
        candidate_label=args.candidate_label,
    )

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    baseline = report["baseline"]
    candidate = report["candidate"]
    print(
        f"{report['benchmark']}: "
        f"{baseline['label']}={baseline['score']:.3f} "
        f"({baseline['passed']}/{baseline['total']}), "
        f"{candidate['label']}={candidate['score']:.3f} "
        f"({candidate['passed']}/{candidate['total']}), "
        f"delta={report['delta']:+.3f}"
    )

    return report


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
