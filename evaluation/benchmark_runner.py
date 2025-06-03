"""
Benchmark Runner for DGM.

Executes agents on benchmark tasks and collects results.
"""

import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import logging
import yaml

from agent import Agent, Task, AgentConfig
from sandbox.sandbox_manager import SandboxManager

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkTask:
    """Represents a single benchmark task."""
    
    name: str
    description: str
    task_prompt: str  # Add task_prompt field
    test_cases: List[Dict[str, Any]]
    timeout: int
    validation_code: str
    scoring_method: str
    
    @classmethod
    def from_config(cls, config_path: str) -> 'BenchmarkTask':
        """Load benchmark task from configuration file."""
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        return cls(
            name=config['name'],
            description=config['description'],
            task_prompt=config.get('task_prompt', config['description']),  # Load task_prompt, fallback to description
            test_cases=config['test_cases'],
            timeout=config.get('timeout', 60),
            validation_code=config.get('validation_code', ''),
            scoring_method=config.get('scoring_method', 'pass_fail')
        )


@dataclass
class BenchmarkResult:
    """Result of running a benchmark task."""
    
    task_name: str
    agent_id: str
    success: bool
    score: float
    execution_time: float
    test_results: List[Dict[str, Any]]
    error: Optional[str] = None
    output: Optional[str] = None


class BenchmarkRunner:
    """Runs agents on benchmark tasks."""
    
    def __init__(
        self,
        benchmarks_dir: str = "./config/benchmarks",
        sandbox_manager: Optional[SandboxManager] = None,
        use_sandbox: bool = True
    ):
        """
        Initialize the benchmark runner.
        
        Args:
            benchmarks_dir: Directory containing benchmark configurations
            sandbox_manager: Optional sandbox manager for secure execution
            use_sandbox: Whether to use sandboxing for agent execution
        """
        self.benchmarks_dir = Path(benchmarks_dir)
        self.sandbox_manager = sandbox_manager
        self.use_sandbox = use_sandbox
        self.benchmarks: Dict[str, BenchmarkTask] = {}
        self._load_benchmarks()
    
    def _load_benchmarks(self) -> None:
        """Load all benchmark configurations."""
        if not self.benchmarks_dir.exists():
            logger.warning(f"Benchmarks directory not found: {self.benchmarks_dir}")
            return
        
        for config_file in self.benchmarks_dir.glob("*.yaml"):
            try:
                benchmark = BenchmarkTask.from_config(str(config_file))
                self.benchmarks[benchmark.name] = benchmark
                logger.info(f"Loaded benchmark: {benchmark.name}")
            except Exception as e:
                logger.error(f"Failed to load benchmark {config_file}: {e}")
    
    async def run_benchmark(
        self,
        agent: Agent,
        benchmark_name: str,
        verbose: bool = False
    ) -> BenchmarkResult:
        """
        Run a single benchmark on an agent.
        
        Args:
            agent: The agent to evaluate
            benchmark_name: Name of the benchmark to run
            verbose: Whether to log detailed output
            
        Returns:
            Benchmark result
        """
        if benchmark_name not in self.benchmarks:
            raise ValueError(f"Unknown benchmark: {benchmark_name}")
        
        benchmark = self.benchmarks[benchmark_name]
        start_time = time.time()
        
        try:
            # Create task for the agent
            # Build enhanced task description with official test cases (standardized format)
            test_cases_text = "\n\nOFFICIAL TEST CASES:\n"
            for i, test_case in enumerate(benchmark.test_cases, 1):
                func_name = test_case.get('function_name', 'function')
                test_cases_text += f"{i}. Function: {func_name}\n"
                for j, (inp, exp) in enumerate(zip(test_case['inputs'], test_case['expected_outputs'])):
                    test_cases_text += f"   {j+1}. Input: {inp} → Expected: {exp}\n"
            
            enhanced_description = f"{benchmark.task_prompt}{test_cases_text}\nFocus on these exact test cases - do not invent additional ones."
            
            task = Task(
                task_id=f"benchmark_{benchmark_name}_{int(time.time())}",
                description=enhanced_description,
                metadata={
                    'benchmark': benchmark_name,
                    'timeout': benchmark.timeout
                }
            )
            
            # Run agent on the task
            if self.use_sandbox and self.sandbox_manager:
                result = await self._run_in_sandbox(agent, task, benchmark)
            else:
                result = await self._run_directly(agent, task, benchmark)
            
            execution_time = time.time() - start_time
            
            # Calculate score
            score = self._calculate_score(result, benchmark)
            
            return BenchmarkResult(
                task_name=benchmark_name,
                agent_id=agent.agent_id,
                success=score > 0,
                score=score,
                execution_time=execution_time,
                test_results=result['test_results'],
                output=result.get('output', '')
            )
            
        except Exception as e:
            logger.error(f"Benchmark {benchmark_name} failed: {e}")
            return BenchmarkResult(
                task_name=benchmark_name,
                agent_id=agent.agent_id,
                success=False,
                score=0.0,
                execution_time=time.time() - start_time,
                test_results=[],
                error=str(e)
            )
    
    async def _run_directly(
        self,
        agent: Agent,
        task: Task,
        benchmark: BenchmarkTask
    ) -> Dict[str, Any]:
        """Run agent directly without sandboxing."""
        # Run the agent
        agent_result = await agent.solve_task(task)
        
        # Run test cases
        test_results = []
        for test_case in benchmark.test_cases:
            test_result = await self._run_test_case(
                agent_result.get('solution', ''),
                test_case,
                benchmark
            )
            test_results.append(test_result)
        
        return {
            'test_results': test_results,
            'output': agent_result.get('output', '')
        }
    
    async def _run_in_sandbox(
        self,
        agent: Agent,
        task: Task,
        benchmark: BenchmarkTask
    ) -> Dict[str, Any]:
        """Run agent in a sandboxed environment."""
        # TODO: Implement sandboxed execution using SandboxManager
        # For now, fall back to direct execution
        logger.warning("Sandbox execution not fully implemented, using direct execution")
        return await self._run_directly(agent, task, benchmark)
    
    async def _run_test_case(
        self,
        solution: str,
        test_case: Dict[str, Any],
        benchmark: BenchmarkTask
    ) -> Dict[str, Any]:
        """Run a single test case with multiple inputs/outputs."""
        try:
            # Create a temporary file with the solution
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.py',
                delete=False
            ) as f:
                f.write(solution)
                solution_file = f.name
            
            function_name = test_case.get('function_name', 'solve')
            inputs = test_case.get('inputs', [])
            expected_outputs = test_case.get('expected_outputs', [])
            
            results = []
            overall_success = True
            
            # Test each input/expected_output pair
            for i, (input_val, expected_val) in enumerate(zip(inputs, expected_outputs)):
                test_code = f"""
import sys
import json
sys.path.insert(0, '{os.path.dirname(solution_file)}')

# Import the solution
from {os.path.basename(solution_file)[:-3]} import *

# Test case {i+1}
input_value = {repr(input_val)}
expected_output = {repr(expected_val)}

# Run the solution
try:
    result = {function_name}(input_value)
    success = result == expected_output
    error = None
except Exception as e:
    result = None
    success = False
    error = str(e)

print(json.dumps({{
    'success': success,
    'result': result,
    'expected': expected_output,
    'error': error,
    'input': input_value
}}))
"""
                
                # Execute the test
                proc = await asyncio.create_subprocess_exec(
                    'python', '-c', test_code,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=benchmark.timeout
                )
                
                # Parse result
                if proc.returncode == 0:
                    test_result = json.loads(stdout.decode())
                else:
                    test_result = {
                        'success': False,
                        'error': stderr.decode(),
                        'result': None,
                        'expected': expected_val,
                        'input': input_val
                    }
                
                results.append(test_result)
                if not test_result['success']:
                    overall_success = False
            
            return {
                'success': overall_success,
                'individual_results': results,
                'passed': sum(1 for r in results if r['success']),
                'total': len(results)
            }
            
        except asyncio.TimeoutError:
            return {
                'success': False,
                'error': 'Timeout',
                'result': None,
                'expected': test_case.get('expected_output')
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'result': None,
                'expected': test_case.get('expected_output')
            }
        finally:
            # Clean up
            if 'solution_file' in locals():
                os.unlink(solution_file)
    
    def _calculate_score(
        self,
        result: Dict[str, Any],
        benchmark: BenchmarkTask
    ) -> float:
        """Calculate score based on test results."""
        test_results = result.get('test_results', [])
        
        if not test_results:
            return 0.0
        
        # Handle new standardized format with individual_results
        total_passed = 0
        total_tests = 0
        
        for test_result in test_results:
            if 'individual_results' in test_result:
                # New format: each test_result has individual_results
                total_passed += test_result.get('passed', 0)
                total_tests += test_result.get('total', 0)
            else:
                # Fallback: old format
                total_tests += 1
                if test_result.get('success', False):
                    total_passed += 1
        
        if total_tests == 0:
            return 0.0
        
        if benchmark.scoring_method == 'pass_fail':
            # Binary scoring: all tests must pass
            return 1.0 if total_passed == total_tests else 0.0
        
        elif benchmark.scoring_method == 'partial':
            # Partial credit based on passed tests
            return total_passed / total_tests
        
        else:
            # Default to pass/fail
            return 1.0 if total_passed == total_tests else 0.0
    
    async def run_all_benchmarks(
        self,
        agent: Agent,
        benchmark_names: Optional[List[str]] = None
    ) -> Dict[str, BenchmarkResult]:
        """
        Run multiple benchmarks on an agent.
        
        Args:
            agent: The agent to evaluate
            benchmark_names: List of benchmarks to run (None = all)
            
        Returns:
            Dictionary mapping benchmark names to results
        """
        if benchmark_names is None:
            benchmark_names = list(self.benchmarks.keys())
        
        results = {}
        
        for benchmark_name in benchmark_names:
            if benchmark_name not in self.benchmarks:
                logger.warning(f"Skipping unknown benchmark: {benchmark_name}")
                continue
            
            logger.info(f"Running benchmark: {benchmark_name}")
            result = await self.run_benchmark(agent, benchmark_name)
            results[benchmark_name] = result
        
        return results
    
    def get_average_score(self, results: Dict[str, BenchmarkResult]) -> float:
        """Calculate average score across all benchmarks."""
        if not results:
            return 0.0
        
        total_score = sum(r.score for r in results.values())
        return total_score / len(results)