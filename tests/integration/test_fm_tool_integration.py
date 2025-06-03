"""
Integration tests for FM interface and tool usage.
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
from agent.fm_interface.api_handler import ApiHandler
from agent.tools.bash_tool import BashTool
from agent.tools.edit_tool import EditTool
from agent.agent import Agent


class TestFMToolIntegration(unittest.TestCase):
    """Test FM interface and tool integration."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)
        
        # Create test files
        (self.test_path / "test.py").write_text("print('Hello World')")
        (self.test_path / "data.txt").write_text("sample data")
        
        # FM config
        self.fm_config = {
            "provider": "anthropic",
            "model": "claude-3-sonnet-20240229",
            "max_retries": 3
        }
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.test_dir)
    
    @patch('agent.fm_interface.providers.anthropic.AnthropicProvider.generate')
    async def test_fm_generates_tool_calls(self, mock_generate):
        """Test FM interface generates appropriate tool calls."""
        # Mock FM to generate bash command
        mock_generate.return_value = json.dumps({
            "tool": "bash",
            "command": "ls -la",
            "reasoning": "List directory contents"
        })
        
        fm = FMInterface(self.fm_config)
        
        # Request tool usage
        messages = [
            {"role": "user", "content": "List all files in the current directory"}
        ]
        
        response = await fm.generate_response(messages)
        tool_call = json.loads(response)
        
        # Verify FM generated appropriate tool call
        self.assertEqual(tool_call["tool"], "bash")
        self.assertEqual(tool_call["command"], "ls -la")
    
    @patch('agent.fm_interface.providers.anthropic.AnthropicProvider.generate')
    async def test_agent_executes_fm_tool_calls(self, mock_generate):
        """Test agent executes tool calls from FM."""
        # Mock FM to generate edit command
        mock_generate.side_effect = [
            # First call: analyze task
            json.dumps({
                "analysis": "Need to modify the Python file",
                "next_action": "edit"
            }),
            # Second call: generate edit
            json.dumps({
                "tool": "edit",
                "file": "test.py",
                "operation": "replace",
                "old_text": "print('Hello World')",
                "new_text": "print('Hello Universe')",
                "reasoning": "Update greeting message"
            })
        ]
        
        # Create agent
        agent = Agent(
            agent_id="test_agent",
            fm_interface=FMInterface(self.fm_config),
            workspace=str(self.test_path)
        )
        
        # Execute task
        result = await agent.execute_task("Change the greeting to Universe")
        
        # Verify file was modified
        content = (self.test_path / "test.py").read_text()
        self.assertEqual(content, "print('Hello Universe')")
    
    async def test_bash_tool_execution(self):
        """Test bash tool execution with real commands."""
        bash_tool = BashTool()
        
        # Test simple command
        result = await bash_tool.execute(
            command="echo 'test output'",
            cwd=str(self.test_path)
        )
        
        self.assertEqual(result["status"], "success")
        self.assertIn("test output", result["stdout"])
        
        # Test command with error
        result = await bash_tool.execute(
            command="ls /nonexistent/directory",
            cwd=str(self.test_path)
        )
        
        self.assertEqual(result["status"], "error")
        self.assertIn("error", result["stderr"].lower())
    
    async def test_edit_tool_operations(self):
        """Test edit tool operations."""
        edit_tool = EditTool()
        
        # Test file creation
        result = await edit_tool.execute(
            operation="create",
            file=str(self.test_path / "new_file.py"),
            content="# New Python file\nprint('Created')"
        )
        
        self.assertEqual(result["status"], "success")
        self.assertTrue((self.test_path / "new_file.py").exists())
        
        # Test file replacement
        result = await edit_tool.execute(
            operation="replace",
            file=str(self.test_path / "test.py"),
            old_text="Hello World",
            new_text="Hello AI"
        )
        
        self.assertEqual(result["status"], "success")
        content = (self.test_path / "test.py").read_text()
        self.assertIn("Hello AI", content)
        
        # Test append operation
        result = await edit_tool.execute(
            operation="append",
            file=str(self.test_path / "data.txt"),
            content="\nmore data"
        )
        
        self.assertEqual(result["status"], "success")
        content = (self.test_path / "data.txt").read_text()
        self.assertIn("more data", content)
    
    @patch('agent.fm_interface.providers.anthropic.AnthropicProvider.generate')
    async def test_multi_step_tool_usage(self, mock_generate):
        """Test agent using multiple tools in sequence."""
        # Mock FM to generate sequence of tool calls
        mock_generate.side_effect = [
            # Step 1: Create directory
            json.dumps({
                "tool": "bash",
                "command": "mkdir -p src/utils",
                "reasoning": "Create project structure"
            }),
            # Step 2: Create Python file
            json.dumps({
                "tool": "edit",
                "operation": "create",
                "file": "src/utils/helpers.py",
                "content": "def helper():\n    return 'helping'"
            }),
            # Step 3: Create test file
            json.dumps({
                "tool": "edit",
                "operation": "create",
                "file": "src/utils/test_helpers.py",
                "content": "from helpers import helper\n\ndef test_helper():\n    assert helper() == 'helping'"
            }),
            # Step 4: Run test
            json.dumps({
                "tool": "bash",
                "command": "cd src/utils && python -m pytest test_helpers.py",
                "reasoning": "Run the test"
            })
        ]
        
        agent = Agent(
            agent_id="test_agent",
            fm_interface=FMInterface(self.fm_config),
            workspace=str(self.test_path)
        )
        
        # Execute multi-step task
        steps = [
            "Create project structure",
            "Create helper module",
            "Create test module",
            "Run tests"
        ]
        
        for step in steps:
            await agent.execute_task(step)
        
        # Verify all files were created
        self.assertTrue((self.test_path / "src" / "utils" / "helpers.py").exists())
        self.assertTrue((self.test_path / "src" / "utils" / "test_helpers.py").exists())
    
    @patch('agent.fm_interface.providers.anthropic.AnthropicProvider.generate')
    async def test_error_handling_in_tool_chain(self, mock_generate):
        """Test error handling when tools fail in a chain."""
        # Mock FM to generate failing command
        mock_generate.side_effect = [
            json.dumps({
                "tool": "bash",
                "command": "rm -rf /protected/system/file",  # Will fail
                "reasoning": "Dangerous operation"
            }),
            # After failure, generate safe alternative
            json.dumps({
                "tool": "bash",
                "command": "echo 'Using safe alternative'",
                "reasoning": "Safe operation after failure"
            })
        ]
        
        agent = Agent(
            agent_id="test_agent",
            fm_interface=FMInterface(self.fm_config),
            workspace=str(self.test_path)
        )
        
        # First attempt should fail gracefully
        result1 = await agent.execute_task("Remove system file")
        self.assertIn("error", result1.get("status", "").lower())
        
        # Second attempt should succeed
        result2 = await agent.execute_task("Try alternative approach")
        self.assertEqual(result2.get("status"), "success")
    
    async def test_tool_timeout_handling(self):
        """Test handling of tool timeouts."""
        bash_tool = BashTool()
        
        # Command that would hang
        result = await bash_tool.execute(
            command="sleep 60",
            cwd=str(self.test_path),
            timeout=1  # 1 second timeout
        )
        
        self.assertEqual(result["status"], "timeout")
        self.assertIn("timeout", result["error"].lower())
    
    @patch('agent.fm_interface.providers.anthropic.AnthropicProvider.generate')
    async def test_context_preservation_across_tools(self, mock_generate):
        """Test context is preserved across tool executions."""
        # Create initial context file
        context_file = self.test_path / "context.json"
        initial_context = {"step": 0, "data": []}
        context_file.write_text(json.dumps(initial_context))
        
        # Mock FM to update context incrementally
        mock_generate.side_effect = [
            json.dumps({
                "tool": "bash",
                "command": f"echo '{{\"step\": 1}}' >> {context_file}",
                "reasoning": "Update context"
            }),
            json.dumps({
                "tool": "edit",
                "operation": "replace",
                "file": str(context_file),
                "old_text": '"step": 0',
                "new_text": '"step": 2',
                "reasoning": "Increment step"
            })
        ]
        
        agent = Agent(
            agent_id="test_agent",
            fm_interface=FMInterface(self.fm_config),
            workspace=str(self.test_path)
        )
        
        # Execute tasks that modify context
        await agent.execute_task("Initialize context")
        await agent.execute_task("Update context")
        
        # Verify context was preserved and updated
        final_context = json.loads(context_file.read_text())
        self.assertEqual(final_context["step"], 2)


if __name__ == "__main__":
    # Run async tests
    unittest.main()