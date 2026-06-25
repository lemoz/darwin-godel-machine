#!/usr/bin/env python3
"""Verify the planned LiveCodeBench OpenRouter segment run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.estimate_live_run_cost import estimate_live_run_cost
from scripts.prepare_livecodebench_segment import expected_benchmark_names


class LiveCodeBenchPlanError(RuntimeError):
    """Raised when the LiveCodeBench run plan is unsafe or incomplete."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveCodeBenchPlanError(message)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise LiveCodeBenchPlanError(f"Missing config: {path}") from exc
    except yaml.YAMLError as exc:
        raise LiveCodeBenchPlanError(f"Invalid YAML in {path}: {exc}") from exc
    _require(isinstance(data, dict), f"Config must be a mapping: {path}")
    return data


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LiveCodeBenchPlanError(f"Missing generated manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LiveCodeBenchPlanError(f"Invalid manifest JSON: {path}: {exc}") from exc
    _require(isinstance(data, dict), f"Manifest must be a mapping: {path}")
    return data


def _project_path(path_text: str | Path, project_root: Path, *, must_exist: bool = False) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = project_root / path
    try:
        relative_path = path.resolve().relative_to(project_root.resolve())
    except ValueError as exc:
        raise LiveCodeBenchPlanError(f"{path_text} must stay inside the project root") from exc
    path = project_root.resolve() / relative_path
    if must_exist:
        _require(path.exists(), f"Missing required project path: {relative_path}")
    return path


def _project_relative(path: Path, project_root: Path) -> str:
    return str(path.resolve().relative_to(project_root.resolve()))


def _require_command(preflight: list[Any], needle: str, label: str) -> None:
    _require(
        any(needle in str(command) for command in preflight),
        f"Preflight must include {label}",
    )


def verify_livecodebench_segment_plan(
    config_path: Path = PROJECT_ROOT / "config" / "livecodebench_openrouter_segment.yaml",
    *,
    project_root: Path = PROJECT_ROOT,
    require_generated: bool = False,
) -> dict[str, Any]:
    """Verify that the LiveCodeBench segment run is bounded and reproducible."""
    project_root = project_root.resolve()
    config_path = config_path if config_path.is_absolute() else project_root / config_path
    config = _load_yaml(config_path)

    provider_name = config.get("fm_providers", {}).get("primary")
    _require(provider_name == "openai_compatible", "LiveCodeBench plan must use OpenAI-compatible provider")
    provider = config.get("fm_providers", {}).get(provider_name, {})
    _require(isinstance(provider, dict), "Primary provider config must be a mapping")
    _require(provider.get("model") == "moonshotai/kimi-k2.7-code", "Default model must be moonshotai/kimi-k2.7-code")
    _require(provider.get("api_key") == "${OPENROUTER_API_KEY}", "Provider must use OPENROUTER_API_KEY env placeholder")
    _require(provider.get("base_url") == "https://openrouter.ai/api/v1", "Provider must use OpenRouter base_url")
    _require(int(provider.get("max_tokens", 0)) == 4096, "Provider max_tokens must be 4096")

    live_run = config.get("live_run", {})
    _require(isinstance(live_run, dict), "live_run must be a mapping")
    _require(live_run.get("purpose") == "livecodebench_openrouter_segment", "Missing live-run purpose")
    _require(live_run.get("approval_required") is True, "Live run must require approval")
    generations = int(live_run.get("recommended_generations", 0))
    _require(generations == 3, "Recommended generations must be 3")

    segment = live_run.get("segment", {})
    _require(isinstance(segment, dict), "live_run.segment must be a mapping")
    segment_config_path = _project_path(segment.get("config", ""), project_root, must_exist=True)
    segment_config = _load_yaml(segment_config_path)
    _require(
        segment_config.get("purpose") == "livecodebench_segment",
        "Segment config must declare livecodebench_segment purpose",
    )
    expected_names = expected_benchmark_names(segment_config)

    enabled = config.get("benchmarks", {}).get("enabled", [])
    _require(enabled == expected_names, "Enabled benchmarks must match segment question_ids")
    _require(int(segment.get("benchmark_count", 0)) == len(enabled), "Segment benchmark_count mismatch")

    evaluation = config.get("evaluation", {})
    selection = segment_config.get("selection", {})
    generated_benchmarks_dir = _project_path(selection.get("output_dir", ""), project_root)
    _require(
        evaluation.get("benchmarks_dir") == _project_relative(generated_benchmarks_dir, project_root),
        "Evaluation benchmarks_dir must point at generated LiveCodeBench YAMLs",
    )
    _require(config.get("stop_on_error") is True, "LiveCodeBench run must stop on errors")

    agents = config.get("agents", {})
    _require(int(agents.get("max_steps", 0)) == 5, "Agent max_steps must be 5")

    cost_gate = live_run.get("cost_gate", {})
    _require(isinstance(cost_gate, dict), "cost_gate must be a mapping")
    _require(cost_gate.get("check_current_provider_pricing_before_run") is True, "Cost gate must require current pricing check")
    _require(str(cost_gate.get("pricing_checked_at")) == "2026-06-24", "Pricing check date must be 2026-06-24")
    _require(float(cost_gate.get("input_price_per_mtok", 0)) == 0.74, "Input price mismatch")
    _require(float(cost_gate.get("output_price_per_mtok", 0)) == 3.50, "Output price mismatch")
    _require(int(cost_gate.get("max_enabled_benchmarks", 0)) == len(enabled), "Cost gate benchmark count mismatch")
    _require(int(cost_gate.get("max_generations_without_reapproval", 0)) == generations, "Cost gate generation count mismatch")
    _require(int(cost_gate.get("max_agent_steps", 0)) == int(agents.get("max_steps", 0)), "Cost gate max steps mismatch")

    assumed_input_tokens = int(cost_gate.get("assumed_input_tokens_per_call", 0))
    estimate = estimate_live_run_cost(
        config_path=config_path,
        input_price_per_mtok=float(cost_gate["input_price_per_mtok"]),
        output_price_per_mtok=float(cost_gate["output_price_per_mtok"]),
        assumed_input_tokens_per_call=assumed_input_tokens,
        max_budget=float(cost_gate["max_estimated_cost_usd"]),
    )
    _require(estimate["within_budget"], "LiveCodeBench estimate exceeds max budget")

    preflight = live_run.get("required_preflight", [])
    _require(isinstance(preflight, list), "required_preflight must be a list")
    _require_command(preflight, "scripts/prepare_livecodebench_segment.py", "LiveCodeBench segment preparation")
    _require_command(preflight, "scripts/verify_livecodebench_segment_plan.py", "this plan verifier")
    _require_command(preflight, "scripts/verify_sandbox_docker.py --require", "required Docker sandbox check")
    _require_command(preflight, "--max-budget", "paid Kimi cost estimate")

    recommended_run = "\n".join(str(item) for item in live_run.get("recommended_run", []))
    config_label = _project_relative(config_path, project_root)
    _require(f"--config {config_label}" in recommended_run, "Run command must use this config")
    _require("--generations 3" in recommended_run, "Run command must use three generations")
    _require("--allow-network" in recommended_run, "Run command must require --allow-network")
    _require("--env OPENROUTER_API_KEY" in recommended_run, "Run command must pass only OPENROUTER_API_KEY")
    _require("--timeout 7200" in recommended_run, "Run command must allow a 7200-second sandbox timeout")

    generated_manifest_summary: dict[str, Any] | None = None
    if require_generated:
        manifest_path = _project_path(segment.get("manifest_path", ""), project_root, must_exist=True)
        manifest = _load_json(manifest_path)
        _require(manifest.get("benchmark_names") == expected_names, "Generated manifest benchmark names mismatch")
        _require(int(manifest.get("benchmark_count", 0)) == len(expected_names), "Generated manifest benchmark count mismatch")
        _require(
            int(manifest.get("total_test_count", 0)) >= int(segment.get("expected_total_tests_min", 0)),
            "Generated segment has too few total tests",
        )
        _require(
            int(manifest.get("private_test_count", 0)) >= int(segment.get("expected_private_tests_min", 0)),
            "Generated segment has too few private tests",
        )
        for benchmark_name in expected_names:
            benchmark_path = generated_benchmarks_dir / f"{benchmark_name}.yaml"
            _require(benchmark_path.is_file(), f"Missing generated benchmark YAML: {benchmark_path}")
        generated_manifest_summary = {
            "manifest_path": _project_relative(manifest_path, project_root),
            "benchmark_count": manifest["benchmark_count"],
            "total_test_count": manifest["total_test_count"],
            "private_test_count": manifest["private_test_count"],
            "difficulty_counts": manifest["difficulty_counts"],
        }

    return {
        "name": "livecodebench_openrouter_segment_plan",
        "status": "ok",
        "config": _project_relative(config_path, project_root),
        "segment_config": _project_relative(segment_config_path, project_root),
        "approval_required": True,
        "live_calls_performed": 0,
        "provider": provider_name,
        "model": provider["model"],
        "benchmark_count": len(enabled),
        "recommended_generations": generations,
        "max_agent_steps": int(agents["max_steps"]),
        "request_ceiling": estimate["request_ceiling"],
        "estimated_total_cost_usd": estimate["estimated_total_cost_usd"],
        "max_budget_usd": float(cost_gate["max_estimated_cost_usd"]),
        "requires_generated_segment": require_generated,
        "generated_manifest": generated_manifest_summary,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "config" / "livecodebench_openrouter_segment.yaml"),
        help="LiveCodeBench OpenRouter run config to verify.",
    )
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument(
        "--require-generated",
        action="store_true",
        help="Require generated segment manifest and benchmark YAML files to exist.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def _main(args: argparse.Namespace) -> int:
    try:
        report = verify_livecodebench_segment_plan(
            Path(args.config),
            project_root=Path(args.project_root),
            require_generated=args.require_generated,
        )
    except LiveCodeBenchPlanError as exc:
        if args.json:
            print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        else:
            print(f"[fail] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            "[ok] livecodebench_openrouter_segment_plan "
            f"benchmarks={report['benchmark_count']} "
            f"generations={report['recommended_generations']} "
            f"requests<={report['request_ceiling']} "
            f"total=${report['estimated_total_cost_usd']:.4f}"
        )
    return 0


def main() -> int:
    return _main(_build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
