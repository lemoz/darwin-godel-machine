import json
from pathlib import Path

import pytest

from sandbox.sandbox_manager import SandboxResult
from scripts.run_model_matrix import (
    ModelMatrixRunError,
    _build_parser,
    _main_async,
    build_model_matrix_plan,
    execute_model_matrix,
    write_model_matrix_plan,
)


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return
    for child in sorted(path.glob("**/*"), key=lambda item: len(item.parts), reverse=True):
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    path.rmdir()


def test_build_model_matrix_plan_expands_default_config():
    project_root = Path(__file__).resolve().parents[2]

    plan = build_model_matrix_plan(project_root=project_root)

    assert plan["name"] == "live_model_matrix_execution_plan"
    assert plan["dry_run_default"] is True
    assert plan["planner_live_calls_performed"] == 0
    assert plan["completed_trials"] == 0
    assert plan["trial_count"] == 10
    assert plan["model_count"] == 2
    assert plan["trials_per_model"] == 5
    assert plan["total_request_ceiling"] == 250
    assert plan["estimated_total_cost_usd"] == pytest.approx(28.1735)

    first = plan["trials"][0]
    assert first["trial_id"] == "claude-sonnet-4-6-trial-01"
    assert first["api_key_env"] == "ANTHROPIC_API_KEY"
    assert first["config_path"] == (
        ".dgm-live-runs/model-matrix/configs/claude-sonnet-4-6-trial-01.yaml"
    )
    assert first["trial_config"]["fm_providers"]["primary"] == "anthropic"
    assert first["trial_config"]["fm_providers"]["anthropic"]["api_key"] == (
        "${ANTHROPIC_API_KEY}"
    )

    kimi = next(trial for trial in plan["trials"] if trial["provider"] == "openai_compatible")
    assert kimi["api_key_env"] == "OPENROUTER_API_KEY"
    provider_config = kimi["trial_config"]["fm_providers"]["openai_compatible"]
    assert provider_config["base_url"] == "https://openrouter.ai/api/v1"
    assert provider_config["api_key"] == "${OPENROUTER_API_KEY}"


def test_write_model_matrix_plan_materializes_non_secret_manifest(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    run_dir = f"tmp/test-model-matrix-{tmp_path.name}"
    audit_dir = f"tmp/test-model-matrix-audit-{tmp_path.name}"
    plan = build_model_matrix_plan(
        project_root=project_root,
        run_dir=run_dir,
        audit_dir=audit_dir,
    )

    manifest = write_model_matrix_plan(plan, project_root=project_root)

    manifest_path = project_root / manifest["manifest_path"]
    config_path = project_root / manifest["trials"][0]["config_path"]
    try:
        assert manifest_path.exists()
        assert config_path.exists()
        manifest_text = manifest_path.read_text(encoding="utf-8")
        config_text = config_path.read_text(encoding="utf-8")
        assert "trial_config" not in manifest_text
        assert "sk-" not in manifest_text
        assert "${ANTHROPIC_API_KEY}" in config_text
    finally:
        _remove_tree(project_root / run_dir)
        _remove_tree(project_root / audit_dir)


@pytest.mark.asyncio
async def test_execute_model_matrix_runs_trials_with_fake_runner(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    run_dir = f"tmp/test-model-matrix-exec-{tmp_path.name}"
    audit_dir = f"tmp/test-model-matrix-exec-audit-{tmp_path.name}"
    plan = build_model_matrix_plan(
        project_root=project_root,
        run_dir=run_dir,
        audit_dir=audit_dir,
    )
    plan["trials"] = plan["trials"][:2]
    plan["trial_count"] = 2
    calls = []

    async def fake_runner(**kwargs):
        calls.append(kwargs)
        return SandboxResult(success=True, output="ok\n", exit_code=0)

    def fake_scorecard(_metadata_path):
        return {
            "top_score": 0.88,
            "best_average_delta": 0.0,
            "has_improvement": False,
        }

    manifest = await execute_model_matrix(
        plan,
        project_root=project_root,
        allow_network=True,
        runner=fake_runner,
        scorecard_builder=fake_scorecard,
    )

    try:
        assert manifest["status"] == "executed"
        assert manifest["planner_live_calls_performed"] == 0
        assert manifest["completed_trials"] == 2
        assert len(manifest["executions"]) == 2
        assert len(calls) == 2
        assert calls[0]["allow_network"] is True
        assert calls[0]["env_names"] == ["ANTHROPIC_API_KEY"]
        assert calls[0]["network_mode"] == "bridge"
        audit_path = project_root / manifest["executions"][0]["audit_output"]
        assert json.loads(audit_path.read_text(encoding="utf-8"))["env_values"] == "hidden"
        scorecard_path = project_root / manifest["executions"][0]["scorecard_output"]
        assert json.loads(scorecard_path.read_text(encoding="utf-8"))["top_score"] == 0.88
    finally:
        _remove_tree(project_root / run_dir)
        _remove_tree(project_root / audit_dir)


@pytest.mark.asyncio
async def test_execute_model_matrix_requires_network_opt_in():
    project_root = Path(__file__).resolve().parents[2]
    plan = build_model_matrix_plan(project_root=project_root)
    plan["trials"] = plan["trials"][:1]

    with pytest.raises(ModelMatrixRunError, match="allow-network"):
        await execute_model_matrix(plan, project_root=project_root, allow_network=False)


@pytest.mark.asyncio
async def test_execute_model_matrix_rejects_discard_changes():
    project_root = Path(__file__).resolve().parents[2]
    plan = build_model_matrix_plan(project_root=project_root)
    plan["trials"] = plan["trials"][:1]

    with pytest.raises(ModelMatrixRunError, match="sync-back"):
        await execute_model_matrix(
            plan,
            project_root=project_root,
            allow_network=True,
            sync_back=False,
        )


@pytest.mark.asyncio
async def test_run_model_matrix_cli_dry_run_json(capsys):
    args = _build_parser().parse_args(["--dry-run", "--json"])

    exit_code = await _main_async(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"name": "live_model_matrix_execution_plan"' in captured.out
    assert '"planner_live_calls_performed": 0' in captured.out
    assert '"completed_trials": 0' in captured.out
    assert '"trial_count": 10' in captured.out


@pytest.mark.asyncio
async def test_run_model_matrix_cli_rejects_execute_dry_run(capsys):
    args = _build_parser().parse_args(["--execute", "--dry-run", "--json"])

    exit_code = await _main_async(args)
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "cannot be combined" in captured.out
