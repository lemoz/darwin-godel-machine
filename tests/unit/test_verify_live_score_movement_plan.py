from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from scripts.verify_live_score_movement_plan import (
    LiveRunPlanError,
    _build_parser,
    _main,
    verify_live_score_movement_plan,
)


def _load_default_plan(project_root: Path) -> dict:
    return yaml.safe_load(
        (project_root / "config" / "live_score_movement.yaml").read_text(
            encoding="utf-8"
        )
    )


def _write_plan(tmp_path: Path, plan: dict) -> Path:
    config_path = tmp_path / "live_score_movement.yaml"
    config_path.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    return config_path


def test_live_score_movement_plan_verifies_default_config():
    project_root = Path(__file__).resolve().parents[2]

    report = verify_live_score_movement_plan(project_root=project_root)

    assert report["config"] == "config/live_score_movement.yaml"
    assert report["benchmark"] == "humaneval_style"
    assert report["recommended_generations"] == 2
    assert report["max_agent_steps"] == 5
    assert report["max_output_tokens_per_call"] == 2048
    assert report["archive_path"] == ".dgm-live-runs/live-score-movement/archive"
    assert report["approval_required"] is True
    assert report["requires_current_pricing_check"] is True
    assert report["requires_full_process_sandbox"] is True
    assert report["requires_scorecard_improvement"] is True


def test_live_score_movement_plan_rejects_unapproved_run(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    plan = deepcopy(_load_default_plan(project_root))
    plan["live_run"]["approval_required"] = False
    config_path = _write_plan(tmp_path, plan)

    with pytest.raises(LiveRunPlanError, match="explicit approval"):
        verify_live_score_movement_plan(config_path, project_root=project_root)


def test_live_score_movement_plan_rejects_extra_benchmarks(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    plan = deepcopy(_load_default_plan(project_root))
    plan["benchmarks"]["enabled"] = ["humaneval_style", "list_processing"]
    config_path = _write_plan(tmp_path, plan)

    with pytest.raises(LiveRunPlanError, match="humaneval_style only"):
        verify_live_score_movement_plan(config_path, project_root=project_root)


def test_live_score_movement_plan_cli_json(capsys):
    args = _build_parser().parse_args(["--json"])

    exit_code = _main(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"status": "ok"' in captured.out
    assert '"benchmark": "humaneval_style"' in captured.out
