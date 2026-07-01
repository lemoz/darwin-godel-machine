#!/usr/bin/env python3
"""Seed a new live-run archive from a committed proof archive bundle."""

from __future__ import annotations

import argparse
import json
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any


class SeedArchiveError(RuntimeError):
    """Raised when a proof archive cannot safely seed a new run archive."""


def _safe_extract(tar: tarfile.TarFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in tar.getmembers():
        member_path = destination / member.name
        resolved = member_path.resolve()
        if destination != resolved and destination not in resolved.parents:
            raise SeedArchiveError(f"Unsafe archive member path: {member.name}")
    tar.extractall(destination)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SeedArchiveError(f"Archive metadata not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SeedArchiveError(f"Invalid archive metadata JSON: {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("agents"), dict):
        raise SeedArchiveError("Archive metadata must contain an agents object")
    return data


def _find_archive_dir(extracted_root: Path) -> Path:
    candidates = sorted(extracted_root.rglob("archive_metadata.json"))
    if not candidates:
        raise SeedArchiveError("No archive_metadata.json found in proof archive")
    if len(candidates) > 1:
        joined = ", ".join(str(path) for path in candidates)
        raise SeedArchiveError(f"Proof archive has multiple metadata files: {joined}")
    return candidates[0].parent


def seed_archive(
    *,
    archive_tar: Path,
    target_archive: Path,
    focus_agent_ids: list[str],
    min_focus_score: float,
    output: Path | None,
    force: bool,
) -> dict[str, Any]:
    """Extract proof archive into target_archive and rewrite source paths."""
    if target_archive.exists():
        if not force:
            raise SeedArchiveError(f"Target archive already exists: {target_archive}")
        shutil.rmtree(target_archive)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with tarfile.open(archive_tar, "r:gz") as tar:
            _safe_extract(tar, tmp_path)

        extracted_archive = _find_archive_dir(tmp_path)
        shutil.copytree(extracted_archive, target_archive)

    metadata_path = target_archive / "archive_metadata.json"
    metadata = _load_json(metadata_path)
    agents = metadata["agents"]

    for agent_id, agent in agents.items():
        if not isinstance(agent, dict):
            raise SeedArchiveError(f"Invalid agent metadata for {agent_id}")
        agent["source_path"] = (target_archive / agent_id).as_posix()

    missing_focus = [agent_id for agent_id in focus_agent_ids if agent_id not in agents]
    if missing_focus:
        raise SeedArchiveError(f"Focus agents missing from archive: {', '.join(missing_focus)}")

    focus_summary = []
    for agent_id in focus_agent_ids:
        agent = agents[agent_id]
        score = float(agent.get("average_score", 0.0) or 0.0)
        if score < min_focus_score:
            raise SeedArchiveError(
                f"Focus agent {agent_id} score {score:.6f} is below {min_focus_score:.6f}"
            )
        if not agent.get("is_valid"):
            raise SeedArchiveError(f"Focus agent {agent_id} is not valid")
        if not (target_archive / agent_id).exists():
            raise SeedArchiveError(f"Focus agent source directory missing: {agent_id}")
        focus_summary.append(
            {
                "agent_id": agent_id,
                "average_score": score,
                "generation": agent.get("generation"),
                "parent_id": agent.get("parent_id"),
                "source_path": agent["source_path"],
            }
        )

    metadata["seeded_from"] = archive_tar.as_posix()
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    valid_scores = [
        float(agent.get("average_score", 0.0) or 0.0)
        for agent in agents.values()
        if isinstance(agent, dict) and agent.get("is_valid")
    ]
    manifest = {
        "source_archive_tar": archive_tar.as_posix(),
        "target_archive": target_archive.as_posix(),
        "total_agents": len(agents),
        "valid_agents": len(valid_scores),
        "top_score": max(valid_scores) if valid_scores else 0.0,
        "focus_agents": focus_summary,
    }

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-tar", required=True, type=Path)
    parser.add_argument("--target-archive", required=True, type=Path)
    parser.add_argument("--focus-agent-id", action="append", default=[])
    parser.add_argument("--min-focus-score", type=float, default=0.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        manifest = seed_archive(
            archive_tar=args.archive_tar,
            target_archive=args.target_archive,
            focus_agent_ids=args.focus_agent_id,
            min_focus_score=args.min_focus_score,
            output=args.output,
            force=args.force,
        )
    except SeedArchiveError as exc:
        parser.exit(2, f"seed_archive_from_proof: {exc}\n")

    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
