#!/usr/bin/env python3
"""Estimate a DGM live-run token and cost ceiling without calling model APIs."""

import argparse
import json
from typing import Any, Dict

import yaml


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def estimate_live_run(
    config: Dict[str, Any],
    generations: int,
    avg_input_tokens_per_call: int,
    input_usd_per_mtok: float,
    output_usd_per_mtok: float,
) -> Dict[str, Any]:
    """Estimate upper-bound output spend and assumed input spend."""
    provider = config["fm_providers"]["primary"]
    provider_config = config["fm_providers"][provider]
    enabled_benchmarks = config["benchmarks"]["enabled"]
    max_steps = int(config["agents"].get("max_steps", 20))
    max_output_tokens = int(provider_config.get("max_tokens", 8192))

    base_evaluation_tasks = len(enabled_benchmarks)
    tasks_per_generation = 1 + len(enabled_benchmarks)  # self-modification + evaluation
    total_agent_tasks = base_evaluation_tasks + generations * tasks_per_generation
    request_upper_bound = total_agent_tasks * max_steps
    input_tokens = request_upper_bound * avg_input_tokens_per_call
    output_token_ceiling = request_upper_bound * max_output_tokens
    input_cost = input_tokens / 1_000_000 * input_usd_per_mtok
    output_cost = output_token_ceiling / 1_000_000 * output_usd_per_mtok

    return {
        "provider": provider,
        "model": provider_config.get("model"),
        "generations": generations,
        "enabled_benchmarks": enabled_benchmarks,
        "base_evaluation_tasks": base_evaluation_tasks,
        "tasks_per_generation": tasks_per_generation,
        "total_agent_tasks": total_agent_tasks,
        "max_steps_per_task": max_steps,
        "request_upper_bound": request_upper_bound,
        "avg_input_tokens_per_call": avg_input_tokens_per_call,
        "input_tokens_assumed": input_tokens,
        "max_output_tokens_per_call": max_output_tokens,
        "output_token_ceiling": output_token_ceiling,
        "input_usd_per_mtok": input_usd_per_mtok,
        "output_usd_per_mtok": output_usd_per_mtok,
        "input_cost_usd": round(input_cost, 4),
        "output_cost_ceiling_usd": round(output_cost, 4),
        "estimated_total_usd": round(input_cost + output_cost, 4),
    }


def render_markdown(estimate: Dict[str, Any]) -> str:
    benchmarks = ", ".join(estimate["enabled_benchmarks"])
    return f"""# DGM Live Run Cost Estimate

- Provider/model: `{estimate["provider"]}` / `{estimate["model"]}`
- Generations: {estimate["generations"]}
- Enabled benchmarks: {benchmarks}
- Agent tasks: {estimate["total_agent_tasks"]} ({estimate["base_evaluation_tasks"]} base evaluation + {estimate["generations"]} generations x {estimate["tasks_per_generation"]})
- Request upper bound: {estimate["request_upper_bound"]} ({estimate["max_steps_per_task"]} max steps per task)
- Assumed input tokens: {estimate["input_tokens_assumed"]:,} ({estimate["avg_input_tokens_per_call"]:,} average per request)
- Output token ceiling: {estimate["output_token_ceiling"]:,} ({estimate["max_output_tokens_per_call"]:,} max output per request)
- Rates: ${estimate["input_usd_per_mtok"]}/MTok input, ${estimate["output_usd_per_mtok"]}/MTok output
- Estimated input cost: ${estimate["input_cost_usd"]:.4f}
- Estimated output ceiling cost: ${estimate["output_cost_ceiling_usd"]:.4f}
- Estimated total ceiling: ${estimate["estimated_total_usd"]:.4f}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/dgm_config.yaml")
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--avg-input-tokens-per-call", type=int, required=True)
    parser.add_argument("--input-usd-per-mtok", type=float, required=True)
    parser.add_argument("--output-usd-per-mtok", type=float, required=True)
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    args = parser.parse_args()

    estimate = estimate_live_run(
        config=load_config(args.config),
        generations=args.generations,
        avg_input_tokens_per_call=args.avg_input_tokens_per_call,
        input_usd_per_mtok=args.input_usd_per_mtok,
        output_usd_per_mtok=args.output_usd_per_mtok,
    )

    if args.format == "json":
        print(json.dumps(estimate, indent=2))
    else:
        print(render_markdown(estimate))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
