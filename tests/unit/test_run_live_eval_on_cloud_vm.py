import json
from pathlib import Path

import pytest
import yaml

from scripts.run_live_eval_on_cloud_vm import (
    CloudVmRunError,
    SecretSpec,
    _read_exit_code,
    _remote_stream_script,
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
    assert 'ARCHIVE_DIR="$(python - "${CONFIG}"' in script
    assert "archive.tar.gz" in script
    assert "Path(results_dir).glob(\"dgm_report_*.json\")" in script
    assert "find . -path '*/archive_metadata.json'" not in script
    assert "find . -path '*/dgm_report_*.json'" not in script
    assert "preflight_commands.txt" in script
    assert "required_preflight" in script
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
    assert plan["commands"]["sync_artifacts"][4].endswith("/artifacts/.")
    assert plan["commands"]["teardown"][:4] == [
        "gcloud",
        "compute",
        "instances",
        "delete",
    ]


def test_remote_stream_script_follows_log_until_exit_code():
    script = _remote_stream_script(
        startup_log="/var/tmp/run/artifacts/startup.log",
        exit_code="/var/tmp/run/artifacts/exit_code",
    )

    assert "tail -n +1 -F \"$STARTUP_LOG\"" in script
    assert "while [ ! -f \"$EXIT_CODE\" ]" in script
    assert "cat \"$EXIT_CODE\"" in script
    assert "tail -n 80" not in script


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


def test_read_exit_code_from_synced_artifact_dir(tmp_path: Path):
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "exit_code").write_text("2\n", encoding="utf-8")
    plan = {"artifacts": {"local_dir": str(artifact_dir)}}

    assert _read_exit_code(plan) == 2


def test_loop12_cloud_preflight_builds_sandbox_image_on_fresh_vm():
    project_root = Path(__file__).resolve().parents[2]
    config_path = project_root / "config" / "livecodebench_openrouter_loop12_nonregression.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    preflight = config["live_run"]["required_preflight"]
    sandbox_checks = [
        command for command in preflight if "scripts/verify_sandbox_docker.py" in command
    ]

    assert sandbox_checks == [
        'PATH="$PWD/.venv/bin:$PATH" python scripts/verify_sandbox_docker.py --build-image --require'
    ]


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
