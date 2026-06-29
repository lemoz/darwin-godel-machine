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
    assert report["parent_child_deltas"][0]["benchmark_improvements"] == {
        "humaneval_style": 0.5
    }
    assert report["parent_child_deltas"][0]["benchmark_regressions"] == {}
    assert report["parent_child_deltas"][0]["benchmark_unchanged"] == []
    assert report["total_benchmark_improvements"] == 1
    assert report["total_benchmark_regressions"] == 0
    assert report["total_benchmark_unchanged"] == 0
    assert report["has_regression"] is False
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


def test_summarize_archive_scores_reports_benchmark_regressions(tmp_path):
    metadata = tmp_path / "archive_metadata.json"
    _write_archive_metadata(
        metadata,
        {
            "root": {
                "agent_id": "root",
                "parent_id": None,
                "generation": 0,
                "average_score": 0.75,
                "benchmark_scores": {"a": 1.0, "b": 0.5, "c": 0.75},
                "is_valid": True,
            },
            "child": {
                "agent_id": "child",
                "parent_id": "root",
                "generation": 1,
                "average_score": 0.5,
                "benchmark_scores": {"a": 0.5, "b": 0.75, "c": 0.75},
                "is_valid": True,
            },
        },
    )

    report = summarize_archive_scores(metadata)
    delta = report["parent_child_deltas"][0]

    assert delta["benchmark_improvements"] == {"b": 0.25}
    assert delta["benchmark_regressions"] == {"a": -0.5}
    assert delta["benchmark_unchanged"] == ["c"]
    assert report["has_regression"] is True
    assert report["total_benchmark_improvements"] == 1
    assert report["total_benchmark_regressions"] == 1
    assert report["total_benchmark_unchanged"] == 1


def test_summarize_archive_scores_reports_loop_order_and_mutations(tmp_path):
    metadata = tmp_path / "archive_metadata.json"
    _write_archive_metadata(
        metadata,
        {
            "root": {
                "agent_id": "root",
                "parent_id": None,
                "generation": 0,
                "average_score": 1.0,
                "benchmark_scores": {"a": 1.0},
                "is_valid": True,
                "created_at": "2026-06-15T00:00:00",
            },
            "noop": {
                "agent_id": "noop",
                "parent_id": "root",
                "generation": 1,
                "average_score": 0.0,
                "benchmark_scores": {},
                "is_valid": False,
                "created_at": "2026-06-15T00:01:00",
                "metadata": {
                    "mutation": {
                        "mutation_status": "noop",
                        "has_code_changes": False,
                    }
                },
            },
            "changed": {
                "agent_id": "changed",
                "parent_id": "root",
                "generation": 1,
                "average_score": 1.0,
                "benchmark_scores": {"a": 1.0},
                "is_valid": True,
                "created_at": "2026-06-15T00:02:00",
                "metadata": {
                    "mutation": {
                        "mutation_status": "changed",
                        "has_code_changes": True,
                    }
                },
            },
        },
    )

    report = summarize_archive_scores(metadata)

    assert report["total_agents"] == 3
    assert report["valid_agents"] == 2
    assert report["mutation_summary"] == {
        "changed_agents": ["changed"],
        "changed_count": 1,
        "noop_agents": ["noop"],
        "noop_count": 1,
        "status_counts": {"changed": 1, "noop": 1},
        "unknown_agents": [],
        "unknown_count": 0,
    }
    assert [agent["agent_id"] for agent in report["loop_order_agents"]] == [
        "root",
        "noop",
        "changed",
    ]
    assert report["loop_order_agents"][1]["mutation_status"] == "noop"
    assert report["loop_order_agents"][1]["is_valid"] is False
    assert report["loop_order_agents"][2]["has_code_changes"] is True
    assert len(report["parent_child_deltas"]) == 1
    assert report["parent_child_deltas"][0]["child_id"] == "changed"


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
