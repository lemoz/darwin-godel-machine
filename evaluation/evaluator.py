"""
Main evaluator module for running benchmarks and evaluating agents.

This module orchestrates the evaluation process, running agents
through benchmarks and collecting performance metrics.
"""

from typing import Dict, List, Any, Optional, Callable
from pathlib import Path
import yaml
import json
import asyncio
import time
from datetime import datetime

from .benchmark import Benchmark, BenchmarkConfig
from .agent_validator import AgentValidator


class Evaluator:
    """
    Main evaluator for running agent benchmarks.
    
    This class coordinates the evaluation process, including
    agent validation, benchmark execution, and result collection.
    """
    
    def __init__(self, sandbox_manager: Optional[Any] = None):
        """
        Initialize the evaluator.
        
        Args:
            sandbox_manager: Optional sandbox manager for isolated execution
        """
        self.sandbox_manager = sandbox_manager
        self.validator = AgentValidator()
        self.benchmarks: Dict[str, Benchmark] = {}
        self.results: Dict[str, Any] = {}
    
    def load_benchmark(self, benchmark_name: str, benchmark: Benchmark) -> None:
        """
        Load a benchmark into the evaluator.
        
        Args:
            benchmark_name: Name to register the benchmark under
            benchmark: Benchmark instance
        """
        self.benchmarks[benchmark_name] = benchmark
    
    def load_benchmarks_from_directory(self, directory: str) -> None:
        """
        Load all benchmarks from a directory.
        
        Args:
            directory: Path to directory containing benchmark configs
        """
        bench_dir = Path(directory)
        if not bench_dir.exists():
            raise ValueError(f"Benchmark directory {directory} does not exist")
        
        for yaml_file in bench_dir.glob("*.yaml"):
            try:
                # This is simplified - in reality would need to instantiate
                # the correct benchmark class based on the config
                with open(yaml_file, 'r') as f:
                    config_data = yaml.safe_load(f)
                
                # For now, just store the config
                self.benchmarks[yaml_file.stem] = config_data
            except Exception as e:
                print(f"Failed to load benchmark {yaml_file}: {e}")
    
    async def evaluate_agent(
        self,
        agent_path: str,
        agent_executor: Callable,
        benchmark_names: Optional[List[str]] = None,
        validate_first: bool = True
    ) -> Dict[str, Any]:
        """
        Evaluate an agent on specified benchmarks.
        
        Args:
            agent_path: Path to the agent implementation
            agent_executor: Function to execute agent on inputs
            benchmark_names: List of benchmarks to run (None = all)
            validate_first: Whether to validate agent before running
            
        Returns:
            Dict containing evaluation results
        """
        results = {
            'agent_path': agent_path,
            'timestamp': datetime.now().isoformat(),
            'validation': None,
            'benchmarks': {},
            'overall_score': 0.0,
            'metadata': {}
        }
        
        # Validate agent if requested
        if validate_first:
            validation_results = await self.validator.validate_agent(agent_path)
            results['validation'] = validation_results
            
            if not validation_results['valid']:
                results['metadata']['error'] = "Agent validation failed"
                return results
        
        # Determine which benchmarks to run
        benchmarks_to_run = benchmark_names or list(self.benchmarks.keys())
        
        # Run each benchmark
        total_score = 0.0
        benchmark_count = 0
        
        for benchmark_name in benchmarks_to_run:
            if benchmark_name not in self.benchmarks:
                results['benchmarks'][benchmark_name] = {
                    'error': f"Benchmark {benchmark_name} not found"
                }
                continue
            
            try:
                benchmark = self.benchmarks[benchmark_name]
                
                # Run in sandbox if available
                if self.sandbox_manager:
                    benchmark_results = await self._run_in_sandbox(
                        benchmark,
                        agent_executor
                    )
                else:
                    # For testing purposes when benchmark is already instantiated
                    if isinstance(benchmark, Benchmark):
                        benchmark_results = await benchmark.run(agent_executor)
                    else:
                        # Skip if not a proper benchmark instance
                        benchmark_results = {
                            'error': 'Benchmark not properly instantiated'
                        }
                
                results['benchmarks'][benchmark_name] = benchmark_results
                
                # Update overall score
                if 'metrics' in benchmark_results:
                    score = benchmark_results['metrics'].get('success_rate', 0.0)
                    total_score += score
                    benchmark_count += 1
                
            except Exception as e:
                results['benchmarks'][benchmark_name] = {
                    'error': f"Benchmark execution failed: {str(e)}"
                }
        
        # Calculate overall score
        if benchmark_count > 0:
            results['overall_score'] = total_score / benchmark_count
        
        # Store results
        self.results[agent_path] = results
        
        return results
    
    async def _run_in_sandbox(
        self,
        benchmark: Benchmark,
        agent_executor: Callable
    ) -> Dict[str, Any]:
        """
        Run a benchmark in a sandboxed environment.
        
        Args:
            benchmark: Benchmark to run
            agent_executor: Agent execution function
            
        Returns:
            Benchmark results
        """
        # This would use the sandbox manager to create an isolated
        # environment for benchmark execution
        # For now, just run directly
        return await benchmark.run(agent_executor)
    
    def get_benchmark_summary(self, agent_path: str) -> str:
        """
        Get a human-readable summary of benchmark results.
        
        Args:
            agent_path: Path to the agent
            
        Returns:
            Summary string
        """
        if agent_path not in self.results:
            return "No results found for this agent"
        
        results = self.results[agent_path]
        lines = ["Evaluation Summary", "=" * 50]
        
        # Validation status
        if results['validation']:
            if results['validation']['valid']:
                lines.append("✓ Agent validation passed")
            else:
                lines.append("✗ Agent validation failed")
        
        # Overall score
        lines.append(f"\nOverall Score: {results['overall_score']:.2%}")
        
        # Benchmark results
        lines.append("\nBenchmark Results:")
        for name, bench_results in results['benchmarks'].items():
            if 'error' in bench_results:
                lines.append(f"  {name}: ERROR - {bench_results['error']}")
            elif 'metrics' in bench_results:
                score = bench_results['metrics'].get('success_rate', 0.0)
                passed = bench_results.get('passed', 0)
                total = bench_results.get('total_tests', 0)
                lines.append(f"  {name}: {score:.2%} ({passed}/{total} passed)")
            else:
                lines.append(f"  {name}: No metrics available")
        
        return "\n".join(lines)
    
    def save_results(self, output_path: str) -> None:
        """
        Save evaluation results to a file.
        
        Args:
            output_path: Path to save results
        """
        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
    
    def load_results(self, input_path: str) -> None:
        """
        Load evaluation results from a file.
        
        Args:
            input_path: Path to load results from
        """
        with open(input_path, 'r') as f:
            self.results = json.load(f)
    
    def compare_agents(self, agent_paths: List[str]) -> Dict[str, Any]:
        """
        Compare performance of multiple agents.
        
        Args:
            agent_paths: List of agent paths to compare
            
        Returns:
            Comparison results
        """
        comparison = {
            'agents': {},
            'benchmark_rankings': {},
            'overall_ranking': []
        }
        
        # Collect results for each agent
        for agent_path in agent_paths:
            if agent_path in self.results:
                results = self.results[agent_path]
                comparison['agents'][agent_path] = {
                    'overall_score': results['overall_score'],
                    'benchmarks': {}
                }
                
                # Extract benchmark scores
                for bench_name, bench_results in results['benchmarks'].items():
                    if 'metrics' in bench_results:
                        score = bench_results['metrics'].get('success_rate', 0.0)
                        comparison['agents'][agent_path]['benchmarks'][bench_name] = score
                        
                        # Update benchmark rankings
                        if bench_name not in comparison['benchmark_rankings']:
                            comparison['benchmark_rankings'][bench_name] = []
                        comparison['benchmark_rankings'][bench_name].append({
                            'agent': agent_path,
                            'score': score
                        })
        
        # Sort rankings
        for bench_name in comparison['benchmark_rankings']:
            comparison['benchmark_rankings'][bench_name].sort(
                key=lambda x: x['score'],
                reverse=True
            )
        
        # Overall ranking
        overall_scores = [
            (agent, data['overall_score'])
            for agent, data in comparison['agents'].items()
        ]
        overall_scores.sort(key=lambda x: x[1], reverse=True)
        comparison['overall_ranking'] = [
            {'agent': agent, 'score': score}
            for agent, score in overall_scores
        ]
        
        return comparison