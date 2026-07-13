"""
Main DGM Agent implementation.

This module contains the core Agent class that represents a self-modifying
coding agent in the Darwin Gödel Machine system.
"""

import ast
import asyncio
import copy
import hashlib
import json
import logging
import re
import uuid
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from pathlib import Path
import yaml
import os

logger = logging.getLogger(__name__)

from .fm_interface.api_handler import (
    ApiHandler, CompletionRequest, CompletionResponse, Message, MessageRole, ToolCall
)
from .fm_interface.providers.gemini import GeminiHandler
from .fm_interface.providers.anthropic import AnthropicHandler
from .fm_interface.providers.openai_compatible import OpenAICompatibleHandler
from .fm_interface.message_formatter import MessageFormatter, ConversationContext
from .tools.base_tool import BaseTool, ToolRegistry, ToolResult, ToolExecutionStatus
from .tools.bash_tool import BashTool
from .tools.edit_tool import EditTool


@dataclass
class Task:
    """Represents a coding task for the agent."""
    task_id: str
    description: str
    test_description: Optional[str] = None
    constraints: List[str] = field(default_factory=list)
    examples: List[Dict[str, str]] = field(default_factory=list)
    timeout: int = 300
    benchmark_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)


@dataclass
class AgentConfig:
    """Configuration for an agent instance."""
    agent_id: str
    fm_provider: str
    fm_config: Dict[str, Any]
    working_directory: str
    tool_timeout: int = 30
    max_iterations: int = 10
    memory_limit: Optional[int] = None
    sandbox_manager: Optional[Any] = None
    use_sandbox: bool = False
    retain_conversation_history: bool = True


@dataclass
class ToolExecutionEvent:
    """Tool call plus result captured during one assistant turn."""
    tool_call: ToolCall
    result: ToolResult


class Agent:
    """
    Main DGM Agent class.
    
    Represents a self-modifying coding agent that can solve programming tasks
    using Foundation Models and tools. This is the core component that gets
    modified during the self-improvement process.
    """
    
    def __init__(self, config: AgentConfig):
        """
        Initialize the agent.
        
        Args:
            config: Agent configuration
        """
        self.config = config
        self.agent_id = config.agent_id
        self.working_directory = Path(config.working_directory)
        
        # Ensure working directory exists
        self.working_directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize FM interface
        self.fm_handler = self._create_fm_handler(config.fm_provider, config.fm_config)
        
        # Initialize message formatter
        self.message_formatter = MessageFormatter()
        
        # Initialize tool registry
        self.tool_registry = ToolRegistry()
        self._register_default_tools()
        
        # Conversation state
        self.conversation_history: List[Message] = []
        self.current_task: Optional[Task] = None
        self._self_modification_read_observed = False
        self._self_modification_write_observed = False
        
        # Agent metadata
        self.generation = 0  # Which generation this agent is (0 = seed)
        self.parent_id: Optional[str] = None
        self.created_at = None
        self.performance_metrics: Dict[str, float] = {}
    
    def _create_fm_handler(self, provider: str, fm_config: Dict[str, Any]) -> ApiHandler:
        """
        Create the appropriate FM handler based on provider.
        
        Args:
            provider: Provider name ("gemini", "anthropic", etc.)
            fm_config: Provider-specific configuration
            
        Returns:
            ApiHandler: Configured handler instance
        """
        provider_key = provider.lower().replace("-", "_")
        if provider_key == "gemini":
            return GeminiHandler(fm_config)
        elif provider_key == "anthropic":
            return AnthropicHandler(fm_config)
        elif provider_key in {
            "openai",
            "openai_compatible",
            "openrouter",
            "kimi",
            "moonshot",
        }:
            return OpenAICompatibleHandler(fm_config)
        else:
            raise ValueError(f"Unsupported FM provider: {provider}")
    
    def _register_default_tools(self) -> None:
        """Register the default tools available to this agent."""
        # Register bash tool
        bash_tool = BashTool(
            working_directory=str(self.working_directory),
            timeout=self.config.tool_timeout,
            sandbox_manager=self.config.sandbox_manager,
            use_sandbox=self.config.use_sandbox,
        )
        self.tool_registry.register_tool(bash_tool)
        
        # Register edit tool
        edit_tool = EditTool(
            working_directory=str(self.working_directory),
            sandbox_manager=self.config.sandbox_manager,
            use_sandbox=self.config.use_sandbox,
            timeout=self.config.tool_timeout,
        )
        self.tool_registry.register_tool(edit_tool)

    async def close(self) -> None:
        """Release provider resources held by one-shot agent instances."""
        client = getattr(self.fm_handler, "client", None)
        for method_name in ("close", "aclose"):
            close = getattr(client, method_name, None)
            if close is None:
                continue
            result = close()
            if asyncio.iscoroutine(result):
                await result
            return
    
    async def solve_task(self, task: Task) -> Dict[str, Any]:
        """
        Solve a coding task using the agent's capabilities.
        
        Args:
            task: Task to solve
            
        Returns:
            Dict containing solution and execution details
        """
        self.current_task = task
        self._failure_mode_counts: Dict[str, int] = {}
        self._self_modification_read_observed = False
        self._self_modification_write_observed = False
        
        # Clear conversation history for new task
        self.conversation_history = []
        
        # Create conversation context
        context = ConversationContext(
            task_id=task.task_id,
            agent_id=self.agent_id,
            benchmark_name=task.benchmark_name
        )
        
        try:
            # Build initial system message
            system_message = self._build_system_message(context)
            self.conversation_history.append(system_message)
            
            # Build task message
            task_message = self.message_formatter.format_task_message(
                task_description=task.description,
                test_description=task.test_description,
                constraints=task.constraints,
                examples=task.examples
            )
            self.conversation_history.append(task_message)
            
            # Main problem-solving loop
            logger.info(f"Starting task solving steps for task: {task.task_id}")
            solution = await self._solve_with_steps(task)
            logger.info(f"Completed task solving with {len(self.conversation_history)} total messages")
            
            conversation_history = (
                [msg.content for msg in self.conversation_history]
                if self.config.retain_conversation_history
                else []
            )
            return {
                "success": True,
                "solution": solution,
                "task_id": task.task_id,
                "agent_id": self.agent_id,
                "steps": len(self.conversation_history),
                "conversation_history": conversation_history,
                "failure_modes": dict(self._failure_mode_counts),
            }
            
        except Exception as e:
            self._record_failure_mode("timeout/provider failure")
            conversation_history = (
                [msg.content for msg in self.conversation_history]
                if self.config.retain_conversation_history
                else []
            )
            return {
                "success": False,
                "error": str(e),
                "task_id": task.task_id,
                "agent_id": self.agent_id,
                "steps": len(self.conversation_history),
                "conversation_history": conversation_history,
                "failure_modes": dict(self._failure_mode_counts),
            }
    
    async def _solve_with_steps(self, task: Task) -> str:
        """
        Solve the task through multiple LLM calls (steps) to allow agents to
        see tool results and declare completion.
        
        Args:
            task: Task to solve
            
        Returns:
            Solution string
        """
        solution = ""
        max_steps = max(1, int(self.config.max_iterations))
        is_self_modification = self._is_self_modification_task(task)
        initial_agent_code_snapshot = (
            self._snapshot_agent_code_files() if is_self_modification else {}
        )
        patch_due_step = max(2, min(max_steps, max_steps // 3 or 1))
        final_patch_step = max(1, max_steps - 2)
        sent_patch_due_nudge = False
        sent_final_patch_nudge = False
        benchmark_edit_failure_streak = 0
        benchmark_seen_bash_success_with_solution = False
        benchmark_unresolved_bash_failure = False
        benchmark_seen_unsafe_evidence = False
        benchmark_current_solution_known_bad = False
        sent_benchmark_constraint_nudge = False
        sent_benchmark_finalization_nudge = False
        sent_benchmark_edit_reset_nudge = False
        sent_benchmark_no_stdin_nudge = False
        sent_benchmark_failure_repair_nudge = False
        sent_benchmark_unsafe_nudge = False
        
        logger.info(f"Starting task solution with up to {max_steps} steps for task {task.task_id}")
        
        # Each step is an LLM call + tool execution cycle
        for step in range(max_steps):
            logger.info(f"Step {step + 1}/{max_steps}")
            
            # Get completion from FM
            request = CompletionRequest(
                messages=self.conversation_history,
                tools=self._tool_schemas_for_step(
                    is_self_modification=is_self_modification,
                ),
                max_tokens=self.config.fm_config.get("max_tokens", 8192),
                temperature=self.config.fm_config.get("temperature", 0.1),
                tool_choice=self._tool_choice_for_step(
                    task=task,
                    is_self_modification=is_self_modification,
                    initial_agent_code_snapshot=initial_agent_code_snapshot,
                ),
            )
            
            # Debug: Log conversation history size and last few messages
            logger.info(f"Making API call - Step {step + 1}")
            logger.info(f"Conversation history has {len(self.conversation_history)} messages")
            if len(self.conversation_history) > 2:
                # Log last 2 messages (excluding system/task messages)
                for i, msg in enumerate(self.conversation_history[-2:]):
                    logger.info(f"Recent message {i+1}: Role={msg.role}, Content preview={msg.content[:100] if msg.content else 'None'}...")
            response = await self.fm_handler.get_completion(request)
            logger.info(f"API call completed. Tool calls: {len(response.tool_calls) if response.tool_calls else 0}")
            if response.usage:
                logger.info(f"API usage: {response.usage}")
            if response.finish_reason:
                logger.info(f"API finish reason: {response.finish_reason}")
            
            # Log agent's response for debugging
            if response.content:
                logger.info(f"=== AGENT RESPONSE (Step {step + 1}) ===")
                logger.info(response.content)
                logger.info(f"=== END RESPONSE ===")
                if (
                    self._is_benchmark_task(task)
                    and self._text_has_unsafe_benchmark_evidence(response.content)
                ):
                    benchmark_seen_unsafe_evidence = True
            
            # Build metadata for the assistant message so that format_messages
            # can reconstruct proper Anthropic tool_use blocks.
            assistant_metadata: Optional[Dict[str, Any]] = None
            if response.tool_calls:
                assistant_metadata = {
                    "tool_calls": [
                        {
                            "id": tc.call_id or f"toolu_{uuid.uuid4().hex[:16]}",
                            "name": tc.tool_name,
                            "input": tc.parameters,
                        }
                        for tc in response.tool_calls
                    ]
                }

            # Add assistant response to conversation
            assistant_message = Message(
                role=MessageRole.ASSISTANT,
                content=self._compact_assistant_content_for_history(response),
                metadata=assistant_metadata,
            )
            self.conversation_history.append(assistant_message)

            # Optionally dump conversation history to disk for debugging.
            if self.config.fm_config.get("debug_conversation_dump", False):
                debug_dir = Path("debug")
                debug_dir.mkdir(exist_ok=True)
                history_file = debug_dir / f"conversation_history_task_{task.task_id}_step{step+1}.json"
                conversation_data = {
                    "task_id": task.task_id,
                    "step": step + 1,
                    "conversation": [
                        {
                            "role": msg.role.value,
                            "content": (
                                msg.content[:1000] + "..."
                                if len(msg.content) > 1000
                                else msg.content
                            ),
                        }
                        for msg in self.conversation_history
                    ],
                }
                with open(history_file, "w") as f:
                    json.dump(conversation_data, f, indent=2)
                logger.info(f"Saved conversation history to {history_file}")
            
            # Execute any tool calls
            if response.tool_calls:
                logger.info(f"Executing {len(response.tool_calls)} tool calls")
                tool_events = await self._execute_tool_calls(response.tool_calls, task)
                if self._is_benchmark_task(task):
                    if self._events_include_benchmark_edit_failure(tool_events):
                        benchmark_edit_failure_streak += 1
                    elif self._events_include_successful_solution_edit(tool_events):
                        benchmark_edit_failure_streak = 0
                        benchmark_seen_bash_success_with_solution = False
                        benchmark_unresolved_bash_failure = False
                        benchmark_current_solution_known_bad = (
                            self._benchmark_solution_file_is_incomplete()
                        )

                    sample_mismatch = self._events_include_benchmark_sample_mismatch(
                        tool_events,
                        task,
                    )
                    verified_sample_success = (
                        self._events_include_verified_benchmark_sample_success(
                            tool_events,
                            task,
                        )
                    )
                    if (
                        self._events_include_benchmark_bash_failure(tool_events)
                        and self._benchmark_solution_file_exists()
                    ):
                        benchmark_unresolved_bash_failure = True
                        benchmark_current_solution_known_bad = True
                        benchmark_seen_bash_success_with_solution = False

                    if sample_mismatch and self._benchmark_solution_file_exists():
                        benchmark_unresolved_bash_failure = True
                        benchmark_current_solution_known_bad = True
                        benchmark_seen_bash_success_with_solution = False

                    if (
                        self._events_include_successful_bash(tool_events)
                        and self._benchmark_solution_file_exists()
                        and not sample_mismatch
                        and (
                            verified_sample_success
                            or not self._task_has_stdin_example_expectations(task)
                        )
                    ):
                        benchmark_seen_bash_success_with_solution = True
                        benchmark_unresolved_bash_failure = False
                        benchmark_current_solution_known_bad = False

                    if self._events_include_unsafe_benchmark_evidence(tool_events):
                        benchmark_seen_unsafe_evidence = True

                    control_nudge = self._build_benchmark_control_nudge(
                        tool_events=tool_events,
                        task=task,
                        consumed_steps=step + 1,
                        max_steps=max_steps,
                        edit_failure_streak=benchmark_edit_failure_streak,
                        seen_bash_success_with_solution=benchmark_seen_bash_success_with_solution,
                        has_unresolved_bash_failure=benchmark_unresolved_bash_failure,
                        seen_unsafe_evidence=benchmark_seen_unsafe_evidence,
                        current_solution_known_bad=benchmark_current_solution_known_bad,
                        can_send_constraint_nudge=not sent_benchmark_constraint_nudge,
                        can_send_finalization_nudge=not sent_benchmark_finalization_nudge,
                        can_send_edit_reset_nudge=not sent_benchmark_edit_reset_nudge,
                        can_send_no_stdin_nudge=not sent_benchmark_no_stdin_nudge,
                        can_send_failure_repair_nudge=not sent_benchmark_failure_repair_nudge,
                        can_send_unsafe_nudge=not sent_benchmark_unsafe_nudge,
                    )
                    if control_nudge:
                        nudge_kind, nudge_text = control_nudge
                        logger.info("Injecting benchmark control nudge: %s", nudge_kind)
                        self.conversation_history.append(
                            Message(role=MessageRole.USER, content=nudge_text)
                        )
                        if nudge_kind == "constraint":
                            sent_benchmark_constraint_nudge = True
                        elif nudge_kind == "finalization":
                            sent_benchmark_finalization_nudge = True
                        elif nudge_kind == "edit_reset":
                            sent_benchmark_edit_reset_nudge = True
                        elif nudge_kind == "no_stdin_repair":
                            sent_benchmark_no_stdin_nudge = True
                        elif nudge_kind == "sample_failure_repair":
                            sent_benchmark_failure_repair_nudge = True
                        elif nudge_kind == "unsafe_verification":
                            sent_benchmark_unsafe_nudge = True

                if is_self_modification:
                    consumed_steps = step + 1
                    remaining_steps = max_steps - consumed_steps
                    has_agent_code_changes = self._has_agent_code_changes(
                        initial_agent_code_snapshot
                    )
                    if not has_agent_code_changes and remaining_steps > 0:
                        nudge = None
                        if (
                            consumed_steps >= final_patch_step
                            and not sent_final_patch_nudge
                        ):
                            nudge = self._build_self_modification_patch_nudge(
                                consumed_steps=consumed_steps,
                                max_steps=max_steps,
                                final_window=True,
                            )
                            sent_final_patch_nudge = True
                        elif (
                            consumed_steps >= patch_due_step
                            and not sent_patch_due_nudge
                        ):
                            nudge = self._build_self_modification_patch_nudge(
                                consumed_steps=consumed_steps,
                                max_steps=max_steps,
                                final_window=False,
                            )
                            sent_patch_due_nudge = True

                        if nudge:
                            logger.warning(
                                "Self-modification has no agent-code changes "
                                "after step %d/%d; injecting patch-contract nudge",
                                consumed_steps,
                                max_steps,
                            )
                            self.conversation_history.append(
                                Message(role=MessageRole.USER, content=nudge)
                            )
                # Continue to next step so agent can see tool results
                continue
            
            # Check if task appears complete (only when no tools were called)
            task_complete = self._is_task_complete(response.content, task)
            logger.info(f"_is_task_complete returned: {task_complete}")
            
            if task_complete:
                if self._is_benchmark_task(task):
                    block_reason = self._benchmark_completion_block_reason(
                        task=task,
                        current_solution_known_bad=benchmark_current_solution_known_bad,
                        has_unresolved_bash_failure=benchmark_unresolved_bash_failure,
                        seen_unsafe_evidence=benchmark_seen_unsafe_evidence,
                    )
                    if block_reason:
                        logger.warning(
                            "Blocking benchmark task completion: %s",
                            block_reason,
                        )
                        if step < max_steps - 1:
                            self.conversation_history.append(
                                Message(
                                    role=MessageRole.USER,
                                    content=self._build_benchmark_completion_block_nudge(
                                        block_reason
                                    ),
                                )
                            )
                            continue
                        return solution

                logger.info(f"Task complete after Step {step + 1}")
                # Extract Python code from the response
                solution = self._extract_code_solution(response.content)
                return solution or self._read_workspace_solution(task)
            
            # If no tools and not complete, agent might be stuck
            if not response.tool_calls:
                logger.warning(f"Agent made no tool calls and didn't complete task")
                # Add a nudge to help the agent continue
                nudge_message = Message(
                    role=MessageRole.USER,
                    content=self._build_no_progress_nudge(response, task)
                )
                self.conversation_history.append(nudge_message)
                
                # Use the remaining configured attempts for explicit reasks.
                if step >= max_steps - 1:
                    logger.warning("No task completion by the final configured step")
                    break
        
        logger.warning(f"Reached max steps ({max_steps}) without task completion")
        if self._is_benchmark_task(task):
            block_reason = self._benchmark_completion_block_reason(
                task=task,
                current_solution_known_bad=benchmark_current_solution_known_bad,
                has_unresolved_bash_failure=benchmark_unresolved_bash_failure,
                seen_unsafe_evidence=benchmark_seen_unsafe_evidence,
            )
            if block_reason:
                logger.warning(
                    "Not using workspace benchmark solution after step limit: %s",
                    block_reason,
                )
                return solution
        return solution or self._read_workspace_solution(task)

    def _tool_schemas_for_step(
        self,
        *,
        is_self_modification: bool,
    ) -> List[Dict[str, Any]]:
        """Expose a narrow read-only discovery call before Gemma may mutate."""
        schemas = self.tool_registry.get_tool_schemas()
        policy = self.config.fm_config.get("tool_choice_policy")
        if policy != "required_read_then_workspace_change" or not is_self_modification:
            return schemas

        edit_schema = next(
            (copy.deepcopy(schema) for schema in schemas if schema.get("name") == "edit"),
            None,
        )
        if edit_schema is None:
            return schemas

        parameters = edit_schema["parameters"]
        properties = parameters["properties"]
        if self._self_modification_read_observed:
            if self._self_modification_write_observed:
                return schemas
            parameters["properties"]["action"]["enum"] = [
                "line_replace",
                "modify",
                "write",
            ]
            parameters["required"] = ["action", "file_path"]
            edit_schema["description"] = (
                "Required mutation step after source discovery. Make one concrete "
                "Python source edit now; Bash and additional reads are unavailable "
                "until a write succeeds. Prefer line_replace."
            )
            return [edit_schema]

        parameters["properties"] = {
            name: properties[name]
            for name in ("action", "file_path", "line_number", "line_count")
        }
        parameters["properties"]["action"]["enum"] = ["read"]
        parameters["required"] = [
            "action",
            "file_path",
            "line_number",
            "line_count",
        ]
        edit_schema["description"] = (
            "Required discovery step before self-modification. Read a narrow "
            "bounded source range; writing is unavailable until this succeeds."
        )
        return [edit_schema]

    def _tool_choice_for_step(
        self,
        *,
        task: Task,
        is_self_modification: bool,
        initial_agent_code_snapshot: Dict[str, str],
    ) -> Optional[str]:
        """Require native tool use until a task has produced its first artifact."""
        policy = self.config.fm_config.get("tool_choice_policy")
        if policy not in {
            "required_until_workspace_change",
            "required_read_then_workspace_change",
        }:
            return None
        if is_self_modification:
            return (
                None
                if self._has_agent_code_changes(initial_agent_code_snapshot)
                else "required"
            )
        if self._is_benchmark_task(task):
            return None if self._benchmark_solution_file_exists() else "required"
        return None

    def _build_no_progress_nudge(
        self,
        response: CompletionResponse,
        task: Optional[Task] = None,
    ) -> str:
        """Build a targeted reask after an empty or non-terminal assistant turn."""
        content = (response.content or "").strip()
        finish_reason = response.finish_reason or "unknown"
        if task and self._is_self_modification_task(task):
            if finish_reason in {"length", "max_tokens", "content_filter"}:
                return (
                    f"Your previous self-modification response stopped with "
                    f"finish_reason={finish_reason}. Continue concisely. Your "
                    "next response must call the edit tool to modify a Python "
                    "agent-code file such as agent.py, tools/*.py, or "
                    "fm_interface/*.py. Prefer action='line_replace' with "
                    "line_number, line_count, and content_lines. Do not list "
                    "more files or write solution.py."
                )
            return (
                "Continue the self-modification task by making a concrete "
                "Python source edit now. Your next response must call the edit "
                "tool on agent.py, tools/*.py, or fm_interface/*.py. Prefer "
                "action='line_replace' with line_number, line_count, and "
                "content_lines, then finish by naming the changed file."
            )
        if not content or content == "No response generated":
            return (
                "Your previous response had no usable content or tool calls "
                f"(finish_reason={finish_reason}). Continue from the task prompt now: "
                "either call the edit/bash tools to create and test solution.py, "
                "or provide the final Python code in a markdown block ending with "
                "'Task complete'."
            )
        if finish_reason in {"length", "max_tokens", "content_filter"}:
            return (
                f"Your previous response stopped with finish_reason={finish_reason} "
                "before the task was complete. Continue concisely. Do not emit "
                "XML-like <tool_call> text in the assistant message; either make "
                "a real tool call through the provided tool interface, or provide "
                "the final Python code in a markdown block ending with "
                "'Task complete'."
            )
        return (
            "Please continue working on the task. If you have completed it, provide "
            "the final Python code in a markdown block and end with 'Task complete'."
        )

    @staticmethod
    def _compact_assistant_content_for_history(
        response: CompletionResponse,
    ) -> str:
        """Avoid carrying huge truncated pseudo-tool text into the next turn."""
        content = response.content.rstrip() if response.content else ""
        finish_reason = response.finish_reason or ""
        if finish_reason not in {"length", "max_tokens", "content_filter"}:
            return content
        if response.tool_calls:
            return content
        if not content or content == "No response generated":
            return content

        stripped = content.strip()
        looks_like_pseudo_tool = any(
            marker in stripped
            for marker in (
                "<tool_call",
                "</tool_call",
                "<function=",
                "<parameter=",
            )
        )
        if not looks_like_pseudo_tool and len(stripped) <= 2000:
            return content

        preview = (
            "[pseudo-tool-call text omitted]"
            if looks_like_pseudo_tool
            else " ".join(stripped.split())[:300]
        )
        return (
            f"[Assistant response compacted after finish_reason={finish_reason}: "
            f"{len(content)} characters without a valid tool call. Preview: "
            f"{preview}]"
        )

    def _build_self_modification_patch_nudge(
        self,
        *,
        consumed_steps: int,
        max_steps: int,
        final_window: bool,
    ) -> str:
        """Build a steering message when self-modification has not edited code."""
        if final_window:
            return (
                "SELF-MODIFICATION FINAL PATCH WINDOW: no Python agent-code "
                f"changes are detected after {consumed_steps}/{max_steps} "
                "steps. The next response must call the edit tool and change "
                "agent.py, tools/*.py, fm_interface/*.py, or a provider module. "
                "Use action='line_replace' with line_number, line_count, and "
                "content_lines if exact modify text is brittle. Do not call bash "
                "or read more files. Target executable logic or a named prompt "
                "instruction block, not incidental examples. If you do not make "
                "a source edit now, this child will be archived as an invalid "
                "no-op mutation."
            )
        return (
            "SELF-MODIFICATION PATCH REQUIRED: no Python agent-code changes are "
            f"detected after {consumed_steps}/{max_steps} steps. Stop exploring "
            "and make one small, valid source edit now. Prefer an edit tool "
            "line_replace call against agent.py, tools/*.py, fm_interface/*.py, "
            "or a provider module, using line_number, line_count, and "
            "content_lines. Target executable logic or a named instruction block; "
            "do not edit sample workflow text. Do not write solution.py or "
            "continue with read-only inspection."
        )

    @staticmethod
    def _is_self_modification_task(task: Task) -> bool:
        metadata = task.metadata or {}
        return task.task_id.startswith("self_modify") or (
            "parent_id" in metadata and "generation" in metadata
        )

    @staticmethod
    def _is_benchmark_task(task: Task) -> bool:
        metadata = task.metadata or {}
        return bool(
            task.benchmark_name
            or metadata.get("benchmark")
            or task.task_id.startswith("benchmark_")
        )

    @staticmethod
    def _is_agent_code_relative_path(relative_path: Path) -> bool:
        excluded_parts = {".git", "__pycache__", ".dgm_metadata"}
        if any(part in excluded_parts for part in relative_path.parts):
            return False
        if relative_path.suffix != ".py":
            return False
        return relative_path.name not in {"solution.py", "solve.py", "main.py"}

    def _snapshot_agent_code_files(self) -> Dict[str, str]:
        """Return hashes for Python agent-code files in this workspace."""
        snapshot: Dict[str, str] = {}
        for path in sorted(self.working_directory.rglob("*.py")):
            relative_path = path.relative_to(self.working_directory)
            if not self._is_agent_code_relative_path(relative_path):
                continue
            try:
                content = path.read_bytes()
            except OSError as exc:
                logger.debug("Could not snapshot %s: %s", path, exc)
                continue
            snapshot[relative_path.as_posix()] = hashlib.sha256(content).hexdigest()
        return snapshot

    def _has_agent_code_changes(self, before_snapshot: Dict[str, str]) -> bool:
        return self._snapshot_agent_code_files() != before_snapshot

    def _read_workspace_solution(self, task: Optional[Task] = None) -> str:
        """Return solution.py from the working directory when tool use produced one."""
        solution_path = self.working_directory / "solution.py"
        try:
            if solution_path.is_file():
                solution = solution_path.read_text(encoding="utf-8")
                if solution.strip():
                    logger.info(
                        "Using tool-written solution.py after task did not return inline code"
                    )
                    return solution
            if task and self._is_benchmark_task(task):
                for candidate_name in ("solve.py", "main.py"):
                    candidate = self.working_directory / candidate_name
                    if candidate.is_file():
                        solution = candidate.read_text(encoding="utf-8")
                        if solution.strip():
                            logger.info(
                                "Using tool-written %s after solution.py was not found",
                                candidate_name,
                            )
                            return solution

        except OSError as exc:
            logger.warning("Could not read tool-written benchmark solution: %s", exc)
        return ""

    def _benchmark_solution_file_exists(self) -> bool:
        """Return whether a benchmark solution file exists and is non-empty."""
        for candidate_name in ("solution.py", "solve.py", "main.py"):
            candidate = self.working_directory / candidate_name
            try:
                if candidate.is_file() and candidate.read_text(encoding="utf-8").strip():
                    return True
            except OSError:
                continue
        return False

    def _benchmark_solution_file_is_incomplete(self) -> bool:
        """Return whether the current benchmark solution file is only a stub."""
        for candidate_name in ("solution.py", "solve.py", "main.py"):
            candidate = self.working_directory / candidate_name
            try:
                if not candidate.is_file():
                    continue
                source = candidate.read_text(encoding="utf-8")
            except OSError:
                continue
            if source.strip():
                return self._python_solution_source_is_incomplete(source)
        return False

    @staticmethod
    def _python_solution_source_is_incomplete(source: str) -> bool:
        """Return True for syntactically valid Python that cannot solve a task."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return True

        meaningful_nodes = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                continue
            meaningful_nodes.append(node)

        if not meaningful_nodes:
            return True
        return all(isinstance(node, ast.Pass) for node in meaningful_nodes)

    @staticmethod
    def _tool_event_file_path(event: ToolExecutionEvent) -> str:
        file_path = event.tool_call.parameters.get("file_path")
        return file_path if isinstance(file_path, str) else ""

    @staticmethod
    def _events_include_successful_bash(events: List[ToolExecutionEvent]) -> bool:
        return any(
            event.tool_call.tool_name == "bash"
            and event.result.status == ToolExecutionStatus.SUCCESS
            for event in events
        )

    @classmethod
    def _events_include_successful_solution_edit(
        cls,
        events: List[ToolExecutionEvent],
    ) -> bool:
        return any(
            event.tool_call.tool_name == "edit"
            and event.result.status == ToolExecutionStatus.SUCCESS
            and Path(cls._tool_event_file_path(event)).name
            in {"solution.py", "solve.py", "main.py"}
            for event in events
        )

    @classmethod
    def _events_include_benchmark_edit_failure(
        cls,
        events: List[ToolExecutionEvent],
    ) -> bool:
        return any(
            event.tool_call.tool_name == "edit"
            and event.result.status != ToolExecutionStatus.SUCCESS
            and Path(cls._tool_event_file_path(event)).name
            in {"solution.py", "solve.py", "main.py"}
            for event in events
        )

    @staticmethod
    def _tool_event_text(event: ToolExecutionEvent) -> str:
        """Return compact searchable text for a tool call and result."""
        parts: List[str] = []
        try:
            parts.append(json.dumps(event.tool_call.parameters, default=str))
        except TypeError:
            parts.append(str(event.tool_call.parameters))
        if event.result.output:
            parts.append(event.result.output)
        if event.result.error:
            parts.append(event.result.error)
        return "\n".join(parts)

    @staticmethod
    def _tool_event_result_text(event: ToolExecutionEvent) -> str:
        """Return searchable execution evidence without call parameters.

        Tool parameters describe how a command should run.  They are not
        evidence about how it actually ran.  In particular, a normal
        ``timeout`` parameter must not be mistaken for a timeout result.
        """
        parts: List[str] = []
        if event.result.output:
            parts.append(event.result.output)
        if event.result.error:
            parts.append(event.result.error)
        return "\n".join(parts)

    @staticmethod
    def _stdin_example_expectations(task: Optional[Task]) -> Dict[str, str]:
        """Extract public stdin examples from a benchmark task description."""
        if task is None or not task.description:
            return {}

        expectations: Dict[str, str] = {}
        lines = task.description.splitlines()
        index = 0
        while index < len(lines):
            if not re.match(r"\s*\d+\.\s+Stdin:\s*$", lines[index]):
                index += 1
                continue

            index += 1
            input_lines: List[str] = []
            while index < len(lines) and not re.match(
                r"\s*Expected stdout:\s*$",
                lines[index],
            ):
                input_lines.append(lines[index])
                index += 1

            if index >= len(lines):
                break

            index += 1
            expected_lines: List[str] = []
            while index < len(lines):
                line = lines[index]
                if re.match(r"\s*\d+\.\s+Stdin:\s*$", line):
                    break
                if re.match(r"\s*\d+\.\s+Program reads stdin", line):
                    break
                if (
                    line.strip()
                    == "Focus on the requested behavior and the examples above."
                ):
                    break
                expected_lines.append(line)
                index += 1

            raw_input = "\n".join(input_lines).strip()
            raw_expected = "\n".join(expected_lines).strip()
            if raw_input:
                expectations[raw_input] = raw_expected

        return expectations

    @classmethod
    def _task_has_stdin_example_expectations(cls, task: Optional[Task]) -> bool:
        return bool(cls._stdin_example_expectations(task))

    @staticmethod
    def _extract_heredoc_stdin(command: str) -> Optional[str]:
        """Return stdin supplied via a shell heredoc, when parseable."""
        match = re.search(
            r"<<\s*['\"]?([A-Za-z_][A-Za-z0-9_-]*)['\"]?\s*\n(.*?)\n\1(?:\s|$)",
            command,
            re.DOTALL,
        )
        if not match:
            return None
        return match.group(2).strip()

    @staticmethod
    def _stdio_text_matches(actual: str, expected: str) -> bool:
        """Compare stdout using exact trim first, then whitespace normalization."""
        actual_stripped = (actual or "").strip()
        expected_stripped = (expected or "").strip()
        if actual_stripped == expected_stripped:
            return True
        return actual_stripped.split() == expected_stripped.split()

    @classmethod
    def _benchmark_sample_match_for_event(
        cls,
        event: ToolExecutionEvent,
        task: Optional[Task],
    ) -> Optional[bool]:
        """Return whether a bash run matched a prompt-visible stdin example."""
        if event.tool_call.tool_name != "bash":
            return None
        if event.result.status != ToolExecutionStatus.SUCCESS:
            return None
        if not cls._bash_event_runs_solution_file(event):
            return None

        command = event.tool_call.parameters.get("command")
        if not isinstance(command, str):
            return None
        stdin = cls._extract_heredoc_stdin(command)
        if stdin is None:
            return None

        expectations = cls._stdin_example_expectations(task)
        expected = expectations.get(stdin.strip())
        if expected is None:
            return None
        return cls._stdio_text_matches(event.result.output or "", expected)

    @classmethod
    def _events_include_verified_benchmark_sample_success(
        cls,
        events: List[ToolExecutionEvent],
        task: Optional[Task],
    ) -> bool:
        return any(
            cls._benchmark_sample_match_for_event(event, task) is True
            for event in events
        )

    @classmethod
    def _events_include_benchmark_sample_mismatch(
        cls,
        events: List[ToolExecutionEvent],
        task: Optional[Task],
    ) -> bool:
        return any(
            cls._benchmark_sample_match_for_event(event, task) is False
            for event in events
        )

    @staticmethod
    def _text_has_unsafe_benchmark_evidence(text: Optional[str]) -> bool:
        """Return whether text indicates a likely benchmark-scale failure."""
        if not text:
            return False
        lowered = text.lower()
        unsafe_phrases = (
            "memoryerror",
            "timed out",
            "timeout",
            "time limit exceeded",
            "will tle",
            "would tle",
            " tles",
            "too slow",
            "could be too slow",
            "too much memory",
            "memory intensive",
            "not efficient enough",
            "asymptotically unsafe",
            "exceeds memory",
            "will not pass large",
            "cannot handle large",
        )
        if any(phrase in lowered for phrase in unsafe_phrases):
            return True

        large_input_markers = (
            "10^5",
            "10**5",
            "100000",
            "10^6",
            "10**6",
            "1000000",
            "large input",
        )
        quadratic_markers = (
            "o(n^2)",
            "o(r^2)",
            "o(m^2)",
            "quadratic",
            "nested loop",
        )
        return (
            any(marker in lowered for marker in large_input_markers)
            and any(marker in lowered for marker in quadratic_markers)
        )

    @staticmethod
    def _bash_event_runs_solution_file(event: ToolExecutionEvent) -> bool:
        command = event.tool_call.parameters.get("command")
        if not isinstance(command, str):
            return False
        lowered = command.lower()
        solution_names = ("solution.py", "solve.py", "main.py")
        python_names = ("python3", "python")
        return any(
            f"{python_name} {solution_name}" in lowered
            or f"{python_name} ./{solution_name}" in lowered
            for python_name in python_names
            for solution_name in solution_names
        )

    @classmethod
    def _events_include_benchmark_bash_failure(
        cls,
        events: List[ToolExecutionEvent],
    ) -> bool:
        return any(
            event.tool_call.tool_name == "bash"
            and event.result.status != ToolExecutionStatus.SUCCESS
            for event in events
        )

    @classmethod
    def _events_include_no_stdin_bash_failure(
        cls,
        events: List[ToolExecutionEvent],
    ) -> bool:
        for event in events:
            if (
                event.tool_call.tool_name != "bash"
                or event.result.status == ToolExecutionStatus.SUCCESS
            ):
                continue

            event_text = cls._tool_event_text(event).lower()
            if "eoferror" in event_text and "input" in event_text:
                return True
            if not cls._bash_event_runs_solution_file(event):
                continue

            command = event.tool_call.parameters.get("command")
            command_text = command.lower() if isinstance(command, str) else ""
            has_stdin_source = any(
                marker in command_text
                for marker in ("<", "|", "printf", "echo", "cat <<")
            )
            if not has_stdin_source:
                return True
        return False

    @classmethod
    def _events_include_unsafe_benchmark_evidence(
        cls,
        events: List[ToolExecutionEvent],
    ) -> bool:
        return any(
            event.tool_call.tool_name == "bash"
            and (
                event.result.status == ToolExecutionStatus.TIMEOUT
                or cls._text_has_unsafe_benchmark_evidence(
                    cls._tool_event_result_text(event)
                )
            )
            for event in events
        )

    def _build_benchmark_control_nudge(
        self,
        *,
        tool_events: List[ToolExecutionEvent],
        task: Optional[Task],
        consumed_steps: int,
        max_steps: int,
        edit_failure_streak: int,
        seen_bash_success_with_solution: bool,
        has_unresolved_bash_failure: bool,
        seen_unsafe_evidence: bool,
        current_solution_known_bad: bool,
        can_send_constraint_nudge: bool,
        can_send_finalization_nudge: bool,
        can_send_edit_reset_nudge: bool,
        can_send_no_stdin_nudge: bool,
        can_send_failure_repair_nudge: bool,
        can_send_unsafe_nudge: bool,
    ) -> Optional[tuple[str, str]]:
        """Return a benchmark steering nudge after useful tool evidence."""
        if task is None or not self._is_benchmark_task(task):
            return None

        remaining_steps = max_steps - consumed_steps
        if remaining_steps <= 0:
            return None

        no_stdin_failure = self._events_include_no_stdin_bash_failure(tool_events)
        current_bash_failure = self._events_include_benchmark_bash_failure(tool_events)
        unsafe_evidence = (
            seen_unsafe_evidence
            or self._events_include_unsafe_benchmark_evidence(tool_events)
        )

        if can_send_no_stdin_nudge and no_stdin_failure:
            return (
                "no_stdin_repair",
                "BENCHMARK STDIN REPAIR: the last bash run invoked a Python "
                "solution without reliable stdin, or hit EOFError from input(). "
                "Do not run python3 solution.py without stdin. Re-run the "
                "provided sample using a heredoc or printf pipe with the exact "
                "sample input, then repair solution.py only if that check fails.",
            )

        if can_send_unsafe_nudge and unsafe_evidence:
            return (
                "unsafe_verification",
                "BENCHMARK UNSAFE COMPLEXITY BLOCK: recent evidence indicates "
                "a timeout, MemoryError, too-slow algorithm, or benchmark-scale "
                "risk. Do not finalize from public samples alone. Either replace "
                "solution.py with an asymptotically safe approach, or run a "
                "targeted stress/sanity check that exercises the risky large "
                "case before declaring Task complete.",
            )

        if (
            can_send_failure_repair_nudge
            and (
                has_unresolved_bash_failure
                or current_bash_failure
                or current_solution_known_bad
            )
            and self._benchmark_solution_file_exists()
        ):
            return (
                "sample_failure_repair",
                "BENCHMARK FAILURE REPAIR: a failed sample, mismatched expected "
                "stdout, incomplete solution file, or runtime check is still "
                "unresolved for the current solution file. Do not finalize or "
                "cosmetically rewrite. Inspect the failing input/output or "
                "traceback, patch solution.py once, and re-run the failing check "
                "with explicit stdin before ending with Task complete.",
            )

        if (
            can_send_finalization_nudge
            and seen_bash_success_with_solution
            and not has_unresolved_bash_failure
            and not seen_unsafe_evidence
            and remaining_steps <= 2
        ):
            return (
                "finalization",
                "BENCHMARK FINALIZATION GUARD: a non-empty solution file exists "
                "and a recent bash check succeeded. You are near the step limit. "
                "Do not rewrite solution.py just to clean up or optimize unless "
                "a provided sample is known to fail. Only finalize if no later "
                "sample/bash check has failed and no timeout, MemoryError, or "
                "unsafe-complexity evidence is present. If the provided samples "
                "pass, respond now with the current complete Python code in a "
                "markdown python block and end with Task complete.",
            )

        if (
            can_send_edit_reset_nudge
            and edit_failure_streak >= 2
            and self._events_include_benchmark_edit_failure(tool_events)
        ):
            return (
                "edit_reset",
                "BENCHMARK FRESH SOURCE RESET: repeated edit payloads for the "
                "solution file failed. Stop sending fragments, nested arrays, or "
                "serialized lists. Your next response must either call the edit "
                "tool with action='write' and content_lines as a flat JSON array "
                "of complete Python source lines for the whole solution.py, or "
                "provide the whole final Python program in a markdown python "
                "block ending with Task complete.",
            )

        if (
            can_send_constraint_nudge
            and self._events_include_successful_solution_edit(tool_events)
        ):
            return (
                "constraint",
                "BENCHMARK VERIFICATION CHECK: before trusting sample results, "
                "compare the current solution against the task constraints. "
                "State the intended time and memory complexity briefly. Public "
                "samples are only smoke tests; for D/E or large-input tasks, "
                "also run a targeted stress/sanity check when complexity is "
                "uncertain. Never use a bare no-stdin python3 solution.py check "
                "as evidence. Rewrite only if the algorithm is asymptotically "
                "unsafe or an explicit check fails. If the algorithm is safe and "
                "the provided samples pass, finalize instead of doing cosmetic "
                "rewrites.",
            )

        return None

    def _benchmark_completion_block_reason(
        self,
        *,
        task: Optional[Task],
        current_solution_known_bad: bool,
        has_unresolved_bash_failure: bool,
        seen_unsafe_evidence: bool,
    ) -> Optional[str]:
        """Return why benchmark completion must not recover solution.py."""
        if task is None or not self._is_benchmark_task(task):
            return None
        if current_solution_known_bad:
            return "current solution file is known bad or incomplete"
        if has_unresolved_bash_failure:
            return "current solution file has an unresolved failed check"
        if seen_unsafe_evidence:
            return "unsafe complexity evidence remains unresolved"
        if self._benchmark_solution_file_is_incomplete():
            return "current solution file is empty or import-only"
        return None

    @staticmethod
    def _build_benchmark_completion_block_nudge(block_reason: str) -> str:
        return (
            "BENCHMARK COMPLETION BLOCK: do not end with Task complete yet; "
            f"{block_reason}. Patch solution.py with a complete benchmark "
            "solution and re-run a provided sample with explicit stdin. Only "
            "finalize after the actual stdout matches the expected stdout and "
            "no unsafe-complexity evidence remains."
        )
    
    async def _execute_tool_calls(
        self,
        tool_calls: List[ToolCall],
        task: Optional[Task] = None,
    ) -> List[ToolExecutionEvent]:
        """
        Execute tool calls and add results to conversation.

        All tool result messages for a single assistant turn are appended as
        consecutive TOOL-role messages.  The Anthropic ``format_messages``
        implementation batches consecutive TOOL messages into a single user
        message with multiple ``tool_result`` blocks, satisfying the API's
        alternating-role requirement.

        Each TOOL-role message carries ``metadata["tool_use_id"]`` matching the
        corresponding ``tool_use`` block id from the assistant message.

        Args:
            tool_calls: List of tool calls to execute
            task: Current task, used for self-modification-specific repair nudges
        """
        events: List[ToolExecutionEvent] = []
        for i, tool_call in enumerate(tool_calls):
            try:
                logger.info(f"=== TOOL CALL {i+1} ===")
                logger.info(f"Tool: {tool_call.tool_name}")
                logger.info(f"Parameters: {tool_call.parameters}")

                result = await self.tool_registry.execute_tool(
                    tool_call.tool_name,
                    tool_call.parameters,
                )
                if (
                    task is not None
                    and self._is_self_modification_task(task)
                    and tool_call.tool_name == "edit"
                    and tool_call.parameters.get("action") == "read"
                    and result.status == ToolExecutionStatus.SUCCESS
                ):
                    self._self_modification_read_observed = True
                if (
                    task is not None
                    and self._is_self_modification_task(task)
                    and tool_call.tool_name == "edit"
                    and tool_call.parameters.get("action") != "read"
                    and result.status == ToolExecutionStatus.SUCCESS
                ):
                    self._self_modification_write_observed = True
                failure_mode = self._classify_tool_failure(tool_call, result)
                if failure_mode:
                    self._record_failure_mode(failure_mode)

                logger.info(f"Tool Result Status: {result.status}")
                logger.info(
                    f"Tool Result Output: {result.output[:500] if result.output else 'None'}..."
                )
                if result.error:
                    logger.info(f"Tool Result Error: {result.error}")
                logger.info(f"=== END TOOL CALL {i+1} ===")

                # Build the result message, threading in the tool_use_id so that
                # format_messages can construct proper tool_result blocks.
                result_message = self.message_formatter.format_tool_result_message(
                    tool_result=result
                )
                # Inject tool_use_id into metadata.
                if tool_call.call_id:
                    if result_message.metadata is None:
                        result_message.metadata = {}
                    result_message.metadata["tool_use_id"] = tool_call.call_id

                self.conversation_history.append(result_message)
                repair_nudge = self._build_edit_repair_nudge(
                    tool_call,
                    result,
                    task,
                )
                if repair_nudge:
                    self.conversation_history.append(
                        Message(role=MessageRole.USER, content=repair_nudge)
                    )
                events.append(ToolExecutionEvent(tool_call=tool_call, result=result))

            except Exception as e:
                result = ToolResult(
                    status=ToolExecutionStatus.ERROR,
                    output="",
                    error=str(e),
                )
                error_message = Message(
                    role=MessageRole.TOOL,
                    content=f"Tool execution failed: {str(e)}",
                    metadata=(
                        {"tool_use_id": tool_call.call_id}
                        if tool_call.call_id
                        else None
                    ),
                )
                self.conversation_history.append(error_message)
                events.append(ToolExecutionEvent(tool_call=tool_call, result=result))
        return events

    def _record_failure_mode(self, mode: str) -> None:
        counts = getattr(self, "_failure_mode_counts", None)
        if counts is None:
            counts = {}
            self._failure_mode_counts = counts
        counts[mode] = counts.get(mode, 0) + 1

    @staticmethod
    def _classify_tool_failure(
        tool_call: ToolCall,
        result: ToolResult,
    ) -> Optional[str]:
        if result.status == ToolExecutionStatus.SUCCESS:
            return None

        error_text = (result.error or "").lower()
        if result.status == ToolExecutionStatus.TIMEOUT or "timed out" in error_text:
            return "timeout/provider failure"

        if tool_call.tool_name == "edit":
            python_markers = (
                "syntax error",
                "invalid python",
                "unexpected indent",
                "unmatched '",
                "unmatched \"",
            )
            if any(marker in error_text for marker in python_markers):
                return "invalid Python"

            malformed_markers = (
                "invalid parameter",
                "required parameter",
                "unknown parameter",
                "content parameter",
                "content_lines parameter",
                "serialized/list fragment",
                "replacement would overwrite",
                "provide either content or content_lines",
                "line_number parameter",
                "line_count parameter",
            )
            if (
                result.status == ToolExecutionStatus.INVALID_PARAMS
                or any(marker in error_text for marker in malformed_markers)
            ):
                return "malformed edit"

        if "resource guard" in error_text or "unsafe complexity" in error_text:
            return "unsafe complexity"
        return None

    def _build_edit_repair_nudge(
        self,
        tool_call: ToolCall,
        result: ToolResult,
        task: Optional[Task],
    ) -> Optional[str]:
        """Return the most specific repair prompt for a failed edit call."""
        self_modification_nudge = self._build_self_modification_edit_repair_nudge(
            tool_call,
            result,
            task,
        )
        if self_modification_nudge:
            return self_modification_nudge
        return self._build_benchmark_edit_repair_nudge(tool_call, result, task)

    def _build_self_modification_edit_repair_nudge(
        self,
        tool_call: ToolCall,
        result: ToolResult,
        task: Optional[Task],
    ) -> Optional[str]:
        """Return a focused repair prompt after failed self-modification edits."""
        if task is None or not self._is_self_modification_task(task):
            return None
        if tool_call.tool_name != "edit":
            return None
        if result.status == ToolExecutionStatus.SUCCESS:
            return None

        action = tool_call.parameters.get("action")
        error_text = (result.error or result.output or "").lower()
        brittle_match_error = any(
            phrase in error_text
            for phrase in (
                "old_code not found",
                "no occurrences",
                "ambiguous match",
                "search text",
            )
        )
        malformed_content_error = any(
            phrase in error_text
            for phrase in (
                "serialized/list fragment",
                "content_lines parameter",
                "parameter 'content_lines'",
                'parameter "content_lines"',
                "must be an array",
                "content parameter",
                "parameter 'content'",
                'parameter "content"',
                "unknown parameter",
                "valid parameters",
                "json array",
            )
        )
        syntax_error = "syntax error" in error_text
        line_range_error = any(
            phrase in error_text
            for phrase in (
                "line_number",
                "line_replace range",
                "past end",
            )
        )
        if action not in {"modify", "line_replace", "write"}:
            return None
        if (
            not brittle_match_error
            and not malformed_content_error
            and not syntax_error
            and not line_range_error
        ):
            return None

        if malformed_content_error:
            return (
                "SELF-MODIFICATION EDIT REPAIR: the edit payload was malformed. "
                "Retry with the edit tool using content_lines as a JSON array of "
                "plain strings, one complete Python source line per string. Do "
                "not send a serialized list inside the content string."
            )

        if syntax_error:
            return (
                "SELF-MODIFICATION EDIT REPAIR: the attempted source edit made "
                "agent code syntactically invalid. Read only the exact target "
                "line range, then retry a smaller action='line_replace' patch "
                "with complete Python lines that preserve surrounding indentation "
                "and brackets. Prefer changing executable logic or a named "
                "instruction block, not example workflow text."
            )

        if line_range_error:
            return (
                "SELF-MODIFICATION EDIT REPAIR: the requested line_replace range "
                "does not match the current file. Read a narrow range around the "
                "intended target, then retry with the exact current line_number "
                "and line_count. Do not guess line numbers."
            )

        return (
            "SELF-MODIFICATION EDIT REPAIR: the exact modify search_text did not "
            "apply cleanly. Do not retry the same search_text. Read a narrow line "
            "range if needed, then call the edit tool with action='line_replace', "
            "file_path, line_number, line_count, and content_lines. Keep the "
            "replacement syntactically valid and preserve the surrounding code."
        )

    def _build_benchmark_edit_repair_nudge(
        self,
        tool_call: ToolCall,
        result: ToolResult,
        task: Optional[Task],
    ) -> Optional[str]:
        """Return a focused repair prompt after failed benchmark solution edits."""
        if task is None or not self._is_benchmark_task(task):
            return None
        if tool_call.tool_name != "edit":
            return None
        if result.status == ToolExecutionStatus.SUCCESS:
            return None

        action = tool_call.parameters.get("action")
        if action not in {"write", "append", "line_replace"}:
            return None

        error_text = (result.error or result.output or "").lower()
        malformed_content_error = any(
            phrase in error_text
            for phrase in (
                "serialized/list fragment",
                "content_lines parameter",
                "parameter 'content_lines'",
                'parameter "content_lines"',
                "must be an array",
                "content parameter",
                "parameter 'content'",
                'parameter "content"',
                "unknown parameter",
                "valid parameters",
                "json array",
            )
        )
        syntax_error = "syntax error" in error_text
        if not malformed_content_error and not syntax_error:
            return None

        if syntax_error:
            return (
                "BENCHMARK EDIT REPAIR: the previous Python edit was rejected "
                "because solution.py would be syntactically invalid. Retry with "
                "one complete, valid solution.py. Prefer action='write' and "
                "content_lines as a JSON array of plain strings, one full source "
                "line per string. Do not patch partial fragments."
            )

        return (
            "BENCHMARK EDIT REPAIR: the previous edit payload was malformed. "
            "Retry immediately by writing the complete solution.py with the edit "
            "tool using action='write' and content_lines as a JSON array of plain "
            "strings, one complete Python source line per string. Do not nest "
            "arrays or objects inside content_lines, and do not send a serialized "
            "list in content. If tool arguments keep failing, provide the final "
            "Python code in a markdown python block ending with Task complete."
        )
    
    def _build_system_message(self, context: ConversationContext) -> Message:
        """
        Build the system message for the agent.
        
        Args:
            context: Conversation context
            
        Returns:
            System message
        """
        self_modification_instructions = ""
        if context.task_id.startswith("self_modify"):
            self_modification_instructions = """
SELF-MODIFICATION MODE:
=======================
- This task is not a benchmark solution task. Do not create `solution.py`.
- Your output is only useful if the workspace has a real Python source change
  in `agent.py`, `tools/*.py`, `fm_interface/*.py`, or a provider module.
- Read only the files needed to choose a patch. Prefer narrow reads with
  `line_number` and `line_count`; do not read entire large files such as
  `agent.py` unless the exact target cannot be found another way. After a few
  inspection calls, make a small valid edit instead of continuing analysis.
- For source edits, prefer the edit tool action `line_replace` after reading a
  narrow line range. Provide `line_number`, `line_count`, and `content_lines`
  with one complete Python source line per string. Use this instead of long
  `search_text` values when exact matching is unreliable.
- Target executable logic, tool-use repair logic, or a named instruction block
  such as SELF-MODIFICATION MODE or BENCHMARK SOLUTION FILE. Do not edit
  incidental examples, sample workflow text, markdown fences, or comments unless
  the task specifically asks for documentation-only changes.
- Prefer changes that improve benchmark solver control policy, verification
  discipline, malformed-tool recovery, timeout handling, or token-efficient
  reads. Avoid changing `_is_task_complete` or completion phrase detection
  unless the task explicitly asks for completion signaling; that rarely improves
  benchmark score.
- If you are unsure what to change, improve prompt/nudge/tool-use logic in
  `agent.py` with a minimal, syntactically valid patch against the named
  instruction block or method body you intend to improve.
- Before finalizing, name the changed source file and end with `Task complete`.
"""

        # Base system instructions
        base_instructions = f"""You are a sophisticated coding agent capable of solving programming tasks.

Your capabilities:
- You can execute bash commands to run code, check outputs, and manage files
- You can edit files to implement solutions
- You analyze tasks systematically and break them down into steps
- You test your solutions thoroughly before finalizing them
{self_modification_instructions}

Your approach should be:
1. Understand the task requirements completely
2. Plan your solution step by step
3. Implement the solution using available tools
4. Test your implementation carefully
5. Refine as needed

BENCHMARK SOLUTION FILE:
========================
- When solving benchmark programming tasks, write the final program to
  `solution.py` in the current working directory.
- Do not write contest solutions to `solve.py`, `main.py`, or an absolute
  `/tmp/...` path unless you also copy the final code into `solution.py`.
- The evaluator can recover `solution.py` even if you hit the step limit, so
  create or update that file early.
- If the edit tool rejects a Python write as a serialized/list fragment, do
  not retry the same payload. Retry the edit call with `content_lines`, using
  one complete Python source line per string, or provide the final solution in
  a markdown `python` code block and end with the required completion phrase.

TESTING GUIDELINES:
==================
- Focus on the examples provided in the task description
- DO NOT invent additional test cases with your own expected outputs
- If you want to test edge cases, clearly state you're exploring, don't assume the outputs
- Your primary goal is to satisfy the given examples and requirements
- Once `solution.py` passes the provided examples, stop using tools and provide
  the final code block ending with `Task complete`.
- If you are on the final available step and `solution.py` exists, do not run
  more exploratory tests or attempt a risky rewrite. Finalize with the current
  complete solution code unless a provided sample is known to fail.
- Before finalizing a sample-passing solution, compare the algorithm against the
  input constraints. Public samples are only smoke tests; hidden tests often
  fail slow or partial D/E-task approaches.
- For stdin/stdout programs, prefer testing with a quoted heredoc, for example:
  `python3 solution.py << 'EOF'`
  then the sample input, then `EOF` on its own line.
- Do not use `echo -e` for sample tests. Shell behavior differs across
  environments; use heredocs or `printf` instead.
- Do not run `python3 solution.py` with no stdin for an input-reading program.
- Avoid shell pipelines and semicolon-packed one-liners when testing; the bash
  tool intentionally blocks broad shell composition for safety.

IMPORTANT: Task Completion Process
==================================
You will have MULTIPLE opportunities to interact during task solving:
- After you use tools (edit, bash), you'll see the results in the next interaction
- You can then test your solution, debug issues, or refine your implementation
- Only declare the task complete AFTER you've verified your solution works

CRITICAL COMPLETION REQUIREMENT:
⚠️ WITHOUT PROPER COMPLETION SIGNALING, YOUR INLINE SOLUTION MAY NOT BE EVALUATED! ⚠️

When you have VERIFIED your solution works correctly, your response MUST:
1. Include the solution code in a markdown code block
2. End with EXACTLY one of these phrases:
   - "Task complete"
   - "Solution implemented"

Example workflow:
---
Interaction 1: "I'll implement the reverse_string function using the edit tool..."
[Uses edit tool to create solution.py]

Interaction 2: "Good, the file was created. Let me test it..."
[Uses bash tool to run tests]

Interaction 3: "The tests pass! Here's the final solution:

```python
def reverse_string(s):
    return s[::-1]
```

Task complete"
---

REMEMBER:
- Use tools to implement and test your solution
- You'll see tool results before declaring completion
- Only say "Task complete" AFTER verifying your solution works
- The completion phrase must be at the END of your response
- Your code can be perfect, but without `solution.py` or the completion signal, it may score 0

Always be precise, methodical, and thorough in your work."""
        
        # Get available tools
        available_tools = self.tool_registry.get_tool_schemas()
        
        return self.message_formatter.format_system_message(
            base_instructions=base_instructions,
            available_tools=available_tools,
            context=context
        )
    
    def _is_task_complete(self, response: str, task: Task) -> bool:
        """
        Determine if the task appears to be complete based on the response.
        
        Args:
            response: Agent's response
            task: Current task
            
        Returns:
            bool: True if task appears complete
        """
        # Primary completion indicators (MUST match system prompt)
        primary_indicators = [
            "task complete",
            "solution implemented"
        ]
        
        # Secondary indicators (for backward compatibility)
        secondary_indicators = [
            "problem solved",
            "implementation finished",
            "all tests pass",
            "task completed",  # Handle past tense variant
            "solution is implemented",  # Handle variant phrasing
            "i've completed the task",
            "the task is complete"
        ]
        
        response_lower = response.lower().strip()
        
        # First check for primary indicators (these are what we instruct agents to use)
        for indicator in primary_indicators:
            if indicator in response_lower:
                logger.info(f"Task completion detected with primary indicator: '{indicator}'")
                return True
        
        # Then check secondary indicators
        for indicator in secondary_indicators:
            if indicator in response_lower:
                logger.warning(f"Task completion detected with secondary indicator: '{indicator}' - agent should use 'Task complete' or 'Solution implemented'")
                return True
        
        # Additional check: if response ends with code block and contains solution-like language
        # This helps catch cases where agent thinks they're done but forgot the magic phrase
        if response_lower.endswith("```") and any(phrase in response_lower for phrase in ["here's my solution", "here is my solution", "final solution", "complete solution"]):
            logger.warning("Response appears complete (ends with code + solution language) but missing explicit completion signal")
            # Still return False to enforce the requirement, but log it
            return False
        
        # Log when we think agent might be done but didn't signal properly
        if "```python" in response and response_lower.count("```") >= 2:
            # Agent provided code
            done_words = ["done", "finished", "complete", "implemented", "ready", "final"]
            if any(word in response_lower.split() for word in done_words):
                logger.warning(f"Agent response contains code and completion-like words but no explicit completion signal. Response preview: {response_lower[:100]}...")
        
        # If no explicit completion signal, assume not complete
        return False
    
    def _extract_code_solution(self, response: str) -> str:
        """
        Extract Python code from the agent's response.
        
        The agent is instructed to provide code in markdown code blocks.
        
        Args:
            response: Agent's response containing the solution
            
        Returns:
            Extracted Python code
        """
        import re
        
        # Extract code from markdown code blocks
        # Pattern matches ```python or ``` followed by code and closing ```
        # More flexible pattern to handle various formatting
        code_block_pattern = r'```(?:python)?\s*\n(.*?)\n\s*```'
        matches = re.findall(code_block_pattern, response, re.DOTALL)
        
        if matches:
            # Return the last code block (likely the final solution)
            code = matches[-1].strip()
            logger.info(f"Extracted code from markdown block: {len(code)} characters")
            return code
        
        # If no code blocks found, log warning
        logger.warning("No markdown code blocks found in response")
        
        # As a fallback, try to find code that looks like a function definition
        lines = response.split('\n')
        code_lines = []
        in_function = False
        
        for line in lines:
            # Check if line starts a function
            if line.strip().startswith(('def ', 'class ', 'import ', 'from ', 'async def ')):
                in_function = True
                code_lines = [line]
            elif in_function:
                # Continue collecting lines if they're indented or empty
                if line.strip() == '' or line.startswith((' ', '\t')):
                    code_lines.append(line)
                else:
                    # Non-indented non-empty line, function likely ended
                    if not line.strip().startswith(('def ', 'class ', 'import ', 'from ')):
                        break
        
        if code_lines:
            code = '\n'.join(code_lines).strip()
            logger.info(f"Extracted code using fallback method: {len(code)} characters")
            return code
        
        # If all else fails, return empty string and log error
        logger.error("Could not extract any code from response")
        return ""
    
    def get_agent_info(self) -> Dict[str, Any]:
        """
        Get information about this agent.
        
        Returns:
            Dict containing agent metadata
        """
        return {
            "agent_id": self.agent_id,
            "generation": self.generation,
            "parent_id": self.parent_id,
            "fm_provider": self.config.fm_provider,
            "working_directory": str(self.working_directory),
            "available_tools": self.tool_registry.list_tools(),
            "performance_metrics": self.performance_metrics.copy(),
            "created_at": self.created_at
        }
    
    def update_performance_metrics(self, metrics: Dict[str, float]) -> None:
        """
        Update the agent's performance metrics.
        
        Args:
            metrics: New metrics to add/update
        """
        self.performance_metrics.update(metrics)
    
    def clone_for_modification(self, new_agent_id: str) -> 'Agent':
        """
        Create a clone of this agent for modification.
        
        Args:
            new_agent_id: ID for the new agent
            
        Returns:
            New Agent instance that's a copy of this one
        """
        # Create new config
        new_config = AgentConfig(
            agent_id=new_agent_id,
            fm_provider=self.config.fm_provider,
            fm_config=self.config.fm_config.copy(),
            working_directory=f"{self.config.working_directory}_{new_agent_id}",
            tool_timeout=self.config.tool_timeout,
            max_iterations=self.config.max_iterations,
            memory_limit=self.config.memory_limit
        )
        
        # Create new agent
        new_agent = Agent(new_config)
        new_agent.generation = self.generation + 1
        new_agent.parent_id = self.agent_id
        new_agent.performance_metrics = self.performance_metrics.copy()
        
        return new_agent
    
    @classmethod
    def create_seed_agent(
        cls,
        agent_id: str,
        fm_provider: str,
        fm_config: Dict[str, Any],
        working_directory: str
    ) -> 'Agent':
        """
        Create a seed agent (generation 0).
        
        Args:
            agent_id: Unique identifier for the agent
            fm_provider: FM provider name
            fm_config: FM configuration
            working_directory: Working directory for the agent
            
        Returns:
            New seed Agent instance
        """
        config = AgentConfig(
            agent_id=agent_id,
            fm_provider=fm_provider,
            fm_config=fm_config,
            working_directory=working_directory
        )
        
        agent = cls(config)
        agent.generation = 0
        agent.created_at = "seed"
        
        return agent
