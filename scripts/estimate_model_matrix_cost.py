#!/usr/bin/env python3
"""Verify and estimate the dry-run live model-matrix plan."""

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


class ModelMatrixPlanError(RuntimeError):
    """Raised when a model-matrix plan is unsafe or cannot be estimated."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ModelMatrixPlanError(message)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise ModelMatrixPlanError(f"Missing config: {path}") from exc
    except yaml.YAMLError as exc:
        raise ModelMatrixPlanError(f"Invalid YAML in {path}: {exc}") from exc
    _require(isinstance(data, dict), f"Config must be a mapping: {path}")
    return data


def _project_file(path_text: str, project_root: Path) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = project_root / path
    try:
        relative_path = path.resolve().relative_to(project_root.resolve())
    except ValueError as exc:
        raise ModelMatrixPlanError(f"{path_text} must stay inside the project root") from exc
    path = project_root / relative_path
    _require(path.is_file(), f"Missing required project file: {relative_path}")
    return path


def _require_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ModelMatrixPlanError(f"{name} must be greater than zero")


def _require_no_secret_fields(model: dict[str, Any]) -> None:
    forbidden = {"api_key", "secret", "token"}
    present = forbidden.intersection(model)
    _require(
        not present,
        f"Model {model.get('id', '<unknown>')} must use api_key_env, not secret fields",
    )


def _model_cost(
    *,
    model: dict[str, Any],
    request_ceiling: int,
    assumed_input_tokens_per_call: int,
    trials_per_model: int,
) -> dict[str, Any]:
    input_price = float(model.get("input_price_per_mtok", 0))
    output_price = float(model.get("output_price_per_mtok", 0))
    max_tokens = int(model.get("max_tokens", 0))
    _require_positive(f"{model['id']}.input_price_per_mtok", input_price)
    _require_positive(f"{model['id']}.output_price_per_mtok", output_price)
    _require_positive(f"{model['id']}.max_tokens", max_tokens)

    input_token_ceiling = request_ceiling * assumed_input_tokens_per_call
    output_token_ceiling = request_ceiling * max_tokens
    input_cost = input_token_ceiling / 1_000_000 * input_price
    output_cost = output_token_ceiling / 1_000_000 * output_price
    per_trial_total = input_cost + output_cost

    return {
        "id": model["id"],
        "provider": model["provider"],
        "model": model["model"],
        "api_key_env": model["api_key_env"],
        "base_url": model.get("base_url"),
        "pricing_source": model["pricing_source"],
        "input_price_per_mtok": input_price,
        "output_price_per_mtok": output_price,
        "request_ceiling_per_trial": request_ceiling,
        "assumed_input_tokens_per_call": assumed_input_tokens_per_call,
        "max_output_tokens_per_call": max_tokens,
        "temperature": float(model.get("temperature", 0.1)),
        "timeout": int(model.get("timeout", 60)),
        "input_token_ceiling_per_trial": input_token_ceiling,
        "output_token_ceiling_per_trial": output_token_ceiling,
        "estimated_input_cost_usd_per_trial": input_cost,
        "estimated_output_cost_usd_per_trial": output_cost,
        "estimated_total_cost_usd_per_trial": per_trial_total,
        "trials": trials_per_model,
        "total_request_ceiling": request_ceiling * trials_per_model,
        "estimated_total_cost_usd": per_trial_total * trials_per_model,
    }


def estimate_model_matrix_cost(
    config_path: Path = PROJECT_ROOT / "config" / "live_model_matrix.yaml",
    *,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Verify the dry-run matrix contract and estimate its bounded cost."""
    project_root = project_root.resolve()
    config_path = config_path if config_path.is_absolute() else project_root / config_path
    config = _load_yaml(config_path)

    base_config_path = _project_file(config.get("base_live_run_config", ""), project_root)
    base_config = _load_yaml(base_config_path)

    matrix = config.get("model_matrix", {})
    _require(isinstance(matrix, dict), "model_matrix must be a mapping")
    _require(
        matrix.get("purpose") == "live_model_matrix_dry_run",
        "Model matrix must declare live_model_matrix_dry_run purpose",
    )
    _require(matrix.get("approval_required") is True, "Model matrix must require approval")
    _require(matrix.get("dry_run_only") is True, "Model matrix must stay dry_run_only")
    _require(
        matrix.get("benchmark") == "humaneval_calibrated",
        "Model matrix must target humaneval_calibrated",
    )
    _require(
        base_config.get("benchmarks", {}).get("enabled") == ["humaneval_calibrated"],
        "Base live-run config must target humaneval_calibrated only",
    )

    trials_per_model = int(matrix.get("trials_per_model", 0))
    max_trials_without_reapproval = int(matrix.get("max_trials_without_reapproval", 0))
    assumed_input_tokens_per_call = int(matrix.get("assumed_input_tokens_per_call", 0))
    max_estimated_cost_usd = float(matrix.get("max_estimated_cost_usd", 0))
    _require_positive("trials_per_model", trials_per_model)
    _require_positive("max_trials_without_reapproval", max_trials_without_reapproval)
    _require_positive("assumed_input_tokens_per_call", assumed_input_tokens_per_call)
    _require_positive("max_estimated_cost_usd", max_estimated_cost_usd)
    _require(
        trials_per_model <= max_trials_without_reapproval <= 10,
        "Model matrix trials must stay bounded without reapproval",
    )
    _require(matrix.get("pricing_checked_at"), "Model matrix must record pricing_checked_at")

    preflight = matrix.get("required_preflight", [])
    _require(
        any("scripts/verify_demo_path.py" in command for command in preflight),
        "Model matrix preflight must include verify_demo_path.py",
    )
    _require(
        any("scripts/plan_eval_matrix.py" in command for command in preflight),
        "Model matrix preflight must include the no-spend eval matrix planner",
    )
    _require(
        any("scripts/estimate_model_matrix_cost.py" in command for command in preflight),
        "Model matrix preflight must include this estimator",
    )
    _require(
        any("scripts/run_model_matrix.py --dry-run" in command for command in preflight),
        "Model matrix preflight must include the dry-run executor",
    )

    scorecard = matrix.get("post_run_scorecard_template", {})
    _require(
        scorecard.get("require_improvement") is True,
        "Model matrix post-run scorecard must require improvement",
    )
    _require(
        "scripts/summarize_archive_scores.py" in scorecard.get("command", ""),
        "Model matrix post-run scorecard command must summarize archive scores",
    )
    _require(
        "--require-improvement" in scorecard.get("command", ""),
        "Model matrix post-run scorecard must fail closed without improvement",
    )

    models = matrix.get("models", [])
    _require(isinstance(models, list) and len(models) >= 2, "Model matrix needs at least two models")

    base_estimate = estimate_live_run_cost(
        config_path=base_config_path,
        input_price_per_mtok=1,
        output_price_per_mtok=1,
        assumed_input_tokens_per_call=assumed_input_tokens_per_call,
    )
    request_ceiling = int(base_estimate["request_ceiling"])

    model_reports: list[dict[str, Any]] = []
    providers: set[str] = set()
    for raw_model in models:
        _require(isinstance(raw_model, dict), "Each model entry must be a mapping")
        _require(raw_model.get("id"), "Each model must define id")
        _require(raw_model.get("provider"), f"Model {raw_model.get('id')} must define provider")
        _require(raw_model.get("model"), f"Model {raw_model.get('id')} must define model")
        _require(raw_model.get("api_key_env"), f"Model {raw_model.get('id')} must define api_key_env")
        _require(raw_model.get("pricing_source"), f"Model {raw_model.get('id')} must define pricing_source")
        _require(
            str(raw_model["pricing_source"]).startswith("https://"),
            f"Model {raw_model['id']} pricing_source must be an HTTPS URL",
        )
        _require_no_secret_fields(raw_model)

        provider = str(raw_model["provider"])
        providers.add(provider)
        if provider == "openai_compatible":
            base_url = str(raw_model.get("base_url", ""))
            _require(
                base_url.startswith(("https://", "http://")),
                f"Model {raw_model['id']} must define an OpenAI-compatible base_url",
            )

        model_reports.append(
            _model_cost(
                model=raw_model,
                request_ceiling=request_ceiling,
                assumed_input_tokens_per_call=assumed_input_tokens_per_call,
                trials_per_model=trials_per_model,
            )
        )

    _require("anthropic" in providers, "Model matrix must include an Anthropic baseline")
    _require(
        "openai_compatible" in providers,
        "Model matrix must include an OpenAI-compatible comparison model",
    )

    total_cost = sum(item["estimated_total_cost_usd"] for item in model_reports)
    total_requests = sum(item["total_request_ceiling"] for item in model_reports)
    within_budget = total_cost <= max_estimated_cost_usd
    _require(within_budget, "Model matrix estimate exceeds configured max budget")

    return {
        "name": "live_model_matrix_plan",
        "status": "ok",
        "config": str(config_path.relative_to(project_root)),
        "base_live_run_config": str(base_config_path.relative_to(project_root)),
        "benchmark": matrix["benchmark"],
        "approval_required": True,
        "dry_run_only": True,
        "live_calls_performed": 0,
        "pricing_checked_at": str(matrix["pricing_checked_at"]),
        "trials_per_model": trials_per_model,
        "model_count": len(model_reports),
        "request_ceiling_per_trial": request_ceiling,
        "total_request_ceiling": total_requests,
        "assumed_input_tokens_per_call": assumed_input_tokens_per_call,
        "estimated_total_cost_usd": total_cost,
        "max_estimated_cost_usd": max_estimated_cost_usd,
        "within_budget": within_budget,
        "models": model_reports,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "config" / "live_model_matrix.yaml"),
        help="Dry-run model-matrix config to verify and estimate.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a one-line status.",
    )
    return parser


def _main(args: argparse.Namespace) -> int:
    try:
        report = estimate_model_matrix_cost(Path(args.config))
    except ModelMatrixPlanError as exc:
        if args.json:
            print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        else:
            print(f"[fail] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            "[ok] live_model_matrix_plan "
            f"models={report['model_count']} "
            f"trials_per_model={report['trials_per_model']} "
            f"requests<={report['total_request_ceiling']} "
            f"total=${report['estimated_total_cost_usd']:.4f} "
            "dry_run_only=true"
        )
    return 0


def main() -> int:
    return _main(_build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
