#!/usr/bin/env python3
"""Verify and price the broad credible self-elicitation experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = PROJECT_ROOT / "config/livecodebench_self_elicitation_matrix.yaml"


class SelfElicitationEstimateError(RuntimeError):
    """Raised when the declared experiment is not the credible protocol."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SelfElicitationEstimateError(message)


def estimate_self_elicitation_matrix(matrix_path: Path = DEFAULT_MATRIX) -> dict[str, Any]:
    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8")) or {}
    models = matrix.get("models") or []
    native = matrix.get("native") or {}
    evolution = matrix.get("evolution") or {}
    mutation = matrix.get("mutation") or {}
    reference = matrix.get("cost_reference") or {}
    budget = matrix.get("budget") or {}
    cloud = matrix.get("cloud") or {}

    _require(len(models) == 8, "broad credible protocol requires eight models")
    _require(mutation.get("mode") == "self", "mutation mode must be self")
    _require(int(native.get("workers_per_model", 0)) == 1, "one extra native worker is required")
    _require(int(native.get("generations_per_worker", -1)) == 0, "native workers must use zero generations")
    _require(int(evolution.get("workers_per_model", 0)) == 2, "two independent ladders are required")
    _require(int(evolution.get("generations_per_worker", 0)) == 15, "each ladder must use 15 generations")
    _require(int(reference.get("generations", 0)) == 15, "cost reference must cover 15 generations")
    _require(int(reference.get("evaluated_agents", 0)) == 16, "cost reference must cover baseline plus 15 children")

    runner_prompt = int(reference["runner_prompt_tokens"])
    runner_completion = int(reference["runner_completion_tokens"])
    combined_prompt = int(reference["combined_prompt_tokens"])
    combined_completion = int(reference["combined_completion_tokens"])
    evaluated_agents = int(reference["evaluated_agents"])
    native_prompt = runner_prompt / evaluated_agents
    native_completion = runner_completion / evaluated_agents

    model_rows = []
    expected = 0.0
    for model in models:
        input_price = float(model["input_price_per_mtok"])
        output_price = float(model["output_price_per_mtok"])
        native_cost = (
            native_prompt / 1_000_000 * input_price
            + native_completion / 1_000_000 * output_price
        )
        ladder_cost = (
            combined_prompt / 1_000_000 * input_price
            + combined_completion / 1_000_000 * output_price
        )
        credible_cost = native_cost + 2 * ladder_cost
        expected += credible_cost
        model_rows.append(
            {
                "slug": model["slug"],
                "model": model["model"],
                "extra_native_cost_usd": native_cost,
                "one_ladder_cost_usd": ladder_cost,
                "credible_model_cost_usd": credible_cost,
            }
        )

    reserve_fraction = float(budget["reserve_fraction"])
    reserved = expected * (1 + reserve_fraction)
    approved_openrouter = float(budget["approved_openrouter_ceiling_usd"])
    watchdog_stop = float(budget["watchdog_stop_total_usd"])
    watchdog_headroom = float(budget["watchdog_headroom_usd"])
    gcp_ceiling = float(budget["max_estimated_gcp_usd"])
    all_in = float(cloud["max_total_experiment_cost_usd"])
    _require(abs(expected - float(budget["empirical_expected_openrouter_usd"])) < 0.01, "declared expected cost drifted")
    _require(abs(reserved - approved_openrouter) < 0.01, "declared reserve ceiling drifted")
    _require(abs((approved_openrouter - watchdog_stop) - watchdog_headroom) < 0.01, "watchdog headroom drifted")
    _require(approved_openrouter + gcp_ceiling <= all_in + 1e-9, "OpenRouter and GCP ceilings exceed all-in approval")
    _require(float(native["watchdog_stop_usd"]) + float(evolution["max_openrouter_budget_usd"]) <= watchdog_stop, "phase watchdogs exceed total stop threshold")

    return {
        "schema_version": 1,
        "name": "self_elicitation_broad_credible_cost_estimate",
        "matrix": str(matrix_path),
        "models": len(models),
        "native_observations_per_model": 3,
        "independent_ladders_per_model": 2,
        "generations_per_ladder": 15,
        "total_extra_native_evaluations": len(models),
        "total_ladders": len(models) * 2,
        "total_generation_attempt_ceiling": len(models) * 2 * 15,
        "empirical_expected_openrouter_usd": expected,
        "reserve_fraction": reserve_fraction,
        "approved_openrouter_ceiling_usd": approved_openrouter,
        "watchdog_stop_total_usd": watchdog_stop,
        "watchdog_headroom_usd": watchdog_headroom,
        "max_estimated_gcp_usd": gcp_ceiling,
        "approved_all_in_usd": all_in,
        "within_budget": True,
        "models_detail": model_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    matrix_path = args.matrix if args.matrix.is_absolute() else PROJECT_ROOT / args.matrix
    try:
        estimate = estimate_self_elicitation_matrix(matrix_path)
    except (KeyError, OSError, ValueError, SelfElicitationEstimateError, yaml.YAMLError) as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(estimate, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
