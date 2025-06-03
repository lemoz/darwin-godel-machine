"""
Unit tests for evaluation framework components.
"""

import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from evaluation.benchmark_runner import BenchmarkRunner, BenchmarkResult
from evaluation.agent_validator import AgentValidator
from evaluation.scoring import BenchmarkScorer, BinaryScorer, PartialCreditScorer, JsonScorer, FunctionOutputScorer
from tests.test_utils import TestFixtures, AsyncTestRunner, cleanup_test_directory


class TestBenchmarkRunner(unittest.TestCase):
    """Test cases for BenchmarkRunner."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_benchmark_"))
        self.benchmarks_dir = self.temp_dir / "benchmarks"
        self.results_dir = self.temp_dir / "results"
        self.benchmarks_dir.mkdir()
        self.results_dir.mkdir()
        
        # Create test benchmark config
        self.benchmark_config = TestFixtures.create_test_benchmark_config()
        benchmark_file = self.benchmarks_dir / "test_benchmark.yaml"
        
        import yaml
        with open(benchmark_file, 'w') as f:
            yaml.dump(self.benchmark_config, f)
        
        self.runner = BenchmarkRunner(
            benchmarks_dir=str(self.benchmarks_dir),
            results_dir=str(self.results_dir),
            timeout=10
        )
    
    def tearDown(self):
        """Clean up test fixtures."""
        cleanup_test_directory(self.temp_dir)
    
    def test_load_benchmarks(self):
        """Test loading benchmark configurations."""
        self.assertIn('test_benchmark', self.runner.benchmarks)
        loaded_config = self.runner.benchmarks['test_benchmark']
        self.assertEqual(loaded_config['name'], 'test_benchmark')
        self.assertEqual(loaded_config['difficulty'], 'easy')
    
    def test_run_benchmark_success(self):
        """Test running a benchmark successfully."""
        # Create mock agent
        mock_agent = Mock()
        mock_agent.solve_task = AsyncMock(return_value={
            'status': 'completed',
            'result': 'output1'
        })
        
        # Run benchmark
        result = AsyncTestRunner.run(
            self.runner.run_benchmark(mock_agent, 'test_benchmark')
        )
        
        self.assertIsInstance(result, BenchmarkResult)
        self.assertEqual(result.benchmark_name, 'test_benchmark')
        self.assertEqual(len(result.test_results), 1)
        self.assertTrue(result.test_results[0]['passed'])
    
    def test_run_benchmark_timeout(self):
        """Test benchmark timeout handling."""
        # Create mock agent that times out
        mock_agent = Mock()
        
        async def slow_task(*args, **kwargs):
            import asyncio
            await asyncio.sleep(20)  # Longer than timeout
            return {'status': 'completed', 'result': 'output1'}
        
        mock_agent.solve_task = slow_task
        
        # Run benchmark with short timeout
        runner = BenchmarkRunner(
            benchmarks_dir=str(self.benchmarks_dir),
            results_dir=str(self.results_dir),
            timeout=0.1
        )
        
        result = AsyncTestRunner.run(
            runner.run_benchmark(mock_agent, 'test_benchmark')
        )
        
        self.assertEqual(len(result.test_results), 1)
        self.assertFalse(result.test_results[0]['passed'])
        self.assertIn('timeout', result.test_results[0]['error'].lower())
    
    def test_save_results(self):
        """Test saving benchmark results."""
        result = BenchmarkResult(
            benchmark_name='test_benchmark',
            test_results=[{
                'test_id': 'test1',
                'passed': True,
                'actual_output': 'output1',
                'expected_output': 'output1',
                'error': None,
                'execution_time': 0.1
            }],
            metadata={'test': True}
        )
        
        # Save results
        result_file = self.runner._save_results(result, 'test_agent')
        
        self.assertTrue(result_file.exists())
        
        # Load and verify
        with open(result_file, 'r') as f:
            saved_data = json.load(f)
        
        self.assertEqual(saved_data['benchmark_name'], 'test_benchmark')
        self.assertEqual(len(saved_data['test_results']), 1)


class TestAgentValidator(unittest.TestCase):
    """Test cases for AgentValidator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_validator_"))
        self.validator = AgentValidator()
        
        # Create test agent
        self.agent_path = self.temp_dir / "test_agent"
        TestFixtures.create_mock_agent_code(self.agent_path)
    
    def tearDown(self):
        """Clean up test fixtures."""
        cleanup_test_directory(self.temp_dir)
    
    def test_validate_valid_agent(self):
        """Test validating a valid agent."""
        result = AsyncTestRunner.run(
            self.validator.validate_agent(str(self.agent_path))
        )
        
        self.assertTrue(result['is_valid'])
        self.assertTrue(result['syntax_valid'])
        self.assertTrue(result['imports_valid'])
        self.assertTrue(result['methods_valid'])
        self.assertEqual(len(result['errors']), 0)
    
    def test_validate_syntax_error(self):
        """Test validating agent with syntax errors."""
        # Introduce syntax error
        agent_file = self.agent_path / "agent" / "agent.py"
        content = agent_file.read_text()
        content += "\n\nthis is invalid python syntax"
        agent_file.write_text(content)
        
        result = AsyncTestRunner.run(
            self.validator.validate_agent(str(self.agent_path))
        )
        
        self.assertFalse(result['is_valid'])
        self.assertFalse(result['syntax_valid'])
        self.assertGreater(len(result['errors']), 0)
    
    def test_validate_missing_methods(self):
        """Test validating agent with missing required methods."""
        # Remove solve_task method
        agent_file = self.agent_path / "agent" / "agent.py"
        content = agent_file.read_text()
        lines = content.splitlines()
        
        # Remove solve_task method
        new_lines = []
        skip = False
        for line in lines:
            if 'async def solve_task' in line:
                skip = True
            elif skip and line.strip() and not line.startswith(' '):
                skip = False
            
            if not skip:
                new_lines.append(line)
        
        agent_file.write_text('\n'.join(new_lines))
        
        result = AsyncTestRunner.run(
            self.validator.validate_agent(str(self.agent_path))
        )
        
        self.assertFalse(result['is_valid'])
        self.assertFalse(result['methods_valid'])
    
    def test_validate_config(self):
        """Test configuration validation."""
        # Valid config
        valid_config = {
            'agent_id': 'test_agent',
            'fm_provider': 'gemini',
            'fm_config': {
                'model': 'gemini-pro',
                'api_key': 'test_key'
            }
        }
        
        result = self.validator.validate_agent_config(valid_config)
        self.assertTrue(result['valid'])
        self.assertEqual(len(result['errors']), 0)
        
        # Invalid config (missing required field)
        invalid_config = {
            'agent_id': 'test_agent',
            'fm_config': {
                'model': 'gemini-pro'
            }
        }
        
        result = self.validator.validate_agent_config(invalid_config)
        self.assertFalse(result['valid'])
        self.assertGreater(len(result['errors']), 0)


class TestBenchmarkScorer(unittest.TestCase):
    """Test cases for BenchmarkScorer and scoring methods."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.scorer = BenchmarkScorer()
    
    def test_binary_scorer(self):
        """Test binary scoring."""
        scorer = BinaryScorer(strict=True)
        
        # Exact match
        score = scorer.score("hello", "hello", {})
        self.assertEqual(score, 1.0)
        
        # No match
        score = scorer.score("hello", "world", {})
        self.assertEqual(score, 0.0)
        
        # Test non-strict mode
        scorer_non_strict = BinaryScorer(strict=False)
        score = scorer_non_strict.score("  hello  ", "hello", {})
        self.assertEqual(score, 1.0)
    
    def test_partial_credit_scorer(self):
        """Test partial credit scoring."""
        scorer = PartialCreditScorer(
            similarity_threshold=0.9,
            ignore_whitespace=True
        )
        
        # Very similar strings
        score = scorer.score("hello world", "hello  world", {})
        self.assertEqual(score, 1.0)
        
        # Somewhat similar
        score = scorer.score("hello world", "hello earth", {})
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)
        
        # Very different
        score = scorer.score("abc", "xyz", {})
        self.assertLess(score, 0.5)
    
    def test_json_scorer(self):
        """Test JSON scoring."""
        scorer = JsonScorer(
            required_fields=['name'],
            partial_credit=True
        )
        
        # Valid JSON, all fields match
        actual = '{"name": "test", "value": 42}'
        expected = '{"name": "test", "value": 42}'
        score = scorer.score(actual, expected, {})
        self.assertEqual(score, 1.0)
        
        # Missing required field
        actual = '{"value": 42}'
        expected = '{"name": "test", "value": 42}'
        score = scorer.score(actual, expected, {})
        self.assertEqual(score, 0.0)
        
        # Partial match
        scorer_partial = JsonScorer(partial_credit=True)
        actual = '{"name": "test", "value": 100}'
        expected = '{"name": "test", "value": 42}'
        score = scorer_partial.score(actual, expected, {})
        self.assertEqual(score, 0.5)  # 1 out of 2 fields match
    
    def test_function_output_scorer(self):
        """Test function output scoring."""
        scorer = FunctionOutputScorer(
            scoring_method="average",
            min_pass_rate=0.8
        )
        
        # Single test
        score = scorer.score("42", "42", {})
        self.assertEqual(score, 1.0)
        
        # Multiple tests
        results = [
            ("42", "42", {}),
            ("hello", "hello", {}),
            ("world", "earth", {}),
            ("test", "test", {})
        ]
        
        score = scorer.score_multiple(results)
        self.assertEqual(score, 0.75)  # 3 out of 4 pass
    
    def test_get_scorer(self):
        """Test getting appropriate scorer based on config."""
        # Binary scorer
        config = {'scoring': {'method': 'binary'}}
        scorer = self.scorer.get_scorer(config)
        self.assertIsInstance(scorer, BinaryScorer)
        
        # Partial credit scorer
        config = {'scoring': {'method': 'partial'}}
        scorer = self.scorer.get_scorer(config)
        self.assertIsInstance(scorer, PartialCreditScorer)
        
        # JSON scorer
        config = {'scoring': {'method': 'json'}}
        scorer = self.scorer.get_scorer(config)
        self.assertIsInstance(scorer, JsonScorer)
        
        # Function scorer
        config = {'scoring': {'method': 'function'}}
        scorer = self.scorer.get_scorer(config)
        self.assertIsInstance(scorer, FunctionOutputScorer)
    
    def test_score_benchmark(self):
        """Test scoring complete benchmark results."""
        config = {'scoring': {'method': 'binary'}}
        
        results = [
            {
                'actual_output': 'hello',
                'expected_output': 'hello',
                'test_case': {},
                'error': None
            },
            {
                'actual_output': 'world',
                'expected_output': 'world',
                'test_case': {},
                'error': None
            },
            {
                'actual_output': 'test',
                'expected_output': 'fail',
                'test_case': {},
                'error': None
            },
            {
                'actual_output': '',
                'expected_output': 'error',
                'test_case': {},
                'error': 'Test failed'
            }
        ]
        
        summary = self.scorer.score_benchmark(config, results)
        
        self.assertEqual(summary['total_tests'], 4)
        self.assertEqual(summary['passed_tests'], 2)
        self.assertEqual(summary['total_score'], 0.5)  # 2/4 passed
        self.assertEqual(len(summary['scores']), 4)


if __name__ == '__main__':
    unittest.main()