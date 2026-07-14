import json
from pathlib import Path

import pytest

from scripts.summarize_self_elicitation_matrix import SummaryError, summarize_matrix


def _write_run(
    root: Path,
    run_id: str,
    *,
    baseline: int,
    top: int,
    changed: int = 0,
    noop: int = 0,
    api_errors: int = 0,
) -> None:
    run = root / run_id
    run.mkdir(parents=True)
    top_id = "base" if top == baseline else "child"
    agents = [
        {"agent_id": "base", "generation": 0, "solved_count": baseline},
    ]
    if top_id == "child":
        agents.append({"agent_id": "child", "generation": 1, "solved_count": top})
    (run / "scorecard.json").write_text(
        json.dumps(
            {
                "top_agent_id": top_id,
                "total_agents": len(agents),
                "valid_agents": len(agents),
                "loop_order_agents": agents,
                "mutation_summary": {
                    "changed_count": changed,
                    "noop_count": noop,
                    "unknown_count": 0,
                },
                "has_improvement": top > baseline,
                "improvements": [],
            }
        ),
        encoding="utf-8",
    )
    (run / "telemetry.json").write_text(
        json.dumps(
            {
                "provider": {
                    "timeout_count": 0,
                    "api_error_count": api_errors,
                    "empty_response_count": 0,
                },
                "tokens": {"total_tokens": 100, "estimated_cost_usd": 1.0},
                "run": {"observed_runtime_seconds": 10},
                "dgm_report": {"total_generations": changed + noop},
            }
        ),
        encoding="utf-8",
    )
    (run / "controller.log").write_text(
        "Failure modes: {'no-op': %d, 'hidden-test failure': 2}\n" % noop,
        encoding="utf-8",
    )
    (run / "exit_code").write_text("0\n", encoding="utf-8")


def _write_matrix(path: Path) -> None:
    path.write_text(
        """\
name: test_matrix
segment:
  segment_id: test_segment
evolution:
  generations_per_worker: 3
models:
  - slug: model-a
    model: vendor/model-a
    vendor: Vendor
  - slug: model-b
    model: vendor/model-b
    vendor: Vendor
""",
        encoding="utf-8",
    )


def test_summarize_matrix_reports_conservative_replicated_overhang(tmp_path: Path):
    matrix = tmp_path / "matrix.yaml"
    artifacts = tmp_path / "artifacts"
    _write_matrix(matrix)
    evolution = artifacts / "recovered-gcs"
    native = artifacts / "recovered-native"

    _write_run(native, "native-model-a", baseline=5, top=5)
    _write_run(evolution, "run-model-a-w01", baseline=6, top=9, changed=2, noop=1)
    _write_run(evolution, "run-model-a-w02", baseline=7, top=8, changed=1, noop=2)
    _write_run(native, "native-model-b", baseline=8, top=8)
    _write_run(evolution, "run-model-b-w01", baseline=8, top=8, api_errors=2)
    _write_run(evolution, "run-model-b-w02", baseline=9, top=9, api_errors=3)

    summary = summarize_matrix(matrix_path=matrix, artifacts_root=artifacts)

    model_a, model_b = summary["models"]
    assert model_a["native_observations"] == [5, 6, 7]
    assert model_a["native_median"] == 6
    assert model_a["ladder_tops"] == [9, 8]
    assert model_a["observed_peak"] == 9
    assert model_a["replicated_ladder_floor"] == 8
    assert model_a["reliable_score"] == 8
    assert model_a["capability_overhang"] == 2
    assert model_a["native_realization"] == 0.75
    assert model_a["measurement_status"] == "measured"
    assert model_b["measurement_status"] == "protocol_blocked"
    assert model_b["capability_overhang"] is None
    assert model_b["native_realization"] is None
    assert summary["totals"]["ladders"] == 4
    assert summary["totals"]["generation_attempt_ceiling"] == 12
    assert summary["totals"]["provider_api_errors"] == 5
    assert summary["totals"]["failure_modes"]["hidden-test failure"] == 8


def test_summarize_matrix_requires_two_ladders_per_model(tmp_path: Path):
    matrix = tmp_path / "matrix.yaml"
    artifacts = tmp_path / "artifacts"
    _write_matrix(matrix)
    _write_run(artifacts / "recovered-native", "native-model-a", baseline=5, top=5)
    _write_run(artifacts / "recovered-gcs", "run-model-a-w01", baseline=5, top=5)

    with pytest.raises(SummaryError, match="Expected two evolution ladders"):
        summarize_matrix(matrix_path=matrix, artifacts_root=artifacts)
