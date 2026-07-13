#!/usr/bin/env python3
"""Plan and execute heterogeneous Luna-mutator runner fleets on ephemeral VMs."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_live_eval_on_cloud_vm import (
    CloudVmRunError,
    SecretSpec,
    build_cloud_vm_plan,
    execute_plan,
    write_plan_files,
)
from scripts.run_parallel_cloud_dgm import (
    get_openrouter_total_usage,
    recover_missing_gcs_artifacts,
)


DEFAULT_MATRIX = PROJECT_ROOT / "config/livecodebench_luna_runner_matrix.yaml"
DEFAULT_GENERATED_MANIFEST = (
    PROJECT_ROOT / "config/generated/luna_runner_matrix/manifest.json"
)


class RunnerMatrixError(RuntimeError):
    """Raised when a heterogeneous runner matrix is unsafe or incomplete."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RunnerMatrixError(message)


def _parse_secret(value: str) -> SecretSpec:
    if "=" not in value:
        raise RunnerMatrixError("secret must use ENV_NAME=SECRET_NAME")
    env_name, secret_name = value.split("=", 1)
    _require(bool(env_name and secret_name), "secret names must be non-empty")
    return SecretSpec(env_name=env_name, secret_name=secret_name)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_runner_matrix_plan(
    *,
    phase: str,
    base_run_id: str,
    matrix_path: Path,
    generated_manifest_path: Path,
    project: str,
    zone: str,
    machine_type: str,
    boot_disk_size_gb: int,
    repo_url: str,
    commit: str,
    secret_specs: list[SecretSpec],
    artifact_root: Path,
    plan_dir: Path,
    gcs_root: str | None,
    max_budget_usd: float | None = None,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Build one isolated cloud plan per calibration or evolution worker."""
    _require(phase in {"calibration", "evolution"}, "phase must be calibration or evolution")
    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8")) or {}
    manifest = _read_json(generated_manifest_path)
    _require(manifest is not None, "generated config manifest is missing")
    _require(len(matrix.get("models") or []) == 10, "matrix must contain ten models")
    configs = {
        (item["slug"], item["phase"]): item
        for item in manifest.get("configs", [])
        if isinstance(item, dict)
    }
    phase_config = matrix[phase]
    if phase == "calibration":
        workers_per_model = 1
        generations = int(phase_config["generations"])
    else:
        workers_per_model = int(phase_config["workers_per_model"])
        generations = int(phase_config["generations_per_worker"])
    max_concurrency = int(phase_config["max_concurrency"])
    budget = float(
        max_budget_usd
        if max_budget_usd is not None
        else phase_config["max_openrouter_budget_usd"]
    )
    _require(workers_per_model > 0, "workers per model must be positive")
    _require(generations >= 0, "generations cannot be negative")
    _require(max_concurrency > 0, "max concurrency must be positive")
    _require(budget > 0, "matrix budget must be positive")

    mutation = matrix["mutation"]
    if phase == "evolution":
        _require(
            max_concurrency >= len(matrix["models"]),
            "evolution concurrency must start one worker per model",
        )

    worker_plans = []
    for worker_index in range(1, workers_per_model + 1):
        for model in matrix["models"]:
            slug = model["slug"]
            generated = configs.get((slug, phase))
            _require(generated is not None, f"missing generated {phase} config for {slug}")
            config_label = generated["config"]
            config_path = project_root / config_label
            _require(config_path.exists(), f"generated config does not exist: {config_label}")
            if (
                phase == "evolution"
                and phase_config.get("seed_mode", "calibrated_archive")
                != "fresh_native"
            ):
                proof = (
                    project_root
                    / matrix["seed"]["calibration_bundle"]
                    / slug
                    / "archive.tar.gz"
                )
                _require(proof.exists(), f"calibrated archive is missing: {proof}")
            suffix = slug if workers_per_model == 1 else f"{slug}-w{worker_index:02d}"
            run_id = f"{base_run_id}-{suffix}"
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
                model=model["model"],
                input_price_per_mtok=float(model["input_price_per_mtok"]),
                output_price_per_mtok=float(model["output_price_per_mtok"]),
                mutation_model=mutation["model"],
                mutation_input_price_per_mtok=float(mutation["input_price_per_mtok"]),
                mutation_output_price_per_mtok=float(mutation["output_price_per_mtok"]),
                gcs_artifact_uri=gcs_uri,
            )
            worker_plans.append(
                {
                    "model_slug": slug,
                    "model": model["model"],
                    "worker_id": worker_index,
                    "run_id": run_id,
                    "config": config_label,
                    "plan_path": str(plan_path),
                    "artifact_dir": str(artifact_dir),
                    "gcs_uri": gcs_uri,
                    "cloud_plan": cloud_plan,
                }
            )
    _require(max_concurrency <= len(worker_plans), "max concurrency exceeds worker count")
    return {
        "schema_version": 1,
        "name": "cloud_luna_runner_matrix_plan",
        "status": "planned",
        "phase": phase,
        "base_run_id": base_run_id,
        "matrix": str(matrix_path),
        "generated_manifest": str(generated_manifest_path),
        "model_count": len(matrix["models"]),
        "workers_per_model": workers_per_model,
        "workers": len(worker_plans),
        "generations_per_worker": generations,
        "total_generation_attempt_ceiling": len(worker_plans) * generations,
        "scheduling": "worker_round_robin",
        "max_concurrency": max_concurrency,
        "max_budget_usd": budget,
        "project": project,
        "zone": zone,
        "machine_type": machine_type,
        "source": {
            "repo_url": repo_url,
            "commit": commit,
            "mutation_model": mutation["model"],
            "seed_mode": phase_config.get("seed_mode", "calibrated_archive"),
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


def write_runner_matrix_plan(plan: dict[str, Any], output: Path) -> None:
    for worker in plan["worker_plans"]:
        write_plan_files(worker["cloud_plan"], Path(worker["plan_path"]))
    _write_json(output, _public_manifest(plan))


def _delete_vms(plan: dict[str, Any]) -> None:
    groups: dict[tuple[str, str], list[str]] = {}
    for worker in plan["worker_plans"]:
        vm = worker["cloud_plan"]["vm"]
        groups.setdefault((vm["project"], vm["zone"]), []).append(vm["name"])
    for (project, zone), vm_names in groups.items():
        subprocess.run(
            [
                "gcloud",
                "compute",
                "instances",
                "delete",
                *vm_names,
                "--project",
                project,
                "--zone",
                zone,
                "--quiet",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def aggregate_runner_matrix(plan: dict[str, Any]) -> dict[str, Any]:
    model_rows: dict[str, dict[str, Any]] = {}
    total_cost = 0.0
    total_tokens = 0
    for worker in plan["worker_plans"]:
        artifact_dir = Path(worker["artifact_dir"])
        scorecard = _read_json(artifact_dir / "scorecard.json")
        telemetry = _read_json(artifact_dir / "telemetry.json")
        exit_code = None
        try:
            exit_code = int((artifact_dir / "exit_code").read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError):
            pass
        tokens = (telemetry or {}).get("tokens", {})
        cost = float(tokens.get("estimated_cost_usd", 0.0) or 0.0)
        token_count = int(tokens.get("total_tokens", 0) or 0)
        top_score = float((scorecard or {}).get("top_score", 0.0) or 0.0)
        total_cost += cost
        total_tokens += token_count
        row = model_rows.setdefault(
            worker["model_slug"],
            {
                "model_slug": worker["model_slug"],
                "model": worker["model"],
                "top_score": 0.0,
                "workers_with_scorecards": 0,
                "workers": [],
            },
        )
        row["top_score"] = max(row["top_score"], top_score)
        row["workers_with_scorecards"] += int(scorecard is not None)
        row["workers"].append(
            {
                "run_id": worker["run_id"],
                "exit_code": exit_code,
                "has_scorecard": scorecard is not None,
                "top_score": top_score,
                "model_cost_usd": cost,
                "total_tokens": token_count,
                "artifact_dir": str(artifact_dir),
                "gcs_uri": worker.get("gcs_uri"),
            }
        )
    return {
        "schema_version": 1,
        "name": "cloud_luna_runner_matrix_aggregate",
        "phase": plan["phase"],
        "models": list(model_rows.values()),
        "models_with_scorecards": sum(
            1 for row in model_rows.values() if row["workers_with_scorecards"] > 0
        ),
        "workers_with_scorecards": sum(
            row["workers_with_scorecards"] for row in model_rows.values()
        ),
        "total_model_cost_usd_from_telemetry": total_cost,
        "total_tokens": total_tokens,
    }


async def execute_runner_matrix(
    plan: dict[str, Any],
    *,
    budget_api_key: str,
    poll_seconds: float,
    executor: Callable[[dict[str, Any]], None] = execute_plan,
    usage_reader: Callable[[str], float] = get_openrouter_total_usage,
    progress_output: Path | None = None,
) -> dict[str, Any]:
    start_usage = await asyncio.to_thread(usage_reader, budget_api_key)
    if progress_output is not None:
        _write_json(
            progress_output,
            {
                "schema_version": 1,
                "name": "cloud_luna_runner_matrix_live_state",
                "status": "running",
                "phase": plan["phase"],
                "openrouter_usage_start_usd": start_usage,
                "openrouter_usage_current_usd": start_usage,
                "openrouter_usage_delta_usd": 0.0,
                "max_budget_usd": plan["max_budget_usd"],
            },
        )
    semaphore = asyncio.Semaphore(plan["max_concurrency"])
    done = asyncio.Event()
    stop_requested = asyncio.Event()
    budget_exceeded = False

    async def run_worker(worker: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            if stop_requested.is_set():
                return {"run_id": worker["run_id"], "status": "budget_skipped"}
            try:
                await asyncio.to_thread(executor, worker["cloud_plan"])
                return {"run_id": worker["run_id"], "status": "complete"}
            except Exception as exc:
                return {"run_id": worker["run_id"], "status": "failed", "error": str(exc)}

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
            if progress_output is not None:
                _write_json(
                    progress_output,
                    {
                        "schema_version": 1,
                        "name": "cloud_luna_runner_matrix_live_state",
                        "status": "running",
                        "phase": plan["phase"],
                        "openrouter_usage_start_usd": start_usage,
                        "openrouter_usage_current_usd": usage,
                        "openrouter_usage_delta_usd": delta,
                        "max_budget_usd": plan["max_budget_usd"],
                    },
                )
            print(
                f"[budget] OpenRouter usage delta=${delta:.4f}/${plan['max_budget_usd']:.2f}",
                file=sys.stderr,
            )
            if delta >= plan["max_budget_usd"]:
                budget_exceeded = True
                stop_requested.set()
                await asyncio.to_thread(_delete_vms, plan)
                return

    tasks = [asyncio.create_task(run_worker(worker)) for worker in plan["worker_plans"]]
    watchdog = asyncio.create_task(budget_watchdog())
    try:
        executions = await asyncio.gather(*tasks)
    finally:
        done.set()
        await watchdog
    final_usage = await asyncio.to_thread(usage_reader, budget_api_key)
    recovered = await asyncio.to_thread(recover_missing_gcs_artifacts, plan)
    aggregate = aggregate_runner_matrix(plan)
    aggregate.update(
        {
            "status": "budget_stopped" if budget_exceeded else "complete",
            "executions": executions,
            "openrouter_usage_start_usd": start_usage,
            "openrouter_usage_end_usd": final_usage,
            "openrouter_usage_delta_usd": max(0.0, final_usage - start_usage),
            "budget_exceeded": budget_exceeded,
            "gcs_recovered_workers": recovered,
        }
    )
    return aggregate


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("calibration", "evolution"), required=True)
    parser.add_argument("--base-run-id", required=True)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument(
        "--generated-manifest",
        type=Path,
        default=DEFAULT_GENERATED_MANIFEST,
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--zone", default="us-central1-a")
    parser.add_argument("--machine-type", default="n2-standard-8")
    parser.add_argument("--boot-disk-size-gb", type=int, default=100)
    parser.add_argument("--repo-url", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--secret", action="append", default=[])
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--gcs-root")
    parser.add_argument("--max-budget", type=float)
    parser.add_argument("--budget-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--budget-poll-seconds", type=float, default=15.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--aggregate-output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    return parser


async def _main(args: argparse.Namespace) -> int:
    try:
        plan = build_runner_matrix_plan(
            phase=args.phase,
            base_run_id=args.base_run_id,
            matrix_path=args.matrix,
            generated_manifest_path=args.generated_manifest,
            project=args.project,
            zone=args.zone,
            machine_type=args.machine_type,
            boot_disk_size_gb=args.boot_disk_size_gb,
            repo_url=args.repo_url,
            commit=args.commit,
            secret_specs=[_parse_secret(value) for value in args.secret],
            artifact_root=args.artifact_root,
            plan_dir=args.plan_dir,
            gcs_root=args.gcs_root,
            max_budget_usd=args.max_budget,
        )
        write_runner_matrix_plan(plan, args.output)
        print(
            f"[ok] runner matrix phase={plan['phase']} models={plan['model_count']} "
            f"workers={plan['workers']} generations<={plan['total_generation_attempt_ceiling']}"
        )
        if not args.execute:
            return 0
        api_key = os.environ.get(args.budget_env, "")
        _require(bool(api_key), f"budget environment variable is missing: {args.budget_env}")
        aggregate = await execute_runner_matrix(
            plan,
            budget_api_key=api_key,
            poll_seconds=args.budget_poll_seconds,
            progress_output=args.aggregate_output,
        )
        _write_json(args.aggregate_output, aggregate)
        print(
            f"[ok] runner matrix status={aggregate['status']} "
            f"models={aggregate['models_with_scorecards']}/{plan['model_count']} "
            f"workers={aggregate['workers_with_scorecards']}/{plan['workers']} "
            f"usage_delta=${aggregate['openrouter_usage_delta_usd']:.4f}"
        )
        return 0 if aggregate["status"] == "complete" else 2
    except (CloudVmRunError, OSError, RunnerMatrixError, yaml.YAMLError) as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 1


def main() -> int:
    return asyncio.run(_main(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
