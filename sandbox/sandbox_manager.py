"""Docker-backed sandbox manager for isolated command execution.

The docker SDK import is deferred so that missing the optional ``docker``
package does not crash the entire program at startup. Callers can check
``is_docker_available()`` and fall back to direct subprocess execution.
"""

import asyncio
import os
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path

# Lazy / optional docker import — do NOT import at module level so the whole
# program doesn't crash when the docker SDK is missing.
docker = None
try:
    import docker as _docker
    docker = _docker
except ImportError:
    docker = None


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution."""
    image_name: str = "dgm-sandbox"
    memory_limit: str = "2g"
    cpu_limit: str = "1"
    timeout: int = 300
    network_mode: str = "none"
    working_dir: str = "/home/dgm_agent/workspace"
    auto_build_image: bool = True


@dataclass
class SandboxResult:
    """Result of sandbox execution."""
    success: bool
    output: str
    error: Optional[str] = None
    exit_code: Optional[int] = None
    execution_time: Optional[float] = None


class SandboxManager:
    """Manager for Docker-based command execution."""

    def __init__(self, config: SandboxConfig = None):
        """
        Initialize the sandbox manager.

        Args:
            config: Sandbox configuration
        """
        self.config = config or SandboxConfig()
        self.docker_client = None  # Initialised lazily when/if docker is needed

    def _get_client(self):
        """Return a cached docker client, creating it on first use."""
        self._require_docker()
        if self.docker_client is None:
            self.docker_client = self._create_docker_client()
        return self.docker_client

    def _create_docker_client(self):
        """Create a Docker client, including common local context fallbacks."""
        candidates = [docker.from_env]
        for socket_path in self._candidate_socket_paths():
            candidates.append(
                lambda socket_path=socket_path: docker.DockerClient(
                    base_url=f"unix://{socket_path}"
                )
            )

        last_error = None
        for make_client in candidates:
            client = None
            try:
                client = make_client()
                client.ping()
                return client
            except Exception as exc:
                last_error = exc
                if client is not None:
                    try:
                        client.close()
                    except Exception:
                        pass

        raise RuntimeError(f"Docker daemon is not reachable: {last_error}")

    @staticmethod
    def _candidate_socket_paths() -> List[Path]:
        """Return common Docker socket paths not always exposed via DOCKER_HOST."""
        paths: List[Path] = []
        docker_host = os.environ.get("DOCKER_HOST", "")
        if docker_host.startswith("unix://"):
            paths.append(Path(docker_host.removeprefix("unix://")))

        home = Path.home()
        paths.extend([
            home / ".docker" / "run" / "docker.sock",
            home / ".colima" / "default" / "docker.sock",
            Path("/var/run/docker.sock"),
        ])

        seen = set()
        existing_paths = []
        for path in paths:
            resolved = path.expanduser()
            if resolved in seen or not resolved.exists():
                continue
            seen.add(resolved)
            existing_paths.append(resolved)
        return existing_paths

    def _require_docker(self):
        """Raise a clear error if the docker SDK is not installed."""
        if docker is None:
            raise ImportError(
                "The 'docker' package is required to use SandboxManager but it "
                "is not installed. Install it with `pip install docker`, or use "
                "direct subprocess execution (use_sandbox=False) instead."
            )

    @staticmethod
    def _cpu_limit_to_nano_cpus(cpu_limit: str) -> Optional[int]:
        """Convert a Docker-style CPU count string into nano CPUs."""
        try:
            value = float(cpu_limit)
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        return int(value * 1_000_000_000)

    async def execute_in_sandbox(
        self,
        command: str,
        agent_code_path: Optional[str] = None,
        workspace_path: Optional[str] = None,
        timeout: Optional[int] = None
    ) -> SandboxResult:
        """Execute a shell command inside a one-shot Docker container."""
        return await asyncio.to_thread(
            self._execute_in_sandbox_sync,
            command,
            agent_code_path,
            workspace_path,
            timeout,
        )

    async def create_sandbox_environment(self, agent_id: str) -> str:
        """Create a stopped container and return its id."""
        client = self._get_client()
        container = await asyncio.to_thread(
            client.containers.create,
            image=self.config.image_name,
            command=["/bin/bash", "-lc", "sleep infinity"],
            name=None,
            detach=True,
            working_dir=self.config.working_dir,
            mem_limit=self.config.memory_limit,
            nano_cpus=self._cpu_limit_to_nano_cpus(self.config.cpu_limit),
            network_mode=self.config.network_mode,
            labels={"dgm_agent_id": agent_id},
        )
        return container.id

    async def cleanup_sandbox(self, container_id: str) -> None:
        """Remove a sandbox container if it still exists."""
        client = self._get_client()

        def _remove() -> None:
            container = client.containers.get(container_id)
            try:
                container.remove(force=True)
            except Exception:
                pass

        await asyncio.to_thread(_remove)

    def build_sandbox_image(self) -> bool:
        """Build the local sandbox image from ``sandbox/Dockerfile``."""
        client = self._get_client()
        project_root = Path(__file__).resolve().parents[1]
        client.images.build(
            path=str(project_root),
            dockerfile="sandbox/Dockerfile",
            tag=self.config.image_name,
            rm=True,
        )
        return True

    def ensure_sandbox_image(self) -> bool:
        """
        Ensure the configured image exists.

        Returns True when this call built the image, False when it already
        existed.
        """
        client = self._get_client()
        try:
            client.images.get(self.config.image_name)
            return False
        except Exception as exc:
            if docker is None or not isinstance(exc, docker.errors.ImageNotFound):
                raise
            if not self.config.auto_build_image:
                raise
            self.build_sandbox_image()
            return True

    def is_docker_available(self) -> bool:
        """
        Check if Docker is available and accessible.

        Returns:
            bool: True if Docker SDK is installed and daemon is reachable.
        """
        if docker is None:
            return False
        try:
            self._get_client()
            return True
        except Exception:
            return False

    def is_sandbox_ready(self) -> bool:
        """
        Check whether Docker is reachable and the configured image is available.

        This is the readiness predicate callers should use before opting into
        sandbox execution. It includes the image build/presence check so callers
        can fall back consistently when Docker is installed but the configured
        sandbox image cannot be built or found.
        """
        if not self.is_docker_available():
            return False
        try:
            self.ensure_sandbox_image()
            return True
        except Exception:
            return False

    def _execute_in_sandbox_sync(
        self,
        command: str,
        agent_code_path: Optional[str],
        workspace_path: Optional[str],
        timeout: Optional[int],
    ) -> SandboxResult:
        """Synchronous Docker execution body used via ``asyncio.to_thread``."""
        client = self._get_client()
        effective_timeout = timeout or self.config.timeout
        started_at = time.time()
        container = None

        volumes: Dict[str, Dict[str, str]] = {}
        if workspace_path:
            workspace = Path(workspace_path).resolve()
            volumes[str(workspace)] = {
                "bind": self.config.working_dir,
                "mode": "rw",
            }

        if agent_code_path:
            agent_code = Path(agent_code_path).resolve()
            agent_mount = agent_code if agent_code.is_dir() else agent_code.parent
            volumes[str(agent_mount)] = {
                "bind": "/home/dgm_agent/agent_code",
                "mode": "ro",
            }

        try:
            container = client.containers.run(
                image=self.config.image_name,
                command=["/bin/bash", "-lc", command],
                detach=True,
                working_dir=self.config.working_dir,
                volumes=volumes,
                mem_limit=self.config.memory_limit,
                nano_cpus=self._cpu_limit_to_nano_cpus(self.config.cpu_limit),
                network_mode=self.config.network_mode,
            )
            wait_result = container.wait(timeout=effective_timeout)
            exit_code = wait_result.get("StatusCode", 1)
            output = container.logs(stdout=True, stderr=False).decode(
                "utf-8",
                errors="replace",
            )
            error = container.logs(stdout=False, stderr=True).decode(
                "utf-8",
                errors="replace",
            ) or None
            return SandboxResult(
                success=exit_code == 0,
                output=output,
                error=error,
                exit_code=exit_code,
                execution_time=time.time() - started_at,
            )
        except Exception as exc:
            if container is not None:
                try:
                    container.kill()
                except Exception:
                    pass
            return SandboxResult(
                success=False,
                output="",
                error=f"Sandbox execution failed or timed out after {effective_timeout}s: {exc}",
                exit_code=None,
                execution_time=time.time() - started_at,
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
