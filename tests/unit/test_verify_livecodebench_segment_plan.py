import base64
import json
import pickle
import zlib
from pathlib import Path

import pytest
import yaml

from scripts.prepare_livecodebench_segment import prepare_livecodebench_segment
from scripts.verify_livecodebench_segment_plan import (
    LiveCodeBenchPlanError,
    _build_parser,
    _main,
    verify_livecodebench_segment_plan,
)


def _encoded_tests(tests: list[dict]) -> str:
    return base64.b64encode(zlib.compress(pickle.dumps(json.dumps(tests)))).decode("utf-8")


def _write_fixture_segment(tmp_path: Path) -> Path:
    jsonl = tmp_path / "fixture.jsonl"
    problems = [
        {
            "question_title": "Add",
            "question_content": "Read two integers and print their sum.",
            "platform": "atcoder",
            "question_id": "abc001_a",
            "contest_id": "abc001",
            "contest_date": "2025-01-01T00:00:00",
            "starter_code": "",
            "difficulty": "easy",
            "public_test_cases": json.dumps([
                {"input": "1 2\n", "output": "3\n", "testtype": "stdin"},
            ]),
            "private_test_cases": _encoded_tests([
                {"input": "10 20\n", "output": "30\n", "testtype": "stdin"},
            ]),
            "metadata": "{}",
        },
        {
            "question_title": "Multiply",
            "question_content": "Read two integers and print their product.",
            "platform": "atcoder",
            "question_id": "abc001_b",
            "contest_id": "abc001",
            "contest_date": "2025-01-01T00:00:00",
            "starter_code": "",
            "difficulty": "hard",
            "public_test_cases": json.dumps([
                {"input": "2 3\n", "output": "6\n", "testtype": "stdin"},
            ]),
            "private_test_cases": _encoded_tests([
                {"input": "4 5\n", "output": "20\n", "testtype": "stdin"},
            ]),
            "metadata": "{}",
        },
    ]
    jsonl.write_text("\n".join(json.dumps(problem) for problem in problems) + "\n")
    segment_config = {
        "purpose": "livecodebench_segment",
        "approval_required": True,
        "live_calls_performed": 0,
        "source": {
            "dataset": "livecodebench/code_generation_lite",
            "source_file": "fixture.jsonl",
            "version_label": "fixture",
            "local_jsonl": "fixture.jsonl",
        },
        "selection": {
            "segment_id": "fixture_segment",
            "output_dir": "generated/benchmarks",
            "manifest_path": "generated/manifest.json",
            "per_problem_timeout_seconds": 5,
            "question_ids": ["abc001_a", "abc001_b"],
        },
        "gates": {
            "min_problem_count": 2,
            "required_difficulties": ["easy", "hard"],
            "min_total_tests": 4,
            "min_private_tests": 2,
            "require_stdin_only": True,
        },
    }
    segment_config_path = tmp_path / "segment.yaml"
    segment_config_path.write_text(yaml.safe_dump(segment_config), encoding="utf-8")
    prepare_livecodebench_segment(segment_config_path, project_root=tmp_path, write=True)
    return segment_config_path


def _write_live_config(tmp_path: Path, segment_config_path: Path) -> Path:
    live_config = {
        "fm_providers": {
            "primary": "openai_compatible",
            "openai_compatible": {
                "model": "moonshotai/kimi-k2.7-code",
                "api_key": "${OPENROUTER_API_KEY}",
                "base_url": "https://openrouter.ai/api/v1",
                "max_tokens": 4096,
                "temperature": 0.1,
                "timeout": 90,
                "timeout_retries": 1,
                "timeout_retry_delay": 1,
            },
        },
        "archive": {"path": "runs/archive"},
        "parent_selection": {
            "lambda": 10,
            "alpha_0": 0.5,
            "require_non_regression": True,
            "regression_tolerance": 0.0,
            "elite_selection_probability": 0.35,
        },
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
            "enabled": ["livecodebench_abc001_a", "livecodebench_abc001_b"],
        },
        "stop_on_error": True,
        "live_run": {
            "purpose": "livecodebench_openrouter_segment",
            "approval_required": True,
            "recommended_generations": 3,
            "segment": {
                "config": str(segment_config_path.relative_to(tmp_path)),
                "manifest_path": "generated/manifest.json",
                "segment_id": "fixture_segment",
                "benchmark_count": 2,
                "expected_total_tests_min": 4,
                "expected_private_tests_min": 2,
            },
            "cost_gate": {
                "check_current_provider_pricing_before_run": True,
                "pricing_checked_at": "2026-06-24",
                "input_price_per_mtok": 0.74,
                "output_price_per_mtok": 3.50,
                "assumed_input_tokens_per_call": 50000,
                "max_estimated_cost_usd": 6,
                "max_generations_without_reapproval": 3,
                "max_agent_steps": 5,
                "max_output_tokens_per_call": 4096,
                "max_enabled_benchmarks": 2,
            },
            "required_preflight": [
                "python scripts/prepare_livecodebench_segment.py --config segment.yaml",
                "python scripts/verify_livecodebench_segment_plan.py --require-generated",
                "python scripts/verify_sandbox_docker.py --require",
                "python scripts/estimate_live_run_cost.py --max-budget 30",
            ],
            "recommended_run": [
                "python scripts/run_dgm_in_sandbox.py --config live.yaml --generations 3 --allow-network --env OPENROUTER_API_KEY --timeout 7200",
            ],
        },
    }
    live_config_path = tmp_path / "live.yaml"
    live_config_path.write_text(yaml.safe_dump(live_config, sort_keys=False), encoding="utf-8")
    return live_config_path


def test_default_livecodebench_segment_plan_is_bounded():
    project_root = Path(__file__).resolve().parents[2]

    report = verify_livecodebench_segment_plan(project_root=project_root)

    assert report["benchmark_count"] == 24
    assert report["recommended_generations"] == 3
    assert report["request_ceiling"] == 990
    assert report["estimated_total_cost_usd"] == pytest.approx(50.82264)


def test_scale72_livecodebench_segment_plan_is_bounded():
    project_root = Path(__file__).resolve().parents[2]

    report = verify_livecodebench_segment_plan(
        project_root / "config" / "livecodebench_openrouter_scale72.yaml",
        project_root=project_root,
    )

    assert report["benchmark_count"] == 72
    assert report["recommended_generations"] == 3
    assert report["request_ceiling"] == 2910
    assert report["estimated_total_cost_usd"] == pytest.approx(149.38776)


def test_livecodebench_segment_plan_requires_generated_manifest(tmp_path):
    segment_config_path = _write_fixture_segment(tmp_path)
    live_config_path = _write_live_config(tmp_path, segment_config_path)

    report = verify_livecodebench_segment_plan(
        live_config_path,
        project_root=tmp_path,
        require_generated=True,
    )

    assert report["generated_manifest"]["benchmark_count"] == 2
    assert report["generated_manifest"]["total_test_count"] == 4
    assert report["estimated_total_cost_usd"] == pytest.approx(5.64696)
    assert report["require_non_regression"] is True
    assert report["timeout_retries"] == 1
    assert report["elite_selection_probability"] == pytest.approx(0.35)


def test_livecodebench_segment_plan_rejects_mismatched_enabled(tmp_path):
    segment_config_path = _write_fixture_segment(tmp_path)
    live_config_path = _write_live_config(tmp_path, segment_config_path)
    plan = yaml.safe_load(live_config_path.read_text(encoding="utf-8"))
    plan["benchmarks"]["enabled"] = ["livecodebench_abc001_a"]
    live_config_path.write_text(yaml.safe_dump(plan), encoding="utf-8")

    with pytest.raises(LiveCodeBenchPlanError, match="Enabled benchmarks"):
        verify_livecodebench_segment_plan(live_config_path, project_root=tmp_path)


def test_livecodebench_segment_plan_requires_non_regression_selection(tmp_path):
    segment_config_path = _write_fixture_segment(tmp_path)
    live_config_path = _write_live_config(tmp_path, segment_config_path)
    plan = yaml.safe_load(live_config_path.read_text(encoding="utf-8"))
    plan["parent_selection"]["require_non_regression"] = False
    live_config_path.write_text(yaml.safe_dump(plan), encoding="utf-8")

    with pytest.raises(LiveCodeBenchPlanError, match="require non-regression"):
        verify_livecodebench_segment_plan(live_config_path, project_root=tmp_path)


def test_livecodebench_segment_plan_cli_json(tmp_path, capsys):
    segment_config_path = _write_fixture_segment(tmp_path)
    live_config_path = _write_live_config(tmp_path, segment_config_path)

    args = _build_parser().parse_args([
        "--config",
        str(live_config_path),
        "--project-root",
        str(tmp_path),
        "--require-generated",
        "--json",
    ])

    exit_code = _main(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"name": "livecodebench_openrouter_segment_plan"' in captured.out
    assert '"requires_generated_segment": true' in captured.out
