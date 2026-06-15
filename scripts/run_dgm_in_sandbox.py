#!/usr/bin/env python3
"""Run the DGM controller process inside the Docker sandbox."""

from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import sys
from pathlib import Path
from typing import List, Mapping, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sandbox_manager import SandboxConfig, SandboxManager, SandboxResult


class SandboxRunError(RuntimeError):
    """Raised when the sandboxed DGM runner cannot start safely."""


def _project_relative(path: Path, project_root: Path) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        path = project_root / path
    try:
        return path.resolve().relative_to(project_root.resolve())
    except ValueError as exc:
        raise SandboxRunError(
            f"{path} is outside project root {project_root}; mount it through config first"
        ) from exc


def build_dgm_command(config_path: Path, generations: int, project_root: Path) -> str:
    """Build the command executed inside the mounted project workspace."""
    relative_config = _project_relative(config_path, project_root)
    return (
        "python run_dgm.py "
        f"--config {shlex.quote(str(relative_config))} "
        f"--generations {generations}"
    )


def load_sandbox_config(config_path: Path, timeout: Optional[int] = None) -> SandboxConfig:
    """Load SandboxConfig fields from a DGM YAML config."""
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    sandbox_data = data.get("sandbox", {})
    kwargs = {
        key: value
        for key, value in sandbox_data.items()
        if key in SandboxConfig.__dataclass_fields__
    }
    if timeout is not None:
        kwargs["timeout"] = timeout
    return SandboxConfig(**kwargs)


def collect_environment(
    names: List[str],
    environ: Mapping[str, str] = os.environ,
) -> dict[str, str]:
    """Collect explicitly requested environment variables for the container."""
    selected: dict[str, str] = {}
    missing = []
    for name in names:
        if name not in environ or environ[name] == "":
            missing.append(name)
        else:
            selected[name] = environ[name]
    if missing:
        raise SandboxRunError(
            "Requested environment variables are not set: " + ", ".join(sorted(missing))
        )
    return selected


def validate_environment_pass_through(env_names: List[str], allow_network: bool) -> None:
    """Require explicit network opt-in before passing host environment values."""
    if env_names and not allow_network:
        raise SandboxRunError(
            "Refusing to pass environment variables without --allow-network; "
            "rerun without --env or add --allow-network for live provider calls"
        )


def resolve_network_mode(allow_network: bool, requested_network_mode: str) -> str:
    """Resolve Docker networking for full-process runs.

    The full-process runner keeps network access off unless the caller opts in
    with ``--allow-network``. This prevents a permissive project config from
    silently enabling live network access.
    """
    return requested_network_mode if allow_network else "none"


async def run_sandboxed_dgm(
    *,
    config_path: Path,
    generations: int,
    project_root: Path = PROJECT_ROOT,
    env_names: Optional[List[str]] = None,
    allow_network: bool = False,
    network_mode: str = "bridge",
    timeout: Optional[int] = None,
    sync_back: bool = True,
    manager: Optional[SandboxManager] = None,
) -> SandboxResult:
    """
    Run ``run_dgm.py`` as a whole process inside Docker.

    The project is mounted as the sandbox workspace. Live provider calls require
    both ``allow_network=True`` and explicit ``env_names`` for provider secrets.
    """
    config_path = (project_root / config_path).resolve() if not config_path.is_absolute() else config_path.resolve()
    project_root = project_root.resolve()
    command = build_dgm_command(config_path, generations, project_root)
    validate_environment_pass_through(env_names or [], allow_network)
    environment = collect_environment(env_names or [])
    sandbox_config = load_sandbox_config(config_path, timeout=timeout)
    manager = manager or SandboxManager(sandbox_config)

    if not manager.is_sandbox_ready():
        raise SandboxRunError("Docker sandbox is not ready; cannot run full DGM process")

    return await manager.execute_project_command(
        command=command,
        project_path=str(project_root),
        timeout=timeout or sandbox_config.timeout,
        environment=environment,
        network_mode=resolve_network_mode(allow_network, network_mode),
        read_only=False,
        sync_back=sync_back,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/dgm_config.yaml")
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument("--timeout", type=int, help="Container timeout in seconds.")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Environment variable name to pass into the container. Repeat as needed.",
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow container network access for live provider calls.",
    )
    parser.add_argument(
        "--network-mode",
        default="bridge",
        help="Docker network mode used only with --allow-network.",
    )
    parser.add_argument(
        "--discard-changes",
        action="store_true",
        help=(
            "Run in the staged sandbox workspace but do not sync successful "
            "writes/deletes back to the host checkout."
        ),
    )
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    try:
        result = await run_sandboxed_dgm(
            config_path=Path(args.config),
            generations=args.generations,
            project_root=Path(args.project_root),
            env_names=args.env,
            allow_network=args.allow_network,
            network_mode=args.network_mode,
            timeout=args.timeout,
            sync_back=not args.discard_changes,
        )
    except SandboxRunError as exc:
        print(f"[fail] {exc}", file=sys.stderr)
        return 1

    if result.output:
        print(result.output, end="" if result.output.endswith("\n") else "\n")
    if result.error:
        print(result.error, file=sys.stderr, end="" if result.error.endswith("\n") else "\n")
    return 0 if result.success else result.exit_code or 1


def main() -> int:
    parser = _build_parser()
    return asyncio.run(_main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
