#!/usr/bin/env python3
"""Build structured telemetry from a live DGM run's durable artifacts."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


class TelemetryError(RuntimeError):
    """Raised when live-run telemetry cannot be summarized."""


TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3})")
REQUEST_RE = re.compile(
    r"timeout:\s*(?P<timeout>[0-9.]+)s,\s*model:\s*(?P<model>[^,]+),\s*base_url:\s*(?P<base_url>[^)]+)"
)
FINISH_REASON_RE = re.compile(r"finish_reason[=:]\s*['\"]?(?P<reason>[A-Za-z0-9_-]+)")


def _load_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TelemetryError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TelemetryError(f"Invalid {label} JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise TelemetryError(f"{label} JSON must contain an object: {path}")
    return data


def _optional_json(path: Path | None, *, label: str) -> dict[str, Any] | None:
    if path is None:
        return None
    return _load_json(path, label=label)


def _parse_timestamp(line: str) -> datetime | None:
    match = TIMESTAMP_RE.match(line)
    if not match:
        return None
    return datetime.strptime(
        f"{match.group(1)}.{match.group(2)}",
        "%Y-%m-%d %H:%M:%S.%f",
    )


def _parse_api_usage(line: str) -> dict[str, int] | None:
    if "API usage:" not in line:
        return None
    raw = line.split("API usage:", 1)[1].strip()
    try:
        parsed = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return {
        "prompt_tokens": int(parsed.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(parsed.get("completion_tokens", 0) or 0),
        "total_tokens": int(parsed.get("total_tokens", 0) or 0),
    }


def _estimate_cost(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    input_price_per_mtok: float,
    output_price_per_mtok: float,
) -> float:
    return round(
        (prompt_tokens / 1_000_000) * input_price_per_mtok
        + (completion_tokens / 1_000_000) * output_price_per_mtok,
        6,
    )


def parse_controller_log(log_path: Path) -> dict[str, Any]:
    """Parse controller/provider telemetry from a DGM controller log."""
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError as exc:
        raise TelemetryError(f"Controller log not found: {log_path}") from exc

    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    usage_events = 0
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    tokens_by_model: dict[str, Counter[str]] = defaultdict(Counter)
    finish_reasons: Counter[str] = Counter()
    completion_seconds: list[float] = []
    model = None
    active_model = None
    base_url = None
    configured_timeout = None
    completed = False

    timeout_count = 0
    empty_response_count = 0
    api_error_count = 0
    error_count = 0
    http_post_count = 0
    resource_guard_rejections = 0
    traceback_count = 0

    for line in lines:
        timestamp = _parse_timestamp(line)
        if timestamp is not None:
            first_timestamp = first_timestamp or timestamp
            last_timestamp = timestamp

        usage = _parse_api_usage(line)
        if usage is not None:
            usage_events += 1
            prompt_tokens += usage["prompt_tokens"]
            completion_tokens += usage["completion_tokens"]
            total_tokens += usage["total_tokens"]
            model_tokens = tokens_by_model[active_model or "unknown"]
            model_tokens["usage_events"] += 1
            model_tokens.update(usage)

        request_match = REQUEST_RE.search(line)
        if request_match:
            model = request_match.group("model").strip()
            active_model = model
            base_url = request_match.group("base_url").strip()
            configured_timeout = float(request_match.group("timeout"))

        finish_match = FINISH_REASON_RE.search(line)
        if finish_match:
            finish_reasons[finish_match.group("reason")] += 1

        duration_match = re.search(r"completed successfully in ([0-9.]+)s", line)
        if duration_match:
            completion_seconds.append(float(duration_match.group(1)))

        lowered = line.lower()
        if "http request: post" in lowered and "/chat/completions" in lowered:
            http_post_count += 1
        if "request timed out" in lowered or "timed out after" in lowered:
            timeout_count += 1
        if "no response generated" in lowered:
            empty_response_count += 1
        if "openai-compatible api error" in lowered or "api status error" in lowered:
            api_error_count += 1
        if " - error - " in lowered or "\terror\t" in lowered or lowered.startswith("error"):
            error_count += 1
        if "resource guard rejected solution before execution" in lowered:
            resource_guard_rejections += 1
        if "Traceback (most recent call last):" in line:
            traceback_count += 1
        if "DGM run completed successfully" in line:
            completed = True

    observed_runtime_seconds = None
    if first_timestamp is not None and last_timestamp is not None:
        observed_runtime_seconds = (last_timestamp - first_timestamp).total_seconds()

    return {
        "line_count": len(lines),
        "start_time": first_timestamp.isoformat() if first_timestamp else None,
        "end_time": last_timestamp.isoformat() if last_timestamp else None,
        "observed_runtime_seconds": observed_runtime_seconds,
        "completed": completed,
        "provider": {
            "model_from_log": model,
            "base_url_from_log": base_url,
            "configured_timeout_seconds": configured_timeout,
            "http_post_count": http_post_count,
            "timeout_count": timeout_count,
            "empty_response_count": empty_response_count,
            "api_error_count": api_error_count,
            "finish_reasons": dict(sorted(finish_reasons.items())),
            "completion_latency_seconds": {
                "count": len(completion_seconds),
                "max": max(completion_seconds) if completion_seconds else None,
                "average": (
                    sum(completion_seconds) / len(completion_seconds)
                    if completion_seconds
                    else None
                ),
            },
        },
        "tokens": {
            "usage_events": usage_events,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "by_model": {
                model_name: {
                    "usage_events": int(counts.get("usage_events", 0)),
                    "prompt_tokens": int(counts.get("prompt_tokens", 0)),
                    "completion_tokens": int(counts.get("completion_tokens", 0)),
                    "total_tokens": int(counts.get("total_tokens", 0)),
                }
                for model_name, counts in sorted(tokens_by_model.items())
            },
        },
        "failure_signals": {
            "error_count": error_count,
            "traceback_count": traceback_count,
            "resource_guard_rejections": resource_guard_rejections,
        },
    }


def _generation_score(scorecard: dict[str, Any], generation: int) -> float | None:
    for item in scorecard.get("generation_best_scores") or []:
        if isinstance(item, dict) and int(item.get("generation", -1)) == generation:
            return float(item.get("average_score", 0.0))
    return None


def _solved_count(scores: dict[str, Any]) -> int:
    return sum(1 for value in scores.values() if float(value) > 0.0)


def summarize_scorecard(scorecard: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract compact score movement from an archive scorecard."""
    if scorecard is None:
        return None

    generations = []
    for item in scorecard.get("generation_best_scores") or []:
        if not isinstance(item, dict):
            continue
        benchmark_scores = item.get("benchmark_scores") or {}
        if not isinstance(benchmark_scores, dict):
            benchmark_scores = {}
        generations.append(
            {
                "generation": int(item.get("generation", 0)),
                "agent_id": item.get("agent_id"),
                "average_score": float(item.get("average_score", 0.0)),
                "benchmark_count": len(benchmark_scores),
                "solved_count": _solved_count(benchmark_scores),
            }
        )

    improvements = []
    for item in scorecard.get("improvements") or []:
        if not isinstance(item, dict):
            continue
        improvements.append(
            {
                "parent_id": item.get("parent_id"),
                "child_id": item.get("child_id"),
                "average_delta": float(item.get("average_delta", 0.0)),
                "benchmark_improvements": sorted((item.get("benchmark_improvements") or {}).keys()),
                "benchmark_regressions": sorted((item.get("benchmark_regressions") or {}).keys()),
            }
        )

    loop_order_agents = []
    for item in scorecard.get("loop_order_agents") or []:
        if not isinstance(item, dict):
            continue
        loop_order_agents.append(
            {
                "agent_id": item.get("agent_id"),
                "parent_id": item.get("parent_id"),
                "generation": int(item.get("generation", 0) or 0),
                "average_score": float(item.get("average_score", 0.0) or 0.0),
                "is_valid": bool(item.get("is_valid", False)),
                "benchmark_count": int(item.get("benchmark_count", 0) or 0),
                "solved_count": int(item.get("solved_count", 0) or 0),
                "mutation_status": item.get("mutation_status"),
                "has_code_changes": item.get("has_code_changes"),
            }
        )

    return {
        "base_score": _generation_score(scorecard, 0),
        "top_score": float(scorecard.get("top_score", 0.0)),
        "top_agent_id": scorecard.get("top_agent_id"),
        "best_average_delta": float(scorecard.get("best_average_delta", 0.0)),
        "total_agents": int(scorecard.get("total_agents", 0) or 0),
        "valid_agents": int(scorecard.get("valid_agents", 0) or 0),
        "has_improvement": bool(scorecard.get("has_improvement", False)),
        "has_regression": bool(scorecard.get("has_regression", False)),
        "improvement_count": len(improvements),
        "total_benchmark_improvements": int(scorecard.get("total_benchmark_improvements", 0) or 0),
        "total_benchmark_regressions": int(scorecard.get("total_benchmark_regressions", 0) or 0),
        "total_benchmark_unchanged": int(scorecard.get("total_benchmark_unchanged", 0) or 0),
        "generation_best_scores": generations,
        "loop_order_agents": loop_order_agents,
        "mutation_summary": scorecard.get("mutation_summary") or {},
        "improvements": improvements,
    }


def summarize_archive_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract loop-order and zero-score telemetry from archive metadata."""
    if metadata is None:
        return None
    agents = metadata.get("agents")
    if not isinstance(agents, dict):
        raise TelemetryError("Archive metadata must contain an agents object")

    loop_agents = []
    zero_scores_by_benchmark: Counter[str] = Counter()
    mutation_status_counts: Counter[str] = Counter()
    for agent_id, raw in agents.items():
        if not isinstance(raw, dict):
            continue
        mutation = {}
        metadata_raw = raw.get("metadata")
        if isinstance(metadata_raw, dict) and isinstance(metadata_raw.get("mutation"), dict):
            mutation = metadata_raw["mutation"]
        mutation_status = mutation.get("mutation_status")
        has_code_changes = mutation.get("has_code_changes")
        if raw.get("parent_id"):
            mutation_status_counts[str(mutation_status or "unknown")] += 1
        benchmark_scores = raw.get("benchmark_scores") or {}
        if not isinstance(benchmark_scores, dict):
            benchmark_scores = {}
        normalized_scores = {
            str(name): float(score)
            for name, score in benchmark_scores.items()
        }
        if raw.get("is_valid", False):
            for benchmark, score in normalized_scores.items():
                if score <= 0.0:
                    zero_scores_by_benchmark[benchmark] += 1
        loop_agents.append(
            {
                "agent_id": str(raw.get("agent_id") or agent_id),
                "parent_id": raw.get("parent_id"),
                "generation": int(raw.get("generation", 0) or 0),
                "average_score": float(raw.get("average_score", 0.0) or 0.0),
                "is_valid": bool(raw.get("is_valid", False)),
                "created_at": raw.get("created_at"),
                "benchmark_count": len(normalized_scores),
                "solved_count": _solved_count(normalized_scores),
                "mutation_status": mutation_status,
                "has_code_changes": has_code_changes,
            }
        )

    loop_agents.sort(
        key=lambda item: (
            str(item.get("created_at") or ""),
            int(item["generation"]),
            str(item["agent_id"]),
        )
    )
    return {
        "loop_order_agents": loop_agents,
        "mutation_summary": {
            "status_counts": dict(sorted(mutation_status_counts.items())),
        },
        "zero_score_counts_by_benchmark": dict(sorted(zero_scores_by_benchmark.items())),
    }


def summarize_dgm_report(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if report is None:
        return None
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return None
    return {
        "total_generations": int(summary.get("total_generations", 0) or 0),
        "runtime_hours": float(summary.get("runtime_hours", 0.0) or 0.0),
        "total_agents_created": int(summary.get("total_agents_created", 0) or 0),
        "successful_improvements": int(summary.get("successful_improvements", 0) or 0),
        "improvement_rate": float(summary.get("improvement_rate", 0.0) or 0.0),
        "consecutive_noop_mutations": int(
            summary.get("consecutive_noop_mutations", 0) or 0
        ),
        "final_archive_size": int(summary.get("final_archive_size", 0) or 0),
    }


def summarize_live_run_telemetry(
    *,
    controller_log: Path,
    scorecard_path: Path | None = None,
    dgm_report_path: Path | None = None,
    archive_metadata_path: Path | None = None,
    provider: str | None = None,
    model: str | None = None,
    input_price_per_mtok: float = 0.0,
    output_price_per_mtok: float = 0.0,
    model_prices: dict[str, tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Build a structured telemetry report from live-run artifacts."""
    log_summary = parse_controller_log(controller_log)
    scorecard = _optional_json(scorecard_path, label="scorecard")
    dgm_report = _optional_json(dgm_report_path, label="DGM report")
    archive_metadata = _optional_json(archive_metadata_path, label="archive metadata")

    tokens = dict(log_summary["tokens"])
    per_model_tokens = {}
    for model_name, raw_tokens in (tokens.get("by_model") or {}).items():
        prices = (model_prices or {}).get(model_name)
        if prices is None:
            prices = (input_price_per_mtok, output_price_per_mtok)
        per_model_tokens[model_name] = {
            **raw_tokens,
            "input_price_per_mtok": prices[0],
            "output_price_per_mtok": prices[1],
            "estimated_cost_usd": _estimate_cost(
                prompt_tokens=int(raw_tokens["prompt_tokens"]),
                completion_tokens=int(raw_tokens["completion_tokens"]),
                input_price_per_mtok=prices[0],
                output_price_per_mtok=prices[1],
            ),
        }
    estimated_cost = (
        round(
            sum(item["estimated_cost_usd"] for item in per_model_tokens.values()),
            6,
        )
        if per_model_tokens
        else _estimate_cost(
            prompt_tokens=int(tokens["prompt_tokens"]),
            completion_tokens=int(tokens["completion_tokens"]),
            input_price_per_mtok=input_price_per_mtok,
            output_price_per_mtok=output_price_per_mtok,
        )
    )
    tokens.update(
        {
            "input_price_per_mtok": input_price_per_mtok,
            "output_price_per_mtok": output_price_per_mtok,
            "estimated_cost_usd": estimated_cost,
            "by_model": per_model_tokens,
        }
    )

    provider_summary = dict(log_summary["provider"])
    provider_summary.update(
        {
            "name": provider,
            "model": model or provider_summary.get("model_from_log"),
        }
    )

    failure_summary = dict(log_summary["failure_signals"])
    failure_summary.update(
        {
            "provider_timeout_count": provider_summary["timeout_count"],
            "empty_response_count": provider_summary["empty_response_count"],
            "provider_api_error_count": provider_summary["api_error_count"],
        }
    )

    archive_summary = summarize_archive_metadata(archive_metadata)
    if archive_summary:
        failure_summary["zero_score_counts_by_benchmark"] = archive_summary[
            "zero_score_counts_by_benchmark"
        ]

    return {
        "schema_version": 1,
        "run": {
            "controller_log": str(controller_log),
            "scorecard": str(scorecard_path) if scorecard_path else None,
            "dgm_report": str(dgm_report_path) if dgm_report_path else None,
            "archive_metadata": str(archive_metadata_path) if archive_metadata_path else None,
            "completed": log_summary["completed"],
            "start_time": log_summary["start_time"],
            "end_time": log_summary["end_time"],
            "observed_runtime_seconds": log_summary["observed_runtime_seconds"],
            "line_count": log_summary["line_count"],
        },
        "provider": provider_summary,
        "tokens": tokens,
        "failure_reason_summary": failure_summary,
        "score": summarize_scorecard(scorecard),
        "archive": archive_summary,
        "dgm_report": summarize_dgm_report(dgm_report),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controller-log", required=True, help="Path to the DGM controller log.")
    parser.add_argument("--scorecard", help="Optional archive scorecard JSON.")
    parser.add_argument("--dgm-report", help="Optional DGM final report JSON.")
    parser.add_argument("--archive-metadata", help="Optional archive_metadata.json.")
    parser.add_argument("--provider", help="Provider label, for example openrouter.")
    parser.add_argument("--model", help="Model label when the log does not expose it.")
    parser.add_argument("--input-price-per-mtok", type=float, default=0.0)
    parser.add_argument("--output-price-per-mtok", type=float, default=0.0)
    parser.add_argument(
        "--model-price",
        action="append",
        default=[],
        metavar="MODEL=INPUT,OUTPUT",
        help="Per-model USD/M-token pricing for mixed-model runs. Repeat as needed.",
    )
    parser.add_argument("--output", help="Optional path to write telemetry JSON.")
    return parser


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _main(args: argparse.Namespace) -> int:
    try:
        model_prices = {}
        for raw in args.model_price:
            model_name, separator, prices = raw.partition("=")
            input_price, comma, output_price = prices.partition(",")
            if not separator or not comma or not model_name:
                raise TelemetryError(
                    "model-price must use MODEL=INPUT,OUTPUT"
                )
            model_prices[model_name] = (float(input_price), float(output_price))
        telemetry = summarize_live_run_telemetry(
            controller_log=Path(args.controller_log),
            scorecard_path=Path(args.scorecard) if args.scorecard else None,
            dgm_report_path=Path(args.dgm_report) if args.dgm_report else None,
            archive_metadata_path=Path(args.archive_metadata) if args.archive_metadata else None,
            provider=args.provider,
            model=args.model,
            input_price_per_mtok=args.input_price_per_mtok,
            output_price_per_mtok=args.output_price_per_mtok,
            model_prices=model_prices,
        )
        if args.output:
            _write_json(Path(args.output), telemetry)
    except TelemetryError as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 1

    print(
        "live telemetry: "
        f"completed={str(telemetry['run']['completed']).lower()} "
        f"posts={telemetry['provider']['http_post_count']} "
        f"timeouts={telemetry['provider']['timeout_count']} "
        f"empty={telemetry['provider']['empty_response_count']} "
        f"tokens={telemetry['tokens']['total_tokens']} "
        f"cost=${telemetry['tokens']['estimated_cost_usd']:.6f}"
    )
    return 0


def main() -> int:
    return _main(_build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
