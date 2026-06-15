#!/usr/bin/env python3
"""Verify the no-network DGM setup and demo path."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
    module=r"agent\.fm_interface\.providers\.gemini",
)

from evaluation.benchmark_runner import BenchmarkRunner
from sandbox.sandbox_manager import SandboxConfig, SandboxManager, SandboxResult
from scripts.compare_benchmark_solutions import compare_solutions
from scripts.run_dgm_in_sandbox import (
    _build_parser as build_sandbox_runner_parser,
    SandboxRunError,
    resolve_network_mode,
    validate_environment_pass_through,
)


class VerificationError(RuntimeError):
    """Raised when the no-network demo path fails verification."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _check_file(path: Path, project_root: Path | None = None) -> dict[str, Any]:
    _require(path.exists(), f"Missing required file: {path}")
    _require(path.is_file(), f"Expected file path: {path}")
    label = path
    if project_root is not None:
        try:
            label = path.relative_to(project_root)
        except ValueError:
            label = path
    return {"name": f"file:{label}", "status": "ok"}


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VerificationError(f"Invalid JSON in {path}: {exc}") from exc


async def _verify_humaneval_reference(project_root: Path) -> dict[str, Any]:
    runner = BenchmarkRunner(
        benchmarks_dir=str(project_root / "config" / "benchmarks"),
        use_sandbox=False,
    )
    expected = {
        "humaneval_style",
        "list_processing",
        "simple_algorithm",
        "string_manipulation",
    }
    loaded = set(runner.benchmarks)
    _require(
        expected.issubset(loaded),
        f"Missing benchmark configs: {sorted(expected - loaded)}",
    )

    task = runner.benchmarks["humaneval_style"]
    reference_solution = (
        project_root / "tests" / "fixtures" / "reference_solutions" / "humaneval_style.py"
    ).read_text(encoding="utf-8")
    test_results = []
    for test_case in task.test_cases:
        test_results.append(
            await runner._run_test_case(reference_solution, test_case, task)
        )

    score = runner._calculate_score({"test_results": test_results}, task)
    _require(score == 1.0, f"HumanEval-style reference score was {score}, expected 1.0")
    return {
        "name": "humaneval_reference",
        "status": "ok",
        "score": score,
        "test_cases": len(task.test_cases),
    }


async def _verify_score_movement(project_root: Path) -> dict[str, Any]:
    report = await compare_solutions(
        benchmarks_dir=project_root / "config" / "benchmarks",
        benchmark_name="humaneval_style",
        baseline_path=project_root / "docs" / "demo" / "humaneval_style_baseline.py",
        candidate_path=project_root / "docs" / "demo" / "humaneval_style_improved.py",
    )
    checked_in = _load_json(project_root / "docs" / "demo" / "humaneval_score_movement.json")

    _require(report["baseline"]["score"] == 0.5, "Expected baseline score 0.5")
    _require(report["candidate"]["score"] == 1.0, "Expected candidate score 1.0")
    _require(report["delta"] == 0.5, "Expected score delta 0.5")
    _require(checked_in["baseline"]["score"] == report["baseline"]["score"], "Stale baseline JSON report")
    _require(checked_in["candidate"]["score"] == report["candidate"]["score"], "Stale candidate JSON report")
    _require(checked_in["delta"] == report["delta"], "Stale delta JSON report")

    return {
        "name": "score_movement_demo",
        "status": "ok",
        "baseline_score": report["baseline"]["score"],
        "candidate_score": report["candidate"]["score"],
        "delta": report["delta"],
    }


def _verify_live_run_docs(project_root: Path) -> dict[str, Any]:
    readme = project_root / "docs" / "live-runs" / "2026-06-12-proof" / "README.md"
    transcript = project_root / "docs" / "live-runs" / "2026-06-12-proof" / "transcript.txt"
    _check_file(readme, project_root)
    _check_file(transcript, project_root)

    readme_text = readme.read_text(encoding="utf-8")
    _require("API calls: 20" in readme_text, "Live-run README is missing API-call evidence")
    _require("Top score: 1.000" in readme_text, "Live-run README is missing top score")
    _require(
        "does not prove benchmark improvement" in readme_text,
        "Live-run README must keep the benchmark-improvement caveat",
    )

    transcript_text = transcript.read_text(encoding="utf-8")
    _require("POST https://api.anthropic.com/v1/messages" in transcript_text, "Transcript lacks live API evidence")
    _require("DGM run completed" in transcript_text, "Transcript lacks completion evidence")

    return {
        "name": "live_run_docs",
        "status": "ok",
        "readme": str(readme.relative_to(project_root)),
        "transcript": str(transcript.relative_to(project_root)),
    }


def _verify_archive_lineage(project_root: Path) -> dict[str, Any]:
    svg = project_root / "docs" / "archive-lineage-example.svg"
    _check_file(svg, project_root)
    text = svg.read_text(encoding="utf-8")
    _require("DGM archive lineage" in text, "Archive lineage SVG missing label")
    _require("score 0.810" in text, "Archive lineage SVG missing expected top score")
    return {
        "name": "archive_lineage_artifact",
        "status": "ok",
        "path": str(svg.relative_to(project_root)),
    }


def _verify_sandbox_runner_cli(project_root: Path) -> dict[str, Any]:
    runner = project_root / "scripts" / "run_dgm_in_sandbox.py"
    _check_file(runner, project_root)
    parser = build_sandbox_runner_parser()
    help_text = parser.format_help()
    args = parser.parse_args([
        "--allow-network",
        "--env",
        "ANTHROPIC_API_KEY",
        "--discard-changes",
    ])

    _require("--allow-network" in help_text, "Sandbox runner help missing --allow-network")
    _require("--env" in help_text, "Sandbox runner help missing --env")
    _require("--discard-changes" in help_text, "Sandbox runner help missing --discard-changes")
    _require(args.allow_network is True, "Sandbox runner parser did not accept --allow-network")
    _require(args.env == ["ANTHROPIC_API_KEY"], "Sandbox runner parser did not collect --env")
    _require(args.discard_changes is True, "Sandbox runner parser did not accept --discard-changes")
    _require(
        resolve_network_mode(False, "bridge") == "none",
        "Sandbox runner must keep network disabled without --allow-network",
    )
    _require(
        resolve_network_mode(True, "bridge") == "bridge",
        "Sandbox runner did not honor explicit --allow-network network mode",
    )
    try:
        validate_environment_pass_through(["ANTHROPIC_API_KEY"], allow_network=False)
    except SandboxRunError:
        pass
    else:
        raise VerificationError(
            "Sandbox runner must reject --env without explicit --allow-network"
        )
    validate_environment_pass_through(["ANTHROPIC_API_KEY"], allow_network=True)

    return {
        "name": "sandbox_runner_cli",
        "status": "ok",
        "path": str(runner.relative_to(project_root)),
        "safe_flags": ["--allow-network", "--env", "--discard-changes"],
        "network_default": "none",
        "env_requires_network": True,
    }


async def _verify_sandbox_discard_changes_contract() -> dict[str, Any]:
    class MutatingSandboxManager(SandboxManager):
        async def execute_in_sandbox(self, *args: Any, **kwargs: Any) -> SandboxResult:
            workspace = Path(kwargs["workspace_path"])
            (workspace / "kept.txt").write_text("sandbox\n", encoding="utf-8")
            (workspace / "created.txt").write_text("created\n", encoding="utf-8")
            (workspace / "removed.txt").unlink()
            return SandboxResult(success=True, output="mutated staged workspace\n", exit_code=0)

    def seed_host_project(host_project: Path) -> None:
        host_project.mkdir(parents=True)
        (host_project / "kept.txt").write_text("host\n", encoding="utf-8")
        (host_project / "removed.txt").write_text("remove me\n", encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="dgm-sandbox-sync-contract-") as temp_dir:
        host_project = Path(temp_dir) / "sync"
        seed_host_project(host_project)
        manager = MutatingSandboxManager(SandboxConfig())

        result = await manager.execute_project_command(
            command="mutate staged workspace",
            project_path=str(host_project),
            sync_back=True,
        )

        _require(result.success, "Sandbox sync-back contract did not complete")
        _require(
            (host_project / "kept.txt").read_text(encoding="utf-8") == "sandbox\n",
            "Sandbox sync-back contract did not propagate staged file updates",
        )
        _require(
            (host_project / "created.txt").read_text(encoding="utf-8") == "created\n",
            "Sandbox sync-back contract did not propagate staged file creates",
        )
        _require(
            not (host_project / "removed.txt").exists(),
            "Sandbox sync-back contract did not propagate staged file deletes",
        )

    with tempfile.TemporaryDirectory(prefix="dgm-sandbox-discard-contract-") as temp_dir:
        host_project = Path(temp_dir) / "discard"
        seed_host_project(host_project)
        manager = MutatingSandboxManager(SandboxConfig())

        result = await manager.execute_project_command(
            command="mutate staged workspace",
            project_path=str(host_project),
            sync_back=False,
        )

        _require(result.success, "Sandbox discard-changes contract did not complete")
        _require(
            (host_project / "kept.txt").read_text(encoding="utf-8") == "host\n",
            "Sandbox discard-changes contract leaked staged file updates",
        )
        _require(
            not (host_project / "created.txt").exists(),
            "Sandbox discard-changes contract leaked staged file creates",
        )
        _require(
            (host_project / "removed.txt").read_text(encoding="utf-8") == "remove me\n",
            "Sandbox discard-changes contract leaked staged file deletes",
        )

    return {
        "name": "sandbox_discard_changes_contract",
        "status": "ok",
        "proves": [
            "sync_back_true_mirrors_staged_writes",
            "sync_back_false_preserves_host_checkout",
        ],
    }


async def verify_demo_path(project_root: Path = PROJECT_ROOT) -> list[dict[str, Any]]:
    """Run all no-network setup/demo verification checks."""
    project_root = project_root.resolve()
    checks: list[dict[str, Any]] = []

    required_files = [
        project_root / "README.md",
        project_root / "requirements.txt",
        project_root / "config" / "dgm_config.yaml",
        project_root / "config" / "benchmarks" / "humaneval_style.yaml",
        project_root / "docs" / "demo" / "humaneval_style_baseline.py",
        project_root / "docs" / "demo" / "humaneval_style_improved.py",
        project_root / "docs" / "demo" / "humaneval_score_movement.json",
    ]
    checks.extend(_check_file(path, project_root) for path in required_files)
    checks.append(await _verify_humaneval_reference(project_root))
    checks.append(await _verify_score_movement(project_root))
    checks.append(_verify_live_run_docs(project_root))
    checks.append(_verify_archive_lineage(project_root))
    checks.append(_verify_sandbox_runner_cli(project_root))
    checks.append(await _verify_sandbox_discard_changes_contract())
    return checks


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        default=str(PROJECT_ROOT),
        help="Repository root to verify.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of human-readable checks.",
    )
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    try:
        checks = await verify_demo_path(Path(args.project_root))
    except VerificationError as exc:
        if args.json:
            print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        else:
            print(f"[fail] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"status": "ok", "checks": checks}, indent=2, sort_keys=True))
    else:
        for check in checks:
            print(f"[ok] {check['name']}")
        print("No-network DGM demo path verified.")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
