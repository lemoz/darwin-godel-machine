from scripts.estimate_live_run_cost import estimate_live_run, render_markdown


def _config():
    return {
        "fm_providers": {
            "primary": "anthropic",
            "anthropic": {
                "model": "claude-sonnet-4-6",
                "max_tokens": 1000,
            },
        },
        "agents": {"max_steps": 2},
        "benchmarks": {"enabled": ["a", "b", "c"]},
    }


def test_estimate_live_run_counts_base_eval_and_generations():
    estimate = estimate_live_run(
        config=_config(),
        generations=3,
        avg_input_tokens_per_call=100,
        input_usd_per_mtok=3.0,
        output_usd_per_mtok=15.0,
    )

    assert estimate["base_evaluation_tasks"] == 3
    assert estimate["tasks_per_generation"] == 4
    assert estimate["total_agent_tasks"] == 15
    assert estimate["request_upper_bound"] == 30
    assert estimate["input_tokens_assumed"] == 3000
    assert estimate["output_token_ceiling"] == 30000
    assert estimate["estimated_total_usd"] == 0.459


def test_render_markdown_includes_approval_relevant_numbers():
    estimate = estimate_live_run(
        config=_config(),
        generations=1,
        avg_input_tokens_per_call=100,
        input_usd_per_mtok=3.0,
        output_usd_per_mtok=15.0,
    )

    markdown = render_markdown(estimate)

    assert "Provider/model: `anthropic` / `claude-sonnet-4-6`" in markdown
    assert "Request upper bound: 14" in markdown
    assert "Estimated total ceiling:" in markdown
