from pathlib import Path

import pytest

from sandbox.sandbox_manager import SandboxResult
from scripts.verify_sandbox_docker import (
    SandboxDockerSmokeError,
    verify_docker_sandbox,
)


class NotReadyManager:
    def is_sandbox_ready(self):
        return False


@pytest.mark.asyncio
async def test_verify_docker_sandbox_skips_when_not_ready(tmp_path):
    result = await verify_docker_sandbox(NotReadyManager(), temp_parent=tmp_path)

    assert result == {
        "status": "skipped",
        "reason": "Docker sandbox or image is not ready",
    }


@pytest.mark.asyncio
async def test_verify_docker_sandbox_checks_sync_and_discard_paths(tmp_path):
    class MutatingManager:
        def __init__(self):
            self.calls = []

        def is_sandbox_ready(self):
            return True

        async def execute_project_command(self, **kwargs):
            self.calls.append(kwargs)
            project = Path(kwargs["project_path"])
            if kwargs["sync_back"]:
                (project / "kept.txt").write_text("sandbox\n", encoding="utf-8")
                (project / "created.txt").write_text("created\n", encoding="utf-8")
                (project / "removed.txt").unlink()
            return SandboxResult(success=True, output="ok\n", exit_code=0)

    manager = MutatingManager()

    result = await verify_docker_sandbox(manager, temp_parent=tmp_path)

    assert result == {
        "status": "ok",
        "checks": [
            "docker_sync_back_mirrors_staged_writes",
            "docker_discard_changes_preserves_host_checkout",
        ],
    }
    assert [call["sync_back"] for call in manager.calls] == [True, False]
    assert all(call["network_mode"] == "none" for call in manager.calls)


@pytest.mark.asyncio
async def test_verify_docker_sandbox_reports_failed_container_result(tmp_path):
    class FailingManager:
        def is_sandbox_ready(self):
            return True

        async def execute_project_command(self, **kwargs):
            return SandboxResult(success=False, output="", error="boom", exit_code=1)

    with pytest.raises(SandboxDockerSmokeError, match="sync-back smoke failed: boom"):
        await verify_docker_sandbox(FailingManager(), temp_parent=tmp_path)
