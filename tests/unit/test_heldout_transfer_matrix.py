from pathlib import Path

import yaml

from scripts.materialize_heldout_transfer_matrix import materialize_transfer_matrix


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MATRIX = PROJECT_ROOT / "config/livecodebench_heldout_transfer_matrix.yaml"
SEARCH_SEGMENT = PROJECT_ROOT / "config/livecodebench_segment_loop12.yaml"
HELDOUT_SEGMENT = PROJECT_ROOT / "config/livecodebench_segment_heldout12.yaml"


def test_heldout_segment_is_disjoint_and_matches_difficulty_mix():
    search = yaml.safe_load(SEARCH_SEGMENT.read_text(encoding="utf-8"))
    heldout = yaml.safe_load(HELDOUT_SEGMENT.read_text(encoding="utf-8"))
    search_ids = set(search["selection"]["question_ids"])
    heldout_ids = heldout["selection"]["question_ids"]

    assert len(heldout_ids) == 12
    assert search_ids.isdisjoint(heldout_ids)
    assert heldout["selection"]["segment_id"] == "release_v6_atcoder_heldout12"


def test_materializes_frozen_transfer_configs(tmp_path: Path):
    matrix_path = tmp_path / "config/livecodebench_heldout_transfer_matrix.yaml"
    matrix_path.parent.mkdir(parents=True)
    matrix_path.write_text(MATRIX.read_text(encoding="utf-8"), encoding="utf-8")
    output_dir = tmp_path / "config/generated/heldout_transfer_matrix"

    manifest = materialize_transfer_matrix(
        matrix_path=matrix_path,
        output_dir=output_dir,
        project_root=tmp_path,
    )

    assert manifest["config_count"] == 4
    assert {item["phase"] for item in manifest["configs"]} == {"calibration"}
    for item in manifest["configs"]:
        config = yaml.safe_load((tmp_path / item["config"]).read_text(encoding="utf-8"))
        assert config["live_run"]["recommended_generations"] == 0
        assert config["live_run"]["matrix"]["mutation_mode"] == "none_frozen_replay"
        assert config["live_run"]["segment"]["disjoint_from"] == "release_v6_atcoder_loop12"
        assert len(config["benchmarks"]["enabled"]) == 12
        assert len(config["live_run"]["transfer"]["agents"]) >= 2
        commands = config["live_run"]["required_preflight"]
        assert "prepare_livecodebench_segment.py" in commands[0]
        assert "seed_archive_from_proof.py" in commands[1]
        assert "--focus-agent-id" in commands[1]
        assert "--agent-id" not in commands[1]
        assert "rescore_archive_agents.py" in commands[2]
        assert "--agent-id" in commands[2]
        assert "--focus-agent-id" not in commands[2]
        assert "--replicates 2" in commands[2]
        assert "--prune-unselected" in commands[2]
