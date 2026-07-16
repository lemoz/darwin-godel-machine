import asyncio
import json
import threading
import time
from pathlib import Path

import pytest
import yaml

from scripts.run_live_eval_on_cloud_vm import SecretSpec
from scripts.run_parallel_cloud_dgm import (
    ParallelCloudRunError,
    aggregate_parallel_artifacts,
    build_parallel_cloud_plan,
    execute_parallel_cloud_plan,
    get_openrouter_key_usage,
    recover_missing_gcs_artifacts,
)


def _config(path: Path, generations: int = 3) -> Path:
    path.write_text(
        yaml.safe_dump({
            "fm_providers": {
                "primary": "openai_compatible",
                "openai_compatible": {
                    "model": "google/gemma-3-27b-it",
                    "max_tokens": 1024,
                    "timeout_retries": 0,
                },
            },
            "agents": {"max_steps": 2},
            "self_modification": {"max_steps": 3},
            "benchmarks": {"enabled": ["one", "two"]},
            "live_run": {
                "recommended_generations": generations,
                "parallel": {"seed_changed_count": 4, "seed_noop_count": 2},
            },
        }),
        encoding="utf-8",
    )
    return path


def _plan(tmp_path: Path, *, workers: int = 2, max_budget: float = 100) -> dict:
    config = _config(tmp_path / "config.yaml")
    return build_parallel_cloud_plan(
        base_run_id="gemma-test",
        workers=workers,
        max_concurrency=workers,
        project="test-project",
        zone="us-central1-a",
        machine_type="n2-standard-8",
        boot_disk_size_gb=100,
        repo_url="https://github.com/example/repo.git",
        commit="abc123",
        config_path=config,
        config_label="config/test.yaml",
        generations=3,
        secret_specs=[SecretSpec("OPENROUTER_API_KEY", "openrouter-api-key")],
        artifact_root=tmp_path / "artifacts",
        plan_dir=tmp_path / "plans",
        gcs_root="gs://bucket/run",
        model="google/gemma-3-27b-it",
        input_price_per_mtok=0.08,
        output_price_per_mtok=0.16,
        assumed_input_tokens_per_call=12000,
        max_budget_usd=max_budget,
    )


def test_parallel_plan_has_isolated_workers_and_shared_budget(tmp_path):
    plan = _plan(tmp_path)

    assert plan["workers"] == 2
    assert plan["total_generation_attempt_ceiling"] == 6
    assert plan["seed_mutation_counts"] == {"changed": 4, "noop": 2}
    assert plan["budget"]["parallel_estimated_cost_usd"] == pytest.approx(
        plan["budget"]["per_worker_estimated_cost_usd"] * 2
    )
    run_ids = [worker["run_id"] for worker in plan["worker_plans"]]
    assert run_ids == ["gemma-test-w01", "gemma-test-w02"]
    assert len({worker["artifact_dir"] for worker in plan["worker_plans"]}) == 2
    assert all(worker["gcs_uri"].endswith(worker["run_id"]) for worker in plan["worker_plans"])
    assert all(
        worker["cloud_plan"]["secrets"]["env_values"] == "hidden"
        for worker in plan["worker_plans"]
    )


def test_parallel_plan_rejects_shared_estimate_over_budget(tmp_path):
    with pytest.raises(ParallelCloudRunError, match="exceeds shared budget"):
        _plan(tmp_path, workers=8, max_budget=0.01)


def test_openrouter_key_usage_is_key_scoped(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"data":{"usage":12.5,"usage_daily":1.25}}'

    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setattr(
        "scripts.run_parallel_cloud_dgm.urllib.request.urlopen",
        fake_urlopen,
    )

    assert get_openrouter_key_usage("secret") == 12.5
    assert requests[0][0].full_url == "https://openrouter.ai/api/v1/key"
    assert requests[0][0].headers["Authorization"] == "Bearer secret"


def test_parallel_aggregate_subtracts_seed_counts(tmp_path):
    plan = _plan(tmp_path)
    for index, worker in enumerate(plan["worker_plans"], start=1):
        artifact_dir = Path(worker["artifact_dir"])
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "scorecard.json").write_text(json.dumps({
            "top_score": 0.5 + index / 10,
            "mutation_summary": {
                "changed_count": 4 + index,
                "noop_count": 2 + index,
            },
        }), encoding="utf-8")
        (artifact_dir / "telemetry.json").write_text(json.dumps({
            "tokens": {
                "estimated_cost_usd": index / 10,
                "total_tokens": index * 100,
            },
        }), encoding="utf-8")
        (artifact_dir / "exit_code").write_text("0\n", encoding="utf-8")

    aggregate = aggregate_parallel_artifacts(plan)

    assert aggregate["workers_with_scorecards"] == 2
    assert aggregate["top_score"] == pytest.approx(0.7)
    assert aggregate["fresh_changed_count"] == 3
    assert aggregate["fresh_noop_count"] == 3
    assert aggregate["total_model_cost_usd_from_telemetry"] == pytest.approx(0.3)
    assert aggregate["total_tokens"] == 300


def test_parallel_artifact_recovery_uses_single_process_gcloud(tmp_path):
    plan = _plan(tmp_path)
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        run_id = command[-2].rstrip("/").split("/")[-1]
        artifact_dir = tmp_path / "artifacts" / run_id
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "scorecard.json").write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")

    from types import SimpleNamespace

    recovered = recover_missing_gcs_artifacts(plan, runner=fake_runner)

    assert recovered == ["gemma-test-w01", "gemma-test-w02"]
    assert len(calls) == 2
    assert all(
        kwargs["env"]["CLOUDSDK_STORAGE_PROCESS_COUNT"] == "1"
        for _, kwargs in calls
    )


async def test_parallel_executor_honors_concurrency(tmp_path):
    plan = _plan(tmp_path, workers=3)
    plan["max_concurrency"] = 2
    lock = threading.Lock()
    active = 0
    max_active = 0

    def fake_executor(cloud_plan):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1

    aggregate = await execute_parallel_cloud_plan(
        plan,
        budget_api_key="test-key",
        poll_seconds=0.01,
        executor=fake_executor,
        usage_reader=lambda _key: 10.0,
    )

    assert max_active == 2
    assert aggregate["status"] == "complete"
    assert all(item["status"] == "complete" for item in aggregate["executions"])
