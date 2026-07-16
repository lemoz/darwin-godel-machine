from types import SimpleNamespace

import pytest

from archive.agent_archive import AgentArchive, ArchivedAgent
from scripts.rescore_archive_agents import RescoreError, apply_rescore


def _agent(tmp_path, agent_id, score):
    source = tmp_path / "archive" / agent_id
    source.mkdir(parents=True)
    (source / "agent.py").write_text("class Agent: pass\n", encoding="utf-8")
    return ArchivedAgent(
        agent_id=agent_id,
        parent_id="old-parent",
        generation=3,
        source_path=str(source),
        created_at="2026-07-12T00:00:00",
        benchmark_scores={"old": score},
        average_score=score,
        is_valid=True,
        metadata={},
    )


def test_apply_rescore_averages_replicates_and_prunes(tmp_path):
    archive = AgentArchive(str(tmp_path / "archive"))
    archive.agents = {
        "keep": _agent(tmp_path, "keep", 0.9),
        "remove": _agent(tmp_path, "remove", 0.8),
    }
    controller = SimpleNamespace(
        archive=archive,
        config={"fm_providers": {"primary": "gemma_solver"}},
        _resolve_fm_provider=lambda: (
            "openai_compatible",
            {"model": "google/gemma-3-27b-it"},
            "gemma_solver",
        ),
    )

    manifest = apply_rescore(
        controller,
        agent_ids=["keep"],
        score_runs={"keep": [{"a": 1.0, "b": 0.0}, {"a": 0.0, "b": 0.0}]},
        prune_unselected=True,
    )

    kept = archive.get_agent("keep")
    assert kept.benchmark_scores == {"a": 0.5, "b": 0.0}
    assert kept.average_score == pytest.approx(0.25)
    assert kept.parent_id is None
    assert kept.generation == 0
    assert kept.metadata["score_calibration"]["replicates"] == 2
    assert archive.get_agent("remove") is None
    assert not (tmp_path / "archive" / "remove").exists()
    assert manifest["removed_agent_count"] == 1


def test_apply_rescore_rejects_missing_agent(tmp_path):
    archive = AgentArchive(str(tmp_path / "archive"))
    controller = SimpleNamespace(archive=archive)

    with pytest.raises(RescoreError, match="missing requested agents"):
        apply_rescore(
            controller,
            agent_ids=["missing"],
            score_runs={"missing": [{"a": 1.0}]},
            prune_unselected=False,
        )
