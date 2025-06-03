"""
Test utilities and fixtures for DGM tests.
"""

import os
import tempfile
import shutil
import json
from pathlib import Path
from typing import Dict, Any, Optional
import asyncio

from agent import Agent, Task, AgentConfig


class TestFixtures:
    """Provides test fixtures and utilities."""
    
    @staticmethod
    def create_temp_directory() -> Path:
        """Create a temporary directory for test isolation."""
        return Path(tempfile.mkdtemp(prefix="dgm_test_"))
    
    @staticmethod
    def create_mock_agent_code(agent_path: Path) -> None:
        """Create a minimal agent implementation for testing."""
        # Create agent directory structure
        agent_dir = agent_path / "agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        
        # Create __init__.py
        (agent_dir / "__init__.py").write_text(
            'from .agent import Agent, Task, AgentConfig\n'
            '__all__ = ["Agent", "Task", "AgentConfig"]'
        )
        
        # Create minimal agent.py
        agent_code = '''"""Test agent implementation."""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class Task:
    """Task representation."""
    def __init__(self, task_id: str, description: str, metadata: Optional[Dict[str, Any]] = None):
        self.task_id = task_id
        self.description = description
        self.metadata = metadata or {}


class AgentConfig:
    """Agent configuration."""
    def __init__(self, agent_id: str, fm_provider: str, fm_config: Dict[str, Any], 
                 working_directory: str = ".", max_iterations: int = 10):
        self.agent_id = agent_id
        self.fm_provider = fm_provider
        self.fm_config = fm_config
        self.working_directory = working_directory
        self.max_iterations = max_iterations


class Agent:
    """Test agent with minimal implementation."""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.tool_registry = {}
        self.system_prompt = "I am a test agent."
        logger.info(f"Initialized test agent: {config.agent_id}")
    
    async def solve_task(self, task: Task, verbose: bool = False) -> Dict[str, Any]:
        """Solve a task (mock implementation)."""
        logger.info(f"Solving task: {task.task_id}")
        
        # Mock task solving
        if "fail" in task.description.lower():
            return {
                'status': 'failed',
                'error': 'Task contains fail keyword'
            }
        
        return {
            'status': 'completed',
            'result': f'Solved task: {task.task_id}'
        }
    
    def get_agent_info(self) -> Dict[str, Any]:
        """Get agent information."""
        return {
            'agent_id': self.config.agent_id,
            'version': '1.0.0',
            'capabilities': ['test'],
            'available_tools': list(self.tool_registry.keys())
        }
'''
        (agent_dir / "agent.py").write_text(agent_code)
        
        # Create tools directory
        tools_dir = agent_dir / "tools"
        tools_dir.mkdir(exist_ok=True)
        (tools_dir / "__init__.py").write_text("")
        
        # Create fm_interface directory
        fm_dir = agent_dir / "fm_interface"
        fm_dir.mkdir(exist_ok=True)
        (fm_dir / "__init__.py").write_text("")
    
    @staticmethod
    def create_benchmark_results(
        benchmark_name: str,
        num_tests: int = 5,
        success_rate: float = 0.8
    ) -> Dict[str, Any]:
        """Create mock benchmark results."""
        test_results = []
        
        for i in range(num_tests):
            passed = i < int(num_tests * success_rate)
            test_results.append({
                'test_id': f'test_{i}',
                'passed': passed,
                'actual_output': 'test output' if passed else 'error',
                'expected_output': 'test output',
                'error': None if passed else 'Test failed',
                'execution_time': 0.1
            })
        
        return {
            'benchmark_name': benchmark_name,
            'test_results': test_results,
            'overall_score': success_rate,
            'benchmark_scores': {benchmark_name: success_rate},
            'detailed_results': {benchmark_name: {'test_results': test_results}}
        }
    
    @staticmethod
    def create_test_config() -> Dict[str, Any]:
        """Create a test DGM configuration."""
        return {
            'archive': {
                'path': './test_archive',
                'min_score_threshold': 0.1
            },
            'parent_selection': {
                'performance_weight': 0.7,
                'novelty_weight': 0.3,
                'min_score': 0.0
            },
            'evaluation': {
                'benchmarks_dir': './config/benchmarks',
                'results_dir': './test_results',
                'timeout_seconds': 30,
                'benchmarks': ['test_benchmark']
            },
            'agents': {
                'base_agent_path': './test_agent',
                'workspace_dir': './test_workspace'
            },
            'fm_settings': {
                'provider': 'test',
                'config': {
                    'model': 'test-model',
                    'api_key': 'test-key'
                }
            },
            'self_modification': {
                'max_iterations': 5
            },
            'logging': {
                'level': 'INFO'
            }
        }
    
    @staticmethod
    def create_test_benchmark_config() -> Dict[str, Any]:
        """Create a test benchmark configuration."""
        return {
            'name': 'test_benchmark',
            'description': 'Test benchmark for unit tests',
            'difficulty': 'easy',
            'timeout': 10,
            'category': 'test',
            'task_template': 'Solve {task}',
            'test_cases': [
                {
                    'task': 'test task 1',
                    'inputs': ['input1'],
                    'expected_outputs': ['output1']
                }
            ],
            'scoring': {
                'method': 'binary',
                'strict': False
            }
        }


class AsyncTestRunner:
    """Helper for running async tests."""
    
    @staticmethod
    def run(coro):
        """Run an async coroutine in a test context."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def cleanup_test_directory(path: Path) -> None:
    """Clean up a test directory."""
    if path.exists() and path.is_dir():
        shutil.rmtree(path)


def assert_files_exist(base_path: Path, files: list) -> None:
    """Assert that specified files exist."""
    for file_path in files:
        full_path = base_path / file_path
        assert full_path.exists(), f"Expected file not found: {full_path}"


def assert_json_valid(file_path: Path) -> Dict[str, Any]:
    """Assert that a file contains valid JSON and return parsed content."""
    assert file_path.exists(), f"JSON file not found: {file_path}"
    
    with open(file_path, 'r') as f:
        try:
            data = json.load(f)
            return data
        except json.JSONDecodeError as e:
            raise AssertionError(f"Invalid JSON in {file_path}: {e}")