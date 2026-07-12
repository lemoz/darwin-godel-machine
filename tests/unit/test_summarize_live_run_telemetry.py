import json
from pathlib import Path

import pytest

from scripts.summarize_live_run_telemetry import (
    TelemetryError,
    parse_controller_log,
    summarize_live_run_telemetry,
)


def test_parse_controller_log_counts_provider_and_usage_events(tmp_path: Path):
    log_path = tmp_path / "controller.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-06-25 10:00:00,000 - INFO - Starting OpenAI-compatible API request (timeout: 60s, model: moonshotai/kimi-k2.7-code, base_url: https://openrouter.ai/api/v1)",
                "2026-06-25 10:00:01,000 - INFO - HTTP Request: POST https://openrouter.ai/api/v1/chat/completions",
                "2026-06-25 10:00:02,000 - INFO - OpenAI-compatible API request completed successfully in 2.00s",
                "2026-06-25 10:00:02,010 - INFO - API usage: {'prompt_tokens': 1000, 'completion_tokens': 200, 'total_tokens': 1200}",
                "2026-06-25 10:00:03,000 - WARNING - OpenAI-compatible API request timed out after 60.00s (configured timeout: 60s, model: moonshotai/kimi-k2.7-code)",
                "2026-06-25 10:00:04,000 - INFO - No response generated",
                "2026-06-25 10:00:05,000 - WARNING - Resource guard rejected solution before execution",
                "2026-06-25 10:00:06,000 - INFO - DGM run completed successfully!",
            ]
        ),
        encoding="utf-8",
    )

    summary = parse_controller_log(log_path)

    assert summary["completed"] is True
    assert summary["provider"]["model_from_log"] == "moonshotai/kimi-k2.7-code"
    assert summary["provider"]["base_url_from_log"] == "https://openrouter.ai/api/v1"
    assert summary["provider"]["http_post_count"] == 1
    assert summary["provider"]["timeout_count"] == 1
    assert summary["provider"]["empty_response_count"] == 1
    assert summary["provider"]["completion_latency_seconds"]["average"] == 2.0
    assert summary["tokens"]["prompt_tokens"] == 1000
    assert summary["tokens"]["completion_tokens"] == 200
    assert summary["tokens"]["total_tokens"] == 1200
    assert summary["tokens"]["by_model"]["moonshotai/kimi-k2.7-code"] == {
        "usage_events": 1,
        "prompt_tokens": 1000,
        "completion_tokens": 200,
        "total_tokens": 1200,
    }
    assert summary["failure_signals"]["resource_guard_rejections"] == 1
    assert summary["observed_runtime_seconds"] == 6.0


def test_summarize_live_run_telemetry_merges_score_and_archive_artifacts(tmp_path: Path):
    log_path = tmp_path / "controller.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-06-25 10:00:00,000 - INFO - Starting OpenAI-compatible API request (timeout: 60s, model: model/from-log, base_url: https://openrouter.ai/api/v1)",
                "2026-06-25 10:00:01,000 - INFO - API usage: {'prompt_tokens': 1000000, 'completion_tokens': 500000, 'total_tokens': 1500000}",
                "2026-06-25 10:00:02,000 - INFO - DGM run completed successfully!",
            ]
        ),
        encoding="utf-8",
    )
    scorecard_path = tmp_path / "scorecard.json"
    scorecard_path.write_text(
        json.dumps(
            {
                "top_score": 0.75,
                "top_agent_id": "child",
                "best_average_delta": 0.25,
                "total_agents": 2,
                "valid_agents": 2,
                "has_improvement": True,
                "has_regression": False,
                "total_benchmark_improvements": 1,
                "total_benchmark_regressions": 0,
                "total_benchmark_unchanged": 3,
                "generation_best_scores": [
                    {
                        "generation": 0,
                        "agent_id": "base",
                        "average_score": 0.5,
                        "benchmark_scores": {"a": 1.0, "b": 0.0},
                    },
                    {
                        "generation": 1,
                        "agent_id": "child",
                        "average_score": 0.75,
                        "benchmark_scores": {"a": 1.0, "b": 1.0},
                    },
                ],
                "loop_order_agents": [
                    {
                        "agent_id": "base",
                        "parent_id": None,
                        "generation": 0,
                        "average_score": 0.5,
                        "is_valid": True,
                        "benchmark_count": 2,
                        "solved_count": 1,
                    },
                    {
                        "agent_id": "child",
                        "parent_id": "base",
                        "generation": 1,
                        "average_score": 0.75,
                        "is_valid": True,
                        "benchmark_count": 2,
                        "solved_count": 2,
                        "mutation_status": "changed",
                        "has_code_changes": True,
                    },
                ],
                "mutation_summary": {
                    "status_counts": {"changed": 1},
                    "changed_count": 1,
                    "noop_count": 0,
                },
                "improvements": [
                    {
                        "parent_id": "base",
                        "child_id": "child",
                        "average_delta": 0.25,
                        "benchmark_improvements": {"b": 1.0},
                        "benchmark_regressions": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    archive_path = tmp_path / "archive_metadata.json"
    archive_path.write_text(
        json.dumps(
            {
                "agents": {
                    "base": {
                        "agent_id": "base",
                        "generation": 0,
                        "average_score": 0.5,
                        "is_valid": True,
                        "benchmark_scores": {"a": 1.0, "b": 0.0},
                    },
                    "child": {
                        "agent_id": "child",
                        "parent_id": "base",
                        "generation": 1,
                        "average_score": 0.75,
                        "is_valid": True,
                        "benchmark_scores": {"a": 1.0, "b": 1.0},
                        "metadata": {
                            "mutation": {
                                "mutation_status": "changed",
                                "has_code_changes": True,
                            }
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    report_path = tmp_path / "dgm_report.json"
    report_path.write_text(
        json.dumps(
            {
                "summary": {
                    "total_generations": 1,
                    "runtime_hours": 0.1,
                    "total_agents_created": 1,
                    "successful_improvements": 1,
                    "improvement_rate": 1.0,
                    "consecutive_noop_mutations": 0,
                    "final_archive_size": 2,
                }
            }
        ),
        encoding="utf-8",
    )

    telemetry = summarize_live_run_telemetry(
        controller_log=log_path,
        scorecard_path=scorecard_path,
        dgm_report_path=report_path,
        archive_metadata_path=archive_path,
        provider="openrouter",
        model="model/override",
        input_price_per_mtok=0.74,
        output_price_per_mtok=3.50,
    )

    assert telemetry["provider"]["name"] == "openrouter"
    assert telemetry["provider"]["model"] == "model/override"
    assert telemetry["tokens"]["estimated_cost_usd"] == 2.49
    assert telemetry["score"]["base_score"] == 0.5
    assert telemetry["score"]["top_score"] == 0.75
    assert telemetry["score"]["improvement_count"] == 1
    assert telemetry["score"]["loop_order_agents"][1]["mutation_status"] == "changed"
    assert telemetry["score"]["mutation_summary"]["status_counts"] == {"changed": 1}
    assert telemetry["archive"]["loop_order_agents"][1]["has_code_changes"] is True
    assert telemetry["archive"]["mutation_summary"]["status_counts"] == {"changed": 1}
    assert telemetry["archive"]["zero_score_counts_by_benchmark"] == {"b": 1}
    assert telemetry["dgm_report"]["total_generations"] == 1
    assert telemetry["dgm_report"]["consecutive_noop_mutations"] == 0


def test_summarize_live_run_telemetry_rejects_missing_log(tmp_path: Path):
    with pytest.raises(TelemetryError, match="Controller log not found"):
        summarize_live_run_telemetry(controller_log=tmp_path / "missing.log")


def test_summarize_live_run_telemetry_prices_each_model(tmp_path: Path):
    log_path = tmp_path / "controller.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-07-12 10:00:00,000 - INFO - Starting OpenAI-compatible API request (timeout: 60s, model: openai/gpt-5.6-sol, base_url: https://openrouter.ai/api/v1)",
                "2026-07-12 10:00:01,000 - INFO - API usage: {'prompt_tokens': 1000000, 'completion_tokens': 100000, 'total_tokens': 1100000}",
                "2026-07-12 10:00:02,000 - INFO - Starting OpenAI-compatible API request (timeout: 60s, model: google/gemma-3-27b-it, base_url: https://openrouter.ai/api/v1)",
                "2026-07-12 10:00:03,000 - INFO - API usage: {'prompt_tokens': 1000000, 'completion_tokens': 100000, 'total_tokens': 1100000}",
            ]
        ),
        encoding="utf-8",
    )

    telemetry = summarize_live_run_telemetry(
        controller_log=log_path,
        input_price_per_mtok=0.08,
        output_price_per_mtok=0.16,
        model_prices={
            "openai/gpt-5.6-sol": (5, 30),
            "google/gemma-3-27b-it": (0.08, 0.16),
        },
    )

    assert telemetry["tokens"]["by_model"]["openai/gpt-5.6-sol"][
        "estimated_cost_usd"
    ] == pytest.approx(8.0)
    assert telemetry["tokens"]["by_model"]["google/gemma-3-27b-it"][
        "estimated_cost_usd"
    ] == pytest.approx(0.096)
    assert telemetry["tokens"]["estimated_cost_usd"] == pytest.approx(8.096)
