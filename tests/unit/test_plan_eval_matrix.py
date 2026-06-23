from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from scripts.plan_eval_matrix import (
    EvalMatrixPlanError,
    _build_parser,
    _main_async,
    plan_eval_matrix,
)


def _load_default_plan(project_root: Path) -> dict:
    return yaml.safe_load(
        (project_root / "config" / "eval_model_matrix.yaml").read_text(
            encoding="utf-8"
        )
    )


def _write_plan(tmp_path: Path, plan: dict) -> Path:
    config_path = tmp_path / "eval_model_matrix.yaml"
    config_path.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    return config_path


@pytest.mark.asyncio
async def test_eval_matrix_plan_passes_default_config():
    project_root = Path(__file__).resolve().parents[2]

    report = await plan_eval_matrix(project_root=project_root)

    assert report["name"] == "eval_model_matrix_plan"
    assert report["status"] == "ok"
    assert report["approval_required"] is True
    assert report["live_calls_performed"] == 0
    assert report["benchmark_count"] == 3
    assert report["benchmark_families"] == [
        "algorithmic_reasoning",
        "calibrated_hidden_cases",
        "hidden_case_headroom",
    ]
    assert report["total_eval_cases"] == 87
    assert report["min_total_eval_cases"] == 75
    assert report["average_delta"] == pytest.approx((0.5 + (7 / 17) + 0.4) / 3)
    assert report["ready_for_live_matrix"] is True
    assert report["decision"] == "prepare_live_matrix_plan"

    by_id = {item["id"]: item for item in report["benchmarks"]}
    assert by_id["humaneval_style"]["baseline_score"] == pytest.approx(0.5)
    assert by_id["humaneval_style"]["candidate_score"] == 1.0
    assert by_id["humaneval_style"]["delta"] == pytest.approx(0.5)
    assert by_id["humaneval_style"]["total_eval_cases"] == 20
    assert by_id["humaneval_style"]["passed_gate"] is True

    assert by_id["humaneval_headroom"]["baseline_score"] == pytest.approx(10 / 17)
    assert by_id["humaneval_headroom"]["candidate_score"] == 1.0
    assert by_id["humaneval_headroom"]["delta"] == pytest.approx(7 / 17)
    assert by_id["humaneval_headroom"]["total_eval_cases"] == 17
    assert by_id["humaneval_headroom"]["passed_gate"] is True

    assert by_id["humaneval_calibrated"]["baseline_score"] == pytest.approx(0.6)
    assert by_id["humaneval_calibrated"]["candidate_score"] == 1.0
    assert by_id["humaneval_calibrated"]["delta"] == pytest.approx(0.4)
    assert by_id["humaneval_calibrated"]["total_eval_cases"] == 50
    assert by_id["humaneval_calibrated"]["passed_gate"] is True


@pytest.mark.asyncio
async def test_eval_matrix_plan_rejects_weak_average_delta(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    plan = deepcopy(_load_default_plan(project_root))
    plan["gate"]["min_average_delta"] = 0.99
    config_path = _write_plan(tmp_path, plan)

    with pytest.raises(EvalMatrixPlanError, match="not ready"):
        await plan_eval_matrix(config_path, project_root=project_root)


@pytest.mark.asyncio
async def test_eval_matrix_plan_rejects_secret_fields(tmp_path):
    project_root = Path(__file__).resolve().parents[2]
    plan = deepcopy(_load_default_plan(project_root))
    plan["benchmarks"][0]["token"] = "placeholder-leaked-token"
    config_path = _write_plan(tmp_path, plan)

    with pytest.raises(EvalMatrixPlanError, match="secret fields"):
        await plan_eval_matrix(config_path, project_root=project_root)


@pytest.mark.asyncio
async def test_eval_matrix_plan_cli_json(capsys):
    args = _build_parser().parse_args(["--json"])

    exit_code = await _main_async(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"name": "eval_model_matrix_plan"' in captured.out
    assert '"live_calls_performed": 0' in captured.out
    assert '"ready_for_live_matrix": true' in captured.out


@pytest.mark.asyncio
async def test_eval_matrix_plan_cli_text(capsys):
    args = _build_parser().parse_args([])

    exit_code = await _main_async(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "eval_model_matrix_plan" in captured.out
    assert "benchmarks=3" in captured.out
    assert "cases=87" in captured.out
    assert "decision=prepare_live_matrix_plan" in captured.out
