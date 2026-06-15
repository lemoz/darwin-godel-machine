from pathlib import Path

import pytest

from scripts.compare_benchmark_solutions import compare_solutions


@pytest.mark.asyncio
async def test_demo_solutions_show_score_movement():
    project_root = Path(__file__).resolve().parents[2]

    report = await compare_solutions(
        benchmarks_dir=project_root / "config" / "benchmarks",
        benchmark_name="humaneval_style",
        baseline_path=project_root / "docs" / "demo" / "humaneval_style_baseline.py",
        candidate_path=project_root / "docs" / "demo" / "humaneval_style_improved.py",
    )

    assert report["benchmark"] == "humaneval_style"
    assert report["baseline"]["score"] == pytest.approx(0.5)
    assert report["candidate"]["score"] == pytest.approx(1.0)
    assert report["delta"] == pytest.approx(0.5)
    assert report["baseline"]["passed"] == 10
    assert report["baseline"]["total"] == 20
    assert report["candidate"]["passed"] == 20
    assert report["candidate"]["total"] == 20


@pytest.mark.asyncio
async def test_headroom_demo_solutions_show_hidden_case_score_movement():
    project_root = Path(__file__).resolve().parents[2]

    report = await compare_solutions(
        benchmarks_dir=project_root / "config" / "benchmarks",
        benchmark_name="humaneval_headroom",
        baseline_path=project_root / "docs" / "demo" / "humaneval_headroom_baseline.py",
        candidate_path=project_root / "docs" / "demo" / "humaneval_headroom_improved.py",
    )

    assert report["benchmark"] == "humaneval_headroom"
    assert report["baseline"]["score"] == pytest.approx(10 / 17)
    assert report["candidate"]["score"] == pytest.approx(1.0)
    assert report["delta"] == pytest.approx(7 / 17)
    assert report["baseline"]["passed"] == 10
    assert report["baseline"]["total"] == 17
    assert report["candidate"]["passed"] == 17
    assert report["candidate"]["total"] == 17
