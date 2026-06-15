from pathlib import Path

import pytest

from scripts.estimate_live_run_cost import (
    CostEstimateError,
    _build_parser,
    _main,
    estimate_live_run_cost,
)


def test_estimate_live_score_movement_cost_from_config():
    project_root = Path(__file__).resolve().parents[2]

    estimate = estimate_live_run_cost(
        config_path=project_root / "config" / "live_score_movement.yaml",
        input_price_per_mtok=3,
        output_price_per_mtok=15,
        assumed_input_tokens_per_call=50_000,
        max_budget=5,
    )

    assert estimate["model"] == "claude-sonnet-4-6"
    assert estimate["enabled_benchmarks"] == ["humaneval_headroom"]
    assert estimate["benchmark_count"] == 1
    assert estimate["generations"] == 2
    assert estimate["max_agent_steps"] == 5
    assert estimate["request_ceiling"] == 25
    assert estimate["base_evaluation_request_ceiling"] == 5
    assert estimate["requests_per_generation_ceiling"] == 10
    assert estimate["input_token_ceiling"] == 1_250_000
    assert estimate["output_token_ceiling"] == 51_200
    assert estimate["estimated_total_cost_usd"] == pytest.approx(4.518)
    assert estimate["within_budget"] is True


def test_estimate_live_run_cost_rejects_zero_price():
    project_root = Path(__file__).resolve().parents[2]

    with pytest.raises(CostEstimateError, match="input_price_per_mtok"):
        estimate_live_run_cost(
            config_path=project_root / "config" / "live_score_movement.yaml",
            input_price_per_mtok=0,
            output_price_per_mtok=15,
            assumed_input_tokens_per_call=50_000,
        )


def test_estimate_live_run_cost_cli_fails_over_budget(capsys):
    args = _build_parser().parse_args([
        "--input-price-per-mtok",
        "3",
        "--output-price-per-mtok",
        "15",
        "--assumed-input-tokens-per-call",
        "50000",
        "--max-budget",
        "1",
    ])

    exit_code = _main(args)
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "total=$4.5180" in captured.out
    assert "exceeds max budget" in captured.err


def test_estimate_live_run_cost_cli_json(capsys):
    args = _build_parser().parse_args([
        "--input-price-per-mtok",
        "3",
        "--output-price-per-mtok",
        "15",
        "--assumed-input-tokens-per-call",
        "50000",
        "--json",
    ])

    exit_code = _main(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"status": "ok"' in captured.out
    assert '"request_ceiling": 25' in captured.out
