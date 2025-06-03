"""
Integration tests for benchmark and evaluation system.
"""

import unittest
import asyncio
from pathlib import Path
import tempfile
import json
import yaml
from unittest.mock import patch, AsyncMock, MagicMock
import subprocess

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.test_utils import TestFixtures
from evaluation.benchmark_runner import BenchmarkRunner
from evaluation.agent_validator import AgentValidator
from evaluation.scoring import ScoringMethods
from agent.agent import Agent
from agent.fm_interface.api_handler import ApiHandler


class TestBenchmarkEvaluation(unittest.TestCase):
    """Test benchmark and evaluation integration."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)
        
        # Create directories
        (self.test_path / "benchmarks").mkdir(parents=True)
        (self.test_path / "agents").mkdir(parents=True)
        
        # Create sample benchmarks
        self.create_test_benchmarks()
        
        # FM config for agent
        self.fm_config = {
            "provider": "anthropic",
            "model": "claude-3-sonnet-20240229",
            "max_retries": 3
        }
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.test_dir)
    
    def create_test_benchmarks(self):
        """Create various test benchmark configurations."""
        # String manipulation benchmark
        string_bench = {
            "name": "string_manipulation",
            "type": "coding",
            "tasks": [
                {
                    "id": "reverse_string",
                    "description": "Reverse a string",
                    "input": "hello",
                    "expected_output": "olleh"
                },
                {
                    "id": "capitalize_words",
                    "description": "Capitalize first letter of each word",
                    "input": "hello world",
                    "expected_output": "Hello World"
                }
            ],
            "timeout": 30,
            "scoring": {
                "method": "binary",
                "max_score": 1.0
            }
        }
        
        # Math benchmark with partial credit
        math_bench = {
            "name": "math_operations",
            "type": "coding",
            "tasks": [
                {
                    "id": "factorial",
                    "description": "Calculate factorial",
                    "input": "5",
                    "expected_output": "120"
                },
                {
                    "id": "fibonacci",
                    "description": "Calculate nth fibonacci number",
                    "input": "10",
                    "expected_output": "55"
                }
            ],
            "timeout": 30,
            "scoring": {
                "method": "partial_credit",
                "max_score": 1.0,
                "partial_scores": {
                    "correct_approach": 0.3,
                    "partial_result": 0.5,
                    "full_result": 1.0
                }
            }
        }
        
        # JSON output benchmark
        json_bench = {
            "name": "data_processing",
            "type": "coding",
            "tasks": [
                {
                    "id": "parse_json",
                    "description": "Parse and transform JSON",
                    "input": '{"name": "test", "value": 42}',
                    "expected_output": '{"test": 42}'
                }
            ],
            "timeout": 30,
            "scoring": {
                "method": "json_match",
                "max_score": 1.0
            }
        }
        
        # Save benchmarks
        for bench in [string_bench, math_bench, json_bench]:
            path = self.test_path / "benchmarks" / f"{bench['name']}.yaml"
            with open(path, 'w') as f:
                yaml.dump(bench, f)
    
    async def test_benchmark_runner_with_real_agent(self):
        """Test benchmark runner with a real agent."""
        # Create a simple agent that can solve string reversal
        agent_path = self.test_path / "agents" / "string_agent"
        agent_path.mkdir(parents=True)
        
        agent_code = '''
import sys

def solve_task(task_description, task_input):
    """Solve benchmark tasks."""
    if "reverse" in task_description.lower():
        return task_input[::-1]
    elif "capitalize" in task_description.lower():
        return task_input.title()
    return task_input

if __name__ == "__main__":
    # Read task from command line
    if len(sys.argv) > 2:
        description = sys.argv[1]
        task_input = sys.argv[2]
        result = solve_task(description, task_input)
        print(result)
'''
        
        (agent_path / "agent.py").write_text(agent_code)
        
        # Run benchmark
        runner = BenchmarkRunner(str(self.test_path / "benchmarks"))
        result = await runner.run_agent_benchmark(
            agent_path=str(agent_path),
            benchmark_name="string_manipulation"
        )
        
        # Verify results
        self.assertEqual(result["agent_id"], "string_agent")
        self.assertEqual(result["benchmark"], "string_manipulation")
        self.assertEqual(result["score"], 1.0)  # Should solve both tasks
        self.assertEqual(result["tasks"]["reverse_string"]["status"], "passed")
        self.assertEqual(result["tasks"]["capitalize_words"]["status"], "passed")
    
    async def test_agent_validator_integration(self):
        """Test agent validator checks agent structure."""
        validator = AgentValidator()
        
        # Create valid agent
        valid_agent_path = self.test_path / "agents" / "valid_agent"
        TestFixtures.create_mock_agent_code(valid_agent_path)
        
        # Validate
        is_valid, errors = await validator.validate_agent(str(valid_agent_path))
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        
        # Create invalid agent (missing files)
        invalid_agent_path = self.test_path / "agents" / "invalid_agent"
        invalid_agent_path.mkdir(parents=True)
        
        is_valid, errors = await validator.validate_agent(str(invalid_agent_path))
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
        self.assertIn("agent.py", errors[0])  # Should mention missing file
    
    async def test_scoring_methods_integration(self):
        """Test different scoring methods with real outputs."""
        scoring = ScoringMethods()
        
        # Test binary scoring
        binary_config = {"method": "binary", "max_score": 1.0}
        
        score = scoring.calculate_score(
            output="olleh",
            expected="olleh",
            config=binary_config
        )
        self.assertEqual(score, 1.0)
        
        score = scoring.calculate_score(
            output="hello",
            expected="olleh",
            config=binary_config
        )
        self.assertEqual(score, 0.0)
        
        # Test partial credit
        partial_config = {
            "method": "partial_credit",
            "max_score": 1.0,
            "partial_scores": {
                "correct_approach": 0.3,
                "partial_result": 0.5,
                "full_result": 1.0
            }
        }
        
        # Simulate partial credit scenarios
        score = scoring.calculate_score(
            output="119",  # Close to 120
            expected="120",
            config=partial_config,
            metadata={"approach": "factorial"}
        )
        self.assertGreater(score, 0)  # Should get partial credit
        
        # Test JSON matching
        json_config = {"method": "json_match", "max_score": 1.0}
        
        score = scoring.calculate_score(
            output='{"test": 42}',
            expected='{"test": 42}',
            config=json_config
        )
        self.assertEqual(score, 1.0)
        
        # Different order but same content
        score = scoring.calculate_score(
            output='{"value": 42, "name": "test"}',
            expected='{"name": "test", "value": 42}',
            config=json_config
        )
        self.assertEqual(score, 1.0)  # JSON equality ignores order
    
    @patch('agent.fm_interface.providers.anthropic.AnthropicProvider.generate')
    async def test_agent_solving_benchmark(self, mock_generate):
        """Test agent using FM to solve benchmark tasks."""
        # Mock FM to provide solutions
        mock_generate.side_effect = [
            # Analyze reverse string task
            json.dumps({
                "understanding": "Need to reverse the input string",
                "approach": "Use Python string slicing [::-1]"
            }),
            # Generate solution
            json.dumps({
                "solution": "return input_string[::-1]",
                "confidence": 0.95
            }),
            # Analyze capitalize task
            json.dumps({
                "understanding": "Capitalize first letter of each word",
                "approach": "Use Python title() method"
            }),
            # Generate solution
            json.dumps({
                "solution": "return input_string.title()",
                "confidence": 0.9
            })
        ]
        
        # Create agent with FM interface
        agent_path = self.test_path / "agents" / "fm_agent"
        agent_path.mkdir(parents=True)
        
        # Agent that uses FM to solve tasks
        agent_code = '''
import sys
import json
from agent.fm_interface.api_handler import FMInterface

async def solve_with_fm(description, task_input):
    """Use FM to solve task."""
    fm_config = {
        "provider": "anthropic",
        "model": "claude-3-sonnet-20240229"
    }
    fm = FMInterface(fm_config)
    
    # Ask FM to analyze
    analysis = await fm.generate_response([
        {"role": "user", "content": f"Analyze this task: {description}"}
    ])
    
    # Ask FM for solution
    solution = await fm.generate_response([
        {"role": "user", "content": f"Generate Python code to solve: {description}"}
    ])
    
    # Execute solution (simplified)
    sol_data = json.loads(solution)
    if "return input_string[::-1]" in sol_data.get("solution", ""):
        return task_input[::-1]
    elif "return input_string.title()" in sol_data.get("solution", ""):
        return task_input.title()
    
    return task_input

if __name__ == "__main__":
    import asyncio
    if len(sys.argv) > 2:
        description = sys.argv[1]
        task_input = sys.argv[2]
        result = asyncio.run(solve_with_fm(description, task_input))
        print(result)
'''
        
        (agent_path / "agent.py").write_text(agent_code)
        
        # Run benchmark with FM-powered agent
        runner = BenchmarkRunner(str(self.test_path / "benchmarks"))
        result = await runner.run_agent_benchmark(
            agent_path=str(agent_path),
            benchmark_name="string_manipulation"
        )
        
        # Should solve tasks using FM guidance
        self.assertGreater(result["score"], 0)
    
    async def test_benchmark_timeout_handling(self):
        """Test handling of agent timeouts during benchmark."""
        # Create agent that hangs
        agent_path = self.test_path / "agents" / "hanging_agent"
        agent_path.mkdir(parents=True)
        
        hanging_code = '''
import time
import sys

if __name__ == "__main__":
    # Simulate hanging
    time.sleep(60)
    print("This should not be reached")
'''
        
        (agent_path / "agent.py").write_text(hanging_code)
        
        # Create benchmark with short timeout
        timeout_bench = {
            "name": "quick_test",
            "type": "coding",
            "tasks": [{
                "id": "test_task",
                "description": "Test task",
                "input": "test",
                "expected_output": "test"
            }],
            "timeout": 2,  # 2 second timeout
            "scoring": {"method": "binary", "max_score": 1.0}
        }
        
        with open(self.test_path / "benchmarks" / "quick_test.yaml", 'w') as f:
            yaml.dump(timeout_bench, f)
        
        # Run benchmark
        runner = BenchmarkRunner(str(self.test_path / "benchmarks"))
        result = await runner.run_agent_benchmark(
            agent_path=str(agent_path),
            benchmark_name="quick_test"
        )
        
        # Should timeout
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["tasks"]["test_task"]["status"], "timeout")
        self.assertIn("timeout", result["tasks"]["test_task"]["error"].lower())
    
    async def test_multi_benchmark_evaluation(self):
        """Test running multiple benchmarks on same agent."""
        # Create versatile agent
        agent_path = self.test_path / "agents" / "versatile_agent"
        agent_path.mkdir(parents=True)
        
        versatile_code = '''
import sys
import json

def solve_task(description, task_input):
    """Solve various tasks."""
    desc_lower = description.lower()
    
    # String tasks
    if "reverse" in desc_lower:
        return task_input[::-1]
    elif "capitalize" in desc_lower:
        return task_input.title()
    
    # Math tasks
    elif "factorial" in desc_lower:
        n = int(task_input)
        result = 1
        for i in range(1, n + 1):
            result *= i
        return str(result)
    elif "fibonacci" in desc_lower:
        n = int(task_input)
        a, b = 0, 1
        for _ in range(n):
            a, b = b, a + b
        return str(a)
    
    # JSON tasks
    elif "parse" in desc_lower and "json" in desc_lower:
        data = json.loads(task_input)
        if "name" in data and "value" in data:
            return json.dumps({data["name"]: data["value"]})
    
    return task_input

if __name__ == "__main__":
    if len(sys.argv) > 2:
        description = sys.argv[1]
        task_input = sys.argv[2]
        result = solve_task(description, task_input)
        print(result)
'''
        
        (agent_path / "agent.py").write_text(versatile_code)
        
        # Run multiple benchmarks
        runner = BenchmarkRunner(str(self.test_path / "benchmarks"))
        
        results = {}
        for benchmark in ["string_manipulation", "math_operations", "data_processing"]:
            result = await runner.run_agent_benchmark(
                agent_path=str(agent_path),
                benchmark_name=benchmark
            )
            results[benchmark] = result
        
        # Should perform well on all benchmarks
        self.assertEqual(results["string_manipulation"]["score"], 1.0)
        self.assertGreater(results["math_operations"]["score"], 0.5)
        self.assertGreater(results["data_processing"]["score"], 0)
        
        # Aggregate performance
        total_score = sum(r["score"] for r in results.values())
        avg_score = total_score / len(results)
        self.assertGreater(avg_score, 0.6)  # Good overall performance


if __name__ == "__main__":
    # Run async tests
    unittest.main()