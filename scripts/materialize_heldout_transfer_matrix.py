#!/usr/bin/env python3
"""Materialize frozen native-versus-mutated held-out evaluation configs."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = PROJECT_ROOT / "config/livecodebench_heldout_transfer_matrix.yaml"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "config/generated/heldout_transfer_matrix"


class TransferMaterializationError(RuntimeError):
    """Raised when the transfer matrix cannot be materialized safely."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TransferMaterializationError(message)


def _relative(path: Path, project_root: Path) -> str:
    return path.resolve().relative_to(project_root.resolve()).as_posix()


def _load_matrix(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _require(payload.get("name") == "livecodebench_heldout_transfer", "unexpected matrix name")
    models = payload.get("models")
    _require(isinstance(models, list) and models, "models must be a non-empty list")
    _require(
        len({model.get("slug") for model in models}) == len(models),
        "model slugs must be unique",
    )
    return payload


def _preflight_commands(
    *,
    matrix: dict[str, Any],
    model: dict[str, Any],
    config_label: str,
    archive: str,
) -> list[str]:
    seed_agent_args = " ".join(
        f"--focus-agent-id {agent['id']}" for agent in model["agents"]
    )
    rescore_agent_args = " ".join(
        f"--agent-id {agent['id']}" for agent in model["agents"]
    )
    seed_manifest = f"{archive}/seed-manifest.json"
    transfer_manifest = f"{archive}/transfer.json"
    return [
        (
            'PATH="$PWD/.venv/bin:$PATH" python '
            "scripts/prepare_livecodebench_segment.py --config "
            f"{matrix['segment']['config']}"
        ),
        (
            'PATH="$PWD/.venv/bin:$PATH" python scripts/seed_archive_from_proof.py '
            f"--archive-tar {model['proof_archive']} --target-archive {archive} "
            f"{seed_agent_args} --min-focus-score 0 --output {seed_manifest} --force"
        ),
        (
            'PATH="$PWD/.venv/bin:$PATH" python scripts/rescore_archive_agents.py '
            f"--config {config_label} {rescore_agent_args} "
            f"--replicates {model['replicates']} "
            f"--prune-unselected --output {transfer_manifest}"
        ),
    ]


def _materialized_config(
    *,
    matrix: dict[str, Any],
    model: dict[str, Any],
    config_label: str,
) -> dict[str, Any]:
    slug = str(model["slug"])
    root = f".dgm-live-runs/{matrix['run_root']}/{slug}"
    archive = f"{root}/archive"
    runner = deepcopy(matrix["runner_defaults"])
    runner["model"] = model["model"]
    mutator = deepcopy(matrix["mutation"])
    for key in ("mode", "provider_key", "max_agent_iterations"):
        mutator.pop(key, None)
    mutator["model"] = model["model"]
    config = {
        "fm_providers": {
            "primary": "runner",
            "runner": runner,
            "self_mutator": mutator,
        },
        "archive": {"path": archive},
        "parent_selection": {
            "lambda": 10,
            "alpha_0": 0.5,
            "require_non_regression": True,
            "require_per_benchmark_non_regression": True,
            "regression_tolerance": 0.0,
        },
        "evaluation": {
            "benchmarks_dir": ".dgm-live-runs/livecodebench-heldout12/benchmarks",
            "results_dir": f"{root}/results",
            "timeout_seconds": 30,
            "use_sandbox": False,
        },
        "sandbox": {
            "image_name": "dgm-sandbox",
            "memory_limit": "2g",
            "cpu_limit": "1",
            "timeout": 43200,
            "network_mode": "none",
            "working_dir": "/home/dgm_agent/workspace",
            "auto_build_image": True,
        },
        "agents": {
            "workspace_dir": f"{root}/workspace",
            "initial_agent_path": "agent/agent.py",
            "max_steps": 7,
        },
        "self_modification": {
            "fm_provider": "self_mutator",
            "max_steps": 3,
            "max_consecutive_noop_mutations": 8,
        },
        "benchmarks": {
            "timeout_default": 30,
            "max_attempts": 3,
            "enabled": list(matrix["segment"]["benchmarks"]),
        },
        "target_performance": 1.0,
        "logging": {"level": "INFO"},
        "generation_delay_seconds": 0,
        "stop_on_error": True,
    }
    config["live_run"] = {
        "purpose": "livecodebench_heldout_transfer",
        "approval_required": True,
        "recommended_generations": 0,
        "matrix": {
            "name": matrix["name"],
            "phase": "calibration",
            "model_slug": slug,
            "runner_model": model["model"],
            "mutation_model": model["model"],
            "mutation_mode": "none_frozen_replay",
        },
        "segment": {
            "config": matrix["segment"]["config"],
            "manifest_path": matrix["segment"]["manifest_path"],
            "segment_id": matrix["segment"]["segment_id"],
            "benchmark_count": matrix["segment"]["benchmark_count"],
            "prompt_examples_are_public_only": True,
            "scored_tests_include_private": True,
            "disjoint_from": "release_v6_atcoder_loop12",
        },
        "transfer": {
            "proof_archive": model["proof_archive"],
            "replicates": int(model["replicates"]),
            "agents": deepcopy(model["agents"]),
        },
        "cost_gate": {
            "max_estimated_cost_usd": matrix["calibration"]["max_openrouter_budget_usd"],
            "solver_input_price_per_mtok": model["input_price_per_mtok"],
            "solver_output_price_per_mtok": model["output_price_per_mtok"],
            "max_enabled_benchmarks": matrix["segment"]["benchmark_count"],
            "max_output_tokens_per_call": runner["max_tokens"],
        },
    }
    config["live_run"]["required_preflight"] = _preflight_commands(
        matrix=matrix,
        model=model,
        config_label=config_label,
        archive=archive,
    )
    return config


def materialize_transfer_matrix(
    *,
    matrix_path: Path = DEFAULT_MATRIX,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    matrix = _load_matrix(matrix_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    configs = []
    for model in matrix["models"]:
        path = output_dir / f"{model['slug']}-calibration.yaml"
        label = _relative(path, project_root)
        config = _materialized_config(matrix=matrix, model=model, config_label=label)
        path.write_text(yaml.safe_dump(config, sort_keys=False, width=1000), encoding="utf-8")
        configs.append(
            {
                "slug": model["slug"],
                "model": model["model"],
                "phase": "calibration",
                "config": label,
                "archive": config["archive"]["path"],
            }
        )
    manifest = {
        "schema_version": 1,
        "name": f"materialized_{matrix['name']}",
        "matrix": _relative(matrix_path, project_root),
        "config_count": len(configs),
        "configs": configs,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    matrix_path = args.matrix if args.matrix.is_absolute() else PROJECT_ROOT / args.matrix
    output_dir = args.output_dir if args.output_dir.is_absolute() else PROJECT_ROOT / args.output_dir
    try:
        result = materialize_transfer_matrix(
            matrix_path=matrix_path,
            output_dir=output_dir,
            project_root=PROJECT_ROOT,
        )
    except (OSError, TransferMaterializationError, yaml.YAMLError) as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else f"[ok] materialized {result['config_count']} transfer configs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
