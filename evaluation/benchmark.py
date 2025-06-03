"""
Benchmark module for evaluating agent performance.

This module provides the base classes and utilities for creating
and running benchmarks to test agent capabilities.
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import yaml
import asyncio
import time
import json
from abc import ABC, abstractmethod


@dataclass
class BenchmarkConfig:
    """Configuration for a benchmark."""
    name: str
    description: str
    version: str = "1.0"
    timeout: int = 300  # seconds
    max_attempts: int = 1
    tags: List[str] = field(default_factory=list)
    difficulty: str = "medium"  # easy, medium, hard
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TestCase:
    """Individual test case within a benchmark."""
    id: str
    description: str
    input: Any
    expected_output: Any
    timeout: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TestResult:
    """Result of running a test case."""
    test_id: str
    passed: bool
    actual_output: Any
    execution_time: float
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Benchmark(ABC):
    """
    Abstract base class for benchmarks.
    
    Benchmarks evaluate agent performance on specific tasks.
    Each benchmark contains multiple test cases.
    """
    
    def __init__(self, config: BenchmarkConfig):
        """
        Initialize the benchmark.
        
        Args:
            config: Benchmark configuration
        """
        self.config = config
        self.test_cases: List[TestCase] = []
        self.results: List[TestResult] = []
        self.setup_complete = False
    
    @abstractmethod
    async def setup(self) -> None:
        """
        Set up the benchmark environment.
        
        This method should prepare any resources needed for the benchmark.
        """
        pass
    
    @abstractmethod
    async def teardown(self) -> None:
        """
        Clean up after benchmark execution.
        
        This method should clean up any resources created during setup.
        """
        pass
    
    @abstractmethod
    def generate_test_cases(self) -> List[TestCase]:
        """
        Generate test cases for the benchmark.
        
        Returns:
            List of test cases
        """
        pass
    
    @abstractmethod
    async def evaluate_output(
        self,
        test_case: TestCase,
        actual_output: Any
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluate whether the actual output matches expected output.
        
        Args:
            test_case: The test case
            actual_output: The output produced by the agent
            
        Returns:
            Tuple of (passed, error_message)
        """
        pass
    
    async def run_test_case(
        self,
        test_case: TestCase,
        agent_executor: Any
    ) -> TestResult:
        """
        Run a single test case.
        
        Args:
            test_case: The test case to run
            agent_executor: Function to execute agent on the test
            
        Returns:
            TestResult
        """
        start_time = time.time()
        timeout = test_case.timeout or self.config.timeout
        
        try:
            # Execute with timeout
            actual_output = await asyncio.wait_for(
                agent_executor(test_case.input),
                timeout=timeout
            )
            
            # Evaluate the output
            passed, error = await self.evaluate_output(test_case, actual_output)
            
            execution_time = time.time() - start_time
            
            return TestResult(
                test_id=test_case.id,
                passed=passed,
                actual_output=actual_output,
                execution_time=execution_time,
                error=error
            )
            
        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            return TestResult(
                test_id=test_case.id,
                passed=False,
                actual_output=None,
                execution_time=execution_time,
                error=f"Timeout after {timeout} seconds"
            )
        except Exception as e:
            execution_time = time.time() - start_time
            return TestResult(
                test_id=test_case.id,
                passed=False,
                actual_output=None,
                execution_time=execution_time,
                error=f"Exception: {str(e)}"
            )
    
    async def run(self, agent_executor: Any) -> Dict[str, Any]:
        """
        Run the complete benchmark.
        
        Args:
            agent_executor: Function to execute agent on test inputs
            
        Returns:
            Dict containing benchmark results
        """
        # Setup
        if not self.setup_complete:
            await self.setup()
            self.setup_complete = True
        
        # Generate test cases if not already done
        if not self.test_cases:
            self.test_cases = self.generate_test_cases()
        
        # Run all test cases
        self.results = []
        for test_case in self.test_cases:
            result = await self.run_test_case(test_case, agent_executor)
            self.results.append(result)
        
        # Calculate metrics
        metrics = self.calculate_metrics()
        
        # Teardown
        await self.teardown()
        
        return {
            'benchmark': self.config.name,
            'version': self.config.version,
            'total_tests': len(self.test_cases),
            'passed': sum(1 for r in self.results if r.passed),
            'failed': sum(1 for r in self.results if not r.passed),
            'metrics': metrics,
            'results': [self._result_to_dict(r) for r in self.results]
        }
    
    def calculate_metrics(self) -> Dict[str, float]:
        """
        Calculate benchmark metrics.
        
        Returns:
            Dict of metric name to value
        """
        if not self.results:
            return {}
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        execution_times = [r.execution_time for r in self.results]
        
        metrics = {
            'success_rate': passed / total if total > 0 else 0.0,
            'avg_execution_time': sum(execution_times) / len(execution_times),
            'max_execution_time': max(execution_times),
            'min_execution_time': min(execution_times)
        }
        
        # Add timeout rate
        timeouts = sum(1 for r in self.results if r.error and 'Timeout' in r.error)
        metrics['timeout_rate'] = timeouts / total if total > 0 else 0.0
        
        return metrics
    
    def _result_to_dict(self, result: TestResult) -> Dict[str, Any]:
        """Convert TestResult to dictionary."""
        return {
            'test_id': result.test_id,
            'passed': result.passed,
            'execution_time': result.execution_time,
            'error': result.error,
            'metadata': result.metadata
        }
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'Benchmark':
        """
        Load benchmark configuration from YAML file.
        
        Args:
            yaml_path: Path to YAML configuration
            
        Returns:
            Benchmark instance
        """
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        
        config = BenchmarkConfig(
            name=data['name'],
            description=data['description'],
            version=data.get('version', '1.0'),
            timeout=data.get('timeout', 300),
            max_attempts=data.get('max_attempts', 1),
            tags=data.get('tags', []),
            difficulty=data.get('difficulty', 'medium'),
            metadata=data.get('metadata', {})
        )
        
        # This would need to instantiate the appropriate benchmark subclass
        # based on the configuration
        raise NotImplementedError("Subclasses must implement from_yaml")


class SimpleFunctionBenchmark(Benchmark):
    """
    A simple benchmark for testing function implementation tasks.
    
    This is a concrete implementation for testing purposes.
    """
    
    def __init__(self, config: BenchmarkConfig, test_functions: List[Dict[str, Any]]):
        """
        Initialize the benchmark.
        
        Args:
            config: Benchmark configuration
            test_functions: List of function test specifications
        """
        super().__init__(config)
        self.test_functions = test_functions
    
    async def setup(self) -> None:
        """No setup needed for simple function tests."""
        pass
    
    async def teardown(self) -> None:
        """No teardown needed for simple function tests."""
        pass
    
    def generate_test_cases(self) -> List[TestCase]:
        """Generate test cases from function specifications."""
        test_cases = []
        
        for i, func_spec in enumerate(self.test_functions):
            test_case = TestCase(
                id=f"test_{i}",
                description=func_spec.get('description', f"Test case {i}"),
                input=func_spec['input'],
                expected_output=func_spec['expected_output'],
                metadata=func_spec.get('metadata', {})
            )
            test_cases.append(test_case)
        
        return test_cases
    
    async def evaluate_output(
        self,
        test_case: TestCase,
        actual_output: Any
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluate function output.
        
        For simple functions, just check equality.
        """
        if actual_output == test_case.expected_output:
            return True, None
        else:
            return False, f"Expected {test_case.expected_output}, got {actual_output}"