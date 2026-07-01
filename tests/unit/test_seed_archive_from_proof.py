import json
import tarfile
from pathlib import Path

import pytest

from scripts.seed_archive_from_proof import SeedArchiveError, seed_archive


def _write_proof_archive(tmp_path: Path) -> Path:
    source = tmp_path / "source" / "archive"
    source.mkdir(parents=True)
    agents = {
        "root": {
            "agent_id": "root",
            "parent_id": None,
            "generation": 0,
            "source_path": "old/archive/root",
            "created_at": "2026-01-01T00:00:00",
            "benchmark_scores": {"b": 0.5},
            "average_score": 0.5,
            "is_valid": True,
            "metadata": {},
        },
        "top": {
            "agent_id": "top",
            "parent_id": "root",
            "generation": 1,
            "source_path": "old/archive/top",
            "created_at": "2026-01-01T00:00:00",
            "benchmark_scores": {"b": 0.75},
            "average_score": 0.75,
            "is_valid": True,
            "metadata": {},
        },
    }
    for agent_id in agents:
        agent_dir = source / agent_id
        agent_dir.mkdir()
        (agent_dir / "agent.py").write_text("class Agent: pass\n", encoding="utf-8")
    (source / "archive_metadata.json").write_text(
        json.dumps({"agents": agents}, indent=2),
        encoding="utf-8",
    )

    archive_tar = tmp_path / "proof.tar.gz"
    with tarfile.open(archive_tar, "w:gz") as tar:
        tar.add(source, arcname="archive")
    return archive_tar


def test_seed_archive_rewrites_source_paths_and_writes_manifest(tmp_path: Path):
    archive_tar = _write_proof_archive(tmp_path)
    target = tmp_path / "run" / "archive"
    output = tmp_path / "run" / "seed_manifest.json"

    manifest = seed_archive(
        archive_tar=archive_tar,
        target_archive=target,
        focus_agent_ids=["top"],
        min_focus_score=0.7,
        output=output,
        force=False,
    )

    metadata = json.loads((target / "archive_metadata.json").read_text(encoding="utf-8"))
    assert metadata["agents"]["top"]["source_path"] == (target / "top").as_posix()
    assert metadata["seeded_from"] == archive_tar.as_posix()
    assert manifest["total_agents"] == 2
    assert manifest["valid_agents"] == 2
    assert manifest["focus_agents"][0]["agent_id"] == "top"
    assert json.loads(output.read_text(encoding="utf-8")) == manifest


def test_seed_archive_rejects_missing_focus_agent(tmp_path: Path):
    archive_tar = _write_proof_archive(tmp_path)

    with pytest.raises(SeedArchiveError, match="Focus agents missing"):
        seed_archive(
            archive_tar=archive_tar,
            target_archive=tmp_path / "run" / "archive",
            focus_agent_ids=["missing"],
            min_focus_score=0.0,
            output=None,
            force=False,
        )
