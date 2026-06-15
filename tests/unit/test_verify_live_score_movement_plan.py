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
    assert report["benchmark"] == "humaneval_calibrated"
    assert report["recommended_generations"] == 2
    assert report["max_agent_steps"] == 5
    assert report["max_output_tokens_per_call"] == 2048
    assert report["archive_path"] == ".dgm-live-runs/live-score-movement/archive"
    assert report["approval_required"] is True
    assert report["requires_current_pricing_check"] is True
    assert report["requires_full_process_sandbox"] is True
    assert report["requires_scorecard_improvement"] is True
    assert report["requires_headroom_gate"] is True
    assert report["headroom_baseline_score"] == pytest.approx(0.6)
    assert report["headroom_candidate_score"] == 1.0
    assert report["headroom_delta"] == pytest.approx(0.4)
    assert report["headroom_public_examples"] == 10
    assert report["headroom_evaluation_cases"] == 50
    assert report["headroom_score_report"] == "docs/demo/humaneval_calibrated_score_movement.json"
    assert report["pricing_checked_at"] == "2026-06-15"
    assert report["input_price_per_mtok"] == 3
    assert report["output_price_per_mtok"] == 15
    assert report["assumed_input_tokens_per_call"] == 50_000
    assert report["request_ceiling"] == 25
    assert report["input_token_ceiling"] == 1_250_000
    assert report["output_token_ceiling"] == 51_200
    assert report["estimated_total_cost_usd"] == pytest.approx(4.518)
    assert report["max_estimated_cost_usd"] == 5


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
    plan["benchmarks"]["enabled"] = ["humaneval_calibrated", "list_processing"]
    config_path = _write_plan(tmp_path, plan)

    with pytest.raises(LiveRunPlanError, match="humaneval_calibrated only"):
        verify_live_score_movement_plan(config_path, project_root=project_root)


def test_live_score_movement_plan_rejects_missing_headroom(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    plan = deepcopy(_load_default_plan(project_root))
    plan["live_run"]["headroom_gate"]["max_baseline_score"] = 0.1
    config_path = _write_plan(tmp_path, plan)

    with pytest.raises(LiveRunPlanError, match="baseline score is too high"):
        verify_live_score_movement_plan(config_path, project_root=project_root)


def test_live_score_movement_plan_rejects_overly_weak_baseline(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    plan = deepcopy(_load_default_plan(project_root))
    plan["live_run"]["headroom_gate"]["min_baseline_score"] = 0.9
    config_path = _write_plan(tmp_path, plan)

    with pytest.raises(LiveRunPlanError, match="baseline score is too low"):
        verify_live_score_movement_plan(config_path, project_root=project_root)


def test_live_score_movement_plan_cli_json(capsys):
    args = _build_parser().parse_args(["--json"])

    exit_code = _main(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"status": "ok"' in captured.out
    assert '"benchmark": "humaneval_calibrated"' in captured.out
