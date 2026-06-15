"""
Bash tool implementation for executing shell commands.

This tool allows the DGM agent to execute bash commands in a controlled manner,
with safety restrictions and timeout handling.
"""

import asyncio
import os
import re
import shutil
import shlex
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, List
import time

from .base_tool import BaseTool, ToolResult, ToolExecutionStatus, ToolParameter


class BashTool(BaseTool):
    """
    Tool for executing bash commands with safety restrictions.
    
    This tool provides the agent with the ability to run shell commands,
    execute scripts, and interact with the file system. It includes safety
    measures to prevent dangerous operations.
    """
    
    def __init__(
        self,
        working_directory: str = None,
        timeout: int = 30,
        sandbox_manager: Any = None,
        use_sandbox: bool = False,
    ):
        """
        Initialize the Bash tool.
        
        Args:
            working_directory: Directory to execute commands in
            timeout: Default timeout for command execution
            sandbox_manager: Optional Docker sandbox manager for command execution
            use_sandbox: Whether to execute commands through the sandbox when available
        """
        self.working_directory = working_directory or os.getcwd()
        self.default_timeout = timeout
        self.sandbox_manager = sandbox_manager
        self.use_sandbox = use_sandbox
        
        # Commands that are blocked for safety
        self.blocked_commands = {
            'rm', 'rmdir', 'del', 'delete', 'format', 'fdisk',
            'mkfs', 'dd', 'sudo', 'su', 'passwd', 'chown', 'chmod',
            'kill', 'killall', 'shutdown', 'reboot', 'halt',
            'iptables', 'ufw', 'firewall-cmd', 'netsh'
        }
        
        # Commands that require special handling
        self.restricted_commands = {
            'cd': self._handle_cd,
            'pwd': self._handle_pwd,
            'ls': self._handle_ls,
            'cat': self._handle_cat,
            'echo': self._handle_echo
        }
        
        super().__init__()

    def _sanitized_environment(self) -> Dict[str, str]:
        """Return the process environment without credential-like variables."""
        sensitive_terms = ("key", "token", "secret", "password", "credential")
        return {
            key: value
            for key, value in os.environ.items()
            if not any(term in key.lower() for term in sensitive_terms)
        }

    def _can_use_sandbox(self) -> bool:
        """Return True when sandboxed command execution is configured."""
        if not self.use_sandbox or self.sandbox_manager is None:
            return False
        readiness_check = getattr(self.sandbox_manager, "is_sandbox_ready", None)
        if readiness_check is not None:
            return bool(readiness_check())
        availability_check = getattr(self.sandbox_manager, "is_docker_available", None)
        if availability_check is None:
            return True
        if not bool(availability_check()):
            return False
        ensure_image = getattr(self.sandbox_manager, "ensure_sandbox_image", None)
        if ensure_image is not None:
            try:
                ensure_image()
            except Exception:
                return False
        return True
    
    def get_name(self) -> str:
        """Get the name of this tool."""
        return "bash"
    
    def get_description(self) -> str:
        """Get a description of what this tool does."""
        return ("Execute bash/shell commands with safety restrictions. "
                "Can run most common commands but blocks dangerous operations "
                "like file deletion, system modification, and network changes.")
    
    def get_parameters(self) -> List[ToolParameter]:
        """Get the parameters this tool accepts."""
        return [
            ToolParameter(
                name="command",
                type="string",
                description="The bash command to execute",
                required=True
            ),
            ToolParameter(
                name="timeout",
                type="integer",
                description="Timeout in seconds (default: 30, max: 300)",
                required=False,
                default=30
            ),
            ToolParameter(
                name="capture_output",
                type="boolean",
                description="Whether to capture and return command output",
                required=False,
                default=True
            )
        ]
    
    def get_timeout(self) -> int:
        """Get the default timeout for this tool."""
        return self.default_timeout
    
    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """
        Execute a bash command with the given parameters.
        
        Args:
            parameters: Dictionary containing 'command' and optional 'timeout'
            
        Returns:
            ToolResult: Result of the command execution
        """
        start_time = time.time()
        
        try:
            command = parameters["command"].strip()
            timeout = min(parameters.get("timeout", self.default_timeout), 300)  # Max 5 minutes
            capture_output = parameters.get("capture_output", True)
            
            # Safety check for empty commands
            if not command:
                return ToolResult(
                    status=ToolExecutionStatus.INVALID_PARAMS,
                    output="",
                    error="Command cannot be empty"
                )
            
            # Parse command to check for blocked operations
            safety_check = self._check_command_safety(command)
            if not safety_check["safe"]:
                return ToolResult(
                    status=ToolExecutionStatus.ERROR,
                    output="",
                    error=f"Command blocked for safety: {safety_check['reason']}"
                )
            
            # Handle special commands
            first_word = command.split()[0] if command.split() else ""
            if first_word in {"cd", "pwd"}:
                return await self.restricted_commands[first_word](command, timeout)

            if self._can_use_sandbox():
                result = await self._execute_sandbox_command(
                    command,
                    timeout,
                    capture_output,
                )
                result.execution_time = time.time() - start_time
                return result

            if first_word in self.restricted_commands:
                return await self.restricted_commands[first_word](command, timeout)
            
            # Execute the command
            result = await self._execute_command(command, timeout, capture_output)
            
            execution_time = time.time() - start_time
            result.execution_time = execution_time
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            return ToolResult(
                status=ToolExecutionStatus.ERROR,
                output="",
                error=f"Failed to execute command: {str(e)}",
                execution_time=execution_time
            )

    async def _execute_sandbox_command(
        self,
        command: str,
        timeout: int,
        capture_output: bool,
    ) -> ToolResult:
        """Execute a shell command through the configured Docker sandbox."""
        sandbox_temp_parent = Path.home() / ".cache" / "dgm-sandbox"
        sandbox_temp_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(sandbox_temp_parent)) as temp_dir:
            staged_workspace = Path(temp_dir)
            self._copy_workspace(
                source=Path(self.working_directory),
                destination=staged_workspace,
            )
            sandbox_result = await self.sandbox_manager.execute_in_sandbox(
                command=command,
                workspace_path=str(staged_workspace),
                timeout=timeout,
            )
            self._copy_workspace(
                source=staged_workspace,
                destination=Path(self.working_directory),
            )

        timed_out = (
            sandbox_result.exit_code is None
            and "timed out" in (sandbox_result.error or "").lower()
        )
        if sandbox_result.success:
            status = ToolExecutionStatus.SUCCESS
        elif timed_out:
            status = ToolExecutionStatus.TIMEOUT
        else:
            status = ToolExecutionStatus.ERROR

        return ToolResult(
            status=status,
            output=sandbox_result.output if capture_output else "",
            error=sandbox_result.error,
            metadata={
                "exit_code": sandbox_result.exit_code,
                "sandboxed": True,
            },
            execution_time=sandbox_result.execution_time,
        )

    @staticmethod
    def _copy_workspace(source: Path, destination: Path) -> None:
        """Copy workspace files while skipping generated Python cache files."""
        source = source.resolve()
        destination = destination.resolve()
        if not source.exists():
            destination.mkdir(parents=True, exist_ok=True)
            return

        def ignore(_dir: str, names: List[str]) -> set:
            return {
                name
                for name in names
                if name == "__pycache__" or name.endswith((".pyc", ".pyo"))
            }

        shutil.copytree(
            source,
            destination,
            dirs_exist_ok=True,
            ignore=ignore,
        )
    
    def _check_command_safety(self, command: str) -> Dict[str, Any]:
        """
        Check if a command is safe to execute.
        
        Args:
            command: Command to check
            
        Returns:
            Dict with 'safe' boolean and 'reason' if unsafe
        """
        # Parse command to get the first word (command name)
        try:
            parts = shlex.split(command)
            if not parts:
                return {"safe": False, "reason": "Empty command"}
            
            cmd_name = parts[0].split('/')[-1]  # Handle full paths
            
            # Check blocked commands
            if cmd_name in self.blocked_commands:
                return {"safe": False, "reason": f"Command '{cmd_name}' is blocked for safety"}
            
            # Check for dangerous patterns
            dangerous_patterns = ['>', '>>', '|', '&&', '||', ';', '$(', '`']
            for pattern in dangerous_patterns:
                if pattern in command and not self._is_safe_usage(command, pattern):
                    return {"safe": False, "reason": f"Pattern '{pattern}' requires careful review"}
            
            # Check for network commands
            network_commands = ['wget', 'curl', 'nc', 'netcat', 'ssh', 'scp', 'rsync']
            if cmd_name in network_commands:
                return {"safe": False, "reason": f"Network command '{cmd_name}' is restricted"}
            
            return {"safe": True, "reason": ""}
            
        except Exception as e:
            return {"safe": False, "reason": f"Failed to parse command: {str(e)}"}
    
    def _is_safe_usage(self, command: str, pattern: str) -> bool:
        """
        Check if a potentially dangerous pattern is used safely.

        For redirect operators (``>`` / ``>>``), the target path is resolved
        against the working directory and checked for containment — a relative
        path like ``../../outside`` will be blocked.

        Args:
            command: Full command
            pattern: Dangerous pattern found

        Returns:
            bool: True if usage appears safe
        """
        if pattern in [">", ">>"]:
            # Find redirect target: text after the operator.
            # Use a simple split on the operator (first occurrence only).
            idx = command.find(pattern)
            if idx == -1:
                return False
            output_file = command[idx + len(pattern):].strip().split()[0] if command[idx + len(pattern):].strip() else ""
            if not output_file:
                return False

            # Resolve the target against the working directory.
            wd = Path(self.working_directory).resolve()
            if Path(output_file).is_absolute():
                target = Path(output_file).resolve()
            else:
                target = (wd / output_file).resolve()

            # Containment check.
            try:
                contained = target.is_relative_to(wd)
            except AttributeError:  # pragma: no cover — Python < 3.9
                try:
                    contained = os.path.commonpath([str(target), str(wd)]) == str(wd)
                except ValueError:
                    contained = False

            return contained

        if pattern == "|":
            # Allow basic pipes to common safe commands.
            safe_pipe_targets = ["grep", "sort", "uniq", "head", "tail", "wc"]
            parts = command.split("|")
            if len(parts) == 2:
                target_cmd = parts[1].strip().split()[0] if parts[1].strip() else ""
                if target_cmd in safe_pipe_targets:
                    return True

        return False
    
    async def _execute_command(
        self,
        command: str,
        timeout: int,
        capture_output: bool,
    ) -> ToolResult:
        """
        Execute a shell command.

        The subprocess is started in its own process group (``start_new_session=True``).
        On timeout the entire process group is killed with SIGKILL so that child
        processes spawned by ``/bin/sh`` do not leak.

        Args:
            command: Command to execute
            timeout: Timeout in seconds
            capture_output: Whether to capture output

        Returns:
            ToolResult: Execution result
        """
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
                cwd=self.working_directory,
                env=self._sanitized_environment(),
                start_new_session=True,  # puts the shell in its own process group
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )

                stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
                stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

                if process.returncode == 0:
                    status = ToolExecutionStatus.SUCCESS
                    output = stdout_text
                    error = stderr_text if stderr_text else None
                else:
                    status = ToolExecutionStatus.ERROR
                    output = stdout_text
                    error = f"Command failed with exit code {process.returncode}: {stderr_text}"

                return ToolResult(
                    status=status,
                    output=output,
                    error=error,
                    metadata={"exit_code": process.returncode},
                )

            except asyncio.TimeoutError:
                # Kill the entire process group so child processes don't leak.
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass  # Process already exited.
                await process.wait()

                return ToolResult(
                    status=ToolExecutionStatus.TIMEOUT,
                    output="",
                    error=f"Command timed out after {timeout} seconds",
                )

        except Exception as e:
            return ToolResult(
                status=ToolExecutionStatus.ERROR,
                output="",
                error=f"Failed to execute command: {str(e)}",
            )
    
    # Special command handlers
    
    async def _handle_cd(self, command: str, timeout: int) -> ToolResult:
        """Handle cd command by updating working directory."""
        parts = command.split()
        if len(parts) == 1:
            # cd with no arguments goes to home
            new_dir = os.path.expanduser("~")
        else:
            new_dir = parts[1]
        
        try:
            # Resolve the path
            if not os.path.isabs(new_dir):
                new_dir = os.path.join(self.working_directory, new_dir)
            new_dir = os.path.abspath(new_dir)
            
            # Check if directory exists and is accessible
            if not os.path.exists(new_dir):
                return ToolResult(
                    status=ToolExecutionStatus.ERROR,
                    output="",
                    error=f"Directory does not exist: {new_dir}"
                )
            
            if not os.path.isdir(new_dir):
                return ToolResult(
                    status=ToolExecutionStatus.ERROR,
                    output="",
                    error=f"Not a directory: {new_dir}"
                )
            
            # Update working directory
            self.working_directory = new_dir
            
            return ToolResult(
                status=ToolExecutionStatus.SUCCESS,
                output=f"Changed directory to: {new_dir}",
                metadata={"new_directory": new_dir}
            )
            
        except Exception as e:
            return ToolResult(
                status=ToolExecutionStatus.ERROR,
                output="",
                error=f"Failed to change directory: {str(e)}"
            )
    
    async def _handle_pwd(self, command: str, timeout: int) -> ToolResult:
        """Handle pwd command."""
        return ToolResult(
            status=ToolExecutionStatus.SUCCESS,
            output=self.working_directory
        )
    
    async def _handle_ls(self, command: str, timeout: int) -> ToolResult:
        """Handle ls command safely."""
        # Use the actual ls command but ensure we're in our working directory
        return await self._execute_command(command, timeout, True)
    
    async def _handle_cat(self, command: str, timeout: int) -> ToolResult:
        """Handle cat command with size limits."""
        # Use the actual cat command but we could add file size checks here
        return await self._execute_command(command, timeout, True)
    
    async def _handle_echo(self, command: str, timeout: int) -> ToolResult:
        """Handle echo command."""
        return await self._execute_command(command, timeout, True)
