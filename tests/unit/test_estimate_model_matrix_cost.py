from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from scripts.estimate_model_matrix_cost import (
    ModelMatrixPlanError,
    _build_parser,
    _main,
    estimate_model_matrix_cost,
)


def _load_default_plan(project_root: Path) -> dict:
    return yaml.safe_load(
        (project_root / "config" / "live_model_matrix.yaml").read_text(
            encoding="utf-8"
        )
    )


def _write_plan(tmp_path: Path, plan: dict) -> Path:
    config_path = tmp_path / "live_model_matrix.yaml"
    config_path.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    return config_path


def test_model_matrix_estimate_from_default_config():
    project_root = Path(__file__).resolve().parents[2]

    report = estimate_model_matrix_cost(project_root=project_root)

    assert report["config"] == "config/live_model_matrix.yaml"
    assert report["base_live_run_config"] == "config/live_score_movement.yaml"
    assert report["benchmark"] == "humaneval_calibrated"
    assert report["approval_required"] is True
    assert report["dry_run_only"] is True
    assert report["live_calls_performed"] == 0
    assert report["trials_per_model"] == 5
    assert report["model_count"] == 2
    assert report["request_ceiling_per_trial"] == 25
    assert report["total_request_ceiling"] == 250
    assert report["estimated_total_cost_usd"] == pytest.approx(28.1735)
    assert report["max_estimated_cost_usd"] == 30
    assert report["within_budget"] is True

    by_id = {model["id"]: model for model in report["models"]}
    assert by_id["claude-sonnet-4-6"]["provider"] == "anthropic"
    assert by_id["claude-sonnet-4-6"]["estimated_total_cost_usd"] == pytest.approx(22.59)
    assert by_id["kimi-k2.7-code-openrouter"]["provider"] == "openai_compatible"
    assert by_id["kimi-k2.7-code-openrouter"]["base_url"] == "https://openrouter.ai/api/v1"
    assert by_id["kimi-k2.7-code-openrouter"]["estimated_total_cost_usd"] == pytest.approx(5.5835)


def test_model_matrix_rejects_live_enabled_config(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    plan = deepcopy(_load_default_plan(project_root))
    plan["model_matrix"]["dry_run_only"] = False
    config_path = _write_plan(tmp_path, plan)

    with pytest.raises(ModelMatrixPlanError, match="dry_run_only"):
        estimate_model_matrix_cost(config_path, project_root=project_root)


def test_model_matrix_rejects_secret_fields(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    plan = deepcopy(_load_default_plan(project_root))
    plan["model_matrix"]["models"][1]["api_key"] = "placeholder"
    config_path = _write_plan(tmp_path, plan)

    with pytest.raises(ModelMatrixPlanError, match="api_key_env"):
        estimate_model_matrix_cost(config_path, project_root=project_root)


def test_model_matrix_rejects_missing_openai_base_url(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    plan = deepcopy(_load_default_plan(project_root))
    del plan["model_matrix"]["models"][1]["base_url"]
    config_path = _write_plan(tmp_path, plan)

    with pytest.raises(ModelMatrixPlanError, match="base_url"):
        estimate_model_matrix_cost(config_path, project_root=project_root)


def test_model_matrix_rejects_over_budget(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    plan = deepcopy(_load_default_plan(project_root))
    plan["model_matrix"]["max_estimated_cost_usd"] = 1
    config_path = _write_plan(tmp_path, plan)

    with pytest.raises(ModelMatrixPlanError, match="budget"):
        estimate_model_matrix_cost(config_path, project_root=project_root)


def test_model_matrix_requires_eval_matrix_preflight(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    plan = deepcopy(_load_default_plan(project_root))
    plan["model_matrix"]["required_preflight"] = [
        command
        for command in plan["model_matrix"]["required_preflight"]
        if "scripts/plan_eval_matrix.py" not in command
    ]
    config_path = _write_plan(tmp_path, plan)

    with pytest.raises(ModelMatrixPlanError, match="eval matrix planner"):
        estimate_model_matrix_cost(config_path, project_root=project_root)


def test_model_matrix_cli_json(capsys):
    args = _build_parser().parse_args(["--json"])

    exit_code = _main(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"status": "ok"' in captured.out
    assert '"name": "live_model_matrix_plan"' in captured.out
    assert '"live_calls_performed": 0' in captured.out


def test_model_matrix_cli_text(capsys):
    args = _build_parser().parse_args([])

    exit_code = _main(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "live_model_matrix_plan" in captured.out
    assert "requests<=250" in captured.out
    assert "dry_run_only=true" in captured.out
