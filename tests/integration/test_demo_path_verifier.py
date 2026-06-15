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
    assert "live_run_docs" in names
    assert "archive_lineage_artifact" in names
    assert "sandbox_runner_cli" in names
    assert "sandbox_discard_changes_contract" in names
    assert "live_score_movement_plan" in names

    score_check = next(check for check in checks if check["name"] == "score_movement_demo")
    assert score_check["baseline_score"] == 0.5
    assert score_check["candidate_score"] == 1.0
    assert score_check["delta"] == 0.5

    live_run_check = next(check for check in checks if check["name"] == "live_run_docs")
    assert live_run_check["scorecard"] == "docs/live-runs/2026-06-12-proof/scorecard.json"
    assert live_run_check["top_score"] == 1.0
    assert live_run_check["best_average_delta"] == 0.0
    assert live_run_check["has_improvement"] is False

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
    assert live_plan_check["benchmark"] == "humaneval_style"
    assert live_plan_check["recommended_generations"] == 2
    assert live_plan_check["approval_required"] is True
    assert live_plan_check["requires_current_pricing_check"] is True
    assert live_plan_check["requires_full_process_sandbox"] is True
    assert live_plan_check["requires_scorecard_improvement"] is True
    assert live_plan_check["request_ceiling"] == 25
    assert live_plan_check["estimated_total_cost_usd"] == pytest.approx(4.518)
    assert live_plan_check["max_estimated_cost_usd"] == 5
