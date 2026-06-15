import json

import pytest

from scripts.summarize_archive_scores import (
    _build_parser,
    _main,
    summarize_archive_scores,
)


def _write_archive_metadata(path, agents):
    path.write_text(
        json.dumps({"agents": agents, "last_updated": "2026-06-15T00:00:00"}),
        encoding="utf-8",
    )


def test_summarize_archive_scores_finds_parent_child_improvement(tmp_path):
    metadata = tmp_path / "archive_metadata.json"
    _write_archive_metadata(
        metadata,
        {
            "root": {
                "agent_id": "root",
                "parent_id": None,
                "generation": 0,
                "average_score": 0.5,
                "benchmark_scores": {"humaneval_style": 0.5},
                "is_valid": True,
            },
            "child": {
                "agent_id": "child",
                "parent_id": "root",
                "generation": 1,
                "average_score": 1.0,
                "benchmark_scores": {"humaneval_style": 1.0},
                "is_valid": True,
            },
        },
    )

    report = summarize_archive_scores(metadata)

    assert report["total_agents"] == 2
    assert report["valid_agents"] == 2
    assert report["top_agent_id"] == "child"
    assert report["top_score"] == pytest.approx(1.0)
    assert report["best_average_delta"] == pytest.approx(0.5)
    assert report["has_improvement"] is True
    assert report["improvements"] == [report["parent_child_deltas"][0]]
    assert report["parent_child_deltas"][0]["benchmark_deltas"] == {
        "humaneval_style": 0.5
    }
    assert report["generation_best_scores"] == [
        {
            "generation": 0,
            "agent_id": "root",
            "average_score": 0.5,
            "benchmark_scores": {"humaneval_style": 0.5},
        },
        {
            "generation": 1,
            "agent_id": "child",
            "average_score": 1.0,
            "benchmark_scores": {"humaneval_style": 1.0},
        },
    ]


def test_require_improvement_fails_flat_archive(tmp_path, capsys):
    metadata = tmp_path / "archive_metadata.json"
    _write_archive_metadata(
        metadata,
        {
            "root": {
                "agent_id": "root",
                "parent_id": None,
                "generation": 0,
                "average_score": 1.0,
                "benchmark_scores": {"list_processing": 1.0},
                "is_valid": True,
            },
            "child": {
                "agent_id": "child",
                "parent_id": "root",
                "generation": 1,
                "average_score": 1.0,
                "benchmark_scores": {"list_processing": 1.0},
                "is_valid": True,
            },
        },
    )
    args = _build_parser().parse_args([
        "--archive-metadata",
        str(metadata),
        "--require-improvement",
    ])

    exit_code = _main(args)
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "best_delta=+0.000" in captured.out
    assert "no valid parent-child average-score improvement" in captured.err


def test_main_writes_scorecard_json(tmp_path, capsys):
    metadata = tmp_path / "archive_metadata.json"
    output = tmp_path / "scorecard.json"
    _write_archive_metadata(
        metadata,
        {
            "root": {
                "agent_id": "root",
                "parent_id": None,
                "generation": 0,
                "average_score": 0.5,
                "benchmark_scores": {"humaneval_style": 0.5},
                "is_valid": True,
            },
            "child": {
                "agent_id": "child",
                "parent_id": "root",
                "generation": 1,
                "average_score": 0.75,
                "benchmark_scores": {"humaneval_style": 0.75},
                "is_valid": True,
            },
        },
    )
    args = _build_parser().parse_args([
        "--archive-metadata",
        str(metadata),
        "--output",
        str(output),
        "--require-improvement",
    ])

    exit_code = _main(args)
    captured = capsys.readouterr()
    scorecard = json.loads(output.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "best_delta=+0.250" in captured.out
    assert scorecard["has_improvement"] is True
    assert scorecard["best_average_delta"] == pytest.approx(0.25)
