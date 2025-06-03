"""Test to trace the benchmark execution flow and find where the error occurs."""

import asyncio
import traceback
from pathlib import Path
import sys
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from evaluation.benchmark_runner import BenchmarkRunner
from agent.agent import Agent, AgentConfig
from dgm_controller import DGMController

# Setup logging to trace execution
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def trace_benchmark_error():
    """Trace where the BenchmarkTask.get() error occurs."""
    try:
        # Load config
        controller = DGMController()
        
        # Create a simple agent config
        agent_config = AgentConfig(
            agent_id="test_agent",
            fm_provider="anthropic",
            fm_config=controller.config['fm_providers']['anthropic'],
            working_directory="."
        )
        
        # Create agent
        agent = Agent(agent_config)
        logger.info(f"Created agent: {agent.agent_id}")
        
        # Create benchmark runner
        benchmark_runner = BenchmarkRunner(
            benchmarks_dir=Path("config/benchmarks"),
            use_sandbox=False
        )
        
        # Try to run a benchmark
        logger.info("Running benchmark...")
        result = await benchmark_runner.run_benchmark(
            agent=agent,
            benchmark_name="string_manipulation",
            verbose=True
        )
        
        logger.info(f"Benchmark result: {result}")
        
    except Exception as e:
        logger.error(f"Error occurred: {type(e).__name__}: {e}")
        logger.error("Full traceback:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(trace_benchmark_error())