#!/usr/bin/env python3
"""Plan, execute, monitor, and aggregate isolated parallel cloud DGM workers."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.estimate_live_run_cost import CostEstimateError, estimate_live_run_cost
from scripts.run_live_eval_on_cloud_vm import (
    CloudVmRunError,
    SecretSpec,
    build_cloud_vm_plan,
    execute_plan,
    write_plan_files,
)


class ParallelCloudRunError(RuntimeError):
    """Raised when a parallel cloud run cannot be planned or executed safely."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ParallelCloudRunError(message)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_secret(value: str) -> SecretSpec:
    if "=" not in value:
        raise ParallelCloudRunError("secret must use ENV_NAME=SECRET_NAME")
    env_name, secret_name = value.split("=", 1)
    _require(bool(env_name and secret_name), "secret names must be non-empty")
    return SecretSpec(env_name=env_name, secret_name=secret_name)


def build_parallel_cloud_plan(
    *,
    base_run_id: str,
    workers: int,
    max_concurrency: int,
    project: str,
    zone: str,
    machine_type: str,
    boot_disk_size_gb: int,
    repo_url: str,
    commit: str,
    config_path: Path,
    config_label: str,
    generations: int,
    secret_specs: list[SecretSpec],
    artifact_root: Path,
    plan_dir: Path,
    gcs_root: str | None,
    model: str,
    input_price_per_mtok: float,
    output_price_per_mtok: float,
    mutation_model: str | None = None,
    mutation_input_price_per_mtok: float | None = None,
    mutation_output_price_per_mtok: float | None = None,
    assumed_input_tokens_per_call: int,
    max_budget_usd: float,
) -> dict[str, Any]:
    """Build independent VM plans and a shared model-cost ceiling."""
    _require(workers > 0, "workers must be positive")
    _require(max_concurrency > 0, "max_concurrency must be positive")
    _require(max_concurrency <= workers, "max_concurrency cannot exceed workers")
    _require(generations > 0, "generations must be positive")
    _require(max_budget_usd > 0, "max_budget_usd must be positive")

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    recommended = int(config.get("live_run", {}).get("recommended_generations", 0))
    _require(
        recommended == generations,
        "config live_run.recommended_generations must equal requested generations",
    )
    estimate = estimate_live_run_cost(
        config_path=config_path,
        input_price_per_mtok=input_price_per_mtok,
        output_price_per_mtok=output_price_per_mtok,
        assumed_input_tokens_per_call=assumed_input_tokens_per_call,
        mutation_input_price_per_mtok=mutation_input_price_per_mtok,
        mutation_output_price_per_mtok=mutation_output_price_per_mtok,
    )
    shared_estimate = estimate["estimated_total_cost_usd"] * workers
    parallel_config = config.get("live_run", {}).get("parallel", {})
    seed_changed_count = int(parallel_config.get("seed_changed_count", 0) or 0)
    seed_noop_count = int(parallel_config.get("seed_noop_count", 0) or 0)
    _require(seed_changed_count >= 0, "seed_changed_count cannot be negative")
    _require(seed_noop_count >= 0, "seed_noop_count cannot be negative")
    _require(
        shared_estimate <= max_budget_usd,
        (
            f"parallel estimate ${shared_estimate:.4f} exceeds shared budget "
            f"${max_budget_usd:.2f}"
        ),
    )

    worker_plans = []
    for index in range(1, workers + 1):
        run_id = f"{base_run_id}-w{index:02d}"
        artifact_dir = artifact_root / run_id
        startup_path = plan_dir / f"{run_id}-startup.sh"
        plan_path = plan_dir / f"{run_id}-plan.json"
        gcs_uri = f"{gcs_root.rstrip('/')}/{run_id}" if gcs_root else None
        cloud_plan = build_cloud_vm_plan(
            run_id=run_id,
            provider="gcloud",
            project=project,
            zone=zone,
            machine_type=machine_type,
            boot_disk_size_gb=boot_disk_size_gb,
            image_family="debian-12",
            image_project="debian-cloud",
            repo_url=repo_url,
            commit=commit,
            config=config_label,
            generations=generations,
            env_names=[],
            secret_specs=secret_specs,
            artifact_dir=artifact_dir,
            startup_script_path=startup_path,
            fm_provider="openrouter",
            model=model,
            input_price_per_mtok=input_price_per_mtok,
            output_price_per_mtok=output_price_per_mtok,
            mutation_model=mutation_model,
            mutation_input_price_per_mtok=mutation_input_price_per_mtok,
            mutation_output_price_per_mtok=mutation_output_price_per_mtok,
            gcs_artifact_uri=gcs_uri,
        )
        worker_plans.append(
            {
                "worker_id": index,
                "run_id": run_id,
                "plan_path": str(plan_path),
                "artifact_dir": str(artifact_dir),
                "gcs_uri": gcs_uri,
                "cloud_plan": cloud_plan,
            }
        )

    return {
        "name": "parallel_cloud_dgm_plan",
        "schema_version": 1,
        "status": "planned",
        "base_run_id": base_run_id,
        "workers": workers,
        "max_concurrency": max_concurrency,
        "generations_per_worker": generations,
        "total_generation_attempt_ceiling": workers * generations,
        "project": project,
        "zone": zone,
        "machine_type": machine_type,
        "source": {
            "repo_url": repo_url,
            "commit": commit,
            "config": config_label,
            "model": model,
            "mutation_model": mutation_model or model,
        },
        "budget": {
            "max_budget_usd": max_budget_usd,
            "assumed_input_tokens_per_call": assumed_input_tokens_per_call,
            "per_worker_estimated_cost_usd": estimate["estimated_total_cost_usd"],
            "parallel_estimated_cost_usd": shared_estimate,
            "per_worker_request_ceiling": estimate["request_ceiling"],
            "pricing": {
                "input_price_per_mtok": input_price_per_mtok,
                "output_price_per_mtok": output_price_per_mtok,
            },
        },
        "seed_mutation_counts": {
            "changed": seed_changed_count,
            "noop": seed_noop_count,
        },
        "worker_plans": worker_plans,
    }


def _public_manifest(plan: dict[str, Any]) -> dict[str, Any]:
    manifest = {key: value for key, value in plan.items() if key != "worker_plans"}
    manifest["worker_plans"] = [
        {key: value for key, value in worker.items() if key != "cloud_plan"}
        | {"vm": worker["cloud_plan"]["vm"]}
        for worker in plan["worker_plans"]
    ]
    return manifest


def write_parallel_cloud_plan(plan: dict[str, Any], output: Path) -> None:
    for worker in plan["worker_plans"]:
        write_plan_files(worker["cloud_plan"], Path(worker["plan_path"]))
    _write_json(output, _public_manifest(plan))


def get_openrouter_total_usage(api_key: str) -> float:
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/credits",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return float(payload["data"]["total_usage"])


def get_openrouter_key_usage(api_key: str) -> float:
    """Return usage attributed to one OpenRouter API key."""
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/key",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return float(payload["data"]["usage"])


def _delete_worker_vms(plan: dict[str, Any]) -> None:
    for worker in plan["worker_plans"]:
        subprocess.run(
            worker["cloud_plan"]["commands"]["teardown"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def aggregate_parallel_artifacts(plan: dict[str, Any]) -> dict[str, Any]:
    """Aggregate worker-local proof without pretending it is one shared agent."""
    workers = []
    total_model_cost = 0.0
    total_tokens = 0
    top_score = 0.0
    admitted_changed = 0
    noops = 0
    for worker in plan["worker_plans"]:
        artifact_dir = Path(worker["artifact_dir"])
        scorecard = _read_json(artifact_dir / "scorecard.json")
        telemetry = _read_json(artifact_dir / "telemetry.json")
        exit_code_text = None
        try:
            exit_code_text = (artifact_dir / "exit_code").read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            pass

        mutation_summary = (scorecard or {}).get("mutation_summary", {})
        worker_changed = int(mutation_summary.get("changed_count", 0) or 0)
        worker_noops = int(mutation_summary.get("noop_count", 0) or 0)
        seeded_changed = int(plan["seed_mutation_counts"]["changed"])
        seeded_noops = int(plan["seed_mutation_counts"]["noop"])
        fresh_changed = max(0, worker_changed - seeded_changed)
        fresh_noops = max(0, worker_noops - seeded_noops)
        admitted_changed += fresh_changed
        noops += fresh_noops

        tokens = (telemetry or {}).get("tokens", {})
        worker_cost = float(tokens.get("estimated_cost_usd", 0.0) or 0.0)
        worker_tokens = int(tokens.get("total_tokens", 0) or 0)
        worker_top = float((scorecard or {}).get("top_score", 0.0) or 0.0)
        total_model_cost += worker_cost
        total_tokens += worker_tokens
        top_score = max(top_score, worker_top)
        workers.append(
            {
                "run_id": worker["run_id"],
                "exit_code": int(exit_code_text) if exit_code_text else None,
                "has_scorecard": scorecard is not None,
                "top_score": worker_top,
                "fresh_changed_count": fresh_changed,
                "fresh_noop_count": fresh_noops,
                "model_cost_usd": worker_cost,
                "total_tokens": worker_tokens,
                "artifact_dir": str(artifact_dir),
                "gcs_uri": worker.get("gcs_uri"),
            }
        )

    return {
        "name": "parallel_cloud_dgm_aggregate",
        "schema_version": 1,
        "workers_planned": plan["workers"],
        "workers_with_scorecards": sum(1 for worker in workers if worker["has_scorecard"]),
        "top_score": top_score,
        "fresh_changed_count": admitted_changed,
        "fresh_noop_count": noops,
        "total_model_cost_usd_from_telemetry": total_model_cost,
        "total_tokens": total_tokens,
        "note": (
            "Workers are independent seeded DGM runs. top_score is the best worker "
            "score, not a merged-agent score."
        ),
        "workers": workers,
    }


def recover_missing_gcs_artifacts(
    plan: dict[str, Any],
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[str]:
    """Recover durable GCS artifacts when VM teardown beats local syncing."""
    recovered: list[str] = []
    for worker in plan.get("worker_plans", []):
        artifact_dir = Path(worker["artifact_dir"])
        if (artifact_dir / "scorecard.json").exists():
            continue
        gcs_uri = worker.get("gcs_uri")
        if not gcs_uri:
            continue
        artifact_dir.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["CLOUDSDK_STORAGE_PROCESS_COUNT"] = "1"
        env["CLOUDSDK_STORAGE_THREAD_COUNT"] = "1"
        result = runner(
            [
                "gcloud",
                "storage",
                "cp",
                "--recursive",
                gcs_uri,
                str(artifact_dir.parent),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode == 0 and (artifact_dir / "scorecard.json").exists():
            recovered.append(worker["run_id"])
        else:
            print(
                f"[artifact] recovery failed for {worker['run_id']}: "
                f"{result.stderr.strip()}",
                file=sys.stderr,
            )
    return recovered


async def execute_parallel_cloud_plan(
    plan: dict[str, Any],
    *,
    budget_api_key: str,
    poll_seconds: float,
    executor: Callable[[dict[str, Any]], None] = execute_plan,
    usage_reader: Callable[[str], float] = get_openrouter_total_usage,
) -> dict[str, Any]:
    """Execute worker VMs concurrently and stop all VMs at the shared budget."""
    start_usage = await asyncio.to_thread(usage_reader, budget_api_key)
    semaphore = asyncio.Semaphore(plan["max_concurrency"])
    done = asyncio.Event()
    budget_exceeded = False

    async def run_worker(worker: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            try:
                await asyncio.to_thread(executor, worker["cloud_plan"])
                return {"run_id": worker["run_id"], "status": "complete"}
            except Exception as exc:  # keep other independent workers alive
                return {
                    "run_id": worker["run_id"],
                    "status": "failed",
                    "error": str(exc),
                }

    async def budget_watchdog() -> None:
        nonlocal budget_exceeded
        while not done.is_set():
            try:
                await asyncio.wait_for(done.wait(), timeout=poll_seconds)
                return
            except asyncio.TimeoutError:
                pass
            try:
                usage = await asyncio.to_thread(usage_reader, budget_api_key)
            except Exception as exc:
                print(f"[budget] usage check failed: {exc}", file=sys.stderr)
                continue
            delta = max(0.0, usage - start_usage)
            print(
                f"[budget] OpenRouter usage delta=${delta:.4f}/"
                f"${plan['budget']['max_budget_usd']:.2f}",
                file=sys.stderr,
            )
            if delta >= plan["budget"]["max_budget_usd"]:
                budget_exceeded = True
                await asyncio.to_thread(_delete_worker_vms, plan)
                return

    tasks = [asyncio.create_task(run_worker(worker)) for worker in plan["worker_plans"]]
    watchdog = asyncio.create_task(budget_watchdog())
    try:
        executions = await asyncio.gather(*tasks)
    finally:
        done.set()
        await watchdog

    final_usage = await asyncio.to_thread(usage_reader, budget_api_key)
    recovered_workers = await asyncio.to_thread(recover_missing_gcs_artifacts, plan)
    aggregate = aggregate_parallel_artifacts(plan)
    aggregate.update(
        {
            "status": "budget_stopped" if budget_exceeded else "complete",
            "executions": executions,
            "openrouter_usage_start_usd": start_usage,
            "openrouter_usage_end_usd": final_usage,
            "openrouter_usage_delta_usd": max(0.0, final_usage - start_usage),
            "budget_exceeded": budget_exceeded,
            "gcs_recovered_workers": recovered_workers,
        }
    )
    return aggregate


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-run-id", required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-concurrency", type=int, default=8)
    parser.add_argument("--project", required=True)
    parser.add_argument("--zone", default="us-central1-a")
    parser.add_argument("--machine-type", default="n2-standard-8")
    parser.add_argument("--boot-disk-size-gb", type=int, default=100)
    parser.add_argument("--repo-url", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--generations", type=int, required=True)
    parser.add_argument("--secret", action="append", default=[])
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--gcs-root")
    parser.add_argument("--model", required=True)
    parser.add_argument("--input-price-per-mtok", type=float, required=True)
    parser.add_argument("--output-price-per-mtok", type=float, required=True)
    parser.add_argument("--mutation-model")
    parser.add_argument("--mutation-input-price-per-mtok", type=float)
    parser.add_argument("--mutation-output-price-per-mtok", type=float)
    parser.add_argument("--assumed-input-tokens-per-call", type=int, default=12_000)
    parser.add_argument("--max-budget", type=float, default=100.0)
    parser.add_argument("--budget-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--budget-poll-seconds", type=float, default=60.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--aggregate-output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    try:
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = PROJECT_ROOT / config_path
        plan = build_parallel_cloud_plan(
            base_run_id=args.base_run_id,
            workers=args.workers,
            max_concurrency=args.max_concurrency,
            project=args.project,
            zone=args.zone,
            machine_type=args.machine_type,
            boot_disk_size_gb=args.boot_disk_size_gb,
            repo_url=args.repo_url,
            commit=args.commit,
            config_path=config_path,
            config_label=args.config,
            generations=args.generations,
            secret_specs=[_parse_secret(value) for value in args.secret],
            artifact_root=args.artifact_root,
            plan_dir=args.plan_dir,
            gcs_root=args.gcs_root,
            model=args.model,
            input_price_per_mtok=args.input_price_per_mtok,
            output_price_per_mtok=args.output_price_per_mtok,
            mutation_model=args.mutation_model,
            mutation_input_price_per_mtok=args.mutation_input_price_per_mtok,
            mutation_output_price_per_mtok=args.mutation_output_price_per_mtok,
            assumed_input_tokens_per_call=args.assumed_input_tokens_per_call,
            max_budget_usd=args.max_budget,
        )
        write_parallel_cloud_plan(plan, args.output)
        print(
            f"[ok] parallel plan workers={plan['workers']} attempts<="
            f"{plan['total_generation_attempt_ceiling']} estimate=$"
            f"{plan['budget']['parallel_estimated_cost_usd']:.4f}"
        )
        if not args.execute:
            return 0
        api_key = os.environ.get(args.budget_env, "")
        _require(bool(api_key), f"budget environment variable is missing: {args.budget_env}")
        aggregate = await execute_parallel_cloud_plan(
            plan,
            budget_api_key=api_key,
            poll_seconds=args.budget_poll_seconds,
        )
        _write_json(args.aggregate_output, aggregate)
        print(
            f"[ok] parallel run status={aggregate['status']} "
            f"workers={aggregate['workers_with_scorecards']}/{plan['workers']} "
            f"top_score={aggregate['top_score']:.3f} "
            f"usage_delta=${aggregate['openrouter_usage_delta_usd']:.4f}"
        )
        return 0 if aggregate["status"] == "complete" else 2
    except (ParallelCloudRunError, CostEstimateError, CloudVmRunError, OSError) as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 1


def main() -> int:
    return asyncio.run(_main_async(_build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
