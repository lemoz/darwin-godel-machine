#!/usr/bin/env python3
"""Estimate the Luna runner matrix from observed DGM token telemetry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = PROJECT_ROOT / "config/livecodebench_luna_runner_matrix.yaml"
DEFAULT_PROOF = PROJECT_ROOT / "docs/live-runs/lcb64-fable5-mutator-gemma3-20260712-1"


class MatrixEstimateError(RuntimeError):
    """Raised when observed telemetry cannot support a bounded matrix estimate."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MatrixEstimateError(message)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), f"expected JSON object: {path}")
    return payload


def estimate_matrix(
    *,
    matrix_path: Path = DEFAULT_MATRIX,
    proof_dir: Path = DEFAULT_PROOF,
) -> dict[str, Any]:
    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8")) or {}
    models = matrix.get("models") or []
    _require(len(models) == 10, "matrix estimate requires ten models")
    mutation_model = matrix.get("mutation", {}).get("model")
    _require(mutation_model == "openai/gpt-5.6-luna", "matrix mutator must be Luna")

    telemetry_paths = sorted((proof_dir / "workers").glob("w*/telemetry.json"))
    _require(len(telemetry_paths) == 4, "reference proof must contain four telemetry files")
    source_generations = 0
    evaluation_prompt = 0
    evaluation_completion = 0
    mutation_prompt = 0
    mutation_completion = 0
    for path in telemetry_paths:
        telemetry = _load_json(path)
        source_generations += int(telemetry["dgm_report"]["total_generations"])
        by_model = telemetry["tokens"]["by_model"]
        evaluation = by_model["google/gemma-3-27b-it"]
        mutation = by_model["anthropic/claude-fable-5"]
        evaluation_prompt += int(evaluation["prompt_tokens"])
        evaluation_completion += int(evaluation["completion_tokens"])
        mutation_prompt += int(mutation["prompt_tokens"])
        mutation_completion += int(mutation["completion_tokens"])
    _require(source_generations == 64, "reference proof must contain 64 generations")

    eval_prompt_per_run = evaluation_prompt / source_generations
    eval_completion_per_run = evaluation_completion / source_generations
    mutation_prompt_per_generation = mutation_prompt / source_generations
    mutation_completion_per_generation = mutation_completion / source_generations
    seed_mode = matrix["evolution"].get("seed_mode", "calibrated_archive")
    fresh_native = seed_mode == "fresh_native"
    calibration_runs_per_model = (
        0
        if fresh_native
        else len(matrix["seed"]["agent_ids"])
        * int(matrix["calibration"]["replicates"])
    )
    base_initializations_per_model = (
        int(matrix["evolution"]["workers_per_model"]) if fresh_native else 0
    )
    evolution_generations_per_model = (
        int(matrix["evolution"]["workers_per_model"])
        * int(matrix["evolution"]["generations_per_worker"])
    )
    mutation = matrix["mutation"]
    mutation_prompt_total = (
        mutation_prompt_per_generation * evolution_generations_per_model * len(models)
    )
    mutation_completion_total = (
        mutation_completion_per_generation * evolution_generations_per_model * len(models)
    )
    mutation_cost = (
        mutation_prompt_total / 1_000_000 * float(mutation["input_price_per_mtok"])
        + mutation_completion_total
        / 1_000_000
        * float(mutation["output_price_per_mtok"])
    )

    model_rows = []
    calibration_evaluation_cost = 0.0
    evolution_evaluation_cost = 0.0
    for model in models:
        calibration_prompt_tokens = eval_prompt_per_run * calibration_runs_per_model
        calibration_completion_tokens = eval_completion_per_run * calibration_runs_per_model
        evolution_evaluations = (
            evolution_generations_per_model + base_initializations_per_model
        )
        evolution_prompt_tokens = eval_prompt_per_run * evolution_evaluations
        evolution_completion_tokens = eval_completion_per_run * evolution_evaluations
        calibration_cost = (
            calibration_prompt_tokens
            / 1_000_000
            * float(model["input_price_per_mtok"])
            + calibration_completion_tokens
            / 1_000_000
            * float(model["output_price_per_mtok"])
        )
        evolution_cost = (
            evolution_prompt_tokens / 1_000_000 * float(model["input_price_per_mtok"])
            + evolution_completion_tokens
            / 1_000_000
            * float(model["output_price_per_mtok"])
        )
        calibration_evaluation_cost += calibration_cost
        evolution_evaluation_cost += evolution_cost
        model_rows.append(
            {
                "slug": model["slug"],
                "model": model["model"],
                "calibration_evaluations": calibration_runs_per_model,
                "base_initializations": base_initializations_per_model,
                "evolution_generations": evolution_generations_per_model,
                "estimated_calibration_runner_cost_usd": calibration_cost,
                "estimated_evolution_runner_cost_usd": evolution_cost,
                "estimated_runner_tokens": round(
                    calibration_prompt_tokens
                    + calibration_completion_tokens
                    + evolution_prompt_tokens
                    + evolution_completion_tokens
                ),
                "estimated_runner_cost_usd": calibration_cost + evolution_cost,
            }
        )

    evaluation_cost = calibration_evaluation_cost + evolution_evaluation_cost
    estimated_calibration_openrouter_cost = calibration_evaluation_cost
    estimated_evolution_openrouter_cost = evolution_evaluation_cost + mutation_cost
    estimated_openrouter_cost = (
        estimated_calibration_openrouter_cost + estimated_evolution_openrouter_cost
    )
    cloud = matrix["cloud"]
    calibration_vm_hours = (
        0.0
        if fresh_native
        else len(models) * float(cloud["calibration_hours_per_vm"])
    )
    evolution_vm_hours = (
        len(models)
        * int(matrix["evolution"]["workers_per_model"])
        * float(cloud["evolution_hours_per_vm"])
    )
    estimated_gcp_cost = (
        calibration_vm_hours + evolution_vm_hours
    ) * float(cloud["hourly_vm_cost_estimate_usd"])
    reserved_openrouter = float(
        matrix.get("budget", {}).get(
            "reserved_failed_calibration_openrouter_usd",
            0.0,
        )
    )
    reserved_gcp = float(
        matrix.get("budget", {}).get("reserved_failed_calibration_gcp_usd", 0.0)
    )
    estimated_openrouter_cost_with_reserved = (
        estimated_openrouter_cost + reserved_openrouter
    )
    estimated_total_cost = (
        estimated_openrouter_cost_with_reserved + estimated_gcp_cost + reserved_gcp
    )
    calibration_openrouter_budget = float(
        matrix["calibration"]["max_openrouter_budget_usd"]
    )
    evolution_openrouter_budget = float(matrix["evolution"]["max_openrouter_budget_usd"])
    openrouter_budget = float(matrix["budget"]["max_openrouter_total_usd"])
    total_budget = float(cloud["max_total_experiment_cost_usd"])
    _require(
        estimated_calibration_openrouter_cost <= calibration_openrouter_budget,
        "observed-token calibration estimate exceeds the calibration budget",
    )
    _require(
        estimated_evolution_openrouter_cost <= evolution_openrouter_budget,
        "observed-token evolution estimate exceeds the evolution budget",
    )
    _require(
        estimated_openrouter_cost_with_reserved <= openrouter_budget,
        "observed-token OpenRouter estimate exceeds the total matrix budget",
    )
    _require(
        estimated_total_cost <= total_budget,
        "observed-token total estimate exceeds the experiment budget",
    )
    return {
        "schema_version": 1,
        "name": "luna_runner_matrix_observed_cost_estimate",
        "matrix": str(matrix_path),
        "reference_proof": str(proof_dir),
        "reference_generations": source_generations,
        "models": len(models),
        "seed_mode": seed_mode,
        "calibration_evaluations_per_model": calibration_runs_per_model,
        "base_initializations_per_model": base_initializations_per_model,
        "evolution_generations_per_model": evolution_generations_per_model,
        "total_evolution_generations": evolution_generations_per_model * len(models),
        "observed_tokens_per_unit": {
            "runner_prompt": eval_prompt_per_run,
            "runner_completion": eval_completion_per_run,
            "mutation_prompt": mutation_prompt_per_generation,
            "mutation_completion": mutation_completion_per_generation,
        },
        "estimated_runner_cost_usd": evaluation_cost,
        "estimated_luna_mutation_cost_usd": mutation_cost,
        "estimated_calibration_openrouter_cost_usd": estimated_calibration_openrouter_cost,
        "estimated_evolution_openrouter_cost_usd": estimated_evolution_openrouter_cost,
        "estimated_prospective_openrouter_cost_usd": estimated_openrouter_cost,
        "reserved_failed_calibration_openrouter_usd": reserved_openrouter,
        "estimated_openrouter_cost_usd": estimated_openrouter_cost_with_reserved,
        "calibration_openrouter_budget_usd": calibration_openrouter_budget,
        "evolution_openrouter_budget_usd": evolution_openrouter_budget,
        "openrouter_budget_usd": openrouter_budget,
        "estimated_gcp_vm_hours": calibration_vm_hours + evolution_vm_hours,
        "estimated_gcp_cost_usd": estimated_gcp_cost,
        "reserved_failed_calibration_gcp_usd": reserved_gcp,
        "estimated_total_cost_usd": estimated_total_cost,
        "total_budget_usd": total_budget,
        "within_budget": True,
        "models_detail": model_rows,
        "note": (
            "Expected cost uses observed prompt and completion tokens from the completed "
            "64-generation Fable/Gemma proof. The live account-wide watchdog remains the "
            "hard OpenRouter limit."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--proof-dir", type=Path, default=DEFAULT_PROOF)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = estimate_matrix(matrix_path=args.matrix, proof_dir=args.proof_dir)
    except (OSError, KeyError, ValueError, MatrixEstimateError, yaml.YAMLError) as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
