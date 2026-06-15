#!/usr/bin/env python3
"""Summarize score movement from DGM archive metadata."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class ScorecardError(RuntimeError):
    """Raised when archive score metadata cannot be summarized."""


def _load_archive_metadata(metadata_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ScorecardError(f"Archive metadata not found: {metadata_path}") from exc
    except json.JSONDecodeError as exc:
        raise ScorecardError(f"Invalid archive metadata JSON: {metadata_path}: {exc}") from exc

    agents = data.get("agents")
    if not isinstance(agents, dict):
        raise ScorecardError("Archive metadata must contain an agents object")
    return data


def _normalize_agent(agent_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    benchmark_scores = raw.get("benchmark_scores") or {}
    if not isinstance(benchmark_scores, dict):
        benchmark_scores = {}

    return {
        "agent_id": str(raw.get("agent_id") or agent_id),
        "parent_id": raw.get("parent_id"),
        "generation": int(raw.get("generation", 0)),
        "average_score": float(raw.get("average_score", 0.0)),
        "benchmark_scores": {
            str(name): float(score) for name, score in benchmark_scores.items()
        },
        "is_valid": bool(raw.get("is_valid", False)),
        "created_at": raw.get("created_at"),
    }


def _agent_sort_key(agent: dict[str, Any]) -> tuple[int, str, str]:
    return (
        agent["generation"],
        str(agent.get("created_at") or ""),
        agent["agent_id"],
    )


def _generation_best_scores(agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_generation: dict[int, dict[str, Any]] = {}
    for agent in agents:
        if not agent["is_valid"]:
            continue
        generation = agent["generation"]
        current = best_by_generation.get(generation)
        if current is None or agent["average_score"] > current["average_score"]:
            best_by_generation[generation] = agent

    return [
        {
            "generation": generation,
            "agent_id": agent["agent_id"],
            "average_score": agent["average_score"],
            "benchmark_scores": agent["benchmark_scores"],
        }
        for generation, agent in sorted(best_by_generation.items())
    ]


def summarize_archive_scores(
    metadata_path: Path,
    *,
    min_delta: float = 0.0,
) -> dict[str, Any]:
    """Build a score movement scorecard from archive metadata."""
    data = _load_archive_metadata(metadata_path)
    agents = [
        _normalize_agent(agent_id, raw)
        for agent_id, raw in data["agents"].items()
        if isinstance(raw, dict)
    ]
    agents.sort(key=_agent_sort_key)
    valid_agents = [agent for agent in agents if agent["is_valid"]]
    valid_by_id = {agent["agent_id"]: agent for agent in valid_agents}

    parent_child_deltas = []
    for child in valid_agents:
        parent_id = child.get("parent_id")
        if parent_id not in valid_by_id:
            continue

        parent = valid_by_id[parent_id]
        benchmark_deltas = {
            name: child["benchmark_scores"][name] - parent["benchmark_scores"][name]
            for name in sorted(
                set(parent["benchmark_scores"]) & set(child["benchmark_scores"])
            )
        }
        average_delta = child["average_score"] - parent["average_score"]
        parent_child_deltas.append(
            {
                "parent_id": parent["agent_id"],
                "child_id": child["agent_id"],
                "parent_generation": parent["generation"],
                "child_generation": child["generation"],
                "parent_average_score": parent["average_score"],
                "child_average_score": child["average_score"],
                "average_delta": average_delta,
                "benchmark_deltas": benchmark_deltas,
                "is_improvement": average_delta > min_delta,
            }
        )

    improvements = [
        delta for delta in parent_child_deltas if delta["is_improvement"]
    ]
    best_delta = max(
        (delta["average_delta"] for delta in parent_child_deltas),
        default=0.0,
    )
    top_agent = (
        max(valid_agents, key=lambda agent: agent["average_score"])
        if valid_agents
        else None
    )

    return {
        "archive_metadata": str(metadata_path),
        "total_agents": len(agents),
        "valid_agents": len(valid_agents),
        "top_score": top_agent["average_score"] if top_agent else 0.0,
        "top_agent_id": top_agent["agent_id"] if top_agent else None,
        "best_average_delta": best_delta,
        "min_delta": min_delta,
        "has_improvement": bool(improvements),
        "generation_best_scores": _generation_best_scores(agents),
        "parent_child_deltas": parent_child_deltas,
        "improvements": improvements,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive-metadata",
        required=True,
        help="Path to an archive_metadata.json file from a DGM run.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the scorecard JSON.",
    )
    parser.add_argument(
        "--min-delta",
        type=float,
        default=0.0,
        help="Minimum average-score delta required to count as an improvement.",
    )
    parser.add_argument(
        "--require-improvement",
        action="store_true",
        help="Exit non-zero unless at least one valid child improves on its parent.",
    )
    return parser


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _main(args: argparse.Namespace) -> int:
    try:
        report = summarize_archive_scores(
            Path(args.archive_metadata),
            min_delta=args.min_delta,
        )
        if args.output:
            _write_json(Path(args.output), report)
    except ScorecardError as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 1

    print(
        "archive scorecard: "
        f"agents={report['valid_agents']}/{report['total_agents']} "
        f"top_score={report['top_score']:.3f} "
        f"best_delta={report['best_average_delta']:+.3f} "
        f"improvements={len(report['improvements'])}"
    )

    if args.require_improvement and not report["has_improvement"]:
        print(
            "[fail] no valid parent-child average-score improvement found",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> int:
    return _main(_build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
