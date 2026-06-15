"""
Edit tool implementation for file manipulation.

This tool allows the DGM agent to read, write, and modify files.
"""

import json
import os
import shlex
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, List
from .base_tool import BaseTool, ToolResult, ToolExecutionStatus, ToolParameter


_EDIT_TOOL_RUNNER = r"""
import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path


def load_edit_tool():
    code_root = Path("/home/dgm_agent/agent_code")
    agent_pkg = types.ModuleType("agent")
    agent_pkg.__path__ = [str(code_root / "agent")]
    sys.modules.setdefault("agent", agent_pkg)

    tools_pkg = types.ModuleType("agent.tools")
    tools_pkg.__path__ = [str(code_root / "agent" / "tools")]
    sys.modules.setdefault("agent.tools", tools_pkg)

    spec = importlib.util.spec_from_file_location(
        "agent.tools.edit_tool",
        code_root / "agent" / "tools" / "edit_tool.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.EditTool


async def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: edit_tool_runner.py PARAMS_JSON")

    params_file = Path(sys.argv[1]).resolve()
    parameters = json.loads(params_file.read_text(encoding="utf-8"))
    edit_tool = load_edit_tool()(working_directory=str(Path.cwd()))
    result = await edit_tool._execute_direct(parameters)
    print(json.dumps({
        "status": result.status.value,
        "output": result.output,
        "error": result.error or "",
    }))


if __name__ == "__main__":
    asyncio.run(main())
"""


def _resolve_and_check(
    file_path_str: str, working_directory: str
) -> "tuple[Path, ToolResult | None]":
    """
    Resolve *file_path_str* relative to *working_directory* and verify that the
    result is contained within it (path-traversal guard).

    Returns ``(resolved_path, None)`` on success, or
    ``(Path('.'), ToolResult(error=...))`` when the path escapes the sandbox.
    """
    wd = Path(working_directory).resolve()
    full = (wd / file_path_str).resolve()

    # Python 3.9+: Path.is_relative_to; fall back to os.path.commonpath for 3.8.
    try:
        contained = full.is_relative_to(wd)
    except AttributeError:  # pragma: no cover — Python < 3.9
        try:
            contained = os.path.commonpath([str(full), str(wd)]) == str(wd)
        except ValueError:
            contained = False

    if not contained:
        return Path("."), ToolResult(
            status=ToolExecutionStatus.ERROR,
            output="",
            error=(
                f"Path escape detected: '{file_path_str}' resolves outside the "
                f"working directory '{wd}'"
            ),
        )
    return full, None


class EditTool(BaseTool):
    """
    Tool for editing files and manipulating code.
    
    This is a placeholder implementation for Phase 1. Full functionality
    will be implemented in a later phase of the MVP development.
    """
    
    def __init__(
        self,
        working_directory: str = None,
        sandbox_manager: Any = None,
        use_sandbox: bool = False,
        timeout: int = 30,
    ):
        """
        Initialize the Edit tool.
        
        Args:
            working_directory: Directory to operate in
            sandbox_manager: Optional Docker sandbox manager for file operations
            use_sandbox: Whether to execute edits through the sandbox when available
            timeout: Default timeout for sandboxed edit operations
        """
        self.working_directory = working_directory
        self.sandbox_manager = sandbox_manager
        self.use_sandbox = use_sandbox
        self.default_timeout = timeout
        super().__init__()

    def _can_use_sandbox(self) -> bool:
        """Return True when sandboxed edit execution is configured."""
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
        return "edit"
    
    def get_description(self) -> str:
        """Get a description of what this tool does."""
        return ("Edit and manipulate files. Can read file contents, write new files, "
                "and modify existing files. This is a placeholder implementation.")
    
    def get_parameters(self) -> List[ToolParameter]:
        """Get the parameters this tool accepts."""
        return [
            ToolParameter(
                name="action",
                type="string",
                description="Action to perform: 'read', 'write', 'append', 'modify', or 'delete'",
                required=True,
                enum_values=["read", "write", "append", "modify", "delete"],
            ),
            ToolParameter(
                name="file_path",
                type="string",
                description="Path to the file to edit",
                required=True
            ),
            ToolParameter(
                name="content",
                type="string",
                description="Content to write (for write/append actions)",
                required=False
            ),
            ToolParameter(
                name="line_number",
                type="integer",
                description="Line number for modify actions",
                required=False
            ),
            ToolParameter(
                name="search_text",
                type="string",
                description="Text to search for in modify actions",
                required=False
            ),
            ToolParameter(
                name="replace_text",
                type="string",
                description="Text to replace with in modify actions",
                required=False
            )
        ]
    
    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """
        Execute the edit operation.

        All file paths are resolved relative to the working directory and
        checked for containment to prevent path-traversal attacks.

        Args:
            parameters: Dictionary containing edit parameters

        Returns:
            ToolResult: Result of the edit operation
        """
        action = parameters.get("action")
        file_path_str = parameters.get("file_path")
        content = parameters.get("content", "")

        if not action:
            return ToolResult(
                status=ToolExecutionStatus.ERROR,
                output="",
                error="Action parameter is required",
            )

        if not file_path_str:
            return ToolResult(
                status=ToolExecutionStatus.ERROR,
                output="",
                error="File path parameter is required",
            )

        if self.working_directory and self._can_use_sandbox():
            return await self._execute_sandbox_edit(parameters)

        return await self._execute_direct(parameters)

    async def _execute_direct(self, parameters: Dict[str, Any]) -> ToolResult:
        """Execute the edit operation directly in the configured workspace."""
        action = parameters.get("action")
        file_path_str = parameters.get("file_path")
        content = parameters.get("content", "")

        # Resolve path and verify containment.
        if self.working_directory:
            full_path, escape_error = _resolve_and_check(
                file_path_str, self.working_directory
            )
            if escape_error is not None:
                return escape_error
        else:
            full_path = Path(file_path_str)

        try:
            if action == "write":
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content, encoding="utf-8")
                return ToolResult(
                    status=ToolExecutionStatus.SUCCESS,
                    output=f"Successfully wrote {len(content)} characters to {file_path_str}",
                    error="",
                )

            elif action == "read":
                if not full_path.exists():
                    return ToolResult(
                        status=ToolExecutionStatus.ERROR,
                        output="",
                        error=f"File not found: {file_path_str}",
                    )
                content = full_path.read_text(encoding="utf-8")
                return ToolResult(
                    status=ToolExecutionStatus.SUCCESS,
                    output=content,
                    error="",
                )

            elif action == "append":
                if not full_path.exists():
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.touch()
                with open(full_path, "a", encoding="utf-8") as f:
                    f.write(content)
                return ToolResult(
                    status=ToolExecutionStatus.SUCCESS,
                    output=f"Successfully appended {len(content)} characters to {file_path_str}",
                    error="",
                )

            elif action == "modify":
                if not full_path.exists():
                    return ToolResult(
                        status=ToolExecutionStatus.ERROR,
                        output="",
                        error=f"File not found: {file_path_str}",
                    )

                search_text = parameters.get("search_text")
                replace_text = parameters.get("replace_text", "")

                if not search_text:
                    return ToolResult(
                        status=ToolExecutionStatus.ERROR,
                        output="",
                        error="search_text parameter is required for modify action",
                    )

                current_content = full_path.read_text(encoding="utf-8")
                occurrences = current_content.count(search_text)

                if occurrences == 0:
                    return ToolResult(
                        status=ToolExecutionStatus.ERROR,
                        output="",
                        error=f"old_code not found in {file_path_str}: no occurrences of the search text",
                    )

                if occurrences > 1:
                    return ToolResult(
                        status=ToolExecutionStatus.ERROR,
                        output="",
                        error=(
                            f"Ambiguous match in {file_path_str}: "
                            f"{occurrences} occurrences of search text found; "
                            "provide more context to make the match unique"
                        ),
                    )

                # Exactly one occurrence — safe to replace.
                new_content = current_content.replace(search_text, replace_text, 1)
                full_path.write_text(new_content, encoding="utf-8")
                return ToolResult(
                    status=ToolExecutionStatus.SUCCESS,
                    output=f"Successfully replaced 1 occurrence in {file_path_str}",
                    error="",
                )

            elif action == "delete":
                if not full_path.exists():
                    return ToolResult(
                        status=ToolExecutionStatus.ERROR,
                        output="",
                        error=f"File not found: {file_path_str}",
                    )
                full_path.unlink()
                return ToolResult(
                    status=ToolExecutionStatus.SUCCESS,
                    output=f"Successfully deleted {file_path_str}",
                    error="",
                )

            else:
                return ToolResult(
                    status=ToolExecutionStatus.ERROR,
                    output="",
                    error=(
                        f"Unknown action: {action}. "
                        "Valid actions are: read, write, append, modify, delete"
                    ),
                )

        except Exception as e:
            return ToolResult(
                status=ToolExecutionStatus.ERROR,
                output="",
                error=f"Error executing {action} on {file_path_str}: {str(e)}",
            )

    async def _execute_sandbox_edit(self, parameters: Dict[str, Any]) -> ToolResult:
        """Execute the edit operation inside the configured Docker sandbox."""
        started_at = time.time()
        sandbox_temp_parent = Path.home() / ".cache" / "dgm-sandbox"
        sandbox_temp_parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(dir=str(sandbox_temp_parent)) as temp_dir:
            temp_path = Path(temp_dir)
            staged_workspace = temp_path / "workspace"
            agent_code_dir = temp_path / "agent_code"
            tool_code_dir = agent_code_dir / "agent" / "tools"
            tool_code_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(__file__), tool_code_dir / "edit_tool.py")
            shutil.copy2(
                Path(__file__).with_name("base_tool.py"),
                tool_code_dir / "base_tool.py",
            )
            self._copy_workspace(
                source=Path(self.working_directory),
                destination=staged_workspace,
            )

            params_path = staged_workspace / ".dgm_edit_tool_params.json"
            params_path.write_text(json.dumps(parameters), encoding="utf-8")

            sandbox_result = await self.sandbox_manager.execute_in_sandbox(
                command=(
                    f"python3 -c {shlex.quote(_EDIT_TOOL_RUNNER)} "
                    ".dgm_edit_tool_params.json"
                ),
                agent_code_path=str(agent_code_dir),
                workspace_path=str(staged_workspace),
                timeout=self.default_timeout,
            )

            try:
                params_path.unlink(missing_ok=True)
            except TypeError:  # pragma: no cover - Python < 3.8
                if params_path.exists():
                    params_path.unlink()

            if not sandbox_result.success:
                timed_out = (
                    sandbox_result.exit_code is None
                    and "timed out" in (sandbox_result.error or "").lower()
                )
                return ToolResult(
                    status=(
                        ToolExecutionStatus.TIMEOUT
                        if timed_out
                        else ToolExecutionStatus.ERROR
                    ),
                    output=sandbox_result.output,
                    error=sandbox_result.error,
                    metadata={
                        "exit_code": sandbox_result.exit_code,
                        "sandboxed": True,
                    },
                    execution_time=(
                        sandbox_result.execution_time or time.time() - started_at
                    ),
                )

            parsed_result = self._parse_sandbox_result(sandbox_result.output)
            parsed_result.metadata = {
                **(parsed_result.metadata or {}),
                "exit_code": sandbox_result.exit_code,
                "sandboxed": True,
            }
            parsed_result.execution_time = (
                sandbox_result.execution_time or time.time() - started_at
            )

            self._copy_workspace(
                source=staged_workspace,
                destination=Path(self.working_directory),
            )
            self._apply_successful_delete_to_host(parameters, parsed_result)
            return parsed_result

    @staticmethod
    def _parse_sandbox_result(output: str) -> ToolResult:
        """Parse the JSON result emitted by the sandbox edit runner."""
        try:
            payload = json.loads(output)
            status = ToolExecutionStatus(payload.get("status", "error"))
            return ToolResult(
                status=status,
                output=payload.get("output", ""),
                error=payload.get("error", ""),
            )
        except Exception as exc:
            return ToolResult(
                status=ToolExecutionStatus.ERROR,
                output=output,
                error=f"Failed to parse sandbox edit result: {exc}",
            )

    def _apply_successful_delete_to_host(
        self,
        parameters: Dict[str, Any],
        result: ToolResult,
    ) -> None:
        """Propagate the edit tool's file delete action after workspace copy-back."""
        if result.status != ToolExecutionStatus.SUCCESS:
            return
        if parameters.get("action") != "delete":
            return
        file_path_str = parameters.get("file_path")
        if not file_path_str or not self.working_directory:
            return
        full_path, escape_error = _resolve_and_check(
            file_path_str,
            self.working_directory,
        )
        if escape_error is None and full_path.exists():
            full_path.unlink()

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


# TODO: Implement full Edit tool functionality
# 
# Future implementation notes:
# - Implement safe file reading with size limits
# - Add file writing with backup creation
# - Support line-based editing operations
# - Add search and replace functionality
# - Implement syntax validation for code files
# - Add diff generation for modifications
# - Support multiple file operations in one call
# 
# Example structure for future implementation:
# ```python
# async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
#     action = parameters["action"]
#     file_path = parameters["file_path"]
#     
#     if action == "read":
#         return await self._read_file(file_path)
#     elif action == "write":
#         content = parameters["content"]
#         return await self._write_file(file_path, content)
#     elif action == "append":
#         content = parameters["content"]
#         return await self._append_file(file_path, content)
#     elif action == "modify":
#         return await self._modify_file(file_path, parameters)
#     else:
#         return ToolResult(
#             status=ToolExecutionStatus.INVALID_PARAMS,
#             output="",
#             error=f"Unknown action: {action}"
#         )
