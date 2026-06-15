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

    score_check = next(check for check in checks if check["name"] == "score_movement_demo")
    assert score_check["baseline_score"] == 0.5
    assert score_check["candidate_score"] == 1.0
    assert score_check["delta"] == 0.5
