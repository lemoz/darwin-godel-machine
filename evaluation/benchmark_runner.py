"""
Benchmark Runner for DGM.

Executes agents on benchmark tasks and collects results.
"""

import asyncio
import json
import os
import re
import shlex
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import logging
import yaml

# Agent imports — only needed when an actual Agent object is passed in.
# We keep these at module level because benchmark_runner.py is part of the
# evaluation package that depends on the agent package.
from agent import Agent, Task, AgentConfig

# SandboxManager is optional — the docker SDK may not be installed.
# Import lazily so a missing docker package doesn't crash the program.
try:
    from sandbox.sandbox_manager import SandboxManager as _SandboxManager
except ImportError:
    _SandboxManager = None  # type: ignore

logger = logging.getLogger(__name__)

# Regex for valid Python identifiers (used to prevent code injection).
_VALID_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def _is_valid_identifier(name: str) -> bool:
    """Return True if *name* is a safe Python identifier."""
    return bool(_VALID_IDENTIFIER_RE.match(name))


@dataclass
class BenchmarkTask:
    """Represents a single benchmark task."""

    name: str
    description: str
    task_prompt: str
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
            task_prompt=config.get('task_prompt', config['description']),
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
        sandbox_manager: Optional[Any] = None,
        use_sandbox: bool = False
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

        if self.use_sandbox and self.sandbox_manager is None and _SandboxManager:
            candidate = _SandboxManager()
            if candidate.is_docker_available():
                self.sandbox_manager = candidate
            else:
                logger.warning(
                    "Docker sandbox requested but unavailable; using direct subprocess execution"
                )
                self.use_sandbox = False

        if self.use_sandbox and self.sandbox_manager:
            readiness_check = getattr(self.sandbox_manager, "is_sandbox_ready", None)
            if readiness_check is not None:
                if not readiness_check():
                    logger.warning(
                        "Docker sandbox image unavailable; using direct subprocess execution"
                    )
                    self.use_sandbox = False
            else:
                ensure_image = getattr(self.sandbox_manager, "ensure_sandbox_image", None)
                if ensure_image is not None:
                    try:
                        ensure_image()
                    except Exception as exc:
                        logger.warning(
                            "Docker sandbox image unavailable; using direct subprocess execution: %s",
                            exc,
                        )
                        self.use_sandbox = False

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
            # Build enhanced task description with test cases.
            test_cases_text = "\n\nOFFICIAL TEST CASES:\n"
            for i, test_case in enumerate(benchmark.test_cases, 1):
                func_name = test_case.get('function_name', 'function')
                test_cases_text += f"{i}. Function: {func_name}\n"
                for j, (inp, exp) in enumerate(zip(test_case['inputs'], test_case['expected_outputs'])):
                    test_cases_text += f"   {j+1}. Input: {inp} -> Expected: {exp}\n"

            enhanced_description = (
                f"{benchmark.task_prompt}{test_cases_text}"
                "\nFocus on these exact test cases - do not invent additional ones."
            )

            task = Task(
                task_id=f"benchmark_{benchmark_name}_{int(time.time())}",
                description=enhanced_description,
                metadata={
                    'benchmark': benchmark_name,
                    'timeout': benchmark.timeout
                }
            )

            # Run agent on the task.
            if self.use_sandbox and self.sandbox_manager:
                result = await self._run_in_sandbox(agent, task, benchmark)
            else:
                result = await self._run_directly(agent, task, benchmark)

            execution_time = time.time() - start_time

            # Calculate score.
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
        agent_result = await agent.solve_task(task)

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
        """
        Run benchmark flow with sandboxed test execution where available.

        Agent task solving still runs in-process because it may need configured
        provider clients and workspace tools. The generated benchmark solution
        test scripts are isolated by ``_run_test_case`` when sandboxing is
        enabled and Docker is available.
        """
        return await self._run_directly(agent, task, benchmark)

    def _can_use_sandbox(self) -> bool:
        """Return True when sandboxed subprocess execution is configured."""
        if not self.use_sandbox or not self.sandbox_manager:
            return False
        readiness_check = getattr(self.sandbox_manager, "is_sandbox_ready", None)
        if readiness_check is not None:
            return bool(readiness_check())
        availability_check = getattr(self.sandbox_manager, "is_docker_available", None)
        if availability_check is None:
            return True
        if not bool(availability_check()):
            return False
        ensure_image = getattr(self.sandbox_manager, "ensure_sandbox_image", None)
        if ensure_image is not None:
            try:
                ensure_image()
            except Exception:
                return False
        return True

    # ------------------------------------------------------------------
    # Test-generation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_test_script(
        solution_file: str,
        function_name: str,
        raw_input: str,
        raw_expected: str,
        test_index: int
    ) -> str:
        """
        Build a self-contained Python test script for one input/expected pair.

        The script:
        1. Imports the solution module.
        2. Parses *raw_input* with ``ast.literal_eval`` to produce real Python
           objects, then calls ``function_name(*args)``.
        3. Parses *raw_expected* with ``ast.literal_eval``; falls back to
           string comparison if parsing fails.
        4. Prints a single JSON line with keys:
           ``success``, ``actual_output``, ``expected_output``, ``error``.

        Returns the script source as a string.
        """
        module_name = os.path.basename(solution_file)[:-3]
        dir_path = os.path.dirname(solution_file)
        # Embed raw strings safely using repr() so special chars can't escape
        # the surrounding string delimiters.
        return f"""
import sys, ast, json, traceback
sys.path.insert(0, {repr(dir_path)})

try:
    import {module_name} as _sol_mod
except Exception as _imp_err:
    print(json.dumps({{
        "success": False,
        "actual_output": None,
        "expected_output": None,
        "error": "ImportError: " + str(_imp_err)
    }}))
    sys.exit(0)

_raw_input = {repr(raw_input)}
_raw_expected = {repr(raw_expected)}
_func_name = {repr(function_name)}

# --- Parse inputs ---
try:
    _args = ast.literal_eval("(" + _raw_input + ",)")
    if not isinstance(_args, tuple):
        _args = (_args,)
except Exception as _parse_err:
    print(json.dumps({{
        "success": False,
        "actual_output": None,
        "expected_output": None,
        "error": "InputParseError: " + str(_parse_err)
    }}))
    sys.exit(0)

# --- Parse expected output ---
try:
    _expected = ast.literal_eval(_raw_expected.strip())
    _expected_for_compare = _expected
    _use_str_compare = False
except Exception:
    _expected_for_compare = _raw_expected.strip()
    _use_str_compare = True

# --- Call the function ---
try:
    _func = getattr(_sol_mod, _func_name)
    _result = _func(*_args)
except Exception as _call_err:
    print(json.dumps({{
        "success": False,
        "actual_output": None,
        "expected_output": _raw_expected.strip(),
        "error": "CallError: " + str(_call_err)
    }}))
    sys.exit(0)

# --- Compare ---
if _use_str_compare:
    _success = str(_result).strip() == _expected_for_compare
else:
    _success = _result == _expected_for_compare

print(json.dumps({{
    "success": _success,
    "actual_output": repr(_result),
    "expected_output": repr(_expected_for_compare),
    "error": None
}}))
"""

    async def _run_test_case(
        self,
        solution: str,
        test_case: Dict[str, Any],
        benchmark: BenchmarkTask
    ) -> Dict[str, Any]:
        """Run a single test case with multiple inputs/outputs."""
        # --- Security: validate function_name before embedding in code ---
        function_name = test_case.get('function_name', 'solve')
        if not _is_valid_identifier(function_name):
            error_msg = (
                f"Invalid function_name {function_name!r}: must match "
                r"^[a-zA-Z_][a-zA-Z0-9_]*$"
            )
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'individual_results': [],
                'passed': 0,
                'total': 0
            }

        solution_file: Optional[str] = None
        temp_dir: Optional[tempfile.TemporaryDirectory] = None
        try:
            use_sandbox = self._can_use_sandbox()
            if use_sandbox:
                sandbox_temp_parent = Path.home() / ".cache" / "dgm-sandbox"
                sandbox_temp_parent.mkdir(parents=True, exist_ok=True)
                temp_dir = tempfile.TemporaryDirectory(dir=str(sandbox_temp_parent))
            else:
                temp_dir = tempfile.TemporaryDirectory()

            workspace_path = Path(temp_dir.name)
            solution_path = workspace_path / "solution.py"
            solution_path.write_text(solution)
            solution_file = str(solution_path)

            inputs = test_case.get('inputs', [])
            expected_outputs = test_case.get('expected_outputs', [])

            results: List[Dict[str, Any]] = []
            overall_success = True
            sandbox_working_dir = getattr(
                getattr(self.sandbox_manager, "config", None),
                "working_dir",
                "/home/dgm_agent/workspace",
            )

            for i, (input_val, expected_val) in enumerate(zip(inputs, expected_outputs)):
                raw_input = str(input_val)
                raw_expected = str(expected_val)
                sandbox_solution_file = str(Path(sandbox_working_dir) / solution_path.name)

                test_code = self._build_test_script(
                    sandbox_solution_file if use_sandbox else solution_file,
                    function_name,
                    raw_input,
                    raw_expected,
                    i
                )
                test_script_path = workspace_path / f"test_case_{i}.py"
                test_script_path.write_text(test_code)

                if use_sandbox:
                    sandbox_result = await self.sandbox_manager.execute_in_sandbox(
                        command=f"{shlex.quote('python')} {shlex.quote(test_script_path.name)}",
                        workspace_path=str(workspace_path),
                        timeout=benchmark.timeout,
                    )
                    output_text = sandbox_result.output.strip()
                    stderr_text = (sandbox_result.error or "").strip()
                    timed_out = (
                        not sandbox_result.success
                        and sandbox_result.exit_code is None
                        and "timed out" in stderr_text.lower()
                    )
                else:
                    proc = await asyncio.create_subprocess_exec(
                        sys.executable,
                        str(test_script_path),
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )

                    try:
                        stdout, stderr = await asyncio.wait_for(
                            proc.communicate(),
                            timeout=benchmark.timeout
                        )
                    except asyncio.TimeoutError:
                        # Kill the subprocess cleanly on timeout.
                        try:
                            proc.kill()
                        except ProcessLookupError:
                            pass
                        await proc.wait()
                        timeout_result = {
                            'success': False,
                            'actual_output': None,
                            'expected_output': raw_expected.strip(),
                            'error': f'Timeout after {benchmark.timeout}s',
                            'input': raw_input
                        }
                        results.append(timeout_result)
                        overall_success = False
                        continue

                    output_text = stdout.decode().strip()
                    stderr_text = stderr.decode().strip()
                    timed_out = False

                # Parse the machine-readable JSON marker.
                test_result: Dict[str, Any] = {}
                if timed_out:
                    test_result = {
                        'success': False,
                        'actual_output': None,
                        'expected_output': raw_expected.strip(),
                        'error': f'Timeout after {benchmark.timeout}s',
                        'input': raw_input
                    }
                elif output_text:
                    try:
                        # The script prints exactly one JSON line.
                        last_json_line = output_text.split('\n')[-1]
                        test_result = json.loads(last_json_line)
                    except json.JSONDecodeError:
                        test_result = {
                            'success': False,
                            'actual_output': None,
                            'expected_output': raw_expected.strip(),
                            'error': f'Output parse error: {output_text!r}',
                            'input': raw_input
                        }
                else:
                    test_result = {
                        'success': False,
                        'actual_output': None,
                        'expected_output': raw_expected.strip(),
                        'error': stderr_text or 'No output produced',
                        'input': raw_input
                    }

                test_result['input'] = raw_input
                results.append(test_result)
                if not test_result.get('success', False):
                    overall_success = False

            return {
                'success': overall_success,
                'individual_results': results,
                'passed': sum(1 for r in results if r.get('success', False)),
                'total': len(results)
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'individual_results': [],
                'passed': 0,
                'total': 0
            }
        finally:
            if solution_file and os.path.exists(solution_file):
                try:
                    os.unlink(solution_file)
                except OSError:
                    pass
            if temp_dir is not None:
                temp_dir.cleanup()

    def _calculate_score(
        self,
        result: Dict[str, Any],
        benchmark: BenchmarkTask
    ) -> float:
        """Calculate score based on test results."""
        test_results = result.get('test_results', [])

        if not test_results:
            return 0.0

        total_passed = 0
        total_tests = 0

        for test_result in test_results:
            if 'individual_results' in test_result:
                total_passed += test_result.get('passed', 0)
                total_tests += test_result.get('total', 0)
            else:
                total_tests += 1
                if test_result.get('success', False):
                    total_passed += 1

        if total_tests == 0:
            return 0.0

        if benchmark.scoring_method == 'pass_fail':
            return 1.0 if total_passed == total_tests else 0.0
        elif benchmark.scoring_method == 'partial':
            return total_passed / total_tests
        else:
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
