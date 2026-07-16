#!/usr/bin/env python3
"""Rescore selected archive parents with the configured primary solver model."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dgm_controller import DGMController


class RescoreError(RuntimeError):
    """Raised when an archive cannot be calibrated safely."""


def apply_rescore(
    controller: DGMController,
    *,
    agent_ids: list[str],
    score_runs: dict[str, list[dict[str, float]]],
    prune_unselected: bool,
) -> dict[str, Any]:
    """Apply replicated scores and optionally reduce the archive to calibrated seeds."""
    archive = controller.archive
    selected = set(agent_ids)
    missing = selected - set(archive.agents)
    if missing:
        raise RescoreError(f"Archive is missing requested agents: {sorted(missing)}")

    calibrated = []
    for agent_id in agent_ids:
        runs = score_runs.get(agent_id) or []
        if not runs:
            raise RescoreError(f"No score runs supplied for {agent_id}")
        benchmark_names = sorted({name for run in runs for name in run})
        scores = {
            name: sum(float(run.get(name, 0.0)) for run in runs) / len(runs)
            for name in benchmark_names
        }
        agent = archive.agents[agent_id]
        agent.benchmark_scores = scores
        agent.average_score = sum(scores.values()) / len(scores) if scores else 0.0
        agent.is_valid = True
        agent.parent_id = None
        agent.generation = 0
        agent.metadata = {
            **(agent.metadata or {}),
            "score_calibration": {
                "primary_provider": controller.config["fm_providers"]["primary"],
                "model": controller._resolve_fm_provider()[1].get("model"),
                "replicates": len(runs),
                "calibrated_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        calibrated.append(
            {
                "agent_id": agent_id,
                "average_score": agent.average_score,
                "benchmark_scores": scores,
            }
        )

    removed = []
    if prune_unselected:
        archive_root = archive.archive_dir.resolve()
        for agent_id in sorted(set(archive.agents) - selected):
            agent = archive.agents.pop(agent_id)
            source_path = Path(agent.source_path).resolve()
            if source_path.is_relative_to(archive_root) and source_path.exists():
                shutil.rmtree(source_path)
            removed.append(agent_id)

    archive._save_archive()
    return {
        "schema_version": 1,
        "primary_provider": controller.config["fm_providers"]["primary"],
        "model": controller._resolve_fm_provider()[1].get("model"),
        "replicates": len(next(iter(score_runs.values()))),
        "pruned_unselected": prune_unselected,
        "removed_agent_count": len(removed),
        "calibrated_agents": calibrated,
    }


async def rescore_archive(
    *,
    config: Path,
    agent_ids: list[str],
    replicates: int,
    prune_unselected: bool,
) -> dict[str, Any]:
    if replicates < 1:
        raise RescoreError("replicates must be at least 1")
    controller = DGMController(config_or_path=str(config))
    score_runs: dict[str, list[dict[str, float]]] = {}
    for agent_id in agent_ids:
        agent = controller.archive.get_agent(agent_id)
        if agent is None:
            raise RescoreError(f"Archive is missing requested agent: {agent_id}")
        source_path = Path(agent.source_path)
        agent_path = source_path / "agent.py" if source_path.is_dir() else source_path
        if not agent_path.exists():
            raise RescoreError(f"Agent source is missing: {agent_path}")
        score_runs[agent_id] = []
        for _ in range(replicates):
            score_runs[agent_id].append(
                await controller._evaluate_agent(str(agent_path))
            )
    return apply_rescore(
        controller,
        agent_ids=agent_ids,
        score_runs=score_runs,
        prune_unselected=prune_unselected,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--agent-id", action="append", required=True)
    parser.add_argument("--replicates", type=int, default=1)
    parser.add_argument("--prune-unselected", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        manifest = asyncio.run(
            rescore_archive(
                config=args.config,
                agent_ids=args.agent_id,
                replicates=args.replicates,
                prune_unselected=args.prune_unselected,
            )
        )
    except (OSError, RescoreError, ValueError) as exc:
        print(f"[fail] {exc}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
