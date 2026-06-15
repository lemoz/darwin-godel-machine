#!/usr/bin/env python3
"""Optionally verify the real Docker full-process sandbox mount path."""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sandbox_manager import SandboxConfig, SandboxManager, SandboxResult


class SandboxDockerSmokeError(RuntimeError):
    """Raised when the optional Docker sandbox smoke check fails."""


MUTATION_CODE = """
from pathlib import Path

Path("kept.txt").write_text("sandbox\\n", encoding="utf-8")
Path("created.txt").write_text("created\\n", encoding="utf-8")
Path("removed.txt").unlink()
print("mutated staged workspace")
""".strip()


def _mutation_command() -> str:
    return "python -c " + shlex.quote(MUTATION_CODE)


def _make_world_writable(path: Path) -> None:
    path.chmod(
        path.stat().st_mode
        | stat.S_IRUSR
        | stat.S_IWUSR
        | stat.S_IXUSR
        | stat.S_IRGRP
        | stat.S_IWGRP
        | stat.S_IXGRP
        | stat.S_IROTH
        | stat.S_IWOTH
        | stat.S_IXOTH
    )


def _seed_host_project(host_project: Path) -> None:
    host_project.mkdir(parents=True)
    _make_world_writable(host_project)

    files = {
        "kept.txt": "host\n",
        "removed.txt": "remove me\n",
    }
    for name, content in files.items():
        path = host_project / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o666)


async def _run_mutating_project_command(
    manager: SandboxManager,
    *,
    host_project: Path,
    sync_back: bool,
    timeout: int,
) -> SandboxResult:
    return await manager.execute_project_command(
        command=_mutation_command(),
        project_path=str(host_project),
        timeout=timeout,
        environment={},
        network_mode="none",
        read_only=False,
        sync_back=sync_back,
    )


def _require_success(result: SandboxResult, check_name: str) -> None:
    if result.success:
        return
    details = result.error or result.output or f"exit code {result.exit_code}"
    raise SandboxDockerSmokeError(f"{check_name} failed: {details}")


def _require_host_state(host_project: Path, expected_kept: str, *, created: bool, removed: bool) -> None:
    kept = (host_project / "kept.txt").read_text(encoding="utf-8")
    if kept != expected_kept:
        raise SandboxDockerSmokeError(
            f"Expected kept.txt to contain {expected_kept!r}, got {kept!r}"
        )

    if (host_project / "created.txt").exists() != created:
        state = "exist" if created else "remain absent"
        raise SandboxDockerSmokeError(f"Expected created.txt to {state}")

    if (host_project / "removed.txt").exists() != removed:
        state = "exist" if removed else "be deleted"
        raise SandboxDockerSmokeError(f"Expected removed.txt to {state}")


async def verify_docker_sandbox(
    manager: SandboxManager,
    *,
    timeout: int = 20,
    temp_parent: Path | None = None,
) -> dict[str, Any]:
    """Run the optional real-Docker staged workspace smoke check."""
    if not manager.is_sandbox_ready():
        return {
            "status": "skipped",
            "reason": "Docker sandbox or image is not ready",
        }

    parent = temp_parent or Path.home() / ".cache" / "dgm-sandbox-smoke"
    parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="sync-", dir=str(parent)) as temp_dir:
        host_project = Path(temp_dir) / "project"
        _seed_host_project(host_project)
        result = await _run_mutating_project_command(
            manager,
            host_project=host_project,
            sync_back=True,
            timeout=timeout,
        )
        _require_success(result, "sync-back smoke")
        _require_host_state(host_project, "sandbox\n", created=True, removed=False)

    with tempfile.TemporaryDirectory(prefix="discard-", dir=str(parent)) as temp_dir:
        host_project = Path(temp_dir) / "project"
        _seed_host_project(host_project)
        result = await _run_mutating_project_command(
            manager,
            host_project=host_project,
            sync_back=False,
            timeout=timeout,
        )
        _require_success(result, "discard-changes smoke")
        _require_host_state(host_project, "host\n", created=False, removed=True)

    return {
        "status": "ok",
        "checks": [
            "docker_sync_back_mirrors_staged_writes",
            "docker_discard_changes_preserves_host_checkout",
        ],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument(
        "--build-image",
        action="store_true",
        help="Build the sandbox image if it is missing before running the smoke check.",
    )
    parser.add_argument(
        "--require",
        action="store_true",
        help="Exit non-zero instead of skipping when Docker or the image is unavailable.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of human-readable status lines.",
    )
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    manager = SandboxManager(
        SandboxConfig(
            timeout=args.timeout,
            network_mode="none",
            auto_build_image=args.build_image,
        )
    )
    try:
        result = await verify_docker_sandbox(manager, timeout=args.timeout)
    except SandboxDockerSmokeError as exc:
        if args.json:
            print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        else:
            print(f"[fail] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result["status"] == "skipped":
        print(f"[skip] {result['reason']}")
    else:
        for check in result["checks"]:
            print(f"[ok] {check}")
        print("Docker sandbox smoke verified.")

    if result["status"] == "skipped" and args.require:
        return 1
    return 0


def main() -> int:
    parser = _build_parser()
    return asyncio.run(_main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
