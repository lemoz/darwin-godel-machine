"""
Bash tool implementation for executing shell commands.

This tool allows the DGM agent to execute bash commands in a controlled manner,
with safety restrictions and timeout handling.
"""

import asyncio
import subprocess
import os
import shlex
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
    
    def __init__(self, working_directory: str = None, timeout: int = 30):
        """
        Initialize the Bash tool.
        
        Args:
            working_directory: Directory to execute commands in
            timeout: Default timeout for command execution
        """
        self.working_directory = working_directory or os.getcwd()
        self.default_timeout = timeout
        
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
        
        Args:
            command: Full command
            pattern: Dangerous pattern found
            
        Returns:
            bool: True if usage appears safe
        """
        # Simple heuristics for common safe patterns
        if pattern in ['>', '>>']:
            # Allow redirecting to files in current directory
            parts = command.split(pattern)
            if len(parts) == 2:
                output_file = parts[1].strip()
                if output_file and not output_file.startswith('/'):
                    return True
        
        if pattern == '|':
            # Allow basic pipes to common safe commands
            safe_pipe_targets = ['grep', 'sort', 'uniq', 'head', 'tail', 'wc']
            parts = command.split('|')
            if len(parts) == 2:
                target_cmd = parts[1].strip().split()[0]
                if target_cmd in safe_pipe_targets:
                    return True
        
        return False
    
    async def _execute_command(
        self, 
        command: str, 
        timeout: int, 
        capture_output: bool
    ) -> ToolResult:
        """
        Execute a shell command.
        
        Args:
            command: Command to execute
            timeout: Timeout in seconds
            capture_output: Whether to capture output
            
        Returns:
            ToolResult: Execution result
        """
        try:
            # Prepare the subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=subprocess.PIPE if capture_output else None,
                stderr=subprocess.PIPE if capture_output else None,
                cwd=self.working_directory,
                env=os.environ.copy()
            )
            
            # Wait for completion with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=timeout
                )
                
                # Decode output
                stdout_text = stdout.decode('utf-8', errors='replace') if stdout else ""
                stderr_text = stderr.decode('utf-8', errors='replace') if stderr else ""
                
                # Determine status based on return code
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
                    metadata={"exit_code": process.returncode}
                )
                
            except asyncio.TimeoutError:
                # Kill the process if it times out
                process.kill()
                await process.wait()
                
                return ToolResult(
                    status=ToolExecutionStatus.TIMEOUT,
                    output="",
                    error=f"Command timed out after {timeout} seconds"
                )
                
        except Exception as e:
            return ToolResult(
                status=ToolExecutionStatus.ERROR,
                output="",
                error=f"Failed to execute command: {str(e)}"
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