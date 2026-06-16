#!/usr/bin/env python3
"""Materialize and optionally execute the live DGM model matrix."""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sandbox_manager import SandboxResult
from scripts.estimate_model_matrix_cost import estimate_model_matrix_cost
from scripts.run_dgm_in_sandbox import (
    build_run_audit,
    load_sandbox_config,
    run_sandboxed_dgm,
    write_run_audit,
)
from scripts.summarize_archive_scores import ScorecardError, summarize_archive_scores


class ModelMatrixRunError(RuntimeError):
    """Raised when a matrix plan cannot be materialized or executed safely."""


Runner = Callable[..., Awaitable[SandboxResult]]
ScorecardBuilder = Callable[[Path], dict[str, Any]]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ModelMatrixRunError(message)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise ModelMatrixRunError(f"Missing config: {path}") from exc
    except yaml.YAMLError as exc:
        raise ModelMatrixRunError(f"Invalid YAML in {path}: {exc}") from exc
    _require(isinstance(data, dict), f"Config must be a mapping: {path}")
    return data


def _project_path(path_text: str | Path, project_root: Path) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = project_root / path
    try:
        relative_path = path.resolve().relative_to(project_root.resolve())
    except ValueError as exc:
        raise ModelMatrixRunError(f"{path_text} must stay inside the project root") from exc
    return project_root.resolve() / relative_path


def _project_relative(path: Path, project_root: Path) -> str:
    return str(path.resolve().relative_to(project_root.resolve()))


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "model"


def _provider_config(model: dict[str, Any]) -> dict[str, Any]:
    config = {
        "model": model["model"],
        "api_key": "${" + model["api_key_env"] + "}",
        "max_tokens": int(model["max_output_tokens_per_call"]),
        "temperature": float(model.get("temperature", 0.1)),
        "timeout": int(model.get("timeout", 60)),
    }
    if model.get("base_url"):
        config["base_url"] = model["base_url"]
    return config


def _trial_config(
    *,
    base_config: dict[str, Any],
    model: dict[str, Any],
    trial_number: int,
    trial_id: str,
    trial_dir: Path,
    project_root: Path,
    source_config: str,
) -> dict[str, Any]:
    trial_config = copy.deepcopy(base_config)
    provider = model["provider"]
    trial_config["fm_providers"] = {
        "primary": provider,
        provider: _provider_config(model),
    }
    trial_config.setdefault("archive", {})["path"] = _project_relative(
        trial_dir / "archive",
        project_root,
    )
    trial_config.setdefault("evaluation", {})["results_dir"] = _project_relative(
        trial_dir / "results",
        project_root,
    )
    trial_config.setdefault("agents", {})["workspace_dir"] = _project_relative(
        trial_dir / "workspace",
        project_root,
    )
    live_run = trial_config.setdefault("live_run", {})
    live_run["purpose"] = "live_model_matrix_trial"
    live_run["approval_required"] = True
    live_run["matrix_trial"] = {
        "source_config": source_config,
        "model_id": model["id"],
        "provider": provider,
        "trial_number": trial_number,
        "trial_id": trial_id,
        "pricing_source": model["pricing_source"],
        "estimated_total_cost_usd_per_trial": model[
            "estimated_total_cost_usd_per_trial"
        ],
    }
    cost_gate = live_run.setdefault("cost_gate", {})
    cost_gate["pricing_source"] = model["pricing_source"]
    cost_gate["input_price_per_mtok"] = model["input_price_per_mtok"]
    cost_gate["output_price_per_mtok"] = model["output_price_per_mtok"]
    cost_gate["max_output_tokens_per_call"] = model["max_output_tokens_per_call"]
    return trial_config


def build_model_matrix_plan(
    config_path: Path = PROJECT_ROOT / "config" / "live_model_matrix.yaml",
    *,
    project_root: Path = PROJECT_ROOT,
    run_dir: str | Path | None = None,
    audit_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Build a no-network execution plan and per-trial config payloads."""
    project_root = project_root.resolve()
    config_path = config_path if config_path.is_absolute() else project_root / config_path
    estimate = estimate_model_matrix_cost(config_path, project_root=project_root)
    config = _load_yaml(config_path)
    base_config_path = _project_path(config["base_live_run_config"], project_root)
    base_config = _load_yaml(base_config_path)
    matrix = config["model_matrix"]
    output_config = matrix.get("output", {})
    run_root = _project_path(
        run_dir or output_config.get("run_dir", ".dgm-live-runs/model-matrix"),
        project_root,
    )
    audit_root = _project_path(
        audit_dir or output_config.get("audit_dir", ".dgm-sandbox-runs/model-matrix"),
        project_root,
    )
    config_root = run_root / "configs"
    scorecard_root = run_root / "scorecards"
    generations = int(base_config.get("live_run", {}).get("recommended_generations", 0))
    _require(generations > 0, "Base live-run config must define recommended_generations")

    trials: list[dict[str, Any]] = []
    for model in estimate["models"]:
        model_slug = _slug(model["id"])
        for trial_number in range(1, int(estimate["trials_per_model"]) + 1):
            trial_id = f"{model_slug}-trial-{trial_number:02d}"
            trial_dir = run_root / trial_id
            config_path_for_trial = config_root / f"{trial_id}.yaml"
            audit_output = audit_root / f"{trial_id}-audit.json"
            scorecard_output = scorecard_root / f"{trial_id}-scorecard.json"
            archive_metadata = trial_dir / "archive" / "archive_metadata.json"
            trial_config = _trial_config(
                base_config=base_config,
                model=model,
                trial_number=trial_number,
                trial_id=trial_id,
                trial_dir=trial_dir,
                project_root=project_root,
                source_config=_project_relative(config_path, project_root),
            )
            trials.append(
                {
                    "trial_id": trial_id,
                    "model_id": model["id"],
                    "provider": model["provider"],
                    "model": model["model"],
                    "api_key_env": model["api_key_env"],
                    "generations": generations,
                    "config_path": _project_relative(config_path_for_trial, project_root),
                    "archive_metadata": _project_relative(archive_metadata, project_root),
                    "scorecard_output": _project_relative(scorecard_output, project_root),
                    "audit_output": _project_relative(audit_output, project_root),
                    "estimated_total_cost_usd_per_trial": model[
                        "estimated_total_cost_usd_per_trial"
                    ],
                    "trial_config": trial_config,
                }
            )

    manifest_path = run_root / "matrix-plan.json"
    return {
        "name": "live_model_matrix_execution_plan",
        "status": "planned",
        "config": estimate["config"],
        "base_live_run_config": estimate["base_live_run_config"],
        "benchmark": estimate["benchmark"],
        "approval_required": True,
        "dry_run_default": True,
        "planner_live_calls_performed": 0,
        "completed_trials": 0,
        "run_dir": _project_relative(run_root, project_root),
        "audit_dir": _project_relative(audit_root, project_root),
        "manifest_path": _project_relative(manifest_path, project_root),
        "trial_count": len(trials),
        "model_count": estimate["model_count"],
        "trials_per_model": estimate["trials_per_model"],
        "total_request_ceiling": estimate["total_request_ceiling"],
        "estimated_total_cost_usd": estimate["estimated_total_cost_usd"],
        "max_estimated_cost_usd": estimate["max_estimated_cost_usd"],
        "trials": trials,
    }


def _manifest_without_configs(plan: dict[str, Any]) -> dict[str, Any]:
    manifest = dict(plan)
    manifest["trials"] = [
        {key: value for key, value in trial.items() if key != "trial_config"}
        for trial in plan["trials"]
    ]
    return manifest


def write_model_matrix_plan(plan: dict[str, Any], *, project_root: Path) -> dict[str, Any]:
    """Write per-trial configs plus a non-secret matrix manifest."""
    project_root = project_root.resolve()
    for trial in plan["trials"]:
        config_path = project_root / trial["config_path"]
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.safe_dump(trial["trial_config"], sort_keys=False),
            encoding="utf-8",
        )

    manifest = _manifest_without_configs(plan)
    manifest_path = project_root / plan["manifest_path"]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


async def execute_model_matrix(
    plan: dict[str, Any],
    *,
    project_root: Path,
    allow_network: bool,
    timeout: int | None = None,
    sync_back: bool = True,
    runner: Runner = run_sandboxed_dgm,
    scorecard_builder: ScorecardBuilder = summarize_archive_scores,
) -> dict[str, Any]:
    """Execute all planned trials through the full-process sandbox runner."""
    _require(allow_network, "Live model matrix execution requires --allow-network")
    _require(
        sync_back,
        "Live model matrix execution requires sync-back so archive artifacts can be scored",
    )
    project_root = project_root.resolve()
    manifest = write_model_matrix_plan(plan, project_root=project_root)
    executions = []

    for trial in plan["trials"]:
        trial_config_path = project_root / trial["config_path"]
        sandbox_config = load_sandbox_config(trial_config_path, timeout=timeout)
        audit = build_run_audit(
            config_path=trial_config_path,
            generations=int(trial["generations"]),
            project_root=project_root,
            env_names=[trial["api_key_env"]],
            allow_network=True,
            network_mode="bridge",
            timeout=timeout,
            sync_back=sync_back,
            sandbox_config=sandbox_config,
        )
        write_run_audit(audit, project_root / trial["audit_output"])
        result = await runner(
            config_path=trial_config_path,
            generations=int(trial["generations"]),
            project_root=project_root,
            env_names=[trial["api_key_env"]],
            allow_network=True,
            network_mode="bridge",
            timeout=timeout,
            sync_back=sync_back,
        )
        execution = {
            "trial_id": trial["trial_id"],
            "model_id": trial["model_id"],
            "success": bool(result.success),
            "exit_code": result.exit_code,
            "scorecard_output": trial["scorecard_output"],
            "audit_output": trial["audit_output"],
        }
        if result.output:
            execution["output_preview"] = result.output[-4000:]
        if result.error:
            execution["error_preview"] = result.error[-4000:]
        if not result.success:
            executions.append(execution)
            if sync_back:
                manifest["executions"] = executions
                _write_manifest(manifest, project_root / plan["manifest_path"])
            raise ModelMatrixRunError(
                f"Trial {trial['trial_id']} failed with exit code {result.exit_code}"
            )

        try:
            scorecard = scorecard_builder(project_root / trial["archive_metadata"])
        except ScorecardError as exc:
            raise ModelMatrixRunError(
                f"Could not summarize trial {trial['trial_id']}: {exc}"
            ) from exc
        scorecard_path = project_root / trial["scorecard_output"]
        scorecard_path.parent.mkdir(parents=True, exist_ok=True)
        scorecard_path.write_text(
            json.dumps(scorecard, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        execution.update(
            {
                "top_score": scorecard["top_score"],
                "best_average_delta": scorecard["best_average_delta"],
                "has_improvement": scorecard["has_improvement"],
            }
        )
        executions.append(execution)
        manifest["executions"] = executions
        manifest["completed_trials"] = len(executions)
        _write_manifest(manifest, project_root / plan["manifest_path"])

    manifest["status"] = "executed"
    manifest["completed_trials"] = len(executions)
    manifest["executions"] = executions
    _write_manifest(manifest, project_root / plan["manifest_path"])
    return manifest


def _write_manifest(manifest: dict[str, Any], manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(PROJECT_ROOT / "config" / "live_model_matrix.yaml"))
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument(
        "--run-dir",
        help="Project-relative output directory for generated configs and scorecards.",
    )
    parser.add_argument(
        "--audit-dir",
        help="Project-relative output directory for non-secret sandbox audit artifacts.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the no-network execution plan. This is the default when --execute is absent.",
    )
    parser.add_argument(
        "--write-configs",
        action="store_true",
        help="Materialize per-trial configs and a non-secret matrix manifest without live calls.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run each trial through the full-process sandbox runner.",
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Required with --execute so live provider calls are explicit.",
    )
    parser.add_argument("--timeout", type=int, help="Optional sandbox timeout.")
    parser.add_argument(
        "--discard-changes",
        action="store_true",
        help="Do not sync successful sandbox writes back to the host checkout.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    try:
        if args.execute and args.dry_run:
            raise ModelMatrixRunError("--execute cannot be combined with --dry-run")
        if args.execute and args.write_configs:
            raise ModelMatrixRunError("--execute already writes configs; omit --write-configs")
        project_root = Path(args.project_root).resolve()
        plan = build_model_matrix_plan(
            Path(args.config),
            project_root=project_root,
            run_dir=args.run_dir,
            audit_dir=args.audit_dir,
        )
        if args.execute:
            manifest = await execute_model_matrix(
                plan,
                project_root=project_root,
                allow_network=args.allow_network,
                timeout=args.timeout,
                sync_back=not args.discard_changes,
            )
            output = manifest
        elif args.write_configs:
            output = write_model_matrix_plan(plan, project_root=project_root)
        else:
            output = _manifest_without_configs(plan)
    except ModelMatrixRunError as exc:
        if args.json:
            print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        else:
            print(f"[fail] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(output, indent=2, sort_keys=True))
    else:
        mode = "execute" if args.execute else "write-configs" if args.write_configs else "dry-run"
        print(
            "[ok] live_model_matrix_execution_plan "
            f"mode={mode} "
            f"trials={output['trial_count']} "
            f"requests<={output['total_request_ceiling']} "
            f"total=${output['estimated_total_cost_usd']:.4f} "
            f"manifest={output['manifest_path']}"
        )
    return 0


def main() -> int:
    return asyncio.run(_main_async(_build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
