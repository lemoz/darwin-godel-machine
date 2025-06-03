"""
Darwin Gödel Machine Controller.

Main controller that orchestrates the DGM loop of self-improvement.
"""

import asyncio
import logging
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import traceback

import yaml

from agent import Agent, Task, AgentConfig
from archive import AgentArchive, ParentSelector, NoveltyCalculator
from archive.parent_selector import HybridSelection
from evaluation.benchmark_runner import BenchmarkRunner
from evaluation.scorer import BenchmarkScorer
from evaluation.agent_validator import AgentValidator
from utils.logger import setup_logger
from utils.agent_loader import AgentLoader


logger = logging.getLogger(__name__)


class DGMController:
    """
    Main controller for the Darwin Gödel Machine.
    
    Orchestrates the core loop of:
    1. Parent selection from archive
    2. Self-modification of parent agent
    3. Evaluation on benchmarks
    4. Archive update with new agents
    """
    
    def __init__(self, config_or_path: Any = "config/dgm_config.yaml", workspace: Optional[str] = None):
        """
        Initialize DGM controller.
        
        Args:
            config_or_path: Either a config dictionary or path to DGM configuration file
            workspace: Optional workspace directory (only used when config_or_path is a dict)
        """
        # Load configuration
        if isinstance(config_or_path, dict):
            self.config = config_or_path
            self.workspace = workspace or os.getcwd()
        else:
            with open(config_or_path, 'r') as f:
                self.config = yaml.safe_load(f)
            self.workspace = os.path.dirname(os.path.abspath(config_or_path))
        
        # Expand environment variables in config
        self._expand_env_vars(self.config)
        
        # Set up logging
        self.logger = setup_logger(
            self.config.get('logging', {}).get('level', 'INFO')
        )
        
        # Initialize components
        self.archive = AgentArchive(
            archive_dir=self.config['archive']['path']
        )
        
        # Create hybrid selection strategy with configured weights
        selection_strategy = HybridSelection(
            fitness_weight=self.config['parent_selection']['performance_weight'],
            novelty_weight=self.config['parent_selection']['novelty_weight']
        )
        self.parent_selector = ParentSelector(strategy=selection_strategy)
        
        self.novelty_calculator = NoveltyCalculator()
        
        self.benchmark_runner = BenchmarkRunner(
            benchmarks_dir=self.config['evaluation']['benchmarks_dir']
        )
        
        self.scorer = BenchmarkScorer()
        self.validator = AgentValidator()
        
        # Initialize agent loader
        self.agent_loader = AgentLoader(project_root=Path(self.workspace))
        
        # Initialize FM interface (placeholder - should be implemented based on config)
        self.fm_interface = None  # TODO: Initialize based on config['fm_interface']
        
        # Track DGM metrics
        self.generation = 0
        self.total_agents_created = 0
        self.successful_improvements = 0
        self.start_time = datetime.now()
        
        # Create necessary directories
        Path(self.config['archive']['path']).mkdir(parents=True, exist_ok=True)
        Path(self.config['evaluation']['results_dir']).mkdir(parents=True, exist_ok=True)
        Path(self.config['agents']['workspace_dir']).mkdir(parents=True, exist_ok=True)
    
    def _expand_env_vars(self, obj):
        """
        Recursively expand environment variables in config.
        
        Replaces ${VAR_NAME} with the value of environment variable VAR_NAME.
        """
        import re
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                obj[key] = self._expand_env_vars(value)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                obj[i] = self._expand_env_vars(item)
        elif isinstance(obj, str):
            # Replace ${VAR_NAME} with environment variable value
            pattern = r'\$\{([^}]+)\}'
            def replacer(match):
                var_name = match.group(1)
                return os.environ.get(var_name, match.group(0))
            obj = re.sub(pattern, replacer, obj)
        
        return obj
    
    def get_or_create_initial_agent(self) -> str:
        """
        Get or create the initial agent (agent_0).
        
        Returns:
            The agent ID (always 'agent_0' for initial agent)
        """
        agent_id = "agent_0"
        agent_path = Path(self.workspace) / "agents" / agent_id
        
        if not agent_path.exists():
            # Create the initial agent directory and files
            agent_path.mkdir(parents=True, exist_ok=True)
            
            # Create basic agent structure
            (agent_path / "__init__.py").touch()
            
            # Create minimal agent.py
            agent_code = '''"""Initial agent implementation."""

class Agent:
    """Basic agent implementation."""
    
    def __init__(self):
        pass
    
    async def solve_task(self, task):
        """Solve the given task."""
        return "Not implemented"
'''
            (agent_path / "agent.py").write_text(agent_code)
        
        return agent_id
    
    async def run(self, num_generations: Optional[int] = None):
        """
        Run the main DGM loop.
        
        Args:
            num_generations: Number of generations to run. If None, runs indefinitely.
        """
        logger.info("Starting Darwin Gödel Machine")
        logger.info(f"Configuration: {self.config}")
        
        # Initialize with base agent if archive is empty
        if len(self.archive.agents) == 0:
            await self._initialize_base_agent()
        
        generation_count = 0
        
        while num_generations is None or generation_count < num_generations:
            self.generation += 1
            generation_count += 1
            
            logger.info(f"\n{'='*50}")
            logger.info(f"GENERATION {self.generation}")
            logger.info(f"{'='*50}")
            
            try:
                # Run one generation
                await self._run_generation()
                
                # Log progress
                self._log_progress()
                
                # Check stopping criteria
                if self._should_stop():
                    logger.info("Stopping criteria met")
                    break
                
                # Brief pause between generations
                await asyncio.sleep(self.config.get('generation_delay_seconds', 1))
                
            except KeyboardInterrupt:
                logger.info("Interrupted by user")
                break
            except Exception as e:
                logger.error(f"Error in generation {self.generation}: {e}")
                logger.error(traceback.format_exc())
                
                # Continue with next generation after error
                if self.config.get('stop_on_error', False):
                    break
        
        # Final report
        self._generate_final_report()
    
    async def _run_generation(self):
        """Run a single generation of the DGM loop."""
        # 1. Select parent from archive
        # Select parent from archive
        parents = self.parent_selector.select_parents(
            archive=self.archive,
            n_parents=1
        )
        
        parent = parents[0] if parents else None
        
        if parent is None:
            logger.warning("No suitable parent found in archive")
            return
        
        logger.info(f"Selected parent: {parent.agent_id} (score: {parent.average_score:.3f})")
        
        # 2. Create self-modification task
        modification_task = self._create_modification_task(parent)
        
        # 3. Have parent attempt self-modification
        logger.info("Attempting self-modification...")
        modified_agent_path = await self._perform_self_modification(
            parent, modification_task
        )
        
        if modified_agent_path is None:
            logger.warning("Self-modification failed")
            return
        
        # 4. Validate modified agent
        logger.info("Validating modified agent...")
        validation_result = await self.validator.validate_agent(
            modified_agent_path,
            run_functional_tests=True
        )
        
        if not validation_result['is_valid']:
            logger.warning(f"Modified agent validation failed: {validation_result['errors']}")
            return
        
        # 5. Evaluate on benchmarks
        logger.info("Evaluating modified agent on benchmarks...")
        benchmark_scores = await self._evaluate_agent(modified_agent_path)
        
        # 6. Calculate performance metrics
        total_score = sum(benchmark_scores.values()) / len(benchmark_scores)
        logger.info(f"Modified agent total score: {total_score:.3f}")
        
        # 7. Add to archive if meets threshold
        if total_score >= self.config['archive'].get('min_score_threshold', 0.1):
            archived_agent = self.archive.add_agent(
                agent_path=modified_agent_path,
                parent_id=parent.agent_id,
                benchmark_scores=benchmark_scores
            )
            
            logger.info(f"Added agent {archived_agent.agent_id} to archive")
            self.total_agents_created += 1
            
            # Track if this is an improvement
            if total_score > parent.average_score:
                self.successful_improvements += 1
                logger.info("✓ Agent shows improvement over parent!")
        else:
            logger.info("Agent score below threshold, not added to archive")
    
    async def _initialize_base_agent(self):
        """Initialize the archive with the base agent."""
        logger.info("Initializing archive with base agent...")
        
        base_agent_path = self.config['agents']['initial_agent_path']
        
        # Validate base agent
        validation_result = await self.validator.validate_agent(
            base_agent_path
        )
        
        if not validation_result['valid']:
            raise ValueError(f"Base agent validation failed: {validation_result['errors']}")
        
        # Evaluate base agent
        benchmark_scores = await self._evaluate_agent(base_agent_path)
        
        # Add to archive
        base_agent = self.archive.add_agent(
            agent_path=base_agent_path,
            parent_id=None,
            benchmark_scores=benchmark_scores
        )
        
        logger.info(f"Base agent {base_agent.agent_id} added to archive")
        logger.info(f"Base agent score: {base_agent.average_score:.3f}")
    
    def _create_modification_task(self, parent_agent) -> Task:
        """
        Create a self-modification task for the parent agent.
        
        Args:
            parent_agent: The parent agent to be modified
            
        Returns:
            Task object for self-modification
        """
        # Get benchmark performance data
        benchmark_info = []
        for benchmark, score in parent_agent.benchmark_scores.items():
            benchmark_info.append(f"- {benchmark}: {score:.2f}")
        
        # Create modification prompt
        task_description = f"""You are an AI agent participating in the Darwin Gödel Machine (DGM) experiment.
Your task is to modify your own source code to create an improved version of yourself.

Current Performance:
{chr(10).join(benchmark_info)}
Average Score: {parent_agent.average_score:.3f}

Your goal is to improve your performance on coding benchmarks by modifying your source code.
You have access to your complete source code in the current directory.

Specific areas to consider:
1. Improve your problem-solving strategies
2. Enhance your code generation capabilities
3. Optimize your tool usage patterns
4. Refine your prompt engineering
5. Add new capabilities or refactor existing ones

Important constraints:
- Maintain compatibility with the existing Agent interface
- Preserve your self-modification capabilities
- Ensure the modified version can still be instantiated and run

Create your improved version by modifying files in the agent/ directory.
Focus on meaningful improvements that will enhance benchmark performance."""
        
        return Task(
            task_id=f"self_modify_{parent_agent.agent_id}_{self.generation}",
            description=task_description,
            metadata={
                'parent_id': parent_agent.agent_id,
                'generation': self.generation,
                'parent_score': parent_agent.average_score
            }
        )
    
    async def _perform_self_modification(
        self,
        parent_agent,
        modification_task: Task
    ) -> Optional[str]:
        """
        Have the parent agent perform self-modification.
        
        Args:
            parent_agent: The parent agent
            modification_task: The modification task
            
        Returns:
            Path to modified agent or None if failed
        """
        try:
            # Create workspace for modification
            workspace_dir = Path(self.config['agents']['workspace_dir']) / modification_task.task_id
            workspace_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy parent agent code to workspace
            import shutil
            parent_path = Path(parent_agent.source_path)
            shutil.copytree(parent_path, workspace_dir, dirs_exist_ok=True)
            
            # Create agent configuration
            primary_provider = self.config['fm_providers']['primary']
            agent_config = AgentConfig(
                agent_id=parent_agent.agent_id,
                fm_provider=primary_provider,
                fm_config=self.config['fm_providers'][primary_provider],
                working_directory=str(workspace_dir),
                max_iterations=self.config['dgm_settings'].get('max_iterations', 10)
            )
            
            # Instantiate parent agent
            agent = Agent(agent_config)
            
            # Perform self-modification
            result = await agent.solve_task(modification_task)
            
            if result.get('success', False):
                # Extract the solution (modified code) from the result
                modified_code = result.get('solution', '')
                if modified_code:
                    # Save the modified code to the workspace
                    modified_agent_path = workspace_dir / 'agent.py'
                    modified_agent_path.write_text(modified_code)
                    return str(workspace_dir)
                else:
                    logger.warning("Self-modification succeeded but no solution provided")
                    return None
            else:
                logger.warning(f"Self-modification failed: {result.get('error', 'Unknown error')}")
                return None
                
        except Exception as e:
            logger.error(f"Error during self-modification: {e}")
            logger.error(traceback.format_exc())
            return None
    
    async def _evaluate_agent(self, agent_path: str) -> Dict[str, float]:
        """
        Evaluate an agent on all benchmarks.
        
        Args:
            agent_path: Path to the agent to evaluate
            
        Returns:
            Dictionary of benchmark names to scores
        """
        scores = {}
        
        # Get list of benchmarks
        benchmarks = self.config['benchmarks']['enabled']
        
        for benchmark_name in benchmarks:
            try:
                logger.info(f"Running benchmark: {benchmark_name}")
                
                # Create minimal agent config for evaluation
                # Get primary provider name and its config
                primary_provider = self.config['fm_providers']['primary']
                provider_config = self.config['fm_providers'][primary_provider]
                
                agent_config = AgentConfig(
                    agent_id=f"eval_{Path(agent_path).name}",
                    fm_provider=primary_provider,
                    fm_config=provider_config,
                    working_directory=str(Path(agent_path).parent)
                )
                
                # Load the agent class from the file
                agent_path_obj = Path(agent_path)
                if agent_path_obj.name == 'agent.py':
                    # This is an agent file, load it with AgentLoader
                    if 'archive' in str(agent_path_obj):
                        # Loading from archive
                        AgentClass = self.agent_loader.load_from_archive(agent_path_obj)
                    else:
                        # Loading from source
                        AgentClass = self.agent_loader.load_from_source()
                else:
                    # Fallback to default Agent
                    AgentClass = Agent
                
                # Create agent instance
                agent = AgentClass(agent_config)
                
                # Run benchmark
                result = await self.benchmark_runner.run_benchmark(
                    agent=agent,
                    benchmark_name=benchmark_name,
                    verbose=False
                )
                
                # Score results
                # Create a config dict with the expected structure for the scorer
                benchmark_config = {
                    'name': benchmark_name,
                    'scoring': {
                        'method': 'binary'  # Default for all benchmarks
                    }
                }
                scoring_summary = self.scorer.score_benchmark(
                    benchmark_config=benchmark_config,
                    results=result.test_results
                )
                
                scores[benchmark_name] = scoring_summary['total_score']
                logger.info(f"{benchmark_name} score: {scoring_summary['total_score']:.3f}")
                
            except Exception as e:
                logger.error(f"Error evaluating benchmark {benchmark_name}: {e}")
                scores[benchmark_name] = 0.0
        
        return scores
    
    def _should_stop(self) -> bool:
        """Check if stopping criteria are met."""
        # Check time limit
        if 'max_runtime_hours' in self.config:
            runtime = (datetime.now() - self.start_time).total_seconds() / 3600
            if runtime >= self.config['max_runtime_hours']:
                logger.info(f"Reached time limit ({runtime:.1f} hours)")
                return True
        
        # Check performance threshold
        if 'target_performance' in self.config:
            top_agents = self.archive.get_top_agents(n=1)
            if top_agents and top_agents[0].performance_score >= self.config['target_performance']:
                logger.info(f"Reached target performance ({top_agents[0].performance_score:.3f})")
                return True
        
        return False
    
    def _log_progress(self):
        """Log current progress metrics."""
        runtime = (datetime.now() - self.start_time).total_seconds() / 60  # minutes
        
        logger.info("\n--- Progress Report ---")
        logger.info(f"Generation: {self.generation}")
        logger.info(f"Runtime: {runtime:.1f} minutes")
        logger.info(f"Total agents created: {self.total_agents_created}")
        logger.info(f"Successful improvements: {self.successful_improvements}")
        logger.info(f"Archive size: {len(self.archive.agents)}")
        
        # Top agents
        top_agents = self.archive.get_top_agents(n=3)
        logger.info("\nTop agents:")
        for i, agent in enumerate(top_agents):
            logger.info(f"  {i+1}. {agent.agent_id}: {agent.average_score:.3f}")
    
    def _generate_final_report(self):
        """Generate final report of the DGM run."""
        runtime = (datetime.now() - self.start_time).total_seconds() / 3600  # hours
        
        report = {
            'summary': {
                'total_generations': self.generation,
                'runtime_hours': runtime,
                'total_agents_created': self.total_agents_created,
                'successful_improvements': self.successful_improvements,
                'improvement_rate': self.successful_improvements / max(1, self.total_agents_created),
                'final_archive_size': len(self.archive.agents)
            },
            'top_agents': [],
            'performance_trajectory': []
        }
        
        # Add top agents
        top_agents = self.archive.get_top_agents(n=10)
        for agent in top_agents:
            report['top_agents'].append({
                'agent_id': agent.agent_id,
                'score': agent.average_score,
                'generation': agent.generation,
                'benchmark_scores': agent.benchmark_scores
            })
        
        # Save report
        report_path = Path(self.config['evaluation']['results_dir']) / f"dgm_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"\n{'='*50}")
        logger.info("FINAL REPORT")
        logger.info(f"{'='*50}")
        logger.info(f"Total runtime: {runtime:.2f} hours")
        logger.info(f"Generations: {self.generation}")
        logger.info(f"Agents created: {self.total_agents_created}")
        logger.info(f"Improvements: {self.successful_improvements} ({report['summary']['improvement_rate']:.1%})")
        logger.info(f"\nTop agent: {top_agents[0].agent_id if top_agents else 'None'}")
        if top_agents:
            logger.info(f"Top score: {top_agents[0].average_score:.3f}")
        logger.info(f"\nFull report saved to: {report_path}")


async def main():
    """Main entry point for DGM."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Darwin Gödel Machine")
    parser.add_argument(
        '--config',
        type=str,
        default='config/dgm_config.yaml',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--generations',
        type=int,
        default=None,
        help='Number of generations to run (default: unlimited)'
    )
    
    args = parser.parse_args()
    
    # Create and run controller
    controller = DGMController(config_path=args.config)
    await controller.run(num_generations=args.generations)


if __name__ == "__main__":
    asyncio.run(main())