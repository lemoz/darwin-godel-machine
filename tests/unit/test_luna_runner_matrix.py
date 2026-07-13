import json
import time
from pathlib import Path

import pytest
import yaml

from scripts.estimate_luna_runner_matrix import estimate_matrix
from scripts.materialize_luna_runner_matrix import materialize_matrix
from scripts.run_cloud_luna_runner_matrix import (
    _delete_vms,
    build_runner_matrix_plan,
    execute_runner_matrix,
)
from scripts.run_live_eval_on_cloud_vm import SecretSpec


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = PROJECT_ROOT / "config/livecodebench_luna_runner_matrix.yaml"
RECOVERY_MATRIX_PATH = (
    PROJECT_ROOT / "config/livecodebench_luna_recovery_runner_matrix.yaml"
)
REFERENCE_PROOF = (
    PROJECT_ROOT / "docs/live-runs/lcb64-fable5-mutator-gemma3-20260712-1"
)


def _materialized_tree(tmp_path: Path) -> tuple[Path, Path, dict]:
    matrix_path = tmp_path / "config/livecodebench_luna_runner_matrix.yaml"
    matrix_path.parent.mkdir(parents=True)
    matrix_path.write_text(MATRIX_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    output_dir = tmp_path / "config/generated/luna_runner_matrix"
    manifest = materialize_matrix(
        matrix_path=matrix_path,
        output_dir=output_dir,
        project_root=tmp_path,
    )
    return matrix_path, output_dir / "manifest.json", manifest


def _plan_kwargs(tmp_path: Path, matrix_path: Path, manifest_path: Path) -> dict:
    return {
        "base_run_id": "luna-matrix-test",
        "matrix_path": matrix_path,
        "generated_manifest_path": manifest_path,
        "project": "dgm-project",
        "zone": "us-central1-a",
        "machine_type": "n2-standard-8",
        "boot_disk_size_gb": 100,
        "repo_url": "https://github.com/example/dgm.git",
        "commit": "abc1234",
        "secret_specs": [SecretSpec("OPENROUTER_API_KEY", "openrouter-api-key")],
        "artifact_root": tmp_path / "artifacts",
        "plan_dir": tmp_path / "plans",
        "gcs_root": "gs://dgm-runs/luna-matrix-test",
        "project_root": tmp_path,
    }


def test_materializes_ten_runner_models_with_luna_mutation(tmp_path: Path):
    _matrix_path, _manifest_path, manifest = _materialized_tree(tmp_path)

    assert manifest["config_count"] == 20
    assert len({item["slug"] for item in manifest["configs"]}) == 10
    assert {item["phase"] for item in manifest["configs"]} == {
        "calibration",
        "evolution",
    }
    assert len({item["archive"] for item in manifest["configs"]}) == 20
    for item in manifest["configs"]:
        config = yaml.safe_load((tmp_path / item["config"]).read_text(encoding="utf-8"))
        assert config["fm_providers"]["runner"]["model"] == item["model"]
        assert (
            config["fm_providers"]["luna_mutator"]["model"]
            == "openai/gpt-5.6-luna"
        )
        assert config["self_modification"]["fm_provider"] == "luna_mutator"


def test_materializes_recovery_runners_and_builds_native_baseline(tmp_path: Path):
    matrix_path = tmp_path / "config/livecodebench_luna_recovery_runner_matrix.yaml"
    matrix_path.parent.mkdir(parents=True)
    matrix_path.write_text(
        RECOVERY_MATRIX_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    output_dir = tmp_path / "config/generated/luna_recovery_runner_matrix"
    manifest = materialize_matrix(
        matrix_path=matrix_path,
        output_dir=output_dir,
        project_root=tmp_path,
    )
    manifest_path = output_dir / "manifest.json"

    assert manifest["config_count"] == 8
    assert {item["slug"] for item in manifest["configs"]} == {
        "gemini25-flash",
        "gemini35-flash",
        "fable5",
        "gpt56-sol",
    }

    plan = build_runner_matrix_plan(
        phase="evolution",
        generations_override=0,
        workers_per_model_override=1,
        max_concurrency_override=4,
        max_budget_usd=20,
        **_plan_kwargs(tmp_path, matrix_path, manifest_path),
    )

    assert plan["model_count"] == 4
    assert plan["workers"] == 4
    assert plan["generations_per_worker"] == 0
    assert plan["total_generation_attempt_ceiling"] == 0
    assert plan["max_concurrency"] == 4
    assert plan["max_budget_usd"] == 20


def test_calibration_and_evolution_configs_have_full_experiment_shape(tmp_path: Path):
    _matrix_path, _manifest_path, manifest = _materialized_tree(tmp_path)
    configs = {
        (item["slug"], item["phase"]): yaml.safe_load(
            (tmp_path / item["config"]).read_text(encoding="utf-8")
        )
        for item in manifest["configs"]
    }

    calibration = configs[("qwen3-coder", "calibration")]
    assert calibration["evaluation"]["use_sandbox"] is True
    assert calibration["live_run"]["recommended_generations"] == 0
    assert any(
        "rescore_archive_agents.py" in command and "--replicates 2" in command
        for command in calibration["live_run"]["required_preflight"]
    )

    evolution = configs[("gpt56-sol", "evolution")]
    assert evolution["evaluation"]["use_sandbox"] is False
    assert evolution["live_run"]["recommended_generations"] == 15
    assert evolution["live_run"]["parallel"]["workers"] == 3
    assert evolution["live_run"]["parallel"]["shared_max_budget_usd"] == 72
    assert evolution["live_run"]["parallel"]["budget_poll_seconds"] == 15
    assert evolution["live_run"]["seed_mode"] == "fresh_native"
    assert evolution["live_run"]["baseline_agent"] == "agent/agent.py"
    assert evolution["target_performance"] == 1.0
    assert (
        evolution["self_modification"]["constrained_mutation"][
            "max_agent_iterations"
        ]
        == 24
    )
    assert not any(
        "seed_archive_from_proof.py" in command
        for command in evolution["live_run"]["required_preflight"]
    )
    assert "focus_agent_ids" not in evolution["parent_selection"]


def test_observed_cost_estimate_fits_phase_and_total_budgets():
    estimate = estimate_matrix(matrix_path=MATRIX_PATH, proof_dir=REFERENCE_PROOF)

    assert estimate["total_evolution_generations"] == 450
    assert estimate["calibration_evaluations_per_model"] == 0
    assert estimate["base_initializations_per_model"] == 3
    assert estimate["estimated_calibration_openrouter_cost_usd"] == 0
    assert estimate["estimated_evolution_openrouter_cost_usd"] < 72
    assert estimate["estimated_openrouter_cost_usd"] == pytest.approx(79.165, abs=0.001)
    assert estimate["estimated_total_cost_usd"] == pytest.approx(82.979, abs=0.001)
    assert estimate["within_budget"] is True


def test_matrix_cloud_plans_cover_calibration_and_full_evolution(tmp_path: Path):
    matrix_path, manifest_path, _manifest = _materialized_tree(tmp_path)
    kwargs = _plan_kwargs(tmp_path, matrix_path, manifest_path)

    calibration = build_runner_matrix_plan(phase="calibration", **kwargs)
    assert calibration["model_count"] == 10
    assert calibration["workers"] == 10
    assert calibration["generations_per_worker"] == 0
    assert calibration["max_concurrency"] == 6
    assert calibration["max_budget_usd"] == 10
    assert len({worker["run_id"] for worker in calibration["worker_plans"]}) == 10
    assert all(
        worker["cloud_plan"]["source"]["mutation_model"]
        == "openai/gpt-5.6-luna"
        for worker in calibration["worker_plans"]
    )

    evolution = build_runner_matrix_plan(phase="evolution", **kwargs)
    assert evolution["workers"] == 30
    assert evolution["generations_per_worker"] == 15
    assert evolution["total_generation_attempt_ceiling"] == 450
    assert evolution["max_concurrency"] == 10
    assert evolution["max_budget_usd"] == 72
    assert evolution["source"]["seed_mode"] == "fresh_native"
    assert evolution["scheduling"] == "worker_round_robin"
    first_wave = evolution["worker_plans"][:10]
    assert {worker["worker_id"] for worker in first_wave} == {1}
    assert len({worker["model_slug"] for worker in first_wave}) == 10


def test_budget_teardown_deletes_the_fleet_in_one_cloud_call(monkeypatch):
    calls = []
    plan = {
        "worker_plans": [
            {
                "cloud_plan": {
                    "vm": {
                        "name": f"dgm-worker-{index}",
                        "project": "dgm-project",
                        "zone": "us-central1-a",
                    }
                }
            }
            for index in range(3)
        ]
    }

    monkeypatch.setattr(
        "scripts.run_cloud_luna_runner_matrix.subprocess.run",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )
    _delete_vms(plan)

    assert len(calls) == 1
    assert calls[0][0][:4] == ["gcloud", "compute", "instances", "delete"]
    assert calls[0][0][4:7] == [
        "dgm-worker-0",
        "dgm-worker-1",
        "dgm-worker-2",
    ]


@pytest.mark.asyncio
async def test_budget_stop_prevents_queued_workers_from_starting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    worker_plans = []
    for index in range(3):
        artifact_dir = tmp_path / f"w{index}"
        worker_plans.append(
            {
                "model_slug": f"model-{index}",
                "model": f"provider/model-{index}",
                "run_id": f"run-{index}",
                "artifact_dir": str(artifact_dir),
                "gcs_uri": None,
                "cloud_plan": {"commands": {"teardown": ["true"]}},
            }
        )
    plan = {
        "phase": "evolution",
        "workers": 3,
        "max_concurrency": 1,
        "max_budget_usd": 1,
        "worker_plans": worker_plans,
    }
    starts = []
    usage_calls = 0

    def fake_executor(cloud_plan):
        starts.append(cloud_plan)
        time.sleep(0.05)

    def fake_usage(_api_key):
        nonlocal usage_calls
        usage_calls += 1
        return 0.0 if usage_calls == 1 else 2.0

    monkeypatch.setattr(
        "scripts.run_cloud_luna_runner_matrix._delete_vms", lambda _plan: None
    )
    progress_output = tmp_path / "live-state.json"
    aggregate = await execute_runner_matrix(
        plan,
        budget_api_key="test-key",
        poll_seconds=0.01,
        executor=fake_executor,
        usage_reader=fake_usage,
        progress_output=progress_output,
    )

    assert len(starts) == 1
    assert aggregate["status"] == "budget_stopped"
    assert [item["status"] for item in aggregate["executions"]] == [
        "complete",
        "budget_skipped",
        "budget_skipped",
    ]
    live_state = json.loads(progress_output.read_text(encoding="utf-8"))
    assert live_state["openrouter_usage_start_usd"] == 0.0
    assert live_state["openrouter_usage_delta_usd"] == 2.0


@pytest.mark.asyncio
async def test_worker_launch_failure_marks_matrix_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    artifact_dir = tmp_path / "failed-worker"
    plan = {
        "phase": "evolution",
        "workers": 1,
        "max_concurrency": 1,
        "max_budget_usd": 5,
        "worker_plans": [
            {
                "model_slug": "failed-model",
                "model": "provider/failed-model",
                "run_id": "failed-run",
                "artifact_dir": str(artifact_dir),
                "gcs_uri": None,
                "cloud_plan": {"commands": {"teardown": ["true"]}},
            }
        ],
    }

    def fail_launch(_cloud_plan):
        raise RuntimeError("VM creation failed")

    monkeypatch.setattr(
        "scripts.run_cloud_luna_runner_matrix.recover_missing_gcs_artifacts",
        lambda _plan: 0,
    )

    aggregate = await execute_runner_matrix(
        plan,
        budget_api_key="test-key",
        poll_seconds=0.01,
        executor=fail_launch,
        usage_reader=lambda _api_key: 0.0,
    )

    assert aggregate["status"] == "failed"
    assert aggregate["executions"] == [
        {
            "run_id": "failed-run",
            "status": "failed",
            "error": "VM creation failed",
        }
    ]
