"""
Edit tool implementation for file manipulation.

This tool allows the DGM agent to read, write, and modify files.
"""

import os
from pathlib import Path
from typing import Dict, Any, List
from .base_tool import BaseTool, ToolResult, ToolExecutionStatus, ToolParameter


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
    
    def __init__(self, working_directory: str = None):
        """
        Initialize the Edit tool.
        
        Args:
            working_directory: Directory to operate in
        """
        self.working_directory = working_directory
        super().__init__()
    
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