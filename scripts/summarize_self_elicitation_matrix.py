#!/usr/bin/env python3
"""Summarize a completed self-elicitation matrix from durable run artifacts."""

from __future__ import annotations

import argparse
import ast
import json
import statistics
from pathlib import Path
from typing import Any

import yaml


FAILURE_MODE_KEYS = (
    "no-op",
    "malformed edit",
    "invalid Python",
    "unsafe complexity",
    "timeout/provider failure",
    "hidden-test failure",
    "completion/protocol failure",
)


class SummaryError(RuntimeError):
    """Raised when matrix artifacts are missing or internally inconsistent."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SummaryError(f"Missing artifact: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SummaryError(f"Invalid JSON artifact {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SummaryError(f"Expected a JSON object in {path}")
    return data


def _final_failure_modes(log_path: Path) -> dict[str, int]:
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError as exc:
        raise SummaryError(f"Missing artifact: {log_path}") from exc

    result: dict[str, int] = {}
    for line in lines:
        marker = "Failure modes: "
        if marker not in line:
            continue
        try:
            parsed = ast.literal_eval(line.split(marker, 1)[1])
        except (SyntaxError, ValueError):
            continue
        if isinstance(parsed, dict):
            result = {str(key): int(value) for key, value in parsed.items()}
    return result


def summarize_run(run_dir: Path) -> dict[str, Any]:
    """Extract the comparable fields from one native or evolution worker."""
    scorecard = _load_json(run_dir / "scorecard.json")
    telemetry = _load_json(run_dir / "telemetry.json")
    agents = scorecard.get("loop_order_agents") or []
    try:
        base = next(item for item in agents if int(item.get("generation", -1)) == 0)
        top = next(
            item for item in agents if item.get("agent_id") == scorecard["top_agent_id"]
        )
    except (KeyError, StopIteration) as exc:
        raise SummaryError(f"Incomplete scorecard in {run_dir}") from exc

    mutation = scorecard.get("mutation_summary") or {}
    provider = telemetry.get("provider") or {}
    tokens = telemetry.get("tokens") or {}
    runtime = telemetry.get("run") or {}
    report = telemetry.get("dgm_report") or {}
    improvements = []
    for item in scorecard.get("improvements") or []:
        improvements.append(
            {
                "parent_score": item.get("parent_average_score"),
                "child_score": item.get("child_average_score"),
                "gains": sorted((item.get("benchmark_improvements") or {}).keys()),
                "losses": sorted((item.get("benchmark_regressions") or {}).keys()),
            }
        )

    try:
        exit_code = int((run_dir / "exit_code").read_text(encoding="utf-8").strip())
    except FileNotFoundError as exc:
        raise SummaryError(f"Missing artifact: {run_dir / 'exit_code'}") from exc

    return {
        "run_id": run_dir.name,
        "exit_code": exit_code,
        "baseline_solved": int(base["solved_count"]),
        "top_solved": int(top["solved_count"]),
        "top_generation": int(top["generation"]),
        "total_agents": int(scorecard.get("total_agents", 0)),
        "valid_agents": int(scorecard.get("valid_agents", 0)),
        "changed": int(mutation.get("changed_count", 0)),
        "noop": int(mutation.get("noop_count", 0)),
        "unknown": int(mutation.get("unknown_count", 0)),
        "has_improvement": bool(scorecard.get("has_improvement")),
        "improvement_edges": improvements,
        "tokens": int(tokens.get("total_tokens", 0)),
        "prompt_tokens": int(tokens.get("prompt_tokens", 0)),
        "completion_tokens": int(tokens.get("completion_tokens", 0)),
        "telemetry_cost_usd": float(tokens.get("estimated_cost_usd", 0.0)),
        "runtime_seconds": float(runtime.get("observed_runtime_seconds") or 0.0),
        "provider_timeouts": int(provider.get("timeout_count", 0)),
        "provider_api_errors": int(provider.get("api_error_count", 0)),
        "empty_responses": int(provider.get("empty_response_count", 0)),
        "failure_modes": _final_failure_modes(run_dir / "controller.log"),
        "generation_loops": int(report.get("total_generations", 0)),
    }


def _match_slug(run_id: str, slugs: list[str], *, evolution: bool) -> str:
    for slug in sorted(slugs, key=len, reverse=True):
        suffixes = (f"-{slug}-w01", f"-{slug}-w02") if evolution else (f"-{slug}",)
        if run_id.endswith(suffixes):
            return slug
    raise SummaryError(f"Cannot map run id to a configured model: {run_id}")


def summarize_matrix(*, matrix_path: Path, artifacts_root: Path) -> dict[str, Any]:
    """Build the aggregate report for one completed broad-credible matrix."""
    try:
        matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SummaryError(f"Missing matrix config: {matrix_path}") from exc
    if not isinstance(matrix, dict) or not isinstance(matrix.get("models"), list):
        raise SummaryError(f"Invalid matrix config: {matrix_path}")

    models = {item["slug"]: item for item in matrix["models"]}
    slugs = list(models)
    evolution_rows: dict[str, list[dict[str, Any]]] = {slug: [] for slug in slugs}
    native_rows: dict[str, dict[str, Any]] = {}

    evolution_root = artifacts_root / "recovered-gcs"
    native_root = artifacts_root / "recovered-native"
    for run_dir in sorted(path for path in evolution_root.iterdir() if path.is_dir()):
        slug = _match_slug(run_dir.name, slugs, evolution=True)
        evolution_rows[slug].append(summarize_run(run_dir))
    for run_dir in sorted(path for path in native_root.iterdir() if path.is_dir()):
        slug = _match_slug(run_dir.name, slugs, evolution=False)
        if slug in native_rows:
            raise SummaryError(f"Multiple extra native runs found for {slug}")
        native_rows[slug] = summarize_run(run_dir)

    model_rows = []
    for slug, model in models.items():
        ladders = sorted(evolution_rows[slug], key=lambda item: item["run_id"])
        if len(ladders) != 2:
            raise SummaryError(f"Expected two evolution ladders for {slug}; found {len(ladders)}")
        if slug not in native_rows:
            raise SummaryError(f"Missing extra native run for {slug}")

        native = native_rows[slug]
        observations = [native["baseline_solved"], *(row["baseline_solved"] for row in ladders)]
        tops = [row["top_solved"] for row in ladders]
        changed = sum(row["changed"] for row in ladders)
        noop = sum(row["noop"] for row in ladders)
        unknown = sum(row["unknown"] for row in ladders)
        attempts = changed + noop + unknown
        native_median = statistics.median(observations)
        replicated_floor = min(tops)
        reliable_score = max(native_median, replicated_floor)
        provider_api_errors = sum(row["provider_api_errors"] for row in ladders)
        measurement_status = "measured"
        if changed == 0 and provider_api_errors:
            measurement_status = "protocol_blocked"
        elif changed == 0:
            measurement_status = "no_valid_self_edit"

        capability_overhang = reliable_score - native_median
        native_realization = native_median / reliable_score if reliable_score else None
        if measurement_status == "protocol_blocked":
            capability_overhang = None
            native_realization = None

        model_rows.append(
            {
                "slug": slug,
                "model": model["model"],
                "vendor": model["vendor"],
                "measurement_status": measurement_status,
                "native_observations": observations,
                "native_median": native_median,
                "native_min": min(observations),
                "native_max": max(observations),
                "ladder_tops": tops,
                "observed_peak": max(tops),
                "replicated_ladder_floor": replicated_floor,
                "reliable_score": reliable_score,
                "capability_overhang": capability_overhang,
                "native_realization": native_realization,
                "changed_mutations": changed,
                "noop_mutations": noop,
                "mutation_attempts_recorded": attempts,
                "noop_rate": noop / attempts if attempts else None,
                "ladders": ladders,
                "native_run": native,
            }
        )

    evolution = [row for rows in evolution_rows.values() for row in rows]
    native = list(native_rows.values())

    def sum_rows(rows: list[dict[str, Any]], key: str) -> float:
        return sum(row[key] for row in rows)

    return {
        "schema_version": 1,
        "matrix": matrix.get("name"),
        "segment_id": (matrix.get("segment") or {}).get("segment_id"),
        "models": model_rows,
        "totals": {
            "models": len(model_rows),
            "ladders": len(evolution),
            "exit_zero": sum(row["exit_code"] == 0 for row in evolution),
            "generation_attempt_ceiling": (
                len(evolution)
                * int((matrix.get("evolution") or {}).get("generations_per_worker", 0))
            ),
            "generation_loops": int(sum_rows(evolution, "generation_loops")),
            "ladders_with_improvement": sum(row["has_improvement"] for row in evolution),
            "changed_mutations": int(sum_rows(evolution, "changed")),
            "noop_mutations": int(sum_rows(evolution, "noop")),
            "valid_agents": int(sum_rows(evolution, "valid_agents")),
            "total_agents": int(sum_rows(evolution, "total_agents")),
            "tokens": int(sum_rows(evolution, "tokens")),
            "telemetry_cost_usd": sum_rows(evolution, "telemetry_cost_usd"),
            "runtime_seconds": sum_rows(evolution, "runtime_seconds"),
            "provider_timeouts": int(sum_rows(evolution, "provider_timeouts")),
            "provider_api_errors": int(sum_rows(evolution, "provider_api_errors")),
            "empty_responses": int(sum_rows(evolution, "empty_responses")),
            "failure_modes": {
                key: sum(row["failure_modes"].get(key, 0) for row in evolution)
                for key in FAILURE_MODE_KEYS
            },
        },
        "native_totals": {
            "runs": len(native),
            "exit_zero": sum(row["exit_code"] == 0 for row in native),
            "tokens": int(sum_rows(native, "tokens")),
            "telemetry_cost_usd": sum_rows(native, "telemetry_cost_usd"),
            "runtime_seconds": sum_rows(native, "runtime_seconds"),
            "provider_timeouts": int(sum_rows(native, "provider_timeouts")),
            "provider_api_errors": int(sum_rows(native, "provider_api_errors")),
            "empty_responses": int(sum_rows(native, "empty_responses")),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--artifacts-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = summarize_matrix(matrix_path=args.matrix, artifacts_root=args.artifacts_root)
    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
