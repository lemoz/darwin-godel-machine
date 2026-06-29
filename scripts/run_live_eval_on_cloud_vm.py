#!/usr/bin/env python3
"""Plan or launch an ephemeral cloud VM for live DGM evaluation runs."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CloudVmRunError(RuntimeError):
    """Raised when a cloud VM run cannot be planned or launched safely."""


RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,48}$")


@dataclass(frozen=True)
class SecretSpec:
    """A non-secret mapping from an env var to a cloud Secret Manager name."""

    env_name: str
    secret_name: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CloudVmRunError(message)


def _parse_secret_spec(value: str) -> SecretSpec:
    if "=" not in value:
        raise CloudVmRunError("--secret must use ENV_NAME=SECRET_NAME")
    env_name, secret_name = value.split("=", 1)
    env_name = env_name.strip()
    secret_name = secret_name.strip()
    _require(env_name.isidentifier() and env_name.isupper(), f"Invalid secret env name: {env_name}")
    _require(bool(secret_name), f"Missing secret name for {env_name}")
    return SecretSpec(env_name=env_name, secret_name=secret_name)


def _shell_array(values: list[str]) -> str:
    if not values:
        return ""
    return " ".join(shlex.quote(value) for value in values)


def _secret_array(secret_specs: list[SecretSpec]) -> str:
    return _shell_array([f"{item.env_name}={item.secret_name}" for item in secret_specs])


def _metadata_arg(key: str, value: str) -> str:
    return f"{key}={value}"


def _label_value(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]", "-", value.lower())[:63].strip("-")
    return normalized or "unknown"


def _remote_stream_script(*, startup_log: str, exit_code: str) -> str:
    """Build a finite remote log-follow script for the VM startup artifacts."""
    return "\n".join(
        [
            "set -e",
            f"STARTUP_LOG={shlex.quote(startup_log)}",
            f"EXIT_CODE={shlex.quote(exit_code)}",
            "while [ ! -f \"$STARTUP_LOG\" ] && [ ! -f \"$EXIT_CODE\" ]; do",
            "  journalctl -u google-startup-scripts.service -n 80 --no-pager || true",
            "  sleep 10",
            "done",
            "if [ -f \"$STARTUP_LOG\" ]; then",
            "  tail -n +1 -F \"$STARTUP_LOG\" &",
            "  TAIL_PID=$!",
            "fi",
            "while [ ! -f \"$EXIT_CODE\" ]; do",
            "  sleep 10",
            "done",
            "if [ -n \"${TAIL_PID:-}\" ]; then",
            "  kill \"$TAIL_PID\" >/dev/null 2>&1 || true",
            "fi",
            "cat \"$EXIT_CODE\"",
        ]
    )


def validate_run_id(run_id: str) -> None:
    _require(
        RUN_ID_RE.match(run_id) is not None,
        "run_id must be 3-49 chars of lowercase letters, digits, and hyphens",
    )


def build_startup_script(
    *,
    repo_url: str,
    commit: str,
    config: str,
    generations: int,
    run_id: str,
    env_names: list[str],
    secret_specs: list[SecretSpec],
    provider: str,
    model: str,
    input_price_per_mtok: float,
    output_price_per_mtok: float,
    gcs_artifact_uri: str | None = None,
) -> str:
    """Build the startup script that runs on the ephemeral VM."""
    validate_run_id(run_id)
    required_env = sorted(set(env_names + [secret.env_name for secret in secret_specs]))
    secret_specs_text = _secret_array(secret_specs)
    required_env_text = _shell_array(required_env)

    return f"""#!/usr/bin/env bash
set -euo pipefail

RUN_ID={shlex.quote(run_id)}
REPO_URL={shlex.quote(repo_url)}
COMMIT={shlex.quote(commit)}
CONFIG={shlex.quote(config)}
GENERATIONS={generations}
PROVIDER={shlex.quote(provider)}
MODEL={shlex.quote(model)}
INPUT_PRICE_PER_MTOK={input_price_per_mtok}
OUTPUT_PRICE_PER_MTOK={output_price_per_mtok}
GCS_ARTIFACT_URI={shlex.quote(gcs_artifact_uri or "")}
SECRET_SPECS=({secret_specs_text})
REQUIRED_ENV=({required_env_text})
REMOTE_ROOT=/var/tmp/dgm-live-runs
RUN_DIR="${{REMOTE_ROOT}}/${{RUN_ID}}"
ARTIFACT_DIR="${{RUN_DIR}}/artifacts"
REPO_DIR="${{RUN_DIR}}/repo"
CONTROLLER_LOG="${{ARTIFACT_DIR}}/controller.log"
SCORECARD_PATH="${{ARTIFACT_DIR}}/scorecard.json"
TELEMETRY_PATH="${{ARTIFACT_DIR}}/telemetry.json"
EXIT_CODE_PATH="${{ARTIFACT_DIR}}/exit_code"

mkdir -p "${{ARTIFACT_DIR}}"
exec > >(tee -a "${{ARTIFACT_DIR}}/startup.log") 2>&1

sync_artifacts() {{
  if [ -n "${{GCS_ARTIFACT_URI}}" ] && command -v gcloud >/dev/null 2>&1; then
    gcloud storage rsync --recursive "${{ARTIFACT_DIR}}" "${{GCS_ARTIFACT_URI}}" || true
  fi
}}

finish() {{
  status=$?
  echo "${{status}}" > "${{EXIT_CODE_PATH}}"
  sync_artifacts || true
  if [ -n "${{SYNC_PID:-}}" ]; then
    kill "${{SYNC_PID}}" >/dev/null 2>&1 || true
  fi
}}
trap finish EXIT

echo "[dgm-vm] run_id=${{RUN_ID}} commit=${{COMMIT}} config=${{CONFIG}} generations=${{GENERATIONS}}"
apt-get update
apt-get install -y ca-certificates curl docker.io git gnupg python3 python3-pip python3-venv
if ! command -v gcloud >/dev/null 2>&1; then
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | gpg --dearmor -o /etc/apt/keyrings/cloud.google.gpg
  echo "deb [signed-by=/etc/apt/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    > /etc/apt/sources.list.d/google-cloud-sdk.list
  apt-get update
  apt-get install -y google-cloud-cli
fi
systemctl enable --now docker || true

git clone "${{REPO_URL}}" "${{REPO_DIR}}"
cd "${{REPO_DIR}}"
git fetch --all --tags
git checkout "${{COMMIT}}"

python3 -m venv .venv
PATH="${{PWD}}/.venv/bin:${{PATH}}"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

for mapping in "${{SECRET_SPECS[@]}}"; do
  env_name="${{mapping%%=*}}"
  secret_name="${{mapping#*=}}"
  export "${{env_name}}=$(gcloud secrets versions access latest --secret="${{secret_name}}")"
done

if [ -f /etc/dgm-live.env ]; then
  set -a
  # shellcheck disable=SC1091
  source /etc/dgm-live.env
  set +a
fi

for env_name in "${{REQUIRED_ENV[@]}}"; do
  if [ -z "${{!env_name:-}}" ]; then
    echo "[dgm-vm] missing required environment variable: ${{env_name}}" >&2
    exit 2
  fi
done

if [ -n "${{GCS_ARTIFACT_URI}}" ]; then
  while true; do
    sleep 60
    sync_artifacts
  done &
  SYNC_PID=$!
fi

PREFLIGHT_FILE="${{ARTIFACT_DIR}}/preflight_commands.txt"
python - "${{CONFIG}}" > "${{PREFLIGHT_FILE}}" <<'PY'
import sys
import yaml
from pathlib import Path

config = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8")) or {{}}
commands = config.get("live_run", {{}}).get("required_preflight", [])
if not isinstance(commands, list):
    raise SystemExit("live_run.required_preflight must be a list when present")
for command in commands:
    if not isinstance(command, str):
        raise SystemExit("live_run.required_preflight entries must be strings")
    print(command)
PY

if [ -s "${{PREFLIGHT_FILE}}" ]; then
  while IFS= read -r preflight_command; do
    echo "[dgm-vm] preflight: ${{preflight_command}}"
    bash -lc "${{preflight_command}}"
    sync_artifacts
  done < "${{PREFLIGHT_FILE}}"
fi

set +e
python run_dgm.py --config "${{CONFIG}}" --generations "${{GENERATIONS}}" 2>&1 | tee "${{CONTROLLER_LOG}}"
RUN_STATUS=${{PIPESTATUS[0]}}
set -e

ARCHIVE_METADATA="$(find . -path '*/archive_metadata.json' -type f | sort | tail -n 1 || true)"
if [ -n "${{ARCHIVE_METADATA}}" ]; then
  python scripts/summarize_archive_scores.py \
    --archive-metadata "${{ARCHIVE_METADATA}}" \
    --output "${{SCORECARD_PATH}}" || true
fi

DGM_REPORT="$(find . -path '*/dgm_report_*.json' -type f | sort | tail -n 1 || true)"
TELEMETRY_ARGS=(--controller-log "${{CONTROLLER_LOG}}" --provider "${{PROVIDER}}" --model "${{MODEL}}" --input-price-per-mtok "${{INPUT_PRICE_PER_MTOK}}" --output-price-per-mtok "${{OUTPUT_PRICE_PER_MTOK}}" --output "${{TELEMETRY_PATH}}")
if [ -f "${{SCORECARD_PATH}}" ]; then
  TELEMETRY_ARGS+=(--scorecard "${{SCORECARD_PATH}}")
fi
if [ -n "${{DGM_REPORT}}" ]; then
  TELEMETRY_ARGS+=(--dgm-report "${{DGM_REPORT}}")
fi
if [ -n "${{ARCHIVE_METADATA}}" ]; then
  TELEMETRY_ARGS+=(--archive-metadata "${{ARCHIVE_METADATA}}")
fi
python scripts/summarize_live_run_telemetry.py "${{TELEMETRY_ARGS[@]}}" || true

find "${{ARTIFACT_DIR}}" -maxdepth 1 -type f -print | sort
exit "${{RUN_STATUS}}"
"""


def build_cloud_vm_plan(
    *,
    run_id: str,
    provider: str,
    project: str,
    zone: str,
    machine_type: str,
    boot_disk_size_gb: int,
    image_family: str,
    image_project: str,
    repo_url: str,
    commit: str,
    config: str,
    generations: int,
    env_names: list[str],
    secret_specs: list[SecretSpec],
    artifact_dir: Path,
    startup_script_path: Path,
    fm_provider: str,
    model: str,
    input_price_per_mtok: float,
    output_price_per_mtok: float,
    gcs_artifact_uri: str | None = None,
) -> dict[str, Any]:
    """Build a non-secret, executable cloud VM run plan."""
    _require(provider == "gcloud", "Only provider=gcloud is currently supported")
    validate_run_id(run_id)
    _require(generations > 0, "generations must be positive")
    _require(boot_disk_size_gb >= 50, "boot disk should be at least 50GB for live runs")
    _require(bool(project), "project is required")
    _require(bool(zone), "zone is required")
    _require(bool(repo_url), "repo_url is required")
    _require(bool(commit), "commit is required")
    _require(bool(config), "config is required")

    vm_name = f"dgm-{run_id}"
    remote_artifact_dir = f"/var/tmp/dgm-live-runs/{run_id}/artifacts"
    all_env_names = sorted(set(env_names + [secret.env_name for secret in secret_specs]))
    startup_script = build_startup_script(
        repo_url=repo_url,
        commit=commit,
        config=config,
        generations=generations,
        run_id=run_id,
        env_names=env_names,
        secret_specs=secret_specs,
        provider=fm_provider,
        model=model,
        input_price_per_mtok=input_price_per_mtok,
        output_price_per_mtok=output_price_per_mtok,
        gcs_artifact_uri=gcs_artifact_uri,
    )

    metadata = [
        _metadata_arg("dgm-run-id", run_id),
        _metadata_arg("dgm-commit", commit),
        _metadata_arg("dgm-config", config),
    ]
    labels = [
        f"dgm-run-id={_label_value(run_id)}",
        f"dgm-commit={_label_value(commit)}",
        "purpose=live-eval",
    ]
    create_command = [
        "gcloud",
        "compute",
        "instances",
        "create",
        vm_name,
        "--project",
        project,
        "--zone",
        zone,
        "--machine-type",
        machine_type,
        "--boot-disk-size",
        f"{boot_disk_size_gb}GB",
        "--image-family",
        image_family,
        "--image-project",
        image_project,
        "--scopes",
        "cloud-platform",
        "--labels",
        ",".join(labels),
        "--metadata",
        ",".join(metadata),
        "--metadata-from-file",
        f"startup-script={startup_script_path}",
    ]
    startup_log = f"{remote_artifact_dir}/startup.log"
    exit_code = f"{remote_artifact_dir}/exit_code"
    remote_stream_script = _remote_stream_script(
        startup_log=startup_log,
        exit_code=exit_code,
    )
    stream_command = [
        "gcloud",
        "compute",
        "ssh",
        vm_name,
        "--project",
        project,
        "--zone",
        zone,
        "--command",
        "sudo bash -lc " + shlex.quote(remote_stream_script),
    ]
    sync_command = [
        "gcloud",
        "compute",
        "scp",
        "--recurse",
        f"{vm_name}:{remote_artifact_dir}/.",
        str(artifact_dir),
        "--project",
        project,
        "--zone",
        zone,
    ]
    delete_command = [
        "gcloud",
        "compute",
        "instances",
        "delete",
        vm_name,
        "--project",
        project,
        "--zone",
        zone,
        "--quiet",
    ]

    return {
        "name": "dgm_live_eval_cloud_vm_plan",
        "schema_version": 1,
        "status": "planned",
        "provider": provider,
        "vm": {
            "name": vm_name,
            "project": project,
            "zone": zone,
            "machine_type": machine_type,
            "boot_disk_size_gb": boot_disk_size_gb,
            "image_family": image_family,
            "image_project": image_project,
            "ephemeral": True,
        },
        "source": {
            "repo_url": repo_url,
            "commit": commit,
            "config": config,
            "generations": generations,
            "fm_provider": fm_provider,
            "model": model,
        },
        "secrets": {
            "env_names": all_env_names,
            "secret_manager_env_names": [item.env_name for item in secret_specs],
            "secret_manager_secret_names": [item.secret_name for item in secret_specs],
            "env_values": "hidden",
        },
        "artifacts": {
            "local_dir": str(artifact_dir),
            "remote_dir": remote_artifact_dir,
            "gcs_uri": gcs_artifact_uri,
            "startup_log": startup_log,
            "controller_log": f"{remote_artifact_dir}/controller.log",
            "scorecard": f"{remote_artifact_dir}/scorecard.json",
            "telemetry": f"{remote_artifact_dir}/telemetry.json",
            "exit_code": exit_code,
        },
        "startup_script_path": str(startup_script_path),
        "startup_script": startup_script,
        "commands": {
            "create": create_command,
            "stream_logs": stream_command,
            "sync_artifacts": sync_command,
            "teardown": delete_command,
        },
        "run_order": [
            "write_startup_script",
            "create",
            "stream_logs",
            "sync_artifacts",
            "teardown",
        ],
    }


def write_plan_files(plan: dict[str, Any], output_path: Path) -> None:
    """Write startup script plus redacted plan JSON."""
    startup_script_path = Path(plan["startup_script_path"])
    startup_script_path.parent.mkdir(parents=True, exist_ok=True)
    startup_script_path.write_text(plan["startup_script"], encoding="utf-8")
    startup_script_path.chmod(0o700)

    serializable = dict(plan)
    serializable["startup_script"] = "[written to startup_script_path]"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(serializable, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _run_with_retry(command: list[str], *, attempts: int = 20, delay_seconds: int = 15) -> None:
    """Run a command that may fail while the VM is still accepting SSH setup."""
    last_result: subprocess.CompletedProcess[str] | None = None
    for attempt in range(1, attempts + 1):
        last_result = subprocess.run(command, check=False)
        if last_result.returncode == 0:
            return
        if attempt < attempts:
            time.sleep(delay_seconds)
    raise subprocess.CalledProcessError(
        last_result.returncode if last_result else 1,
        command,
    )


def _read_exit_code(plan: dict[str, Any]) -> int | None:
    exit_code_path = Path(plan["artifacts"]["local_dir"]) / "exit_code"
    if not exit_code_path.is_file():
        return None
    try:
        return int(exit_code_path.read_text(encoding="utf-8").strip())
    except ValueError as exc:
        raise CloudVmRunError(f"Invalid VM exit-code artifact: {exit_code_path}") from exc


def execute_plan(plan: dict[str, Any]) -> None:
    """Launch the VM and always attempt artifact sync and teardown."""
    commands = plan["commands"]
    stream_error: subprocess.CalledProcessError | None = None
    try:
        subprocess.run(commands["create"], check=True)
        _run_with_retry(commands["stream_logs"])
    except subprocess.CalledProcessError as exc:
        stream_error = exc
    finally:
        subprocess.run(commands["sync_artifacts"], check=False)
        subprocess.run(commands["teardown"], check=False)
    if stream_error is not None:
        raise stream_error
    exit_code = _read_exit_code(plan)
    if exit_code not in (None, 0):
        raise CloudVmRunError(f"Cloud VM run exited with status {exit_code}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="gcloud")
    parser.add_argument("--project", required=True)
    parser.add_argument("--zone", default="us-central1-a")
    parser.add_argument("--machine-type", default="n2-standard-8")
    parser.add_argument("--boot-disk-size-gb", type=int, default=100)
    parser.add_argument("--image-family", default="debian-12")
    parser.add_argument("--image-project", default="debian-cloud")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repo-url", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--generations", type=int, required=True)
    parser.add_argument("--env", action="append", default=[], help="Required env var name. Repeat as needed.")
    parser.add_argument(
        "--secret",
        action="append",
        default=[],
        help="Secret Manager mapping ENV_NAME=SECRET_NAME. Repeat as needed.",
    )
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--startup-script-path", required=True)
    parser.add_argument("--output", required=True, help="Path to write the non-secret plan JSON.")
    parser.add_argument("--fm-provider", default="openrouter")
    parser.add_argument("--model", default="")
    parser.add_argument("--gcs-artifact-uri", help="Optional gs:// URI for continuous artifact rsync.")
    parser.add_argument("--input-price-per-mtok", type=float, default=0.0)
    parser.add_argument("--output-price-per-mtok", type=float, default=0.0)
    parser.add_argument("--execute", action="store_true", help="Create the VM after writing the plan.")
    return parser


def _main(args: argparse.Namespace) -> int:
    try:
        secret_specs = [_parse_secret_spec(value) for value in args.secret]
        plan = build_cloud_vm_plan(
            run_id=args.run_id,
            provider=args.provider,
            project=args.project,
            zone=args.zone,
            machine_type=args.machine_type,
            boot_disk_size_gb=args.boot_disk_size_gb,
            image_family=args.image_family,
            image_project=args.image_project,
            repo_url=args.repo_url,
            commit=args.commit,
            config=args.config,
            generations=args.generations,
            env_names=args.env,
            secret_specs=secret_specs,
            artifact_dir=Path(args.artifact_dir),
            startup_script_path=Path(args.startup_script_path),
            fm_provider=args.fm_provider,
            model=args.model,
            input_price_per_mtok=args.input_price_per_mtok,
            output_price_per_mtok=args.output_price_per_mtok,
            gcs_artifact_uri=args.gcs_artifact_uri,
        )
        write_plan_files(plan, Path(args.output))
        if args.execute:
            execute_plan(plan)
    except (CloudVmRunError, OSError, subprocess.CalledProcessError) as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 1

    print(
        "cloud vm plan: "
        f"provider={plan['provider']} vm={plan['vm']['name']} "
        f"commit={plan['source']['commit']} generations={plan['source']['generations']} "
        f"artifacts={plan['artifacts']['local_dir']}"
    )
    return 0


def main() -> int:
    return _main(_build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
