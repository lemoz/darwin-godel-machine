import json
from pathlib import Path

import pytest

from scripts.run_live_eval_on_cloud_vm import (
    CloudVmRunError,
    SecretSpec,
    build_cloud_vm_plan,
    build_startup_script,
    write_plan_files,
)


def test_build_startup_script_clones_exact_commit_and_hides_secret_values():
    script = build_startup_script(
        repo_url="https://github.com/example/dgm.git",
        commit="abc1234",
        config="config/live.yaml",
        generations=10,
        run_id="loop12-proof",
        env_names=["OPENROUTER_API_KEY"],
        secret_specs=[SecretSpec("OPENROUTER_API_KEY", "openrouter-api-key")],
        provider="openrouter",
        model="moonshotai/kimi-k2.7-code",
        input_price_per_mtok=0.74,
        output_price_per_mtok=3.50,
        gcs_artifact_uri="gs://dgm-runs/loop12-proof",
    )

    assert "git clone" in script
    assert "COMMIT=abc1234" in script
    assert 'git checkout "${COMMIT}"' in script
    assert "config/live.yaml" in script
    assert "OPENROUTER_API_KEY=openrouter-api-key" in script
    assert "secret-value" not in script
    assert "summarize_live_run_telemetry.py" in script
    assert "summarize_archive_scores.py" in script
    assert "gcloud storage rsync --recursive" in script
    assert "gs://dgm-runs/loop12-proof" in script
    assert "EXIT_CODE_PATH" in script


def test_build_cloud_vm_plan_contains_create_sync_and_teardown_commands(tmp_path: Path):
    plan = build_cloud_vm_plan(
        run_id="loop12-proof",
        provider="gcloud",
        project="dgm-project",
        zone="us-central1-a",
        machine_type="n2-standard-8",
        boot_disk_size_gb=100,
        image_family="debian-12",
        image_project="debian-cloud",
        repo_url="https://github.com/example/dgm.git",
        commit="abc1234",
        config="config/live.yaml",
        generations=10,
        env_names=[],
        secret_specs=[SecretSpec("OPENROUTER_API_KEY", "openrouter-api-key")],
        artifact_dir=tmp_path / "artifacts",
        startup_script_path=tmp_path / "startup.sh",
        fm_provider="openrouter",
        model="moonshotai/kimi-k2.7-code",
        input_price_per_mtok=0.74,
        output_price_per_mtok=3.50,
        gcs_artifact_uri="gs://dgm-runs/loop12-proof",
    )

    assert plan["vm"]["name"] == "dgm-loop12-proof"
    assert plan["vm"]["ephemeral"] is True
    assert plan["source"]["commit"] == "abc1234"
    assert plan["secrets"]["env_names"] == ["OPENROUTER_API_KEY"]
    assert plan["secrets"]["env_values"] == "hidden"
    assert plan["artifacts"]["remote_dir"] == "/var/tmp/dgm-live-runs/loop12-proof/artifacts"
    assert plan["artifacts"]["gcs_uri"] == "gs://dgm-runs/loop12-proof"
    assert plan["artifacts"]["exit_code"] == "/var/tmp/dgm-live-runs/loop12-proof/artifacts/exit_code"
    assert plan["commands"]["create"][:4] == [
        "gcloud",
        "compute",
        "instances",
        "create",
    ]
    assert plan["commands"]["sync_artifacts"][:4] == [
        "gcloud",
        "compute",
        "scp",
        "--recurse",
    ]
    assert plan["commands"]["teardown"][:4] == [
        "gcloud",
        "compute",
        "instances",
        "delete",
    ]


def test_write_plan_files_redacts_inline_startup_script(tmp_path: Path):
    output = tmp_path / "plan.json"
    startup = tmp_path / "startup.sh"
    plan = build_cloud_vm_plan(
        run_id="loop12-proof",
        provider="gcloud",
        project="dgm-project",
        zone="us-central1-a",
        machine_type="n2-standard-8",
        boot_disk_size_gb=100,
        image_family="debian-12",
        image_project="debian-cloud",
        repo_url="https://github.com/example/dgm.git",
        commit="abc1234",
        config="config/live.yaml",
        generations=10,
        env_names=["OPENROUTER_API_KEY"],
        secret_specs=[],
        artifact_dir=tmp_path / "artifacts",
        startup_script_path=startup,
        fm_provider="openrouter",
        model="moonshotai/kimi-k2.7-code",
        input_price_per_mtok=0.74,
        output_price_per_mtok=3.50,
    )

    write_plan_files(plan, output)

    written = json.loads(output.read_text(encoding="utf-8"))
    assert startup.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")
    assert written["startup_script"] == "[written to startup_script_path]"
    assert written["secrets"]["env_values"] == "hidden"


def test_cloud_vm_plan_rejects_non_ephemeral_short_disk(tmp_path: Path):
    with pytest.raises(CloudVmRunError, match="at least 50GB"):
        build_cloud_vm_plan(
            run_id="loop12-proof",
            provider="gcloud",
            project="dgm-project",
            zone="us-central1-a",
            machine_type="n2-standard-8",
            boot_disk_size_gb=20,
            image_family="debian-12",
            image_project="debian-cloud",
            repo_url="https://github.com/example/dgm.git",
            commit="abc1234",
            config="config/live.yaml",
            generations=10,
            env_names=[],
            secret_specs=[],
            artifact_dir=tmp_path / "artifacts",
            startup_script_path=tmp_path / "startup.sh",
            fm_provider="openrouter",
            model="moonshotai/kimi-k2.7-code",
            input_price_per_mtok=0.74,
            output_price_per_mtok=3.50,
        )
