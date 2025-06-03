"""
Evaluation components for the Darwin Gödel Machine.

This module contains components for evaluating agent performance,
running benchmarks, and validating agent implementations.
"""

from .agent_validator import AgentValidator
from .benchmark import Benchmark, BenchmarkConfig
from .evaluator import Evaluator

# Aliases for backwards compatibility
BenchmarkRunner = Evaluator
BenchmarkScorer = Evaluator

__all__ = [
    'AgentValidator',
    'Benchmark',
    'BenchmarkConfig',
    'Evaluator',
    'BenchmarkRunner',
    'BenchmarkScorer'
]