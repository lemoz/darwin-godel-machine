#!/usr/bin/env python3
"""Verify the no-network live score-movement run plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LiveRunPlanError(RuntimeError):
    """Raised when the live score-movement plan is unsafe or incomplete."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveRunPlanError(message)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise LiveRunPlanError(f"Missing live-run config: {path}") from exc
    except yaml.YAMLError as exc:
        raise LiveRunPlanError(f"Invalid live-run config YAML: {path}: {exc}") from exc

    _require(isinstance(data, dict), "Live-run config must be a mapping")
    return data


def _project_relative(path_text: str, project_root: Path) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = project_root / path
    try:
        return path.resolve().relative_to(project_root.resolve())
    except ValueError as exc:
        raise LiveRunPlanError(f"{path_text} must stay inside the project root") from exc


def _require_under_run_dir(path_text: str, project_root: Path, run_dir: Path) -> str:
    relative_path = _project_relative(path_text, project_root)
    try:
        relative_path.relative_to(run_dir)
    except ValueError as exc:
        raise LiveRunPlanError(f"{path_text} must live under {run_dir}") from exc
    return str(relative_path)


def verify_live_score_movement_plan(
    config_path: Path = PROJECT_ROOT / "config" / "live_score_movement.yaml",
    *,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Verify that the live score-movement plan is bounded and gated."""
    project_root = project_root.resolve()
    config_path = config_path if config_path.is_absolute() else project_root / config_path
    config = _load_yaml(config_path)
    run_dir = Path(".dgm-live-runs/live-score-movement")

    providers = config.get("fm_providers", {})
    primary = providers.get("primary")
    _require(primary == "anthropic", "Live score-movement plan must use anthropic provider")
    provider = providers.get(primary, {})
    _require(provider.get("api_key") == "${ANTHROPIC_API_KEY}", "API key must be env-placeholder only")
    _require(provider.get("max_tokens", 0) <= 2048, "Provider max_tokens must stay <= 2048")
    _require(provider.get("timeout", 0) <= 60, "Provider timeout must stay <= 60 seconds")

    benchmark_config = config.get("benchmarks", {})
    enabled = benchmark_config.get("enabled", [])
    _require(enabled == ["humaneval_style"], "Live score-movement run must target humaneval_style only")
    _require(
        benchmark_config.get("max_attempts", 0) <= 3,
        "Benchmark max_attempts must stay <= 3",
    )
    _require(
        benchmark_config.get("timeout_default", 0) <= 30,
        "Benchmark timeout_default must stay <= 30",
    )

    evaluation = config.get("evaluation", {})
    _require(
        evaluation.get("benchmarks_dir") == "config/benchmarks",
        "Evaluation must use config/benchmarks",
    )
    _require(
        evaluation.get("timeout_seconds", 0) <= 30,
        "Evaluation timeout_seconds must stay <= 30",
    )
    _require(
        evaluation.get("use_sandbox") is False,
        "Use the full-process Docker runner instead of nested Docker for this plan",
    )
    archive_path = _require_under_run_dir(config["archive"]["path"], project_root, run_dir)
    results_path = _require_under_run_dir(evaluation["results_dir"], project_root, run_dir)
    workspace_path = _require_under_run_dir(
        config["agents"]["workspace_dir"],
        project_root,
        run_dir,
    )

    agents = config.get("agents", {})
    _require(agents.get("initial_agent_path") == "agent/agent.py", "Initial agent path must be agent/agent.py")
    _require(agents.get("max_steps", 0) <= 5, "Agent max_steps must stay <= 5")

    _require(config.get("generation_delay_seconds") == 0, "Generation delay must be zero for rehearsals")
    _require(config.get("stop_on_error") is True, "Live score-movement plan must stop on errors")

    live_run = config.get("live_run", {})
    _require(live_run.get("purpose") == "live_score_movement_rehearsal", "Missing live-run purpose")
    _require(live_run.get("approval_required") is True, "Live run must require explicit approval")
    _require(live_run.get("recommended_generations") == 2, "Recommended generations must be 2")

    cost_gate = live_run.get("cost_gate", {})
    _require(
        cost_gate.get("check_current_provider_pricing_before_run") is True,
        "Cost gate must require current provider pricing check before run",
    )
    _require(
        cost_gate.get("max_generations_without_reapproval") == 2,
        "Cost gate must cap generations at 2 without reapproval",
    )
    _require(cost_gate.get("max_agent_steps") == agents.get("max_steps"), "Cost gate max steps must match config")
    _require(
        cost_gate.get("max_output_tokens_per_call") == provider.get("max_tokens"),
        "Cost gate output-token cap must match provider max_tokens",
    )
    _require(cost_gate.get("max_enabled_benchmarks") == len(enabled), "Cost gate benchmark count must match config")

    preflight = live_run.get("required_preflight", [])
    _require(
        any("scripts/verify_demo_path.py" in command for command in preflight),
        "Preflight must include verify_demo_path.py",
    )
    _require(
        any("scripts/verify_sandbox_docker.py --require" in command for command in preflight),
        "Preflight must include required Docker sandbox smoke",
    )
    _require(
        any("scripts/verify_live_score_movement_plan.py" in command for command in preflight),
        "Preflight must include this live score-movement plan verifier",
    )

    recommended_run = " ".join(live_run.get("recommended_run", []))
    _require("scripts/run_dgm_in_sandbox.py" in recommended_run, "Run command must use full-process sandbox runner")
    _require("--config config/live_score_movement.yaml" in recommended_run, "Run command must use this config")
    _require("--generations 2" in recommended_run, "Run command must be bounded to two generations")
    _require("--allow-network" in recommended_run, "Run command must require explicit network opt-in")
    _require("--env ANTHROPIC_API_KEY" in recommended_run, "Run command must name the provider env var")
    _require("--audit-output" in recommended_run, "Run command must write a non-secret sandbox audit")

    scorecard = live_run.get("post_run_scorecard", {})
    scorecard_command = scorecard.get("command", "")
    _require(scorecard.get("require_improvement") is True, "Scorecard must require improvement")
    _require("scripts/summarize_archive_scores.py" in scorecard_command, "Scorecard command missing summary script")
    _require("--require-improvement" in scorecard_command, "Scorecard command must use --require-improvement")
    _require(
        ".dgm-live-runs/live-score-movement/archive/archive_metadata.json" in scorecard_command,
        "Scorecard command must target this run archive metadata",
    )

    return {
        "name": "live_score_movement_plan",
        "status": "ok",
        "config": str(config_path.relative_to(project_root)),
        "benchmark": enabled[0],
        "recommended_generations": live_run["recommended_generations"],
        "max_agent_steps": agents["max_steps"],
        "max_output_tokens_per_call": provider["max_tokens"],
        "archive_path": archive_path,
        "results_path": results_path,
        "workspace_path": workspace_path,
        "approval_required": True,
        "requires_current_pricing_check": True,
        "requires_full_process_sandbox": True,
        "requires_scorecard_improvement": True,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "config" / "live_score_movement.yaml"),
        help="Live score-movement run config to verify.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a one-line status.",
    )
    return parser


def _main(args: argparse.Namespace) -> int:
    try:
        report = verify_live_score_movement_plan(Path(args.config))
    except LiveRunPlanError as exc:
        if args.json:
            print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        else:
            print(f"[fail] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            "[ok] live_score_movement_plan "
            f"benchmark={report['benchmark']} "
            f"generations={report['recommended_generations']} "
            f"max_steps={report['max_agent_steps']}"
        )
    return 0


def main() -> int:
    return _main(_build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
