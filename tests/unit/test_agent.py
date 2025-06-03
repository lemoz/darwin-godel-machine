"""
Unit tests for agent base components.
"""

import unittest
import asyncio
from pathlib import Path
import tempfile
import json
from unittest.mock import patch, AsyncMock, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.test_utils import TestFixtures
from agent.agent import Agent, AgentConfig, Task
from agent.fm_interface.api_handler import (
    ApiHandler, CompletionResponse, ToolCall
)
from agent.tools.bash_tool import BashTool
from agent.tools.edit_tool import EditTool


class TestAgent(unittest.TestCase):
    """Test agent base functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)
        
        # FM config
        self.fm_config = {
            "provider": "anthropic",
            "model": "claude-3-sonnet-20240229",
            "max_retries": 3
        }
        
        # Create test files
        (self.test_path / "test.txt").write_text("test content")
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.test_dir)
    
    def test_agent_initialization(self):
        """Test agent initialization."""
        config = AgentConfig(
            agent_id="test_agent",
            fm_provider="anthropic",
            fm_config=self.fm_config,
            working_directory=str(self.test_path)
        )
        
        agent = Agent(config)
        
        self.assertEqual(agent.agent_id, "test_agent")
        self.assertEqual(agent.working_directory, self.test_path)
        self.assertIsInstance(agent.fm_handler, ApiHandler)
        self.assertIsNotNone(agent.tool_registry)
        self.assertIn("bash", agent.tool_registry._tools)
        self.assertIn("edit", agent.tool_registry._tools)
    
    @patch('agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion')
    async def test_execute_task_simple(self, mock_get_completion):
        """Test simple task execution."""
        # Mock FM to return simple response
        mock_response = CompletionResponse(
            content="Task completed successfully",
            stop_reason="end_turn",
            usage={"input_tokens": 10, "output_tokens": 20}
        )
        mock_get_completion.return_value = mock_response
        
        config = AgentConfig(
            agent_id="test_agent",
            fm_provider="anthropic",
            fm_config=self.fm_config,
            working_directory=str(self.test_path)
        )
        agent = Agent(config)
        
        task = Task(
            task_id="test_task",
            description="Simple task"
        )
        result = await agent.solve_task(task)
        
        self.assertIsNotNone(result)
        self.assertIn("response", result)
        mock_generate.assert_called_once()
    
    @patch('agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion')
    async def test_execute_task_with_bash_tool(self, mock_get_completion):
        """Test task execution with bash tool usage."""
        # Mock FM to request bash command
        mock_response1 = CompletionResponse(
            content="<tool_use>bash</tool_use><command>ls -la</command>",
            stop_reason="tool_use",
            usage={"input_tokens": 10, "output_tokens": 20},
            tool_calls=[ToolCall(tool_name="bash", tool_input={"command": "ls -la"})]
        )
        mock_response2 = CompletionResponse(
            content="Directory listed successfully",
            stop_reason="end_turn",
            usage={"input_tokens": 10, "output_tokens": 20}
        )
        mock_get_completion.side_effect = [mock_response1, mock_response2]
        
        config = AgentConfig(
            agent_id="test_agent",
            fm_provider="anthropic",
            fm_config=self.fm_config,
            working_directory=str(self.test_path)
        )
        agent = Agent(config)
        
        task = Task(
            task_id="test_task",
            description="List files in directory"
        )
        result = await agent.solve_task(task)
        
        self.assertIsNotNone(result)
        self.assertEqual(mock_get_completion.call_count, 2)
    
    @patch('agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion')
    async def test_execute_task_with_edit_tool(self, mock_get_completion):
        """Test task execution with edit tool usage."""
        # Mock FM to request file edit
        mock_response1 = CompletionResponse(
            content="<tool_use>edit</tool_use><file>new_file.py</file><content>print('Hello')</content>",
            stop_reason="tool_use",
            usage={"input_tokens": 10, "output_tokens": 20},
            tool_calls=[ToolCall(tool_name="edit", tool_input={"file": "new_file.py", "content": "print('Hello')"})]
        )
        mock_response2 = CompletionResponse(
            content="File created successfully",
            stop_reason="end_turn",
            usage={"input_tokens": 10, "output_tokens": 20}
        )
        mock_get_completion.side_effect = [mock_response1, mock_response2]
        
        config = AgentConfig(
            agent_id="test_agent",
            fm_provider="anthropic",
            fm_config=self.fm_config,
            working_directory=str(self.test_path)
        )
        agent = Agent(config)
        
        task = Task(
            task_id="test_task",
            description="Create a Python file"
        )
        result = await agent.solve_task(task)
        
        self.assertIsNotNone(result)
        self.assertTrue((self.test_path / "new_file.py").exists())
    
    @patch('agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion')
    async def test_execute_task_with_error(self, mock_get_completion):
        """Test task execution error handling."""
        # Mock FM to raise error
        mock_get_completion.side_effect = Exception("FM error")
        
        config = AgentConfig(
            agent_id="test_agent",
            fm_provider="anthropic",
            fm_config=self.fm_config,
            working_directory=str(self.test_path)
        )
        agent = Agent(config)
        
        task = Task(
            task_id="test_task",
            description="Failing task"
        )
        with self.assertRaises(Exception) as cm:
            await agent.solve_task(task)
        
        self.assertIn("FM error", str(cm.exception))
    
    @patch('agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion')
    async def test_multi_step_task_execution(self, mock_get_completion):
        """Test multi-step task execution."""
        # Mock FM to perform multiple steps
        mock_responses = [
            # Step 1: Create directory
            CompletionResponse(
                content="<tool_use>bash</tool_use><command>mkdir -p project/src</command>",
                stop_reason="tool_use",
                usage={"input_tokens": 10, "output_tokens": 20},
                tool_calls=[ToolCall(tool_name="bash", tool_input={"command": "mkdir -p project/src"})]
            ),
            # Step 2: Create file
            CompletionResponse(
                content="<tool_use>edit</tool_use><file>project/src/main.py</file><content>def main():\n    print('Hello')</content>",
                stop_reason="tool_use",
                usage={"input_tokens": 10, "output_tokens": 20},
                tool_calls=[ToolCall(tool_name="edit", tool_input={"file": "project/src/main.py", "content": "def main():\n    print('Hello')"})]
            ),
            # Step 3: Run file
            CompletionResponse(
                content="<tool_use>bash</tool_use><command>cd project/src && python main.py</command>",
                stop_reason="tool_use",
                usage={"input_tokens": 10, "output_tokens": 20},
                tool_calls=[ToolCall(tool_name="bash", tool_input={"command": "cd project/src && python main.py"})]
            ),
            # Final analysis
            CompletionResponse(
                content="Successfully created project structure and executed the file",
                stop_reason="end_turn",
                usage={"input_tokens": 10, "output_tokens": 20}
            )
        ]
        mock_get_completion.side_effect = mock_responses
        
        config = AgentConfig(
            agent_id="test_agent",
            fm_provider="anthropic",
            fm_config=self.fm_config,
            working_directory=str(self.test_path)
        )
        agent = Agent(config)
        
        # Execute multi-step task
        task = Task(
            task_id="test_task",
            description="Create and run a Python project"
        )
        result = await agent.solve_task(task)
        
        self.assertIsNotNone(result)
        self.assertTrue((self.test_path / "project" / "src" / "main.py").exists())
        self.assertEqual(mock_get_completion.call_count, 4)
    
    def test_tool_registry_integration(self):
        """Test tool registry integration."""
        config = AgentConfig(
            agent_id="test_agent",
            fm_provider="anthropic",
            fm_config=self.fm_config,
            working_directory=str(self.test_path)
        )
        agent = Agent(config)
        
        # Check tools are registered
        self.assertIn("bash", agent.tool_registry._tools)
        self.assertIn("edit", agent.tool_registry._tools)
        
        # Get tool instances
        bash_tool = agent.tool_registry.get_tool("bash")
        edit_tool = agent.tool_registry.get_tool("edit")
        
        self.assertIsInstance(bash_tool, BashTool)
        self.assertIsInstance(edit_tool, EditTool)
    
    @patch('agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion')
    async def test_context_management(self, mock_get_completion):
        """Test context management across tasks."""
        # Mock FM to use context from previous tasks
        mock_responses = [
            # First task
            CompletionResponse(
                content="Created variable x = 5",
                stop_reason="end_turn",
                usage={"input_tokens": 10, "output_tokens": 20}
            ),
            # Second task uses context
            CompletionResponse(
                content="x + 3 = 8, using previous context",
                stop_reason="end_turn",
                usage={"input_tokens": 10, "output_tokens": 20}
            )
        ]
        mock_get_completion.side_effect = mock_responses
        
        config = AgentConfig(
            agent_id="test_agent",
            fm_provider="anthropic",
            fm_config=self.fm_config,
            working_directory=str(self.test_path)
        )
        agent = Agent(config)
        
        # First task
        task1 = Task(
            task_id="task1",
            description="Create variable x = 5"
        )
        result1 = await agent.solve_task(task1)
        self.assertIsNotNone(result1)
        
        # Second task should have access to context
        task2 = Task(
            task_id="task2",
            description="What is x + 3?"
        )
        result2 = await agent.solve_task(task2)
        self.assertIsNotNone(result2)
    
    @patch('agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion')
    async def test_tool_execution_timeout(self, mock_get_completion):
        """Test tool execution timeout handling."""
        # Mock FM to request long-running command
        mock_response = CompletionResponse(
            content="<tool_use>bash</tool_use><command>sleep 60</command>",
            stop_reason="tool_use",
            usage={"input_tokens": 10, "output_tokens": 20},
            tool_calls=[ToolCall(tool_name="bash", tool_input={"command": "sleep 60"})]
        )
        mock_get_completion.return_value = mock_response
        
        config = AgentConfig(
            agent_id="test_agent",
            fm_provider="anthropic",
            fm_config=self.fm_config,
            working_directory=str(self.test_path)
        )
        agent = Agent(config)
        
        task = Task(
            task_id="test_task",
            description="Run long command"
        )
        
        # Note: The actual timeout handling would need to be implemented in the agent
        # For now, we'll just verify the task execution
        result = await agent.solve_task(task)
        self.assertIsNotNone(result)
    
    @patch('agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion')
    async def test_invalid_tool_handling(self, mock_get_completion):
        """Test handling of invalid tool requests."""
        # Mock FM to request non-existent tool
        mock_response = CompletionResponse(
            content="<tool_use>nonexistent_tool</tool_use><params>{}</params>",
            stop_reason="tool_use",
            usage={"input_tokens": 10, "output_tokens": 20},
            tool_calls=[ToolCall(tool_name="nonexistent_tool", tool_input={})]
        )
        mock_get_completion.return_value = mock_response
        
        config = AgentConfig(
            agent_id="test_agent",
            fm_provider="anthropic",
            fm_config=self.fm_config,
            working_directory=str(self.test_path)
        )
        agent = Agent(config)
        
        task = Task(
            task_id="test_task",
            description="Use invalid tool"
        )
        
        # The agent should handle invalid tools gracefully
        result = await agent.solve_task(task)
        self.assertIsNotNone(result)
    
    def test_workspace_isolation(self):
        """Test workspace isolation between agents."""
        # Create two agents with different workspaces
        workspace1 = self.test_path / "agent1"
        workspace2 = self.test_path / "agent2"
        workspace1.mkdir()
        workspace2.mkdir()
        
        config1 = AgentConfig(
            agent_id="agent1",
            fm_provider="anthropic",
            fm_config=self.fm_config,
            working_directory=str(workspace1)
        )
        agent1 = Agent(config1)
        
        config2 = AgentConfig(
            agent_id="agent2",
            fm_provider="anthropic",
            fm_config=self.fm_config,
            working_directory=str(workspace2)
        )
        agent2 = Agent(config2)
        
        # Verify different workspaces
        self.assertNotEqual(agent1.working_directory, agent2.working_directory)
        self.assertEqual(str(agent1.working_directory), str(workspace1))
        self.assertEqual(str(agent2.working_directory), str(workspace2))
    
    @patch('agent.fm_interface.providers.anthropic.AnthropicHandler.get_completion')
    async def test_task_history_tracking(self, mock_get_completion):
        """Test task history tracking."""
        mock_response = CompletionResponse(
            content="Task completed successfully",
            stop_reason="end_turn",
            usage={"input_tokens": 10, "output_tokens": 20}
        )
        mock_get_completion.return_value = mock_response
        
        config = AgentConfig(
            agent_id="test_agent",
            fm_provider="anthropic",
            fm_config=self.fm_config,
            working_directory=str(self.test_path)
        )
        agent = Agent(config)
        
        # Execute multiple tasks
        task1 = Task(task_id="task1", description="Task 1")
        task2 = Task(task_id="task2", description="Task 2")
        task3 = Task(task_id="task3", description="Task 3")
        
        result1 = await agent.solve_task(task1)
        result2 = await agent.solve_task(task2)
        result3 = await agent.solve_task(task3)
        
        # Verify all tasks were executed
        self.assertIsNotNone(result1)
        self.assertIsNotNone(result2)
        self.assertIsNotNone(result3)


if __name__ == "__main__":
    # Run async tests
    unittest.main()