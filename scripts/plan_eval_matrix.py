#!/usr/bin/env python3
"""Build a no-network eval matrix gate for future paid model comparisons."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.compare_benchmark_solutions import compare_solutions


class EvalMatrixPlanError(RuntimeError):
    """Raised when the eval matrix is unsafe or not ready for live spend."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvalMatrixPlanError(message)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise EvalMatrixPlanError(f"Missing config: {path}") from exc
    except yaml.YAMLError as exc:
        raise EvalMatrixPlanError(f"Invalid YAML in {path}: {exc}") from exc
    _require(isinstance(data, dict), f"Config must be a mapping: {path}")
    return data


def _project_path(path_text: str | Path, project_root: Path, *, must_be_file: bool) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = project_root / path
    try:
        relative_path = path.resolve().relative_to(project_root.resolve())
    except ValueError as exc:
        raise EvalMatrixPlanError(f"{path_text} must stay inside the project root") from exc
    path = project_root.resolve() / relative_path
    if must_be_file:
        _require(path.is_file(), f"Missing required project file: {relative_path}")
    return path


def _project_relative(path: Path, project_root: Path) -> str:
    resolved_path = path.resolve()
    try:
        return str(resolved_path.relative_to(project_root.resolve()))
    except ValueError:
        return str(resolved_path)


def _require_no_secret_fields(raw: dict[str, Any], label: str) -> None:
    forbidden = {"api_key", "secret", "token"}
    present = forbidden.intersection(raw)
    _require(not present, f"{label} must not contain secret fields")


def _gate_float(gate: dict[str, Any], name: str) -> float:
    value = float(gate.get(name, 0))
    _require(value > 0, f"gate.{name} must be greater than zero")
    return value


def _gate_int(gate: dict[str, Any], name: str) -> int:
    value = int(gate.get(name, 0))
    _require(value > 0, f"gate.{name} must be greater than zero")
    return value


async def plan_eval_matrix(
    config_path: Path = PROJECT_ROOT / "config" / "eval_model_matrix.yaml",
    *,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Score local benchmark fixtures and decide whether live matrix spend is justified."""
    project_root = project_root.resolve()
    config_path = config_path if config_path.is_absolute() else project_root / config_path
    config = _load_yaml(config_path)

    _require(
        config.get("purpose") == "no_spend_eval_model_differentiation",
        "Eval matrix must declare no_spend_eval_model_differentiation purpose",
    )
    _require(config.get("approval_required") is True, "Eval matrix must require approval")
    _require(config.get("live_calls_performed") == 0, "Eval matrix must perform zero live calls")
    _require_no_secret_fields(config, "Eval matrix config")

    benchmarks_dir = _project_path(
        config.get("benchmarks_dir", "config/benchmarks"),
        project_root,
        must_be_file=False,
    )
    _require(benchmarks_dir.is_dir(), f"Missing benchmarks directory: {benchmarks_dir}")

    gate = config.get("gate", {})
    _require(isinstance(gate, dict), "gate must be a mapping")
    min_benchmark_families = _gate_int(gate, "min_benchmark_families")
    min_total_eval_cases = _gate_int(gate, "min_total_eval_cases")
    min_average_delta = _gate_float(gate, "min_average_delta")
    min_delta_per_benchmark = _gate_float(gate, "min_delta_per_benchmark")
    min_baseline_score = _gate_float(gate, "min_baseline_score")
    max_baseline_score = _gate_float(gate, "max_baseline_score")
    min_candidate_score = _gate_float(gate, "min_candidate_score")
    _require(
        min_baseline_score < max_baseline_score,
        "gate.min_baseline_score must be below gate.max_baseline_score",
    )

    configured_benchmarks = config.get("benchmarks", [])
    _require(
        isinstance(configured_benchmarks, list) and configured_benchmarks,
        "benchmarks must be a non-empty list",
    )

    benchmark_reports: list[dict[str, Any]] = []
    for raw in configured_benchmarks:
        _require(isinstance(raw, dict), "Each benchmark entry must be a mapping")
        _require(raw.get("id"), "Each benchmark entry must define id")
        _require(raw.get("family"), f"Benchmark {raw.get('id')} must define family")
        _require_no_secret_fields(raw, f"Benchmark {raw['id']}")

        baseline_path = _project_path(
            raw.get("baseline_solution", ""),
            project_root,
            must_be_file=True,
        )
        candidate_path = _project_path(
            raw.get("candidate_solution", ""),
            project_root,
            must_be_file=True,
        )
        min_eval_cases = int(raw.get("min_eval_cases", 0))
        _require(min_eval_cases > 0, f"Benchmark {raw['id']} must define min_eval_cases")
        min_delta = float(raw.get("min_delta", min_delta_per_benchmark))

        comparison = await compare_solutions(
            benchmarks_dir=benchmarks_dir,
            benchmark_name=str(raw["id"]),
            baseline_path=baseline_path,
            candidate_path=candidate_path,
        )
        baseline = comparison["baseline"]
        candidate = comparison["candidate"]
        delta = comparison["delta"]
        total = int(candidate["total"])
        passed_gate = (
            baseline["score"] >= min_baseline_score
            and baseline["score"] <= max_baseline_score
            and candidate["score"] >= min_candidate_score
            and delta >= min_delta
            and delta >= min_delta_per_benchmark
            and total >= min_eval_cases
        )
        benchmark_reports.append(
            {
                "id": raw["id"],
                "family": raw["family"],
                "baseline_solution": _project_relative(baseline_path, project_root),
                "candidate_solution": _project_relative(candidate_path, project_root),
                "baseline_score": baseline["score"],
                "candidate_score": candidate["score"],
                "delta": delta,
                "baseline_passed": baseline["passed"],
                "candidate_passed": candidate["passed"],
                "total_eval_cases": total,
                "min_eval_cases": min_eval_cases,
                "min_delta": min_delta,
                "passed_gate": passed_gate,
            }
        )

    families = sorted({str(item["family"]) for item in benchmark_reports})
    total_eval_cases = sum(int(item["total_eval_cases"]) for item in benchmark_reports)
    average_delta = mean(float(item["delta"]) for item in benchmark_reports)
    all_benchmarks_passed = all(bool(item["passed_gate"]) for item in benchmark_reports)
    ready_for_live_matrix = (
        all_benchmarks_passed
        and len(families) >= min_benchmark_families
        and total_eval_cases >= min_total_eval_cases
        and average_delta >= min_average_delta
    )

    report = {
        "name": "eval_model_matrix_plan",
        "status": "ok" if ready_for_live_matrix else "blocked",
        "config": _project_relative(config_path, project_root),
        "benchmarks_dir": _project_relative(benchmarks_dir, project_root),
        "approval_required": True,
        "live_calls_performed": 0,
        "benchmark_count": len(benchmark_reports),
        "benchmark_families": families,
        "min_benchmark_families": min_benchmark_families,
        "total_eval_cases": total_eval_cases,
        "min_total_eval_cases": min_total_eval_cases,
        "average_delta": average_delta,
        "min_average_delta": min_average_delta,
        "all_benchmarks_passed": all_benchmarks_passed,
        "ready_for_live_matrix": ready_for_live_matrix,
        "decision": (
            "prepare_live_matrix_plan"
            if ready_for_live_matrix
            else "recalibrate_before_live_spend"
        ),
        "benchmarks": benchmark_reports,
    }
    _require(ready_for_live_matrix, "Eval matrix is not ready for live model spend")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "config" / "eval_model_matrix.yaml"),
    )
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    try:
        report = await plan_eval_matrix(
            Path(args.config),
            project_root=Path(args.project_root),
        )
    except EvalMatrixPlanError as exc:
        if args.json:
            print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        else:
            print(f"[fail] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            "[ok] eval_model_matrix_plan "
            f"benchmarks={report['benchmark_count']} "
            f"families={len(report['benchmark_families'])} "
            f"cases={report['total_eval_cases']} "
            f"average_delta={report['average_delta']:.3f} "
            f"decision={report['decision']}"
        )
    return 0


def main() -> int:
    return asyncio.run(_main_async(_build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
