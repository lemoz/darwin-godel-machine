import json
from pathlib import Path

import pytest
import yaml

from scripts.run_livecodebench_shards import (
    aggregate_scorecards,
    plan_livecodebench_shards,
)


def _write_scale_fixture(tmp_path: Path) -> Path:
    manifest = {
        "problems": [
            {"benchmark": "livecodebench_easy_1", "difficulty": "easy"},
            {"benchmark": "livecodebench_easy_2", "difficulty": "easy"},
            {"benchmark": "livecodebench_medium_1", "difficulty": "medium"},
            {"benchmark": "livecodebench_medium_2", "difficulty": "medium"},
            {"benchmark": "livecodebench_hard_1", "difficulty": "hard"},
            {"benchmark": "livecodebench_hard_2", "difficulty": "hard"},
        ]
    }
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "manifest.json").write_text(json.dumps(manifest))

    config = {
        "fm_providers": {
            "primary": "openai_compatible",
            "openai_compatible": {
                "model": "moonshotai/kimi-k2.7-code",
                "api_key": "${OPENROUTER_API_KEY}",
                "base_url": "https://openrouter.ai/api/v1",
                "max_tokens": 4096,
                "temperature": 0.1,
                "timeout": 90,
            },
        },
        "archive": {"path": "runs/archive"},
        "evaluation": {
            "benchmarks_dir": "generated/benchmarks",
            "results_dir": "runs/results",
            "timeout_seconds": 30,
            "use_sandbox": False,
        },
        "agents": {
            "workspace_dir": "runs/workspace",
            "initial_agent_path": "agent/agent.py",
            "max_steps": 5,
        },
        "benchmarks": {
            "enabled": [
                "livecodebench_easy_1",
                "livecodebench_easy_2",
                "livecodebench_medium_1",
                "livecodebench_medium_2",
                "livecodebench_hard_1",
                "livecodebench_hard_2",
            ],
        },
        "live_run": {
            "purpose": "livecodebench_openrouter_segment",
            "recommended_generations": 3,
            "segment": {"manifest_path": "generated/manifest.json"},
            "sharding": {
                "strategy": "difficulty_balanced_contiguous",
                "run_dir": "runs/scale",
                "audit_dir": "audits/scale",
                "shard_count": 2,
                "shard_size": 3,
                "difficulty_order": ["easy", "medium", "hard"],
                "aggregate_scorecard": "runs/scale/aggregate_scorecard.json",
            },
            "cost_gate": {
                "input_price_per_mtok": 0.74,
                "output_price_per_mtok": 3.50,
                "assumed_input_tokens_per_call": 50000,
                "max_estimated_cost_usd": 10,
            },
        },
    }
    config_path = tmp_path / "live.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    return config_path


def _scorecard(path: Path, base: float, top: float, has_improvement: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "top_score": top,
        "top_agent_id": "top",
        "best_average_delta": top - base,
        "has_improvement": has_improvement,
        "has_regression": False,
        "generation_best_scores": [
            {
                "generation": 0,
                "average_score": base,
                "benchmark_scores": {"a": base, "b": base, "c": base},
            },
            {
                "generation": 1,
                "average_score": top,
                "benchmark_scores": {"a": top, "b": top, "c": top},
            },
        ],
    }))


def test_plan_livecodebench_shards_writes_balanced_configs(tmp_path):
    config_path = _write_scale_fixture(tmp_path)

    plan = plan_livecodebench_shards(config_path, project_root=tmp_path)

    assert plan["shard_count"] == 2
    assert plan["benchmark_count"] == 6
    assert plan["shards"][0]["benchmarks"] == [
        "livecodebench_easy_1",
        "livecodebench_medium_1",
        "livecodebench_hard_1",
    ]
    assert plan["shards"][1]["benchmarks"] == [
        "livecodebench_easy_2",
        "livecodebench_medium_2",
        "livecodebench_hard_2",
    ]
    shard_config = yaml.safe_load((tmp_path / plan["shards"][0]["config"]).read_text())
    assert shard_config["benchmarks"]["enabled"] == plan["shards"][0]["benchmarks"]
    assert shard_config["live_run"]["shard"]["id"] == "shard-01"


def test_aggregate_scorecards_weights_completed_shards(tmp_path):
    config_path = _write_scale_fixture(tmp_path)
    plan = plan_livecodebench_shards(config_path, project_root=tmp_path)
    _scorecard(tmp_path / plan["shards"][0]["scorecard"], 0.3, 0.6, True)
    _scorecard(tmp_path / plan["shards"][1]["scorecard"], 0.2, 0.2, False)

    aggregate = aggregate_scorecards(plan, project_root=tmp_path)

    assert aggregate["status"] == "complete"
    assert aggregate["completed_shards"] == 2
    assert aggregate["total_benchmark_count"] == 6
    assert aggregate["weighted_base_score"] == 0.25
    assert aggregate["weighted_best_shard_score"] == pytest.approx(0.4)
    assert aggregate["weighted_best_delta"] == pytest.approx(0.15)
    assert aggregate["shards_with_improvement"] == 1
