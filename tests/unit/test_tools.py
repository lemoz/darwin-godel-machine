"""
Unit tests for tool implementations.
"""

import unittest
import asyncio
from pathlib import Path
import tempfile
import os
import sys
import subprocess
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.tools.base_tool import BaseTool, ToolRegistry
from agent.tools.bash_tool import BashTool
from agent.tools.edit_tool import EditTool


class TestBaseTool(unittest.TestCase):
    """Test base tool functionality."""
    
    def test_base_tool_abstract(self):
        """Test that BaseTool is abstract."""
        with self.assertRaises(TypeError):
            BaseTool()
    
    def test_tool_registry_initialization(self):
        """Test tool registry initialization."""
        registry = ToolRegistry()
        self.assertIsInstance(registry._tools, dict)
        self.assertEqual(len(registry._tools), 0)
    
    def test_register_tool(self):
        """Test tool registration."""
        registry = ToolRegistry()
        
        # Create a concrete tool
        class TestTool(BaseTool):
            def get_name(self):
                return "test"
            
            def get_description(self):
                return "Test tool"
            
            def get_parameters(self):
                return []
            
            async def execute(self, parameters):
                return ToolResult(
                    status=ToolExecutionStatus.SUCCESS,
                    output="Test executed"
                )
        
        tool = TestTool()
        registry.register_tool(tool)
        
        self.assertIn("test", registry._tools)
        self.assertEqual(registry.get_tool("test"), tool)
    
    def test_get_nonexistent_tool(self):
        """Test getting non-existent tool."""
        registry = ToolRegistry()
        self.assertIsNone(registry.get_tool("nonexistent"))
    
    def test_list_tools(self):
        """Test listing available tools."""
        registry = ToolRegistry()
        
        # Register multiple tools
        class Tool1(BaseTool):
            def get_name(self):
                return "tool1"
            
            def get_description(self):
                return "Tool 1"
            
            def get_parameters(self):
                return []
            
            async def execute(self, parameters):
                return ToolResult(
                    status=ToolExecutionStatus.SUCCESS,
                    output="Tool 1 executed"
                )
        
        class Tool2(BaseTool):
            def get_name(self):
                return "tool2"
            
            def get_description(self):
                return "Tool 2"
            
            def get_parameters(self):
                return []
            
            async def execute(self, parameters):
                return ToolResult(
                    status=ToolExecutionStatus.SUCCESS,
                    output="Tool 2 executed"
                )
        
        registry.register_tool(Tool1())
        registry.register_tool(Tool2())
        
        tools = registry.list_tools()
        self.assertEqual(len(tools), 2)
        self.assertIn("tool1", tools)
        self.assertIn("tool2", tools)


class TestBashTool(unittest.TestCase):
    """Test bash tool functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)
        self.bash_tool = BashTool()
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.test_dir)
    
    def test_bash_tool_properties(self):
        """Test bash tool properties."""
        self.assertEqual(self.bash_tool.get_name(), "bash")
        self.assertIn("Execute bash/shell commands", self.bash_tool.get_description())
    
    async def test_execute_simple_command(self):
        """Test executing simple command."""
        result = await self.bash_tool.execute({
            "command": "echo 'Hello World'",
            "cwd": str(self.test_path)
        })
        
        self.assertEqual(result.status, ToolExecutionStatus.SUCCESS)
        self.assertIn("Hello World", result.output)
    
    async def test_execute_with_error(self):
        """Test executing command that fails."""
        result = await self.bash_tool.execute({
            "command": "ls /nonexistent/path",
            "cwd": str(self.test_path)
        })
        
        self.assertEqual(result.status, ToolExecutionStatus.ERROR)
        self.assertIsNotNone(result.error)
    
    async def test_execute_with_timeout(self):
        """Test command timeout."""
        result = await self.bash_tool.execute({
            "command": "sleep 10",
            "cwd": str(self.test_path),
            "timeout": 1
        })
        
        self.assertEqual(result.status, ToolExecutionStatus.TIMEOUT)
        self.assertIn("timeout", result.error.lower())
    
    async def test_execute_with_cwd(self):
        """Test executing in specific directory."""
        # Create subdirectory
        subdir = self.test_path / "subdir"
        subdir.mkdir()
        (subdir / "test.txt").write_text("test content")
        
        result = await self.bash_tool.execute(
            command="ls",
            cwd=str(subdir)
        )
        
        self.assertEqual(result["status"], "success")
        self.assertIn("test.txt", result["stdout"])
    
    async def test_execute_multiline_command(self):
        """Test executing multiline command."""
        command = """
        echo "Line 1"
        echo "Line 2"
        echo "Line 3"
        """
        
        result = await self.bash_tool.execute(
            command=command,
            cwd=str(self.test_path)
        )
        
        self.assertEqual(result["status"], "success")
        self.assertIn("Line 1", result["stdout"])
        self.assertIn("Line 2", result["stdout"])
        self.assertIn("Line 3", result["stdout"])
    
    async def test_execute_with_pipes(self):
        """Test executing command with pipes."""
        # Create test files
        (self.test_path / "file1.txt").write_text("apple\nbanana\ncherry")
        (self.test_path / "file2.txt").write_text("banana\ndate\nfig")
        
        result = await self.bash_tool.execute(
            command="cat file1.txt | grep banana",
            cwd=str(self.test_path)
        )
        
        self.assertEqual(result["status"], "success")
        self.assertIn("banana", result["stdout"])
        self.assertNotIn("apple", result["stdout"])
    
    async def test_environment_variables(self):
        """Test command with environment variables."""
        result = await self.bash_tool.execute(
            command="echo $TEST_VAR",
            cwd=str(self.test_path),
            env={"TEST_VAR": "test_value"}
        )
        
        self.assertEqual(result["status"], "success")
        self.assertIn("test_value", result["stdout"])


class TestEditTool(unittest.TestCase):
    """Test edit tool functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)
        self.edit_tool = EditTool()
        
        # Create test file
        self.test_file = self.test_path / "test.txt"
        self.test_file.write_text("Line 1\nLine 2\nLine 3")
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.test_dir)
    
    def test_edit_tool_properties(self):
        """Test edit tool properties."""
        self.assertEqual(self.edit_tool.get_name(), "edit")
        self.assertIn("Edit", self.edit_tool.get_description())
    
    async def test_create_file(self):
        """Test creating a new file."""
        new_file = self.test_path / "new_file.py"
        
        result = await self.edit_tool.execute(
            operation="create",
            file=str(new_file),
            content="print('Hello World')"
        )
        
        self.assertEqual(result["status"], "success")
        self.assertTrue(new_file.exists())
        self.assertEqual(new_file.read_text(), "print('Hello World')")
    
    async def test_create_file_with_directories(self):
        """Test creating file with non-existent directories."""
        nested_file = self.test_path / "dir1" / "dir2" / "file.txt"
        
        result = await self.edit_tool.execute(
            operation="create",
            file=str(nested_file),
            content="nested content"
        )
        
        self.assertEqual(result["status"], "success")
        self.assertTrue(nested_file.exists())
        self.assertEqual(nested_file.read_text(), "nested content")
    
    async def test_replace_text(self):
        """Test replacing text in file."""
        result = await self.edit_tool.execute(
            operation="replace",
            file=str(self.test_file),
            old_text="Line 2",
            new_text="Modified Line 2"
        )
        
        self.assertEqual(result["status"], "success")
        content = self.test_file.read_text()
        self.assertNotIn("Line 2", content)
        self.assertIn("Modified Line 2", content)
    
    async def test_replace_nonexistent_text(self):
        """Test replacing non-existent text."""
        result = await self.edit_tool.execute(
            operation="replace",
            file=str(self.test_file),
            old_text="Non-existent",
            new_text="Replacement"
        )
        
        self.assertEqual(result["status"], "error")
        self.assertIn("not found", result["error"])
    
    async def test_append_to_file(self):
        """Test appending to file."""
        result = await self.edit_tool.execute(
            operation="append",
            file=str(self.test_file),
            content="\nLine 4\nLine 5"
        )
        
        self.assertEqual(result["status"], "success")
        content = self.test_file.read_text()
        self.assertIn("Line 4", content)
        self.assertIn("Line 5", content)
        self.assertTrue(content.endswith("Line 5"))
    
    async def test_delete_lines(self):
        """Test deleting lines from file."""
        result = await self.edit_tool.execute(
            operation="delete",
            file=str(self.test_file),
            start_line=2,
            end_line=2
        )
        
        self.assertEqual(result["status"], "success")
        content = self.test_file.read_text()
        self.assertIn("Line 1", content)
        self.assertNotIn("Line 2", content)
        self.assertIn("Line 3", content)
    
    async def test_delete_multiple_lines(self):
        """Test deleting multiple lines."""
        result = await self.edit_tool.execute(
            operation="delete",
            file=str(self.test_file),
            start_line=1,
            end_line=2
        )
        
        self.assertEqual(result["status"], "success")
        content = self.test_file.read_text()
        self.assertNotIn("Line 1", content)
        self.assertNotIn("Line 2", content)
        self.assertIn("Line 3", content)
    
    async def test_insert_at_line(self):
        """Test inserting at specific line."""
        result = await self.edit_tool.execute(
            operation="insert",
            file=str(self.test_file),
            line=2,
            content="Inserted Line"
        )
        
        self.assertEqual(result["status"], "success")
        lines = self.test_file.read_text().splitlines()
        self.assertEqual(lines[0], "Line 1")
        self.assertEqual(lines[1], "Inserted Line")
        self.assertEqual(lines[2], "Line 2")
    
    async def test_read_file(self):
        """Test reading file content."""
        result = await self.edit_tool.execute(
            operation="read",
            file=str(self.test_file)
        )
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["content"], "Line 1\nLine 2\nLine 3")
    
    async def test_read_nonexistent_file(self):
        """Test reading non-existent file."""
        result = await self.edit_tool.execute(
            operation="read",
            file=str(self.test_path / "nonexistent.txt")
        )
        
        self.assertEqual(result["status"], "error")
        self.assertIn("not found", result["error"].lower())
    
    async def test_invalid_operation(self):
        """Test invalid operation."""
        result = await self.edit_tool.execute(
            operation="invalid_op",
            file=str(self.test_file)
        )
        
        self.assertEqual(result["status"], "error")
        self.assertIn("Invalid operation", result["error"])
    
    async def test_file_backup(self):
        """Test file backup functionality."""
        original_content = self.test_file.read_text()
        
        # Make change
        await self.edit_tool.execute(
            operation="replace",
            file=str(self.test_file),
            old_text="Line 2",
            new_text="Changed Line"
        )
        
        # Check backup exists
        backup_files = list(self.test_path.glob("test.txt.backup.*"))
        self.assertEqual(len(backup_files), 1)
        
        # Verify backup content
        backup_content = backup_files[0].read_text()
        self.assertEqual(backup_content, original_content)


if __name__ == "__main__":
    # Run async tests
    unittest.main()