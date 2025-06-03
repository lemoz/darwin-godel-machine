"""
Message formatting utilities for Foundation Model interactions.

This module provides utilities for transforming messages between different formats,
handling context assembly, and managing conversation history for the DGM system.
"""

from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field
from enum import Enum

from .api_handler import Message, MessageRole, ToolCall, ToolResult
from ..tools.base_tool import ToolExecutionStatus


class MessageContext(Enum):
    """Types of context that can be included in messages."""
    TASK_DESCRIPTION = "task_description"
    AGENT_CAPABILITIES = "agent_capabilities"
    TOOL_DESCRIPTIONS = "tool_descriptions"
    EVALUATION_LOGS = "evaluation_logs"
    SYSTEM_INSTRUCTIONS = "system_instructions"


@dataclass
class ConversationContext:
    """Container for conversation context and metadata."""
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    iteration: Optional[int] = None
    benchmark_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MessageFormatter:
    """
    Utilities for formatting and transforming messages for Foundation Model interactions.
    
    This class handles the assembly of conversation context, tool descriptions,
    and other metadata into properly formatted messages for different FM providers.
    """
    
    def __init__(self, include_context: List[MessageContext] = None):
        """
        Initialize the message formatter.
        
        Args:
            include_context: List of context types to include by default
        """
        self.include_context = include_context or [
            MessageContext.TASK_DESCRIPTION,
            MessageContext.AGENT_CAPABILITIES,
            MessageContext.TOOL_DESCRIPTIONS
        ]
    
    def format_system_message(
        self,
        base_instructions: str,
        available_tools: List[Dict[str, Any]] = None,
        context: ConversationContext = None,
        additional_context: Dict[MessageContext, str] = None
    ) -> Message:
        """
        Format a comprehensive system message with instructions and context.
        
        Args:
            base_instructions: Core system instructions for the agent
            available_tools: List of available tool definitions
            context: Conversation context metadata
            additional_context: Additional context to include
            
        Returns:
            Message: Formatted system message
        """
        content_parts = [base_instructions]
        
        # Add tool descriptions if available
        if available_tools and MessageContext.TOOL_DESCRIPTIONS in self.include_context:
            tool_section = self._format_tool_descriptions(available_tools)
            content_parts.append(tool_section)
        
        # Add additional context
        if additional_context:
            for context_type, context_content in additional_context.items():
                if context_type in self.include_context and context_content:
                    content_parts.append(f"\n## {context_type.value.replace('_', ' ').title()}\n{context_content}")
        
        # Add conversation metadata if available
        if context:
            metadata_section = self._format_conversation_metadata(context)
            if metadata_section:
                content_parts.append(metadata_section)
        
        return Message(
            role=MessageRole.SYSTEM,
            content="\n\n".join(content_parts),
            metadata={"context": context, "tools": available_tools}
        )
    
    def format_task_message(
        self,
        task_description: str,
        test_description: Optional[str] = None,
        constraints: Optional[List[str]] = None,
        examples: Optional[List[Dict[str, str]]] = None
    ) -> Message:
        """
        Format a task description message for the agent.
        
        Args:
            task_description: Main task description
            test_description: Description of how the task will be tested
            constraints: List of constraints or requirements
            examples: List of example inputs/outputs
            
        Returns:
            Message: Formatted task message
        """
        content_parts = ["## Task Description", task_description]
        
        if test_description:
            content_parts.extend(["\n## Testing", test_description])
        
        if constraints:
            content_parts.append("\n## Constraints")
            for constraint in constraints:
                content_parts.append(f"- {constraint}")
        
        if examples:
            content_parts.append("\n## Examples")
            for i, example in enumerate(examples, 1):
                content_parts.append(f"\n### Example {i}")
                for key, value in example.items():
                    content_parts.append(f"**{key.title()}**: {value}")
        
        return Message(
            role=MessageRole.USER,
            content="\n".join(content_parts),
            metadata={"type": "task", "examples": examples}
        )
    
    def format_tool_result_message(
        self,
        tool_result: ToolResult,
        include_metadata: bool = True
    ) -> Message:
        """
        Format a tool execution result as a message.
        
        Args:
            tool_result: Result of tool execution
            include_metadata: Whether to include execution metadata
            
        Returns:
            Message: Formatted tool result message
        """
        if tool_result.status == ToolExecutionStatus.SUCCESS:
            content = f"Tool execution successful:\n{tool_result.output}"
        else:
            content = f"Tool execution failed:\n{tool_result.error or 'Unknown error'}"
            if tool_result.output:
                content += f"\nPartial output:\n{tool_result.output}"
        
        metadata = {"tool_result": tool_result} if include_metadata else None
        
        return Message(
            role=MessageRole.TOOL,
            content=content,
            metadata=metadata
        )
    
    def format_evaluation_feedback(
        self,
        evaluation_results: Dict[str, Any],
        failed_tests: List[Dict[str, Any]] = None,
        performance_metrics: Dict[str, float] = None
    ) -> Message:
        """
        Format evaluation feedback for agent improvement.
        
        Args:
            evaluation_results: Results from benchmark evaluation
            failed_tests: List of failed test cases with details
            performance_metrics: Performance metrics and scores
            
        Returns:
            Message: Formatted evaluation feedback
        """
        content_parts = ["## Evaluation Results"]
        
        # Overall results
        if performance_metrics:
            content_parts.append("\n### Performance Metrics")
            for metric, value in performance_metrics.items():
                content_parts.append(f"- {metric}: {value}")
        
        # Failed tests
        if failed_tests:
            content_parts.append("\n### Failed Test Cases")
            for i, test in enumerate(failed_tests, 1):
                content_parts.append(f"\n#### Test {i}")
                content_parts.append(f"Input: {test.get('input', 'N/A')}")
                content_parts.append(f"Expected: {test.get('expected', 'N/A')}")
                content_parts.append(f"Actual: {test.get('actual', 'N/A')}")
                if test.get('error'):
                    content_parts.append(f"Error: {test['error']}")
        
        return Message(
            role=MessageRole.USER,
            content="\n".join(content_parts),
            metadata={"type": "evaluation", "results": evaluation_results}
        )
    
    def create_conversation_history(
        self,
        messages: List[Message],
        max_tokens: Optional[int] = None,
        preserve_system: bool = True
    ) -> List[Message]:
        """
        Create a conversation history with optional token limiting.
        
        Args:
            messages: List of messages to include
            max_tokens: Maximum token count (approximate)
            preserve_system: Always preserve system messages
            
        Returns:
            List of messages within token limits
        """
        if not max_tokens:
            return messages.copy()
        
        # Simple token estimation (rough approximation)
        def estimate_tokens(text: str) -> int:
            return len(text.split()) + len(text) // 4
        
        result = []
        total_tokens = 0
        
        # Always include system messages first if preserving
        if preserve_system:
            for msg in messages:
                if msg.role == MessageRole.SYSTEM:
                    tokens = estimate_tokens(msg.content)
                    result.append(msg)
                    total_tokens += tokens
        
        # Add other messages in reverse order (most recent first)
        other_messages = [msg for msg in messages if msg.role != MessageRole.SYSTEM]
        
        for msg in reversed(other_messages):
            tokens = estimate_tokens(msg.content)
            if total_tokens + tokens > max_tokens:
                break
            result.insert(-len([m for m in result if m.role == MessageRole.SYSTEM]), msg)
            total_tokens += tokens
        
        return result
    
    def _format_tool_descriptions(self, tools: List[Dict[str, Any]]) -> str:
        """
        Format tool descriptions for inclusion in system messages.
        
        Args:
            tools: List of tool definitions
            
        Returns:
            Formatted tool descriptions
        """
        if not tools:
            return ""
        
        content_parts = ["## Available Tools"]
        
        for tool in tools:
            name = tool.get("name", "unknown")
            description = tool.get("description", "No description")
            parameters = tool.get("parameters", {})
            
            content_parts.append(f"\n### {name}")
            content_parts.append(description)
            
            if parameters and "properties" in parameters:
                content_parts.append("\n**Parameters:**")
                for param_name, param_info in parameters["properties"].items():
                    param_type = param_info.get("type", "string")
                    param_desc = param_info.get("description", "")
                    required = param_name in parameters.get("required", [])
                    req_marker = " (required)" if required else ""
                    content_parts.append(f"- `{param_name}` ({param_type}){req_marker}: {param_desc}")
        
        return "\n".join(content_parts)
    
    def _format_conversation_metadata(self, context: ConversationContext) -> Optional[str]:
        """
        Format conversation metadata for inclusion in messages.
        
        Args:
            context: Conversation context
            
        Returns:
            Formatted metadata or None if no relevant metadata
        """
        if not context:
            return None
        
        parts = []
        
        if context.task_id:
            parts.append(f"Task ID: {context.task_id}")
        if context.agent_id:
            parts.append(f"Agent ID: {context.agent_id}")
        if context.iteration is not None:
            parts.append(f"Iteration: {context.iteration}")
        if context.benchmark_name:
            parts.append(f"Benchmark: {context.benchmark_name}")
        
        if not parts:
            return None
        
        return f"\n## Context\n" + "\n".join(f"- {part}" for part in parts)