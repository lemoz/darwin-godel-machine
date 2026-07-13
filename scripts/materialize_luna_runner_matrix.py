#!/usr/bin/env python3
"""Materialize isolated calibration and evolution configs for the runner matrix."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MATRIX = PROJECT_ROOT / "config/livecodebench_luna_runner_matrix.yaml"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "config/generated/luna_runner_matrix"
BENCHMARKS = [
    "livecodebench_abc387_b",
    "livecodebench_abc388_b",
    "livecodebench_abc389_a",
    "livecodebench_abc390_b",
    "livecodebench_abc387_c",
    "livecodebench_abc388_d",
    "livecodebench_abc388_c",
    "livecodebench_abc389_d",
    "livecodebench_abc390_d",
    "livecodebench_abc388_e",
    "livecodebench_abc389_e",
    "livecodebench_abc390_e",
]


class MatrixMaterializationError(RuntimeError):
    """Raised when the runner matrix cannot be materialized safely."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MatrixMaterializationError(message)


def _load_matrix(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _require(payload.get("name") == "livecodebench_luna_runner_matrix", "wrong matrix name")
    models = payload.get("models")
    _require(isinstance(models, list) and len(models) == 10, "matrix must contain ten models")
    slugs = [item.get("slug") for item in models]
    _require(len(set(slugs)) == len(slugs), "matrix model slugs must be unique")
    _require(
        payload.get("mutation", {}).get("model") == "openai/gpt-5.6-luna",
        "matrix mutator must be GPT-5.6 Luna",
    )
    return payload


def _relative(path: Path, project_root: Path) -> str:
    return path.relative_to(project_root).as_posix()


def _base_config(
    matrix: dict[str, Any],
    model: dict[str, Any],
    *,
    phase: str,
) -> dict[str, Any]:
    slug = str(model["slug"])
    root = f".dgm-live-runs/luna-runner-matrix/{phase}/{slug}"
    runner = deepcopy(matrix["runner_defaults"])
    runner["model"] = model["model"]
    mutation = deepcopy(matrix["mutation"])
    mutation.pop("provider_key", None)
    mutation.pop("input_price_per_mtok", None)
    mutation.pop("output_price_per_mtok", None)
    parent_selection = {
        "lambda": 10,
        "alpha_0": 0.5,
        "require_non_regression": True,
        "require_per_benchmark_non_regression": True,
        "regression_tolerance": 0.0,
        "reject_score_ties": False,
        "elite_selection_probability": 0.1,
        "focus_selection_probability": 0.85,
        "focus_include_descendants": True,
        "focus_agent_ids": list(matrix["seed"]["agent_ids"]),
    }
    if phase == "evolution" and matrix["evolution"].get("seed_mode") == "fresh_native":
        parent_selection = {
            "lambda": 10,
            "alpha_0": 0.5,
            "require_non_regression": True,
            "require_per_benchmark_non_regression": True,
            "regression_tolerance": 0.0,
            "reject_score_ties": False,
            "elite_selection_probability": 0.0,
        }
    return {
        "fm_providers": {
            "primary": "runner",
            "runner": runner,
            "luna_mutator": mutation,
        },
        "archive": {"path": f"{root}/archive"},
        "parent_selection": parent_selection,
        "evaluation": {
            "benchmarks_dir": ".dgm-live-runs/livecodebench-loop12/benchmarks",
            "results_dir": f"{root}/results",
            "timeout_seconds": 30,
            "use_sandbox": phase == "calibration",
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
            "fm_provider": "luna_mutator",
            "max_steps": 3,
            "max_consecutive_noop_mutations": 8,
            "constrained_mutation": {
                "enabled": True,
                "max_agent_iterations": int(
                    matrix["mutation"]["max_agent_iterations"]
                ),
                "protected_symbols": {
                    "agent.py": [
                        "Agent._build_system_message",
                        "Agent._is_task_complete",
                        "Agent._extract_code_solution",
                        "Agent._read_workspace_solution",
                        "Agent._benchmark_completion_block_reason",
                    ]
                },
            },
        },
        "benchmarks": {
            "timeout_default": 30,
            "max_attempts": 3,
            "enabled": list(BENCHMARKS),
        },
        "target_performance": float(matrix["evolution"]["target_score"]),
        "logging": {"level": "INFO"},
        "generation_delay_seconds": 0,
        "stop_on_error": True,
    }


def _seed_command(matrix: dict[str, Any], archive: str, source: str, output: str) -> str:
    focus = " ".join(
        f"--focus-agent-id {agent_id}" for agent_id in matrix["seed"]["agent_ids"]
    )
    return (
        "PATH=\"$PWD/.venv/bin:$PATH\" python scripts/seed_archive_from_proof.py "
        f"--archive-tar {source} --target-archive {archive} {focus} "
        f"--min-focus-score 0 --output {output} --force"
    )


def _live_run_metadata(
    matrix: dict[str, Any],
    model: dict[str, Any],
    *,
    phase: str,
    config_label: str,
    archive: str,
) -> dict[str, Any]:
    mutation = matrix["mutation"]
    generations = (
        int(matrix["calibration"]["generations"])
        if phase == "calibration"
        else int(matrix["evolution"]["generations_per_worker"])
    )
    live_run = {
        "purpose": f"livecodebench_luna_runner_matrix_{phase}",
        "approval_required": True,
        "recommended_generations": generations,
        "matrix": {
            "name": matrix["name"],
            "phase": phase,
            "model_slug": model["slug"],
            "runner_model": model["model"],
            "mutation_model": mutation["model"],
        },
        "segment": {
            "config": matrix["segment"]["config"],
            "manifest_path": matrix["segment"]["manifest_path"],
            "segment_id": matrix["segment"]["segment_id"],
            "benchmark_count": matrix["segment"]["benchmark_count"],
            "expected_total_tests_min": 400,
            "expected_private_tests_min": 350,
            "source": "https://huggingface.co/datasets/livecodebench/code_generation_lite",
            "upstream": "https://github.com/livecodebench/livecodebench",
            "prompt_examples_are_public_only": True,
            "scored_tests_include_private": True,
        },
        "cost_gate": {
            "pricing_checked_at": matrix["pricing_checked_at"],
            "pricing_source": matrix["pricing_source"],
            "solver_input_price_per_mtok": model["input_price_per_mtok"],
            "solver_output_price_per_mtok": model["output_price_per_mtok"],
            "mutation_input_price_per_mtok": mutation["input_price_per_mtok"],
            "mutation_output_price_per_mtok": mutation["output_price_per_mtok"],
            "assumed_input_tokens_per_call": 12000,
            "max_estimated_cost_usd": 100,
            "max_generations_without_reapproval": max(1, generations),
            "max_agent_steps": 7,
            "max_self_modification_steps": 3,
            "max_output_tokens_per_call": matrix["runner_defaults"]["max_tokens"],
            "max_enabled_benchmarks": len(BENCHMARKS),
        },
        "post_run_scorecard": {
            "command": (
                "PATH=\"$PWD/.venv/bin:$PATH\" python "
                "scripts/summarize_archive_scores.py "
                f"--archive-metadata {archive}/archive_metadata.json "
                f"--output {archive}/scorecard.json"
            ),
            "require_improvement": False,
        },
    }
    prepare = (
        "PATH=\"$PWD/.venv/bin:$PATH\" python "
        "scripts/prepare_livecodebench_segment.py --config "
        f"{matrix['segment']['config']}"
    )
    verify = (
        "PATH=\"$PWD/.venv/bin:$PATH\" python "
        "scripts/verify_sandbox_docker.py --build-image --require"
    )
    seed_manifest = archive.rsplit("/", 1)[0] + "/seed_manifest.json"
    if phase == "calibration":
        seed_source = matrix["seed"]["source_proof"]
        calibration_output = f"{archive}/calibration.json"
        rescore = (
            "PATH=\"$PWD/.venv/bin:$PATH\" python scripts/rescore_archive_agents.py "
            f"--config {config_label} "
            + " ".join(
                f"--agent-id {agent_id}" for agent_id in matrix["seed"]["agent_ids"]
            )
            + f" --replicates {matrix['calibration']['replicates']} "
            f"--prune-unselected --output {calibration_output}"
        )
        live_run["baseline_proof"] = seed_source
        live_run["required_preflight"] = [
            prepare,
            _seed_command(matrix, archive, seed_source, seed_manifest),
            verify,
            rescore,
        ]
    else:
        seed_mode = matrix["evolution"].get("seed_mode", "calibrated_archive")
        live_run["seed_mode"] = seed_mode
        live_run["parallel"] = {
            "workers": matrix["evolution"]["workers_per_model"],
            "max_concurrency": matrix["evolution"]["max_concurrency"],
            "seed_changed_count": 0,
            "seed_noop_count": 0,
            "shared_max_budget_usd": matrix["evolution"]["max_openrouter_budget_usd"],
            "budget_poll_seconds": matrix["evolution"]["budget_poll_seconds"],
        }
        if seed_mode == "fresh_native":
            live_run["baseline_agent"] = "agent/agent.py"
            live_run["baseline_initialization"] = (
                "DGMController._initialize_base_agent evaluates the common base agent "
                "once per isolated worker before generation 1"
            )
            live_run["required_preflight"] = [prepare, verify]
        else:
            seed_source = (
                f"{matrix['seed']['calibration_bundle']}/{model['slug']}/archive.tar.gz"
            )
            live_run["baseline_proof"] = seed_source
            live_run["required_preflight"] = [
                prepare,
                _seed_command(matrix, archive, seed_source, seed_manifest),
                verify,
            ]
    return live_run


def materialize_matrix(
    *,
    matrix_path: Path = DEFAULT_MATRIX,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    matrix = _load_matrix(matrix_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    configs = []
    for model in matrix["models"]:
        for phase in ("calibration", "evolution"):
            path = output_dir / f"{model['slug']}-{phase}.yaml"
            label = _relative(path, project_root)
            config = _base_config(matrix, model, phase=phase)
            archive = config["archive"]["path"]
            config["live_run"] = _live_run_metadata(
                matrix,
                model,
                phase=phase,
                config_label=label,
                archive=archive,
            )
            path.write_text(
                yaml.safe_dump(config, sort_keys=False, width=1000),
                encoding="utf-8",
            )
            configs.append(
                {
                    "slug": model["slug"],
                    "model": model["model"],
                    "phase": phase,
                    "config": label,
                    "archive": archive,
                }
            )
    manifest = {
        "schema_version": 1,
        "name": "materialized_luna_runner_matrix",
        "matrix": _relative(matrix_path, project_root),
        "config_count": len(configs),
        "configs": configs,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
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
    try:
        result = materialize_matrix(matrix_path=args.matrix, output_dir=args.output_dir)
    except (OSError, MatrixMaterializationError, yaml.YAMLError) as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"[ok] materialized {result['config_count']} runner configs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
