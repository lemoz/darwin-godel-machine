"""
Evaluation components for the Darwin Gödel Machine.

This module contains components for evaluating agent performance,
running benchmarks, and validating agent implementations.

Live modules:
  - benchmark_runner.py  -> BenchmarkRunner (runs agents on YAML benchmark tasks)
  - scorer.py            -> BenchmarkScorer (scoring helpers)
  - agent_validator.py   -> AgentValidator (validates agent implementations)
"""

from .benchmark_runner import BenchmarkRunner
from .scorer import BenchmarkScorer
from .agent_validator import AgentValidator

__all__ = [
    'BenchmarkRunner',
    'BenchmarkScorer',
    'AgentValidator',
]
