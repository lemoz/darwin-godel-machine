#!/usr/bin/env python3
"""Estimate a bounded live DGM run cost from config and current token prices."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CostEstimateError(RuntimeError):
    """Raised when a live-run cost estimate cannot be computed safely."""


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise CostEstimateError(f"Missing config: {path}") from exc
    except yaml.YAMLError as exc:
        raise CostEstimateError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise CostEstimateError(f"Config must be a mapping: {path}")
    return data


def _require_positive(name: str, value: float) -> None:
    if value <= 0:
        raise CostEstimateError(f"{name} must be greater than zero")


def _require_price(name: str, value: float, *, allow_zero_pricing: bool) -> None:
    if allow_zero_pricing:
        if value < 0:
            raise CostEstimateError(f"{name} must be zero or greater")
    else:
        _require_positive(name, value)


def estimate_live_run_cost(
    *,
    config_path: Path,
    input_price_per_mtok: float,
    output_price_per_mtok: float,
    assumed_input_tokens_per_call: int,
    max_budget: float | None = None,
    allow_zero_pricing: bool = False,
    mutation_input_price_per_mtok: float | None = None,
    mutation_output_price_per_mtok: float | None = None,
) -> dict[str, Any]:
    """Estimate the bounded cost ceiling for a planned live DGM run.

    The DGM benchmark runner asks the agent to solve each enabled benchmark once;
    benchmark YAML test cases validate that solution locally and do not add model
    calls. A full run initializes the base agent once, then each generation runs
    one self-modification task plus one child evaluation pass.
    """
    _require_price(
        "input_price_per_mtok",
        input_price_per_mtok,
        allow_zero_pricing=allow_zero_pricing,
    )
    _require_price(
        "output_price_per_mtok",
        output_price_per_mtok,
        allow_zero_pricing=allow_zero_pricing,
    )
    _require_positive("assumed_input_tokens_per_call", assumed_input_tokens_per_call)

    config = _load_yaml(config_path)
    primary = config.get("fm_providers", {}).get("primary")
    provider = config.get("fm_providers", {}).get(primary, {})
    if not provider:
        raise CostEstimateError("Config must define the primary provider settings")

    enabled_benchmarks = config.get("benchmarks", {}).get("enabled", [])
    if not enabled_benchmarks:
        raise CostEstimateError("Config must enable at least one benchmark")

    live_run = config.get("live_run", {})
    generations = live_run.get("recommended_generations")
    if generations is None:
        raise CostEstimateError("Config live_run must define recommended_generations")

    benchmark_max_steps = int(config.get("agents", {}).get("max_steps", 0))
    self_modification_max_steps = int(
        config.get("self_modification", {}).get("max_steps", benchmark_max_steps)
    )
    mutation_provider_key = config.get("self_modification", {}).get(
        "fm_provider",
        primary,
    )
    mutation_provider = config.get("fm_providers", {}).get(
        mutation_provider_key,
        {},
    )
    if not mutation_provider:
        raise CostEstimateError(
            "Config self_modification.fm_provider must name provider settings"
        )
    if mutation_provider_key != primary:
        if mutation_input_price_per_mtok is None or mutation_output_price_per_mtok is None:
            raise CostEstimateError(
                "Distinct mutation provider requires mutation input and output prices"
            )
    mutation_input_price = (
        input_price_per_mtok
        if mutation_input_price_per_mtok is None
        else mutation_input_price_per_mtok
    )
    mutation_output_price = (
        output_price_per_mtok
        if mutation_output_price_per_mtok is None
        else mutation_output_price_per_mtok
    )
    _require_price(
        "mutation_input_price_per_mtok",
        mutation_input_price,
        allow_zero_pricing=allow_zero_pricing,
    )
    _require_price(
        "mutation_output_price_per_mtok",
        mutation_output_price,
        allow_zero_pricing=allow_zero_pricing,
    )

    output_tokens_per_call = int(provider.get("max_tokens", 0))
    mutation_output_tokens_per_call = int(mutation_provider.get("max_tokens", 0))
    timeout_retry_multiplier = max(1, int(provider.get("timeout_retries", 0) or 0) + 1)
    mutation_timeout_retry_multiplier = max(
        1,
        int(mutation_provider.get("timeout_retries", 0) or 0) + 1,
    )
    benchmark_count = len(enabled_benchmarks)
    _require_positive("recommended_generations", int(generations))
    _require_positive("agents.max_steps", benchmark_max_steps)
    _require_positive("self_modification.max_steps", self_modification_max_steps)
    _require_positive("provider.max_tokens", output_tokens_per_call)
    _require_positive(
        "mutation_provider.max_tokens",
        mutation_output_tokens_per_call,
    )

    base_evaluation_requests = benchmark_count * benchmark_max_steps
    evaluation_requests_per_generation = benchmark_count * benchmark_max_steps
    evaluation_request_ceiling_without_retries = base_evaluation_requests + (
        int(generations) * evaluation_requests_per_generation
    )
    mutation_request_ceiling_without_retries = (
        int(generations) * self_modification_max_steps
    )
    evaluation_request_ceiling = (
        evaluation_request_ceiling_without_retries * timeout_retry_multiplier
    )
    mutation_request_ceiling = (
        mutation_request_ceiling_without_retries
        * mutation_timeout_retry_multiplier
    )
    request_ceiling_without_retries = (
        evaluation_request_ceiling_without_retries
        + mutation_request_ceiling_without_retries
    )
    request_ceiling = evaluation_request_ceiling + mutation_request_ceiling
    evaluation_input_token_ceiling = (
        evaluation_request_ceiling * assumed_input_tokens_per_call
    )
    mutation_input_token_ceiling = (
        mutation_request_ceiling * assumed_input_tokens_per_call
    )
    evaluation_output_token_ceiling = (
        evaluation_request_ceiling * output_tokens_per_call
    )
    mutation_output_token_ceiling = (
        mutation_request_ceiling * mutation_output_tokens_per_call
    )
    input_token_ceiling = (
        evaluation_input_token_ceiling + mutation_input_token_ceiling
    )
    output_token_ceiling = (
        evaluation_output_token_ceiling + mutation_output_token_ceiling
    )
    input_cost = (
        evaluation_input_token_ceiling / 1_000_000 * input_price_per_mtok
        + mutation_input_token_ceiling / 1_000_000 * mutation_input_price
    )
    output_cost = (
        evaluation_output_token_ceiling / 1_000_000 * output_price_per_mtok
        + mutation_output_token_ceiling / 1_000_000 * mutation_output_price
    )
    total_cost = input_cost + output_cost

    return {
        "config": str(config_path),
        "model": provider.get("model"),
        "provider": primary,
        "mutation_model": mutation_provider.get("model"),
        "mutation_provider": mutation_provider_key,
        "enabled_benchmarks": list(enabled_benchmarks),
        "benchmark_count": benchmark_count,
        "generations": int(generations),
        "max_agent_steps": benchmark_max_steps,
        "max_self_modification_steps": self_modification_max_steps,
        "timeout_retry_multiplier": timeout_retry_multiplier,
        "mutation_timeout_retry_multiplier": mutation_timeout_retry_multiplier,
        "request_ceiling": request_ceiling,
        "request_ceiling_without_retries": request_ceiling_without_retries,
        "base_evaluation_request_ceiling": base_evaluation_requests,
        "requests_per_generation_ceiling": (
            evaluation_requests_per_generation + self_modification_max_steps
        ),
        "evaluation_request_ceiling": evaluation_request_ceiling,
        "mutation_request_ceiling": mutation_request_ceiling,
        "assumed_input_tokens_per_call": assumed_input_tokens_per_call,
        "max_output_tokens_per_call": output_tokens_per_call,
        "mutation_max_output_tokens_per_call": mutation_output_tokens_per_call,
        "input_token_ceiling": input_token_ceiling,
        "output_token_ceiling": output_token_ceiling,
        "input_price_per_mtok": input_price_per_mtok,
        "output_price_per_mtok": output_price_per_mtok,
        "mutation_input_price_per_mtok": mutation_input_price,
        "mutation_output_price_per_mtok": mutation_output_price,
        "estimated_input_cost_usd": input_cost,
        "estimated_output_cost_usd": output_cost,
        "estimated_total_cost_usd": total_cost,
        "max_budget_usd": max_budget,
        "within_budget": max_budget is None or total_cost <= max_budget,
        "allow_zero_pricing": allow_zero_pricing,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "config" / "live_score_movement.yaml"),
        help="Live-run config to estimate.",
    )
    parser.add_argument(
        "--input-price-per-mtok",
        type=float,
        required=True,
        help="Current provider input price in USD per million tokens.",
    )
    parser.add_argument(
        "--output-price-per-mtok",
        type=float,
        required=True,
        help="Current provider output price in USD per million tokens.",
    )
    parser.add_argument(
        "--mutation-input-price-per-mtok",
        type=float,
        help="Mutation-provider input price; required when it differs from primary.",
    )
    parser.add_argument(
        "--mutation-output-price-per-mtok",
        type=float,
        help="Mutation-provider output price; required when it differs from primary.",
    )
    parser.add_argument(
        "--assumed-input-tokens-per-call",
        type=int,
        default=50_000,
        help="Conservative input-token assumption for each model call.",
    )
    parser.add_argument(
        "--max-budget",
        type=float,
        help="Optional USD ceiling; exits non-zero if the estimate exceeds it.",
    )
    parser.add_argument(
        "--allow-zero-pricing",
        action="store_true",
        help="Allow explicit zero-dollar pricing for provider-advertised free endpoints.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )
    return parser


def _main(args: argparse.Namespace) -> int:
    try:
        estimate = estimate_live_run_cost(
            config_path=Path(args.config),
            input_price_per_mtok=args.input_price_per_mtok,
            output_price_per_mtok=args.output_price_per_mtok,
            assumed_input_tokens_per_call=args.assumed_input_tokens_per_call,
            max_budget=args.max_budget,
            allow_zero_pricing=args.allow_zero_pricing,
            mutation_input_price_per_mtok=args.mutation_input_price_per_mtok,
            mutation_output_price_per_mtok=args.mutation_output_price_per_mtok,
        )
    except CostEstimateError as exc:
        if args.json:
            print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        else:
            print(f"[fail] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {"status": "ok", "estimate": estimate},
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(
            "live run cost estimate: "
            f"requests<={estimate['request_ceiling']} "
            f"input_tokens<={estimate['input_token_ceiling']} "
            f"output_tokens<={estimate['output_token_ceiling']} "
            f"total=${estimate['estimated_total_cost_usd']:.4f}"
        )

    if not estimate["within_budget"]:
        print(
            "[fail] estimated total exceeds max budget "
            f"(${estimate['max_budget_usd']:.2f})",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> int:
    return _main(_build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
