from pathlib import Path

import pytest

from sandbox.sandbox_manager import SandboxConfig, SandboxManager, SandboxResult
from scripts.run_dgm_in_sandbox import (
    SandboxRunError,
    _main_async,
    _build_parser,
    build_run_audit,
    build_dgm_command,
    collect_environment,
    format_run_audit,
    load_sandbox_config,
    resolve_network_mode,
    run_sandboxed_dgm,
    validate_environment_pass_through,
)


def test_build_dgm_command_uses_project_relative_config(tmp_path):
    project_root = tmp_path / "project"
    config = project_root / "config" / "dgm_config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("sandbox: {}\n")

    command = build_dgm_command(config, generations=2, project_root=project_root)

    assert command == "python run_dgm.py --config config/dgm_config.yaml --generations 2"


def test_build_dgm_command_rejects_config_outside_project(tmp_path):
    project_root = tmp_path / "project"
    outside_config = tmp_path / "dgm_config.yaml"
    project_root.mkdir()
    outside_config.write_text("sandbox: {}\n")

    with pytest.raises(SandboxRunError, match="outside project root"):
        build_dgm_command(outside_config, generations=1, project_root=project_root)


def test_collect_environment_requires_explicit_existing_values():
    env = {"ANTHROPIC_API_KEY": "secret"}

    assert collect_environment(["ANTHROPIC_API_KEY"], env) == {
        "ANTHROPIC_API_KEY": "secret"
    }
    with pytest.raises(SandboxRunError, match="not set"):
        collect_environment(["GEMINI_API_KEY"], env)


def test_validate_environment_pass_through_requires_network_opt_in():
    validate_environment_pass_through([], allow_network=False)
    validate_environment_pass_through(["ANTHROPIC_API_KEY"], allow_network=True)

    with pytest.raises(SandboxRunError, match="without --allow-network"):
        validate_environment_pass_through(["ANTHROPIC_API_KEY"], allow_network=False)


def test_resolve_network_mode_requires_explicit_allow_network():
    assert resolve_network_mode(False, "bridge") == "none"
    assert resolve_network_mode(True, "bridge") == "bridge"


def test_run_audit_summarizes_flags_without_secret_values(tmp_path):
    project_root = tmp_path / "project"
    config = project_root / "config" / "dgm_config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("sandbox: {}\n", encoding="utf-8")

    audit = build_run_audit(
        config_path=config,
        generations=2,
        project_root=project_root,
        env_names=["ANTHROPIC_API_KEY"],
        allow_network=True,
        network_mode="bridge",
        timeout=12,
        sync_back=False,
        sandbox_config=SandboxConfig(timeout=300),
    )
    text = format_run_audit(audit)

    assert audit["config"] == "config/dgm_config.yaml"
    assert audit["env_names"] == ["ANTHROPIC_API_KEY"]
    assert audit["env_values"] == "hidden"
    assert audit["sync_mode"] == "discard-changes"
    assert "ANTHROPIC_API_KEY" in text
    assert "env_values=hidden" in text
    assert "secret" not in text.lower()


def test_load_sandbox_config_reads_project_config(tmp_path):
    config = tmp_path / "dgm_config.yaml"
    config.write_text(
        """
sandbox:
  image_name: custom-image
  memory_limit: 1g
  cpu_limit: "0.5"
  network_mode: none
""",
        encoding="utf-8",
    )

    sandbox_config = load_sandbox_config(config, timeout=12)

    assert sandbox_config.image_name == "custom-image"
    assert sandbox_config.memory_limit == "1g"
    assert sandbox_config.cpu_limit == "0.5"
    assert sandbox_config.timeout == 12


def test_parser_exposes_discard_changes_flag():
    args = _build_parser().parse_args(["--discard-changes"])

    assert args.discard_changes is True


def test_project_tree_copy_skips_local_caches(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    (source / "run_dgm.py").write_text("print('ok')\n")
    (source / ".venv").mkdir()
    (source / ".venv" / "ignored.py").write_text("ignored\n")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "ignored.pyc").write_text("ignored\n")

    SandboxManager._copy_project_tree(source, destination)

    assert (destination / "run_dgm.py").exists()
    assert not (destination / ".venv").exists()
    assert not (destination / "__pycache__").exists()


def test_project_tree_sync_propagates_deletes_and_preserves_ignored(tmp_path):
    staged = tmp_path / "staged"
    host = tmp_path / "host"
    staged.mkdir()
    host.mkdir()

    (staged / "kept.txt").write_text("updated\n")
    (staged / "new.txt").write_text("new\n")
    (staged / "nested").mkdir()
    (staged / "nested" / "inside.txt").write_text("inside\n")

    (host / "kept.txt").write_text("old\n")
    (host / "removed.txt").write_text("remove me\n")
    (host / "nested").mkdir()
    (host / "nested" / "old.txt").write_text("remove me\n")
    (host / ".git").mkdir()
    (host / ".git" / "HEAD").write_text("preserve\n")
    (host / ".venv").mkdir()
    (host / ".venv" / "local.py").write_text("preserve\n")

    SandboxManager._sync_project_tree(staged, host)

    assert (host / "kept.txt").read_text() == "updated\n"
    assert (host / "new.txt").read_text() == "new\n"
    assert not (host / "removed.txt").exists()
    assert not (host / "nested" / "old.txt").exists()
    assert (host / "nested" / "inside.txt").read_text() == "inside\n"
    assert (host / ".git" / "HEAD").read_text() == "preserve\n"
    assert (host / ".venv" / "local.py").read_text() == "preserve\n"


@pytest.mark.asyncio
async def test_execute_project_command_can_discard_staged_changes(tmp_path):
    class MutatingSandboxManager(SandboxManager):
        async def execute_in_sandbox(self, *args, **kwargs):
            workspace = Path(kwargs["workspace_path"])
            (workspace / "kept.txt").write_text("sandbox\n")
            (workspace / "created.txt").write_text("created\n")
            (workspace / "removed.txt").unlink()
            return SandboxResult(success=True, output="mutated\n", exit_code=0)

    def seed_host_project(host: Path) -> None:
        host.mkdir()
        (host / "kept.txt").write_text("host\n")
        (host / "removed.txt").write_text("remove me\n")

    synced = tmp_path / "synced"
    seed_host_project(synced)
    sync_result = await MutatingSandboxManager(SandboxConfig()).execute_project_command(
        command="mutate staged workspace",
        project_path=str(synced),
        sync_back=True,
    )

    assert sync_result.success is True
    assert (synced / "kept.txt").read_text() == "sandbox\n"
    assert (synced / "created.txt").read_text() == "created\n"
    assert not (synced / "removed.txt").exists()

    discarded = tmp_path / "discarded"
    seed_host_project(discarded)
    discard_result = await MutatingSandboxManager(SandboxConfig()).execute_project_command(
        command="mutate staged workspace",
        project_path=str(discarded),
        sync_back=False,
    )

    assert discard_result.success is True
    assert (discarded / "kept.txt").read_text() == "host\n"
    assert not (discarded / "created.txt").exists()
    assert (discarded / "removed.txt").read_text() == "remove me\n"


@pytest.mark.asyncio
async def test_run_sandboxed_dgm_invokes_project_command(tmp_path):
    project_root = tmp_path / "project"
    config = project_root / "config" / "dgm_config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("sandbox:\n  network_mode: none\n", encoding="utf-8")

    class FakeManager:
        def __init__(self):
            self.calls = []
            self.config = SandboxConfig(working_dir="/home/dgm_agent/workspace")

        def is_sandbox_ready(self):
            return True

        async def execute_project_command(self, **kwargs):
            self.calls.append(kwargs)
            return SandboxResult(success=True, output="ok\n", exit_code=0)

    manager = FakeManager()
    result = await run_sandboxed_dgm(
        config_path=config,
        generations=2,
        project_root=project_root,
        env_names=[],
        manager=manager,
    )

    assert result.success is True
    assert manager.calls == [
        {
            "command": "python run_dgm.py --config config/dgm_config.yaml --generations 2",
            "project_path": str(project_root.resolve()),
            "timeout": 300,
            "environment": {},
            "network_mode": "none",
            "read_only": False,
            "sync_back": True,
        }
    ]


@pytest.mark.asyncio
async def test_run_sandboxed_dgm_ignores_configured_network_without_opt_in(tmp_path):
    project_root = tmp_path / "project"
    config = project_root / "config" / "dgm_config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("sandbox:\n  network_mode: bridge\n", encoding="utf-8")

    class FakeManager:
        def __init__(self):
            self.calls = []

        def is_sandbox_ready(self):
            return True

        async def execute_project_command(self, **kwargs):
            self.calls.append(kwargs)
            return SandboxResult(success=True, output="ok\n", exit_code=0)

    manager = FakeManager()
    await run_sandboxed_dgm(
        config_path=config,
        generations=1,
        project_root=project_root,
        env_names=[],
        allow_network=False,
        manager=manager,
    )

    assert manager.calls[0]["network_mode"] == "none"


@pytest.mark.asyncio
async def test_run_sandboxed_dgm_uses_requested_network_with_opt_in(tmp_path):
    project_root = tmp_path / "project"
    config = project_root / "config" / "dgm_config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("sandbox:\n  network_mode: none\n", encoding="utf-8")

    class FakeManager:
        def __init__(self):
            self.calls = []

        def is_sandbox_ready(self):
            return True

        async def execute_project_command(self, **kwargs):
            self.calls.append(kwargs)
            return SandboxResult(success=True, output="ok\n", exit_code=0)

    manager = FakeManager()
    await run_sandboxed_dgm(
        config_path=config,
        generations=1,
        project_root=project_root,
        env_names=[],
        allow_network=True,
        network_mode="bridge",
        manager=manager,
    )

    assert manager.calls[0]["network_mode"] == "bridge"


@pytest.mark.asyncio
async def test_run_sandboxed_dgm_rejects_env_without_network_opt_in(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    config = project_root / "config" / "dgm_config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("sandbox:\n  network_mode: none\n", encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")

    class FakeManager:
        def __init__(self):
            self.calls = []

        def is_sandbox_ready(self):
            return True

        async def execute_project_command(self, **kwargs):
            self.calls.append(kwargs)
            return SandboxResult(success=True, output="ok\n", exit_code=0)

    manager = FakeManager()

    with pytest.raises(SandboxRunError, match="without --allow-network"):
        await run_sandboxed_dgm(
            config_path=config,
            generations=1,
            project_root=project_root,
            env_names=["ANTHROPIC_API_KEY"],
            allow_network=False,
            manager=manager,
        )

    assert manager.calls == []


@pytest.mark.asyncio
async def test_run_sandboxed_dgm_passes_env_with_network_opt_in(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    config = project_root / "config" / "dgm_config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("sandbox:\n  network_mode: none\n", encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")

    class FakeManager:
        def __init__(self):
            self.calls = []

        def is_sandbox_ready(self):
            return True

        async def execute_project_command(self, **kwargs):
            self.calls.append(kwargs)
            return SandboxResult(success=True, output="ok\n", exit_code=0)

    manager = FakeManager()
    await run_sandboxed_dgm(
        config_path=config,
        generations=1,
        project_root=project_root,
        env_names=["ANTHROPIC_API_KEY"],
        allow_network=True,
        network_mode="bridge",
        manager=manager,
    )

    assert manager.calls[0]["environment"] == {"ANTHROPIC_API_KEY": "secret"}
    assert manager.calls[0]["network_mode"] == "bridge"


@pytest.mark.asyncio
async def test_run_sandboxed_dgm_can_discard_successful_changes(tmp_path):
    project_root = tmp_path / "project"
    config = project_root / "config" / "dgm_config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("sandbox:\n  network_mode: none\n", encoding="utf-8")

    class FakeManager:
        def __init__(self):
            self.calls = []

        def is_sandbox_ready(self):
            return True

        async def execute_project_command(self, **kwargs):
            self.calls.append(kwargs)
            return SandboxResult(success=True, output="ok\n", exit_code=0)

    manager = FakeManager()
    result = await run_sandboxed_dgm(
        config_path=config,
        generations=1,
        project_root=project_root,
        env_names=[],
        sync_back=False,
        manager=manager,
    )

    assert result.success is True
    assert manager.calls[0]["sync_back"] is False


@pytest.mark.asyncio
async def test_run_sandboxed_dgm_requires_ready_sandbox(tmp_path):
    project_root = tmp_path / "project"
    config = project_root / "config" / "dgm_config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("sandbox: {}\n", encoding="utf-8")

    class NotReadyManager:
        def is_sandbox_ready(self):
            return False

    with pytest.raises(SandboxRunError, match="not ready"):
        await run_sandboxed_dgm(
            config_path=config,
            generations=1,
            project_root=project_root,
            manager=NotReadyManager(),
        )


@pytest.mark.asyncio
async def test_main_prints_non_secret_audit(monkeypatch, tmp_path, capsys):
    from scripts import run_dgm_in_sandbox as sandbox_cli

    project_root = tmp_path / "project"
    config = project_root / "config" / "dgm_config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("sandbox:\n  timeout: 30\n", encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-value")

    async def fake_run_sandboxed_dgm(**kwargs):
        return SandboxResult(success=True, output="ok\n", exit_code=0)

    monkeypatch.setattr(sandbox_cli, "run_sandboxed_dgm", fake_run_sandboxed_dgm)
    args = _build_parser().parse_args([
        "--project-root",
        str(project_root),
        "--config",
        "config/dgm_config.yaml",
        "--generations",
        "1",
        "--allow-network",
        "--env",
        "ANTHROPIC_API_KEY",
        "--discard-changes",
    ])

    exit_code = await _main_async(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == "ok\n"
    assert "[audit] full-process sandbox run" in captured.err
    assert "network_mode=bridge" in captured.err
    assert "env_names=ANTHROPIC_API_KEY" in captured.err
    assert "env_values=hidden" in captured.err
    assert "sync_mode=discard-changes" in captured.err
    assert "secret-value" not in captured.err
