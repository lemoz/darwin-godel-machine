"""
Darwin Gödel Machine Controller.

Main controller that orchestrates the DGM loop of self-improvement.
"""

import ast
import asyncio
import difflib
import gc
import hashlib
import logging
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import traceback

import yaml

from agent import Agent, Task, AgentConfig
from agent.tools.base_tool import ToolExecutionStatus
from agent.tools.edit_tool import EditTool
from archive import AgentArchive, ParentSelector
from evaluation.benchmark_runner import BenchmarkRunner
from evaluation.agent_validator import AgentValidator
from sandbox.sandbox_manager import SandboxConfig, SandboxManager
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

        # Create parent selector using paper-formula parameters from config
        ps_cfg = self.config.get('parent_selection', {})
        self.parent_selector = ParentSelector(
            lam=ps_cfg.get('lambda', 10.0),
            alpha_0=ps_cfg.get('alpha_0', 0.5),
            require_non_regression=ps_cfg.get('require_non_regression', False),
            regression_tolerance=ps_cfg.get('regression_tolerance', 0.0),
            reject_score_ties=ps_cfg.get('reject_score_ties', False),
            elite_selection_probability=ps_cfg.get('elite_selection_probability', 0.0),
        )

        evaluation_config = self.config.get('evaluation', {})
        sandbox_manager = None
        use_sandbox = evaluation_config.get('use_sandbox', False)
        if use_sandbox:
            sandbox_config = SandboxConfig(
                **{
                    key: value
                    for key, value in self.config.get('sandbox', {}).items()
                    if key in SandboxConfig.__dataclass_fields__
                }
            )
            sandbox_manager = SandboxManager(sandbox_config)
            readiness_check = getattr(sandbox_manager, "is_sandbox_ready", None)
            if readiness_check is not None:
                if not readiness_check():
                    logger.warning(
                        "Docker sandbox requested but unavailable; using direct host execution"
                    )
                    sandbox_manager = None
                    use_sandbox = False
            else:
                availability_check = getattr(sandbox_manager, "is_docker_available", None)
                if availability_check is not None and not availability_check():
                    logger.warning(
                        "Docker sandbox requested but unavailable; using direct host execution"
                    )
                    sandbox_manager = None
                    use_sandbox = False
        self.sandbox_manager = sandbox_manager
        self.use_sandbox = use_sandbox

        self.benchmark_runner = BenchmarkRunner(
            benchmarks_dir=evaluation_config.get('benchmarks_dir', 'config/benchmarks'),
            sandbox_manager=sandbox_manager,
            use_sandbox=use_sandbox,
            enabled_benchmarks=self.config.get('benchmarks', {}).get('enabled'),
        )

        self.validator = AgentValidator(
            sandbox_manager=sandbox_manager,
            use_sandbox=use_sandbox,
            timeout=evaluation_config.get('timeout_seconds', 30),
        )

        # Initialize agent loader
        self.agent_loader = AgentLoader(project_root=Path(self.workspace))

        # Initialize FM interface (placeholder - should be implemented based on config)
        self.fm_interface = None  # TODO: Initialize based on config['fm_interface']

        # Track DGM metrics
        self.generation = 0
        self.total_agents_created = 0
        self.successful_improvements = 0
        self.start_time = datetime.now()
        self._mutation_metadata_by_agent_path: Dict[str, Dict[str, Any]] = {}
        self.consecutive_noop_mutations = 0

        # Create necessary directories
        Path(self.config['archive']['path']).mkdir(parents=True, exist_ok=True)
        Path(self.config['evaluation']['results_dir']).mkdir(parents=True, exist_ok=True)
        Path(self.config['agents']['workspace_dir']).mkdir(parents=True, exist_ok=True)

    async def _close_agent(self, agent: Any) -> None:
        """Close provider clients for one-shot agents created by this controller."""
        close = getattr(agent, "close", None)
        if close is None:
            return
        try:
            result = close()
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            logger.debug("Agent cleanup failed: %s", exc)

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

    def _redact_sensitive_values(self, obj):
        """Return a copy of config-like data with secret values redacted."""
        def is_sensitive_key(key: Any) -> bool:
            key_lower = str(key).lower()
            return (
                key_lower in {"api_key", "token", "secret", "password"}
                or key_lower.endswith("_api_key")
                or key_lower.endswith("_token")
                or key_lower.endswith("_secret")
                or key_lower.endswith("_password")
                or "credential" in key_lower
            )

        if isinstance(obj, dict):
            redacted = {}
            for key, value in obj.items():
                if is_sensitive_key(key):
                    redacted[key] = "[REDACTED]"
                else:
                    redacted[key] = self._redact_sensitive_values(value)
            return redacted
        if isinstance(obj, list):
            return [self._redact_sensitive_values(item) for item in obj]
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
        logger.info(f"Configuration: {self._redact_sensitive_values(self.config)}")

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
        parents = self.parent_selector.select_parents(
            archive=self.archive,
            n_parents=1
        )

        parent = parents[0] if parents else None

        if parent is None:
            logger.warning("No suitable parent found in archive")
            return

        logger.info(f"Selected parent: {parent.agent_id} (score: {parent.average_score:.3f})")

        # 2. Create self-modification task (with optional diagnosis/proposal enrichment)
        modification_task = self._create_modification_task(parent)

        # 3. Have parent attempt self-modification
        logger.info("Attempting self-modification...")
        modified_agent_path = await self._perform_self_modification(
            parent, modification_task
        )

        if modified_agent_path is None:
            logger.warning("Self-modification failed")
            return

        mutation_metadata = self._mutation_metadata_by_agent_path.get(
            str(Path(modified_agent_path).resolve()),
            {},
        )
        if mutation_metadata.get("mutation_status") == "noop":
            logger.warning(
                "Self-modification produced no Python agent code changes; "
                "archiving invalid no-op child without benchmark evaluation"
            )
            archived_agent = self.archive.add_agent(
                agent_path=modified_agent_path,
                parent_id=parent.agent_id,
                benchmark_scores={},
                is_valid=False,
                metadata={"mutation": mutation_metadata},
            )
            logger.info(
                "Archived no-op child %s as invalid mutation_status=noop",
                archived_agent.agent_id,
            )
            self.consecutive_noop_mutations += 1
            return

        self.consecutive_noop_mutations = 0

        # 4. Validate modified agent (validator takes only agent_path, returns {'valid': bool, ...})
        logger.info("Validating modified agent...")
        validation_result = await self.validator.validate_agent(
            modified_agent_path
        )

        if not validation_result['valid']:
            logger.warning(f"Modified agent validation failed: {validation_result['errors']}")
            archived_agent = self.archive.add_agent(
                agent_path=modified_agent_path,
                parent_id=parent.agent_id,
                benchmark_scores={},
                is_valid=False,
                metadata={
                    "mutation": mutation_metadata,
                    "validation": validation_result,
                },
            )
            logger.info(
                "Archived validation-failed child %s as invalid",
                archived_agent.agent_id,
            )
            return

        # 5. Evaluate on benchmarks
        logger.info("Evaluating modified agent on benchmarks...")
        benchmark_scores = await self._evaluate_agent(modified_agent_path)

        # 6. Calculate performance metrics (guard against empty dict)
        total_score = sum(benchmark_scores.values()) / len(benchmark_scores) if benchmark_scores else 0.0
        logger.info(f"Modified agent total score: {total_score:.3f}")
        score_delta_metadata = self._build_score_delta_metadata(parent, benchmark_scores)

        # 7. Archive ALL agents that passed validation (paper-faithful — no score gate)
        archived_agent = self.archive.add_agent(
            agent_path=modified_agent_path,
            parent_id=parent.agent_id,
            benchmark_scores=benchmark_scores,
            metadata={
                "score_delta": score_delta_metadata,
                "mutation": mutation_metadata,
            },
        )

        logger.info(f"Added agent {archived_agent.agent_id} to archive")
        self.total_agents_created += 1

        # Track if this is an improvement over the parent
        if total_score > parent.average_score:
            self.successful_improvements += 1
            logger.info("Agent shows improvement over parent!")

    def _build_score_delta_metadata(
        self,
        parent_agent,
        child_scores: Dict[str, float],
    ) -> Dict[str, Any]:
        """Summarize child-vs-parent score movement for selection audits."""
        parent_scores = parent_agent.benchmark_scores or {}
        child_average = (
            sum(child_scores.values()) / len(child_scores)
            if child_scores
            else 0.0
        )
        benchmark_deltas = {}
        benchmark_improvements = {}
        benchmark_regressions = {}

        for benchmark in sorted(set(parent_scores) | set(child_scores)):
            parent_score = parent_scores.get(benchmark, 0.0)
            child_score = child_scores.get(benchmark, 0.0)
            delta = child_score - parent_score
            benchmark_deltas[benchmark] = delta
            if delta > 0:
                benchmark_improvements[benchmark] = delta
            elif delta < 0:
                benchmark_regressions[benchmark] = delta

        average_delta = child_average - parent_agent.average_score
        return {
            "parent_average_score": parent_agent.average_score,
            "child_average_score": child_average,
            "average_delta": average_delta,
            "benchmark_deltas": benchmark_deltas,
            "benchmark_improvements": benchmark_improvements,
            "benchmark_regressions": benchmark_regressions,
            "has_average_regression": average_delta < 0,
            "has_benchmark_regression": bool(benchmark_regressions),
            "selection_non_regression_eligible": (
                average_delta >= 0 and not benchmark_regressions
            ),
        }

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

    def _self_modification_max_steps(self) -> int:
        """Return the iteration budget for self-modification tasks."""
        configured = (
            self.config.get('self_modification', {})
            .get('max_steps', self.config['agents'].get('max_steps', 20))
        )
        max_steps = int(configured)
        if max_steps < 1:
            raise ValueError("self_modification.max_steps must be at least 1")
        return max_steps

    def _create_modification_task(self, parent_agent) -> Task:
        """
        Create a self-modification task for the parent agent.

        Attempts to enrich the task description using PerformanceDiagnosis and
        ModificationProposer.  On any failure, falls back to the static template.

        Args:
            parent_agent: The parent agent to be modified

        Returns:
            Task object for self-modification
        """
        # Get benchmark performance data
        benchmark_info = []
        for benchmark, score in parent_agent.benchmark_scores.items():
            benchmark_info.append(f"- {benchmark}: {score:.2f}")

        # --- Try diagnosis + proposal enrichment ---
        # Build a DiagnosisReport from the parent's archived scores (full eval
        # transcripts are not retained in the archive) and use the synchronous
        # suggestion/summary helpers; the async diagnose_performance entry
        # point needs detailed per-test results we don't have here.
        enrichment = ""
        try:
            from self_modification.performance_diagnosis import (
                PerformanceDiagnosis,
                DiagnosisReport,
            )
            from self_modification.modification_proposal import ModificationProposer

            report = DiagnosisReport(
                overall_score=parent_agent.average_score,
                benchmark_scores=dict(parent_agent.benchmark_scores),
            )
            PerformanceDiagnosis()._generate_improvement_suggestions(report)
            diagnosis_summary = ModificationProposer()._summarize_diagnosis(report)

            suggestions_text = "\n".join(
                f"  - {s}" for s in report.improvement_suggestions
            ) if report.improvement_suggestions else "  (no specific suggestions)"

            high_priority_text = ", ".join(report.high_priority_areas) if report.high_priority_areas else "none"

            enrichment = f"""
Diagnosis Summary: {diagnosis_summary}
High-priority areas: {high_priority_text}
Improvement suggestions:
{suggestions_text}
"""
        except Exception as _exc:
            logger.warning(f"Diagnosis/proposal enrichment failed (using static template): {_exc}")

        self_modification_max_steps = self._self_modification_max_steps()

        # --- Build task description ---
        task_description = f"""You are an AI agent participating in the Darwin Gödel Machine (DGM) experiment.
Your task is to modify your own source code to create an improved version of yourself.

Current Performance:
{chr(10).join(benchmark_info)}
Average Score: {parent_agent.average_score:.3f}
{enrichment}
Your goal is to improve your performance on coding benchmarks by modifying your source code.
You have access to your complete source code in the current directory.
Self-modification turn budget: {self_modification_max_steps} model/tool iterations.

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
- Change at least one Python source file that is part of the agent package
  (`agent.py`, `tools/*.py`, `fm_interface/*.py`, or provider modules).
  No-op attempts or benchmark-only solution files will be rejected as invalid.
- PATCH CONTRACT: inspect at most three source files before your first edit,
  then make a concrete Python source change. The run will treat read-only
  exploration as a failed mutation, even if your analysis is good.
- Make your first source write no later than step 4, or by the halfway point of
  the turn budget if the budget is smaller. After that point, the next action
  must be an edit to `agent.py`, `tools/*.py`, `fm_interface/*.py`, or a
  provider module.
- If you do not have a better patch by the write deadline, implement the safe default:
  improve the benchmark/self-modification steering text in `agent.py` so future
  agents write `solution.py` earlier, recover from tool argument errors, or avoid
  no-op self-modification loops.
- Do not use shell command chaining such as `&&` or `;`; use separate tool calls.
- In your final answer, briefly name the changed source file or files.

Create your improved version by modifying agent.py (and its subpackages) in your
working directory. Focus on meaningful improvements that will enhance benchmark
performance."""

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
            Path to the modified agent.py file, or None if failed.
        """
        try:
            # Create workspace for modification
            workspace_dir = Path(self.config['agents']['workspace_dir']) / modification_task.task_id
            workspace_dir.mkdir(parents=True, exist_ok=True)

            # Copy parent agent code to workspace (the whole package, so
            # relative imports keep working in the copy).
            import shutil
            parent_path = Path(parent_agent.source_path)
            if parent_path.is_file():
                parent_path = parent_path.parent
            shutil.copytree(
                parent_path,
                workspace_dir,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git'),
            )
            before_snapshot = self._snapshot_agent_tree(workspace_dir)

            # Create agent configuration
            primary_provider = self.config['fm_providers']['primary']
            agent_config = AgentConfig(
                agent_id=parent_agent.agent_id,
                fm_provider=primary_provider,
                fm_config=self.config['fm_providers'][primary_provider],
                working_directory=str(workspace_dir),
                max_iterations=self._self_modification_max_steps(),
                sandbox_manager=self.sandbox_manager,
                use_sandbox=self.use_sandbox,
            )

            # Instantiate parent agent
            agent = Agent(agent_config)

            # Perform self-modification
            try:
                result = await agent.solve_task(modification_task)
            finally:
                await self._close_agent(agent)

            if result.get('success', False):
                # (a) If result['solution'] is a non-empty, parseable Python string,
                #     write it to workspace agent.py; otherwise leave files as-is
                #     (the agent edited them in place via its edit tool).
                solution = result.get('solution', '')
                if solution and isinstance(solution, str):
                    try:
                        ast.parse(solution)
                        edit_tool = EditTool(
                            working_directory=str(workspace_dir),
                            sandbox_manager=self.sandbox_manager,
                            use_sandbox=self.use_sandbox,
                            timeout=self.config.get('evaluation', {}).get(
                                'timeout_seconds',
                                30,
                            ),
                        )
                        edit_result = await edit_tool.execute({
                            "action": "write",
                            "file_path": "agent.py",
                            "content": solution,
                        })
                        if edit_result.status != ToolExecutionStatus.SUCCESS:
                            logger.error(
                                "Failed to write solution string to workspace "
                                f"agent.py: {edit_result.error}"
                            )
                            return None
                        logger.info("Wrote solution string to workspace agent.py")
                    except SyntaxError:
                        logger.warning(
                            "result['solution'] is not valid Python — "
                            "relying on in-place edits by the agent."
                        )
                else:
                    logger.info("No solution string provided; relying on in-place edits.")

                # (b) Verify agent.py exists in the workspace
                agent_file = workspace_dir / 'agent.py'
                if not agent_file.exists():
                    logger.error(
                        f"agent.py not found in workspace {workspace_dir} after modification"
                    )
                    return None

                mutation_metadata = self._build_mutation_metadata(
                    parent_agent=parent_agent,
                    task_id=modification_task.task_id,
                    workspace_dir=workspace_dir,
                    before_snapshot=before_snapshot,
                    after_snapshot=self._snapshot_agent_tree(workspace_dir),
                )
                patch_text = self._build_mutation_patch(
                    before_snapshot=before_snapshot,
                    after_snapshot=self._snapshot_agent_tree(workspace_dir),
                    changed_files=mutation_metadata["changed_files"],
                )
                self._write_mutation_artifacts(
                    workspace_dir=workspace_dir,
                    metadata=mutation_metadata,
                    patch_text=patch_text,
                )
                self._mutation_metadata_by_agent_path[
                    str(agent_file.resolve())
                ] = mutation_metadata
                logger.info(
                    "Mutation proof: status=%s changed_code_files=%d changed_files=%d",
                    mutation_metadata["mutation_status"],
                    len(mutation_metadata["changed_code_files"]),
                    len(mutation_metadata["changed_files"]),
                )

                # (c) Return the FILE path, not the directory
                return str(agent_file)
            else:
                logger.warning(f"Self-modification failed: {result.get('error', 'Unknown error')}")
                return None

        except Exception as e:
            logger.error(f"Error during self-modification: {e}")
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def _skip_mutation_path(path: Path) -> bool:
        """Return True for generated/cache paths that should not prove mutation."""
        excluded_dirs = {".git", "__pycache__", ".dgm_metadata"}
        if any(part in excluded_dirs for part in path.parts):
            return True
        return path.suffix == ".pyc"

    @staticmethod
    def _is_agent_code_path(relative_path: str) -> bool:
        """Return True when a changed path is executable agent package code."""
        path = Path(relative_path)
        if path.suffix != ".py":
            return False
        return path.name not in {"solution.py", "solve.py", "main.py"}

    def _snapshot_agent_tree(self, root: Path) -> Dict[str, bytes]:
        """Snapshot non-generated files under an agent package directory."""
        snapshot: Dict[str, bytes] = {}
        for path in sorted(root.rglob("*")):
            relative_path = path.relative_to(root)
            if path.is_dir() or self._skip_mutation_path(relative_path):
                continue
            snapshot[relative_path.as_posix()] = path.read_bytes()
        return snapshot

    @staticmethod
    def _hash_manifest(snapshot: Dict[str, bytes]) -> Dict[str, Dict[str, Any]]:
        return {
            path: {
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
            for path, content in sorted(snapshot.items())
        }

    @staticmethod
    def _tree_sha256(manifest: Dict[str, Dict[str, Any]]) -> str:
        digest = hashlib.sha256()
        for path, item in sorted(manifest.items()):
            digest.update(path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(item["size_bytes"]).encode("ascii"))
            digest.update(b"\0")
            digest.update(item["sha256"].encode("ascii"))
            digest.update(b"\0")
        return digest.hexdigest()

    def _build_mutation_metadata(
        self,
        *,
        parent_agent,
        task_id: str,
        workspace_dir: Path,
        before_snapshot: Dict[str, bytes],
        after_snapshot: Dict[str, bytes],
    ) -> Dict[str, Any]:
        before_manifest = self._hash_manifest(before_snapshot)
        after_manifest = self._hash_manifest(after_snapshot)
        before_paths = set(before_manifest)
        after_paths = set(after_manifest)
        added_files = sorted(after_paths - before_paths)
        removed_files = sorted(before_paths - after_paths)
        modified_files = sorted(
            path
            for path in before_paths & after_paths
            if before_manifest[path]["sha256"] != after_manifest[path]["sha256"]
        )
        changed_files = sorted(added_files + modified_files + removed_files)
        changed_code_files = [
            path for path in changed_files if self._is_agent_code_path(path)
        ]
        mutation_status = "changed" if changed_code_files else "noop"
        return {
            "schema_version": 1,
            "task_id": task_id,
            "parent_agent_id": parent_agent.agent_id,
            "parent_source_path": str(parent_agent.source_path),
            "workspace_dir": str(workspace_dir),
            "mutation_status": mutation_status,
            "has_changes": bool(changed_files),
            "has_code_changes": bool(changed_code_files),
            "added_files": added_files,
            "modified_files": modified_files,
            "removed_files": removed_files,
            "changed_files": changed_files,
            "changed_code_files": changed_code_files,
            "parent_tree_sha256": self._tree_sha256(before_manifest),
            "child_tree_sha256": self._tree_sha256(after_manifest),
            "parent_manifest": before_manifest,
            "child_manifest": after_manifest,
            "artifact_paths": {
                "metadata": ".dgm_metadata/mutation.json",
                "patch": ".dgm_metadata/mutation.patch",
            },
        }

    def _build_mutation_patch(
        self,
        *,
        before_snapshot: Dict[str, bytes],
        after_snapshot: Dict[str, bytes],
        changed_files: List[str],
    ) -> str:
        chunks: List[str] = []
        for relative_path in changed_files:
            before = before_snapshot.get(relative_path, b"")
            after = after_snapshot.get(relative_path, b"")
            try:
                before_lines = before.decode("utf-8").splitlines(keepends=True)
                after_lines = after.decode("utf-8").splitlines(keepends=True)
            except UnicodeDecodeError:
                chunks.append(f"Binary file changed: {relative_path}\n")
                continue
            chunks.extend(
                difflib.unified_diff(
                    before_lines,
                    after_lines,
                    fromfile=f"parent/{relative_path}",
                    tofile=f"child/{relative_path}",
                )
            )
        return "".join(chunks)

    @staticmethod
    def _write_mutation_artifacts(
        *,
        workspace_dir: Path,
        metadata: Dict[str, Any],
        patch_text: str,
    ) -> None:
        metadata_dir = workspace_dir / ".dgm_metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        patch_path = metadata_dir / "mutation.patch"
        patch_path.write_text(patch_text, encoding="utf-8")
        metadata["patch_sha256"] = hashlib.sha256(
            patch_text.encode("utf-8")
        ).hexdigest()
        metadata["patch_size_bytes"] = len(patch_text.encode("utf-8"))
        (metadata_dir / "mutation.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    async def _evaluate_agent(self, agent_path: str) -> Dict[str, float]:
        """
        Evaluate an agent on all benchmarks.

        Args:
            agent_path: Path to the agent.py file to evaluate

        Returns:
            Dictionary of benchmark names to scores
        """
        scores = {}

        # Get list of benchmarks
        benchmarks = self.config['benchmarks']['enabled']

        for benchmark_name in benchmarks:
            try:
                logger.info(f"Running benchmark: {benchmark_name}")

                # Create minimal agent config for evaluation. Benchmark tasks
                # get a scratch workspace so generated solution files do not
                # modify the agent source directory being evaluated.
                primary_provider = self.config['fm_providers']['primary']
                provider_config = self.config['fm_providers'][primary_provider]

                agent_path_obj = Path(agent_path)
                with tempfile.TemporaryDirectory(prefix="dgm-benchmark-") as benchmark_workspace:
                    agent_config = AgentConfig(
                        agent_id=f"eval_{agent_path_obj.stem}_{benchmark_name}",
                        fm_provider=primary_provider,
                        fm_config=provider_config,
                        working_directory=benchmark_workspace,
                        max_iterations=self.config['agents'].get('max_steps', 20),
                        sandbox_manager=self.sandbox_manager,
                        use_sandbox=self.use_sandbox,
                        retain_conversation_history=False,
                    )

                    # Load the agent class from the file path using load_from_path,
                    # which handles all file paths correctly and avoids sys.modules
                    # collisions.  Fall back to the default Agent only when the file
                    # doesn't exist.
                    if agent_path_obj.exists():
                        AgentClass = self.agent_loader.load_from_path(agent_path_obj)
                    else:
                        logger.warning(
                            f"Agent file not found at {agent_path_obj}, using default Agent"
                        )
                        AgentClass = Agent

                    # Create agent instance
                    agent = AgentClass(agent_config)

                    try:
                        # Run benchmark — result.score is the pre-computed pass fraction
                        result = await self.benchmark_runner.run_benchmark(
                            agent=agent,
                            benchmark_name=benchmark_name,
                            verbose=False
                        )
                    finally:
                        await self._close_agent(agent)
                        del agent
                        gc.collect()

                scores[benchmark_name] = result.score
                logger.info(f"{benchmark_name} score: {result.score:.3f}")

            except Exception as e:
                logger.error(f"Error evaluating benchmark {benchmark_name}: {e}")
                scores[benchmark_name] = 0.0
            finally:
                gc.collect()

        return scores

    def _should_stop(self) -> bool:
        """Check if stopping criteria are met."""
        # Check time limit
        if 'max_runtime_hours' in self.config:
            runtime = (datetime.now() - self.start_time).total_seconds() / 3600
            if runtime >= self.config['max_runtime_hours']:
                logger.info(f"Reached time limit ({runtime:.1f} hours)")
                return True

        # Check performance threshold (use .average_score, not .performance_score)
        if 'target_performance' in self.config:
            top_agents = self.archive.get_top_agents(n=1)
            if top_agents and top_agents[0].average_score >= self.config['target_performance']:
                logger.info(f"Reached target performance ({top_agents[0].average_score:.3f})")
                return True

        max_noops = (
            self.config.get('self_modification', {})
            .get('max_consecutive_noop_mutations')
        )
        if max_noops is not None and self.consecutive_noop_mutations >= int(max_noops):
            logger.info(
                "Reached consecutive no-op mutation limit "
                f"({self.consecutive_noop_mutations}/{int(max_noops)})"
            )
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
                'consecutive_noop_mutations': self.consecutive_noop_mutations,
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
        logger.info(f"Consecutive no-op mutations: {self.consecutive_noop_mutations}")
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

    # Fix 7: constructor param is config_or_path, not config_path
    controller = DGMController(config_or_path=args.config)
    await controller.run(num_generations=args.generations)


if __name__ == "__main__":
    asyncio.run(main())
