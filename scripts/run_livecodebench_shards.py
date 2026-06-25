#!/usr/bin/env python3
"""Plan, run, and aggregate sharded LiveCodeBench DGM runs."""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.estimate_live_run_cost import estimate_live_run_cost
from scripts.run_dgm_in_sandbox import SandboxRunError, run_sandboxed_dgm
from scripts.summarize_archive_scores import summarize_archive_scores


class LiveCodeBenchShardError(RuntimeError):
    """Raised when a sharded LiveCodeBench run cannot be planned or completed."""


@dataclass(frozen=True)
class ShardSpec:
    """One planned LiveCodeBench shard."""

    shard_id: str
    index: int
    benchmark_names: list[str]
    config_path: Path
    archive_metadata_path: Path
    scorecard_path: Path
    audit_path: Path
    log_path: Path


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveCodeBenchShardError(message)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise LiveCodeBenchShardError(f"Missing YAML file: {path}") from exc
    except yaml.YAMLError as exc:
        raise LiveCodeBenchShardError(f"Invalid YAML file: {path}: {exc}") from exc
    _require(isinstance(data, dict), f"YAML file must contain a mapping: {path}")
    return data


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LiveCodeBenchShardError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LiveCodeBenchShardError(f"Invalid JSON file: {path}: {exc}") from exc
    _require(isinstance(data, dict), f"JSON file must contain a mapping: {path}")
    return data


def _project_path(path_text: str | Path, project_root: Path) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = project_root / path
    try:
        relative = path.resolve().relative_to(project_root.resolve())
    except ValueError as exc:
        raise LiveCodeBenchShardError(f"{path_text} must stay inside the project root") from exc
    return project_root.resolve() / relative


def _project_relative(path: Path, project_root: Path) -> str:
    return str(path.resolve().relative_to(project_root.resolve()))


def _manifest_by_benchmark(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    problems = manifest.get("problems", [])
    _require(isinstance(problems, list), "Segment manifest must contain problems list")
    result: dict[str, dict[str, Any]] = {}
    for problem in problems:
        _require(isinstance(problem, dict), "Segment manifest problem must be a mapping")
        benchmark = str(problem.get("benchmark", ""))
        _require(benchmark, "Segment manifest problem missing benchmark name")
        result[benchmark] = problem
    return result


def _build_difficulty_balanced_shards(
    *,
    enabled: list[str],
    manifest: dict[str, Any],
    shard_count: int,
    shard_size: int,
    difficulty_order: list[str],
) -> list[list[str]]:
    _require(shard_count > 0, "shard_count must be positive")
    _require(shard_size > 0, "shard_size must be positive")
    _require(difficulty_order, "difficulty_order must be non-empty")
    _require(
        shard_size % len(difficulty_order) == 0,
        "shard_size must divide evenly across difficulty_order",
    )
    _require(
        len(enabled) == shard_count * shard_size,
        "enabled benchmark count must equal shard_count * shard_size",
    )

    problem_by_name = _manifest_by_benchmark(manifest)
    by_difficulty = {difficulty: [] for difficulty in difficulty_order}
    for benchmark in enabled:
        problem = problem_by_name.get(benchmark)
        _require(problem is not None, f"Generated manifest missing benchmark {benchmark}")
        difficulty = str(problem.get("difficulty", ""))
        if difficulty in by_difficulty:
            by_difficulty[difficulty].append(benchmark)

    per_difficulty = shard_size // len(difficulty_order)
    shards: list[list[str]] = []
    for difficulty, benchmarks in by_difficulty.items():
        expected = shard_count * per_difficulty
        _require(
            len(benchmarks) == expected,
            f"difficulty {difficulty!r} has {len(benchmarks)} benchmarks; expected {expected}",
        )

    for shard_index in range(shard_count):
        shard: list[str] = []
        for difficulty in difficulty_order:
            start = shard_index * per_difficulty
            end = start + per_difficulty
            shard.extend(by_difficulty[difficulty][start:end])
        shards.append(shard)

    flattened = [benchmark for shard in shards for benchmark in shard]
    _require(len(flattened) == len(set(flattened)), "Shard plan contains duplicate benchmarks")
    _require(set(flattened) == set(enabled), "Shard plan does not cover all enabled benchmarks")
    return shards


def _write_shard_config(
    *,
    base_config: dict[str, Any],
    base_config_path: Path,
    project_root: Path,
    run_dir: Path,
    audit_dir: Path,
    shard_id: str,
    index: int,
    shard_count: int,
    benchmark_names: list[str],
) -> ShardSpec:
    shard_root = run_dir / "shards" / shard_id
    config_path = run_dir / "configs" / f"{shard_id}.yaml"
    archive_path = shard_root / "archive"
    results_path = shard_root / "results"
    workspace_path = shard_root / "workspace"
    scorecard_path = shard_root / "scorecard.json"
    audit_path = audit_dir / f"{shard_id}-audit.json"
    log_path = shard_root / "dgm_run.log"

    config = copy.deepcopy(base_config)
    config["archive"]["path"] = _project_relative(archive_path, project_root)
    config["evaluation"]["results_dir"] = _project_relative(results_path, project_root)
    config["agents"]["workspace_dir"] = _project_relative(workspace_path, project_root)
    config["benchmarks"]["enabled"] = benchmark_names
    config.setdefault("live_run", {})["shard"] = {
        "id": shard_id,
        "index": index,
        "count": shard_count,
        "parent_config": _project_relative(base_config_path, project_root),
        "benchmark_count": len(benchmark_names),
        "benchmarks": benchmark_names,
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return ShardSpec(
        shard_id=shard_id,
        index=index,
        benchmark_names=benchmark_names,
        config_path=config_path,
        archive_metadata_path=archive_path / "archive_metadata.json",
        scorecard_path=scorecard_path,
        audit_path=audit_path,
        log_path=log_path,
    )


def plan_livecodebench_shards(
    config_path: Path,
    *,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Write shard configs and return a non-secret shard plan."""
    project_root = project_root.resolve()
    config_path = config_path if config_path.is_absolute() else project_root / config_path
    config_path = config_path.resolve()
    base_config = _load_yaml(config_path)

    live_run = base_config.get("live_run", {})
    sharding = live_run.get("sharding", {})
    _require(isinstance(live_run, dict), "live_run must be a mapping")
    _require(isinstance(sharding, dict), "live_run.sharding must be a mapping")
    _require(live_run.get("purpose") == "livecodebench_openrouter_segment", "Not a LiveCodeBench OpenRouter plan")

    enabled = [str(item) for item in base_config.get("benchmarks", {}).get("enabled", [])]
    _require(enabled, "Config must enable benchmarks")
    segment = live_run.get("segment", {})
    _require(isinstance(segment, dict), "live_run.segment must be a mapping")
    manifest_path = _project_path(segment.get("manifest_path", ""), project_root)
    manifest = _load_json(manifest_path)

    run_dir = _project_path(sharding.get("run_dir", ""), project_root)
    audit_dir = _project_path(sharding.get("audit_dir", ""), project_root)
    shard_count = int(sharding.get("shard_count", 0))
    shard_size = int(sharding.get("shard_size", 0))
    difficulty_order = [str(item) for item in sharding.get("difficulty_order", [])]
    strategy = str(sharding.get("strategy", ""))
    _require(strategy == "difficulty_balanced_contiguous", "Unsupported sharding strategy")

    shards = _build_difficulty_balanced_shards(
        enabled=enabled,
        manifest=manifest,
        shard_count=shard_count,
        shard_size=shard_size,
        difficulty_order=difficulty_order,
    )

    specs = [
        _write_shard_config(
            base_config=base_config,
            base_config_path=config_path,
            project_root=project_root,
            run_dir=run_dir,
            audit_dir=audit_dir,
            shard_id=f"shard-{index + 1:02d}",
            index=index + 1,
            shard_count=shard_count,
            benchmark_names=benchmark_names,
        )
        for index, benchmark_names in enumerate(shards)
    ]

    cost_gate = live_run.get("cost_gate", {})
    _require(isinstance(cost_gate, dict), "live_run.cost_gate must be a mapping")
    total_estimate = estimate_live_run_cost(
        config_path=config_path,
        input_price_per_mtok=float(cost_gate["input_price_per_mtok"]),
        output_price_per_mtok=float(cost_gate["output_price_per_mtok"]),
        assumed_input_tokens_per_call=int(cost_gate["assumed_input_tokens_per_call"]),
        max_budget=float(cost_gate["max_estimated_cost_usd"]),
    )
    _require(total_estimate["within_budget"], "Total scale run estimate exceeds max budget")

    shard_summaries = []
    for spec in specs:
        shard_estimate = estimate_live_run_cost(
            config_path=spec.config_path,
            input_price_per_mtok=float(cost_gate["input_price_per_mtok"]),
            output_price_per_mtok=float(cost_gate["output_price_per_mtok"]),
            assumed_input_tokens_per_call=int(cost_gate["assumed_input_tokens_per_call"]),
            max_budget=float(cost_gate["max_estimated_cost_usd"]),
        )
        shard_summaries.append(
            {
                "id": spec.shard_id,
                "index": spec.index,
                "benchmark_count": len(spec.benchmark_names),
                "config": _project_relative(spec.config_path, project_root),
                "archive_metadata": _project_relative(spec.archive_metadata_path, project_root),
                "scorecard": _project_relative(spec.scorecard_path, project_root),
                "audit": _project_relative(spec.audit_path, project_root),
                "log": _project_relative(spec.log_path, project_root),
                "benchmarks": spec.benchmark_names,
                "request_ceiling": shard_estimate["request_ceiling"],
                "estimated_total_cost_usd": shard_estimate["estimated_total_cost_usd"],
                "completed": spec.scorecard_path.is_file(),
            }
        )

    aggregate_scorecard = _project_path(sharding.get("aggregate_scorecard", run_dir / "aggregate_scorecard.json"), project_root)
    return {
        "name": "livecodebench_shard_plan",
        "status": "ok",
        "config": _project_relative(config_path, project_root),
        "segment_manifest": _project_relative(manifest_path, project_root),
        "run_dir": _project_relative(run_dir, project_root),
        "audit_dir": _project_relative(audit_dir, project_root),
        "aggregate_scorecard": _project_relative(aggregate_scorecard, project_root),
        "strategy": strategy,
        "shard_count": shard_count,
        "shard_size": shard_size,
        "benchmark_count": len(enabled),
        "request_ceiling": total_estimate["request_ceiling"],
        "estimated_total_cost_usd": total_estimate["estimated_total_cost_usd"],
        "max_budget_usd": float(cost_gate["max_estimated_cost_usd"]),
        "shards": shard_summaries,
    }


def _scorecard_benchmark_count(scorecard: dict[str, Any]) -> int:
    generations = scorecard.get("generation_best_scores") or []
    if not generations:
        return 0
    first = generations[0]
    scores = first.get("benchmark_scores") if isinstance(first, dict) else {}
    return len(scores) if isinstance(scores, dict) else 0


def _generation_score(scorecard: dict[str, Any], generation: int) -> float | None:
    for item in scorecard.get("generation_best_scores") or []:
        if isinstance(item, dict) and int(item.get("generation", -1)) == generation:
            return float(item.get("average_score", 0.0))
    return None


def aggregate_scorecards(
    plan: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
    require_all: bool = True,
) -> dict[str, Any]:
    """Aggregate per-shard scorecards into one scale-run summary."""
    project_root = project_root.resolve()
    shard_reports = []
    total_benchmarks = 0
    weighted_base = 0.0
    weighted_best = 0.0
    completed = 0

    for shard in plan["shards"]:
        scorecard_path = _project_path(shard["scorecard"], project_root)
        if not scorecard_path.is_file():
            if require_all:
                raise LiveCodeBenchShardError(f"Missing shard scorecard: {shard['scorecard']}")
            continue
        scorecard = _load_json(scorecard_path)
        benchmark_count = _scorecard_benchmark_count(scorecard)
        base_score = _generation_score(scorecard, 0)
        top_score = float(scorecard.get("top_score", 0.0))
        if base_score is None:
            raise LiveCodeBenchShardError(f"Shard scorecard missing generation 0: {shard['scorecard']}")

        completed += 1
        total_benchmarks += benchmark_count
        weighted_base += base_score * benchmark_count
        weighted_best += top_score * benchmark_count
        shard_reports.append(
            {
                "id": shard["id"],
                "benchmark_count": benchmark_count,
                "base_score": base_score,
                "top_score": top_score,
                "best_average_delta": float(scorecard.get("best_average_delta", 0.0)),
                "has_improvement": bool(scorecard.get("has_improvement", False)),
                "has_regression": bool(scorecard.get("has_regression", False)),
                "top_agent_id": scorecard.get("top_agent_id"),
                "scorecard": shard["scorecard"],
            }
        )

    _require(completed > 0, "No completed shard scorecards found")
    aggregate = {
        "name": "livecodebench_scale72_aggregate_scorecard",
        "status": "complete" if completed == plan["shard_count"] else "partial",
        "plan_config": plan["config"],
        "shard_count": plan["shard_count"],
        "completed_shards": completed,
        "total_benchmark_count": total_benchmarks,
        "weighted_base_score": weighted_base / total_benchmarks,
        "weighted_best_shard_score": weighted_best / total_benchmarks,
        "weighted_best_delta": (weighted_best - weighted_base) / total_benchmarks,
        "shards_with_improvement": sum(1 for shard in shard_reports if shard["has_improvement"]),
        "shards_with_regression": sum(1 for shard in shard_reports if shard["has_regression"]),
        "shards": shard_reports,
        "caveat": (
            "This aggregates independent shard-local DGM runs; weighted_best_shard_score "
            "is a shard portfolio score, not one agent evaluated across all shards."
        ),
    }
    return aggregate


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


async def execute_shards(
    plan: dict[str, Any],
    *,
    project_root: Path,
    generations: int,
    env_names: list[str],
    allow_network: bool,
    timeout: int | None,
    resume: bool,
    max_shards: int | None,
) -> dict[str, Any]:
    """Execute planned shards sequentially and return the aggregate scorecard."""
    executed = 0
    for shard in plan["shards"]:
        if max_shards is not None and executed >= max_shards:
            break
        config_path = _project_path(shard["config"], project_root)
        scorecard_path = _project_path(shard["scorecard"], project_root)
        archive_metadata_path = _project_path(shard["archive_metadata"], project_root)
        audit_path = _project_path(shard["audit"], project_root)
        log_path = _project_path(shard["log"], project_root)
        if resume and scorecard_path.is_file():
            print(f"[skip] {shard['id']} already has scorecard {shard['scorecard']}")
            continue

        print(f"[run] {shard['id']} benchmarks={shard['benchmark_count']} config={shard['config']}")
        try:
            result = await run_sandboxed_dgm(
                config_path=config_path,
                generations=generations,
                project_root=project_root,
                env_names=env_names,
                allow_network=allow_network,
                timeout=timeout,
                sync_back=True,
            )
        except SandboxRunError as exc:
            raise LiveCodeBenchShardError(str(exc)) from exc

        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            (result.output or "") + ("\n[stderr]\n" + result.error if result.error else ""),
            encoding="utf-8",
        )
        if not result.success:
            raise LiveCodeBenchShardError(
                f"{shard['id']} failed with exit code {result.exit_code}; log={shard['log']}"
            )
        scorecard = summarize_archive_scores(archive_metadata_path)
        _write_json(scorecard_path, scorecard)
        _write_json(audit_path, {
            "shard": shard["id"],
            "config": shard["config"],
            "env_names": env_names,
            "env_values": "hidden",
            "allow_network": allow_network,
            "timeout": timeout,
            "scorecard": shard["scorecard"],
        })
        print(
            f"[ok] {shard['id']} top_score={scorecard['top_score']:.3f} "
            f"best_delta={scorecard['best_average_delta']:+.3f} "
            f"improvements={len(scorecard['improvements'])}"
        )
        executed += 1

    aggregate = aggregate_scorecards(
        plan,
        project_root=project_root,
        require_all=max_shards is None,
    )
    aggregate_path = _project_path(plan["aggregate_scorecard"], project_root)
    _write_json(aggregate_path, aggregate)
    print(
        "[ok] aggregate "
        f"status={aggregate['status']} "
        f"completed={aggregate['completed_shards']}/{aggregate['shard_count']} "
        f"weighted_base={aggregate['weighted_base_score']:.3f} "
        f"weighted_best={aggregate['weighted_best_shard_score']:.3f} "
        f"delta={aggregate['weighted_best_delta']:+.3f}"
    )
    return aggregate


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "config" / "livecodebench_openrouter_scale72.yaml"))
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument("--generations", type=int, help="Generations per shard. Defaults to live_run.recommended_generations.")
    parser.add_argument("--timeout", type=int, help="Container timeout per shard.")
    parser.add_argument("--env", action="append", default=[], help="Environment variable name to pass to live shard containers.")
    parser.add_argument("--allow-network", action="store_true", help="Allow provider network calls inside shard containers.")
    parser.add_argument("--resume", action="store_true", help="Skip shards that already have scorecards.")
    parser.add_argument("--max-shards", type=int, help="Execute at most this many incomplete shards.")
    parser.add_argument("--execute", action="store_true", help="Run shard containers after planning.")
    parser.add_argument("--plan-only", action="store_true", help="Only write shard configs and print the plan.")
    parser.add_argument("--aggregate-only", action="store_true", help="Only aggregate existing shard scorecards.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    try:
        project_root = Path(args.project_root).resolve()
        plan = plan_livecodebench_shards(Path(args.config), project_root=project_root)
        if args.aggregate_only:
            aggregate = aggregate_scorecards(plan, project_root=project_root, require_all=False)
            _write_json(_project_path(plan["aggregate_scorecard"], project_root), aggregate)
            output = aggregate
        elif args.execute:
            live_config = _load_yaml(_project_path(args.config, project_root))
            generations = args.generations or int(live_config["live_run"]["recommended_generations"])
            output = await execute_shards(
                plan,
                project_root=project_root,
                generations=generations,
                env_names=args.env,
                allow_network=args.allow_network,
                timeout=args.timeout,
                resume=args.resume,
                max_shards=args.max_shards,
            )
        else:
            output = plan
    except LiveCodeBenchShardError as exc:
        if args.json:
            print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        else:
            print(f"[fail] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(output, indent=2, sort_keys=True))
    elif output.get("name") == "livecodebench_shard_plan":
        print(
            "[ok] livecodebench_shard_plan "
            f"shards={output['shard_count']} "
            f"benchmarks={output['benchmark_count']} "
            f"requests<={output['request_ceiling']} "
            f"total=${output['estimated_total_cost_usd']:.4f}"
        )
    return 0


def main() -> int:
    return asyncio.run(_main_async(_build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
