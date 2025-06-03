"""
Main DGM Agent implementation.

This module contains the core Agent class that represents a self-modifying
coding agent in the Darwin Gödel Machine system.
"""

import asyncio
import logging
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
        if provider.lower() == "gemini":
            return GeminiHandler(fm_config)
        elif provider.lower() == "anthropic":
            return AnthropicHandler(fm_config)
        else:
            raise ValueError(f"Unsupported FM provider: {provider}")
    
    def _register_default_tools(self) -> None:
        """Register the default tools available to this agent."""
        # Register bash tool
        bash_tool = BashTool(
            working_directory=str(self.working_directory),
            timeout=self.config.tool_timeout
        )
        self.tool_registry.register_tool(bash_tool)
        
        # Register edit tool (placeholder for now)
        edit_tool = EditTool(working_directory=str(self.working_directory))
        self.tool_registry.register_tool(edit_tool)
    
    async def solve_task(self, task: Task) -> Dict[str, Any]:
        """
        Solve a coding task using the agent's capabilities.
        
        Args:
            task: Task to solve
            
        Returns:
            Dict containing solution and execution details
        """
        self.current_task = task
        
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
            
            return {
                "success": True,
                "solution": solution,
                "task_id": task.task_id,
                "agent_id": self.agent_id,
                "steps": len(self.conversation_history),
                "conversation_history": [msg.content for msg in self.conversation_history]
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "task_id": task.task_id,
                "agent_id": self.agent_id,
                "steps": len(self.conversation_history),
                "conversation_history": [msg.content for msg in self.conversation_history]
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
        max_steps = 20  # Reasonable limit based on observed agent behavior
        
        logger.info(f"Starting task solution with up to {max_steps} steps for task {task.task_id}")
        
        # Each step is an LLM call + tool execution cycle
        for step in range(max_steps):
            logger.info(f"Step {step + 1}/{max_steps}")
            
            # Get completion from FM
            request = CompletionRequest(
                messages=self.conversation_history,
                tools=self.tool_registry.get_tool_schemas(),
                max_tokens=self.config.fm_config.get("max_tokens", 8192),
                temperature=self.config.fm_config.get("temperature", 0.1)
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
            
            # Log agent's response for debugging
            if response.content:
                logger.info(f"=== AGENT RESPONSE (Step {step + 1}) ===")
                logger.info(response.content)
                logger.info(f"=== END RESPONSE ===")
            
            # Add assistant response to conversation
            assistant_message = Message(
                role=MessageRole.ASSISTANT,
                content=response.content.rstrip() if response.content else ""
            )
            self.conversation_history.append(assistant_message)
            
            # Save conversation history for debugging
            import json
            from pathlib import Path
            debug_dir = Path("debug")
            debug_dir.mkdir(exist_ok=True)
            
            history_file = debug_dir / f"conversation_history_task_{task.task_id}_step{step+1}.json"
            conversation_data = {
                "task_id": task.task_id,
                "step": step + 1,
                "conversation": [
                    {
                        "role": msg.role.value,
                        "content": msg.content[:1000] + "..." if len(msg.content) > 1000 else msg.content
                    }
                    for msg in self.conversation_history
                ]
            }
            
            with open(history_file, 'w') as f:
                json.dump(conversation_data, f, indent=2)
            logger.info(f"Saved conversation history to {history_file}")
            
            # Execute any tool calls
            if response.tool_calls:
                logger.info(f"Executing {len(response.tool_calls)} tool calls")
                await self._execute_tool_calls(response.tool_calls)
                # Continue to next step so agent can see tool results
                continue
            
            # Check if task appears complete (only when no tools were called)
            task_complete = self._is_task_complete(response.content, task)
            logger.info(f"_is_task_complete returned: {task_complete}")
            
            if task_complete:
                logger.info(f"Task complete after Step {step + 1}")
                # Extract Python code from the response
                solution = self._extract_code_solution(response.content)
                return solution
            
            # If no tools and not complete, agent might be stuck
            if not response.tool_calls:
                logger.warning(f"Agent made no tool calls and didn't complete task")
                # Add a nudge to help the agent continue
                nudge_message = Message(
                    role=MessageRole.USER,
                    content="Please continue working on the task. If you've completed it, say 'Task complete'."
                )
                self.conversation_history.append(nudge_message)
                
                # If this is near the end, break to avoid infinite nudging
                if step >= max_steps - 5:
                    logger.warning(f"Approaching max steps without completion")
                    break
        
        logger.warning(f"Reached max steps ({max_steps}) without task completion")
        return solution
    
    async def _execute_tool_calls(self, tool_calls: List[ToolCall]) -> None:
        """
        Execute tool calls and add results to conversation.
        
        Args:
            tool_calls: List of tool calls to execute
        """
        for i, tool_call in enumerate(tool_calls):
            try:
                # Log tool call details
                logger.info(f"=== TOOL CALL {i+1} ===")
                logger.info(f"Tool: {tool_call.tool_name}")
                logger.info(f"Parameters: {tool_call.parameters}")
                
                # Execute the tool
                result = await self.tool_registry.execute_tool(
                    tool_call.tool_name,
                    tool_call.parameters
                )
                
                # Log tool result
                logger.info(f"Tool Result Status: {result.status}")
                logger.info(f"Tool Result Output: {result.output[:500] if result.output else 'None'}...")
                if result.error:
                    logger.info(f"Tool Result Error: {result.error}")
                logger.info(f"=== END TOOL CALL {i+1} ===")
                
                # Format result as message
                result_message = self.message_formatter.format_tool_result_message(
                    tool_result=result
                )
                self.conversation_history.append(result_message)
                
            except Exception as e:
                # Add error message to conversation
                error_message = Message(
                    role=MessageRole.TOOL,
                    content=f"Tool execution failed: {str(e)}"
                )
                self.conversation_history.append(error_message)
    
    def _build_system_message(self, context: ConversationContext) -> Message:
        """
        Build the system message for the agent.
        
        Args:
            context: Conversation context
            
        Returns:
            System message
        """
        # Base system instructions
        base_instructions = """You are a sophisticated coding agent capable of solving programming tasks.

Your capabilities:
- You can execute bash commands to run code, check outputs, and manage files
- You can edit files to implement solutions
- You analyze tasks systematically and break them down into steps
- You test your solutions thoroughly before finalizing them

Your approach should be:
1. Understand the task requirements completely
2. Plan your solution step by step
3. Implement the solution using available tools
4. Test your implementation carefully
5. Refine as needed

TESTING GUIDELINES:
==================
- Focus on the examples provided in the task description
- DO NOT invent additional test cases with your own expected outputs
- If you want to test edge cases, clearly state you're exploring, don't assume the outputs
- Your primary goal is to satisfy the given examples and requirements

IMPORTANT: Task Completion Process
==================================
You will have MULTIPLE opportunities to interact during task solving:
- After you use tools (edit, bash), you'll see the results in the next interaction
- You can then test your solution, debug issues, or refine your implementation
- Only declare the task complete AFTER you've verified your solution works

CRITICAL COMPLETION REQUIREMENT:
⚠️ WITHOUT PROPER COMPLETION SIGNALING, YOUR SOLUTION WILL NOT BE EVALUATED! ⚠️

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
- Your code can be perfect, but without the completion signal, it scores 0

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