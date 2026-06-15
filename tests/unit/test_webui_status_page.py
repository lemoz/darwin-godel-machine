import json
from pathlib import Path

from archive.agent_archive import ArchivedAgent
from webui.status_page import (
    build_status_model,
    main,
    render_status_page,
)


def _write_project_files(project_root: Path) -> None:
    (project_root / "docs" / "demo").mkdir(parents=True)
    (project_root / "docs" / "live-runs" / "2026-06-12-proof").mkdir(parents=True)
    (project_root / "docs" / "archive-lineage-example.svg").write_text(
        '<svg aria-label="DGM archive lineage"></svg>',
        encoding="utf-8",
    )
    (project_root / "docs" / "demo" / "humaneval_score_movement.json").write_text(
        json.dumps(
            {
                "benchmark": "humaneval_style",
                "baseline": {"score": 0.5},
                "candidate": {"score": 1.0},
                "delta": 0.5,
            }
        ),
        encoding="utf-8",
    )
    (project_root / "docs" / "live-runs" / "2026-06-12-proof" / "README.md").write_text(
        "live run",
        encoding="utf-8",
    )
    (project_root / "docs" / "live-runs" / "2026-06-12-proof" / "transcript.txt").write_text(
        "transcript",
        encoding="utf-8",
    )
    (project_root / "config").mkdir()
    (project_root / "config" / "dgm_config.yaml").write_text("archive: {}\n", encoding="utf-8")
    (project_root / "scripts").mkdir()
    (project_root / "scripts" / "verify_demo_path.py").write_text("# verifier\n", encoding="utf-8")
    (project_root / "scripts" / "run_dgm_in_sandbox.py").write_text("# sandbox\n", encoding="utf-8")
    (project_root / "README.md").write_text("# DGM\n", encoding="utf-8")


def _write_archive(project_root: Path) -> None:
    archive_dir = project_root / "archive" / "agents"
    archive_dir.mkdir(parents=True)
    root = ArchivedAgent(
        agent_id="root-agent",
        parent_id=None,
        generation=0,
        source_path="/tmp/root-agent",
        created_at="2026-06-12T00:00:00",
        benchmark_scores={"bench": 0.4},
        average_score=0.4,
        is_valid=True,
        metadata={},
    )
    child = ArchivedAgent(
        agent_id="child-agent",
        parent_id="root-agent",
        generation=1,
        source_path="/tmp/child-agent",
        created_at="2026-06-12T00:00:01",
        benchmark_scores={"bench": 0.8},
        average_score=0.8,
        is_valid=True,
        metadata={},
    )
    (archive_dir / "archive_metadata.json").write_text(
        json.dumps({"agents": {root.agent_id: root.to_dict(), child.agent_id: child.to_dict()}}),
        encoding="utf-8",
    )


def test_build_status_model_reads_archive_and_artifacts(tmp_path):
    _write_project_files(tmp_path)
    _write_archive(tmp_path)

    model = build_status_model(tmp_path)

    assert len(model.agents) == 2
    assert model.archive_warning is None
    assert model.score_movement.exists is True
    assert model.score_movement.delta == 0.5
    assert "docs/live-runs/2026-06-12-proof" in model.live_runs
    assert all(artifact.exists for artifact in model.artifacts)


def test_render_status_page_includes_lineage_artifacts_and_commands(tmp_path):
    _write_project_files(tmp_path)
    _write_archive(tmp_path)
    model = build_status_model(tmp_path)

    html = render_status_page(model)

    assert "<!doctype html>" in html
    assert "DGM Local Status" in html
    assert "agent root-ag" in html
    assert "humaneval_style: 0.500 to 1.000 (0.500 delta)" in html
    assert "docs/live-runs/2026-06-12-proof" in html
    assert "python scripts/verify_demo_path.py" in html
    assert "python scripts/run_dgm_in_sandbox.py --help" in html
    assert "python scripts/run_dgm_in_sandbox.py --config config/dgm_config.yaml --generations 1 --discard-changes" in html


def test_render_status_page_handles_missing_archive_without_creating_it(tmp_path):
    _write_project_files(tmp_path)

    model = build_status_model(tmp_path)
    html = render_status_page(model)

    assert model.agents == []
    assert model.archive_warning is not None
    assert "No archived agents found." in html
    assert not (tmp_path / "archive" / "agents").exists()


def test_status_page_cli_writes_html(tmp_path):
    _write_project_files(tmp_path)
    _write_archive(tmp_path)
    output = tmp_path / "status.html"

    result = main(["--project-root", str(tmp_path), "--output", str(output)])

    assert result == 0
    assert output.exists()
    assert "DGM Local Status" in output.read_text(encoding="utf-8")


def test_status_page_cli_resolves_relative_output_under_project_root(tmp_path):
    _write_project_files(tmp_path)
    _write_archive(tmp_path)

    result = main(["--project-root", str(tmp_path), "--output", "docs/status.html"])

    assert result == 0
    assert (tmp_path / "docs" / "status.html").exists()


def test_status_page_cli_resolves_relative_archive_under_project_root(tmp_path, monkeypatch):
    _write_project_files(tmp_path)
    _write_archive(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)

    output = tmp_path / "status.html"
    result = main(
        [
            "--project-root",
            str(tmp_path),
            "--archive-dir",
            "archive/agents",
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert "root-agent" in output.read_text(encoding="utf-8")
