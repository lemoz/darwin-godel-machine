import pytest

import run_dgm


def test_parse_args_defaults_to_documented_three_generations():
    args = run_dgm.parse_args([])

    assert args.config == "config/dgm_config.yaml"
    assert args.generations == 3


def test_parse_args_accepts_generation_and_config_override():
    args = run_dgm.parse_args([
        "--config",
        "custom.yaml",
        "--generations",
        "10",
    ])

    assert args.config == "custom.yaml"
    assert args.generations == 10


async def test_main_passes_cli_args_to_controller(monkeypatch):
    calls = {}

    class FakeController:
        def __init__(self, config_or_path):
            calls["config_or_path"] = config_or_path

        async def run(self, num_generations):
            calls["num_generations"] = num_generations

    monkeypatch.setattr(run_dgm, "DGMController", FakeController)

    await run_dgm.main(["--config", "custom.yaml", "--generations", "2"])

    assert calls == {
        "config_or_path": "custom.yaml",
        "num_generations": 2,
    }


def test_parse_args_rejects_non_integer_generations():
    with pytest.raises(SystemExit):
        run_dgm.parse_args(["--generations", "many"])
