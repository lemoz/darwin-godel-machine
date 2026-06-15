from pathlib import Path

import pytest

from scripts.verify_demo_path import verify_demo_path


@pytest.mark.asyncio
async def test_no_network_demo_path_verifier_passes():
    project_root = Path(__file__).resolve().parents[2]

    checks = await verify_demo_path(project_root)
    names = {check["name"] for check in checks}

    assert "humaneval_reference" in names
    assert "score_movement_demo" in names
    assert "live_headroom_score_movement_demo" in names
    assert "calibrated_score_movement_demo" in names
    assert "live_run_docs" in names
    assert "archive_lineage_artifact" in names
    assert "sandbox_runner_cli" in names
    assert "sandbox_discard_changes_contract" in names
    assert "live_score_movement_plan" in names
    assert "live_score_movement_attempt_docs" in names

    score_check = next(check for check in checks if check["name"] == "score_movement_demo")
    assert score_check["baseline_score"] == 0.5
    assert score_check["candidate_score"] == 1.0
    assert score_check["delta"] == 0.5

    headroom_check = next(
        check for check in checks if check["name"] == "live_headroom_score_movement_demo"
    )
    assert headroom_check["benchmark"] == "humaneval_headroom"
    assert headroom_check["baseline_score"] == pytest.approx(10 / 17)
    assert headroom_check["candidate_score"] == 1.0
    assert headroom_check["delta"] == pytest.approx(7 / 17)

    calibrated_check = next(
        check for check in checks if check["name"] == "calibrated_score_movement_demo"
    )
    assert calibrated_check["benchmark"] == "humaneval_calibrated"
    assert calibrated_check["baseline_score"] == pytest.approx(0.6)
    assert calibrated_check["candidate_score"] == 1.0
    assert calibrated_check["delta"] == pytest.approx(0.4)
    assert calibrated_check["baseline_passed"] == 30
    assert calibrated_check["total"] == 50

    live_run_check = next(check for check in checks if check["name"] == "live_run_docs")
    assert live_run_check["scorecard"] == "docs/live-runs/2026-06-12-proof/scorecard.json"
    assert live_run_check["top_score"] == 1.0
    assert live_run_check["best_average_delta"] == 0.0
    assert live_run_check["has_improvement"] is False

    live_attempt_check = next(
        check for check in checks if check["name"] == "live_score_movement_attempt_docs"
    )
    assert live_attempt_check["scorecard"] == "docs/live-runs/live-score-movement/scorecard.json"
    assert live_attempt_check["top_score"] == pytest.approx(15 / 17)
    assert live_attempt_check["best_average_delta"] == 0.0
    assert live_attempt_check["has_improvement"] is False
    assert live_attempt_check["has_regression"] is True
    assert live_attempt_check["total_benchmark_regressions"] == 1
    assert live_attempt_check["audit_hides_env_values"] is True

    sandbox_check = next(check for check in checks if check["name"] == "sandbox_runner_cli")
    assert "--discard-changes" in sandbox_check["safe_flags"]
    assert "--audit-output" in sandbox_check["safe_flags"]
    assert sandbox_check["network_default"] == "none"
    assert sandbox_check["env_requires_network"] is True
    assert sandbox_check["audit_hides_env_values"] is True
    assert sandbox_check["audit_artifact_writable"] is True

    discard_check = next(
        check for check in checks if check["name"] == "sandbox_discard_changes_contract"
    )
    assert "sync_back_false_preserves_host_checkout" in discard_check["proves"]

    live_plan_check = next(
        check for check in checks if check["name"] == "live_score_movement_plan"
    )
    assert live_plan_check["benchmark"] == "humaneval_calibrated"
    assert live_plan_check["recommended_generations"] == 2
    assert live_plan_check["approval_required"] is True
    assert live_plan_check["requires_current_pricing_check"] is True
    assert live_plan_check["requires_full_process_sandbox"] is True
    assert live_plan_check["requires_scorecard_improvement"] is True
    assert live_plan_check["requires_headroom_gate"] is True
    assert live_plan_check["headroom_baseline_score"] == pytest.approx(0.6)
    assert live_plan_check["headroom_candidate_score"] == 1.0
    assert live_plan_check["headroom_delta"] == pytest.approx(0.4)
    assert live_plan_check["headroom_public_examples"] == 10
    assert live_plan_check["headroom_evaluation_cases"] == 50
    assert live_plan_check["request_ceiling"] == 25
    assert live_plan_check["estimated_total_cost_usd"] == pytest.approx(4.518)
    assert live_plan_check["max_estimated_cost_usd"] == 5
