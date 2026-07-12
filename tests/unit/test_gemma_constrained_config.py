from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = (
    PROJECT_ROOT
    / "config"
    / "livecodebench_openrouter_gemma3_27b_constrained.yaml"
)
PARALLEL_CONFIG_PATH = (
    PROJECT_ROOT
    / "config"
    / "livecodebench_openrouter_gemma3_27b_parallel50.yaml"
)


def test_gemma_constrained_pilot_is_small_and_cost_gated():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    provider = config["fm_providers"]["openai_compatible"]
    constrained = config["self_modification"]["constrained_mutation"]
    live_run = config["live_run"]
    cost_gate = live_run["cost_gate"]

    assert provider["model"] == "google/gemma-3-27b-it"
    assert provider["api_key"] == "${OPENROUTER_API_KEY}"
    assert provider["base_url"] == "https://openrouter.ai/api/v1"
    assert provider["tool_choice_policy"] == "required_read_then_workspace_change"
    assert constrained["enabled"] is True
    assert "Agent._is_task_complete" in constrained["protected_symbols"]["agent.py"]
    assert live_run["recommended_generations"] == 4
    assert cost_gate["input_price_per_mtok"] == 0.08
    assert cost_gate["output_price_per_mtok"] == 0.16
    assert cost_gate["max_estimated_cost_usd"] == 5
    assert cost_gate["max_generations_without_reapproval"] == 12


def test_gemma_parallel_config_uses_shared_100_dollar_cap():
    config = yaml.safe_load(PARALLEL_CONFIG_PATH.read_text(encoding="utf-8"))

    provider = config["fm_providers"]["openai_compatible"]
    live_run = config["live_run"]
    parallel = live_run["parallel"]
    cost_gate = live_run["cost_gate"]

    assert provider["model"] == "google/gemma-3-27b-it"
    assert provider["max_tokens"] == 1024
    assert provider["tool_choice_policy"] == "required_read_then_workspace_change"
    assert live_run["recommended_generations"] == 50
    assert parallel["workers"] == 8
    assert parallel["max_concurrency"] == 8
    assert parallel["shared_max_budget_usd"] == 100
    assert parallel["seed_changed_count"] == 36
    assert parallel["seed_noop_count"] == 14
    assert cost_gate["assumed_input_tokens_per_call"] == 12000
    assert cost_gate["max_estimated_cost_usd"] == 100
