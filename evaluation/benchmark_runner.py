"""
Benchmark Runner for DGM.

Executes agents on benchmark tasks and collects results.
"""

import asyncio
import gc
import json
import os
import re
import shlex
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Set
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
_STDIN_TEST_TYPES = {"stdin", "stdio", "standard_input"}
_TEST_PROCESS_MEMORY_LIMIT_MB = 192
_STDIN_OUTPUT_CAPTURE_LIMIT_BYTES = 16 * 1024 * 1024
_STDIN_STDERR_CAPTURE_LIMIT_BYTES = 256 * 1024
_SUBSET_DP_RESOURCE_GUARD_MIN_N = 12


def _apply_test_process_resource_limits() -> None:
    """Constrain direct test processes so bad solutions cannot kill a shard."""
    try:
        import resource
    except ImportError:
        return

    limit_bytes = _TEST_PROCESS_MEMORY_LIMIT_MB * 1024 * 1024
    for limit_name in ("RLIMIT_AS", "RLIMIT_DATA"):
        limit_kind = getattr(resource, limit_name, None)
        if limit_kind is None:
            continue
        try:
            _soft, hard = resource.getrlimit(limit_kind)
            if hard in (-1, resource.RLIM_INFINITY):
                hard = limit_bytes
            resource.setrlimit(limit_kind, (min(limit_bytes, hard), hard))
        except (OSError, ValueError):
            continue


def _is_valid_identifier(name: str) -> bool:
    """Return True if *name* is a safe Python identifier."""
    return bool(_VALID_IDENTIFIER_RE.match(name))


def _is_stdin_test_case(test_case: Dict[str, Any]) -> bool:
    """Return True for contest-style programs that read stdin and write stdout."""
    return str(test_case.get("testtype", "")).lower() in _STDIN_TEST_TYPES


def _max_first_stdin_integer(test_case: Dict[str, Any]) -> Optional[int]:
    """Return the maximum first integer across stdin examples when parseable."""
    values: List[int] = []
    for raw_input in test_case.get("inputs", []):
        parts = str(raw_input).split()
        if not parts:
            continue
        try:
            values.append(int(parts[0]))
        except ValueError:
            continue
    return max(values) if values else None


def _static_resource_guard_error(
    solution: str,
    test_case: Dict[str, Any],
    benchmark: "BenchmarkTask",
) -> Optional[str]:
    """Reject solutions with obvious memory-explosive patterns before execution."""
    if not _is_stdin_test_case(test_case):
        return None

    max_n = _max_first_stdin_integer(test_case)
    if max_n is None or max_n < _SUBSET_DP_RESOURCE_GUARD_MIN_N:
        return None

    compact_solution = re.sub(r"\s+", "", solution.lower())
    subset_size_pattern = (
        re.search(r"\b\w+=1<<\w+", compact_solution) is not None
        or re.search(r"\b\w+=2\*\*\w+", compact_solution) is not None
    )
    set_per_mask_pattern = (
        "set()for" in compact_solution
        and "range(" in compact_solution
        and ("dp=[" in compact_solution or "dp=list(" in compact_solution)
    )
    submask_iteration_pattern = "(sub-1)&mask" in compact_solution

    if subset_size_pattern and set_per_mask_pattern and submask_iteration_pattern:
        return (
            "Resource guard rejected solution before execution: "
            "subset-DP set-per-mask pattern on stdin benchmark with "
            f"max first input value {max_n}"
        )

    return None


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
    prompt_test_cases: Optional[List[Dict[str, Any]]] = None

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
            scoring_method=config.get('scoring_method', 'pass_fail'),
            prompt_test_cases=config.get('prompt_test_cases'),
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
        use_sandbox: bool = False,
        enabled_benchmarks: Optional[List[str]] = None,
    ):
        """
        Initialize the benchmark runner.

        Args:
            benchmarks_dir: Directory containing benchmark configurations
            sandbox_manager: Optional sandbox manager for secure execution
            use_sandbox: Whether to use sandboxing for agent execution
            enabled_benchmarks: Optional benchmark names to load. When set,
                benchmark configs outside this set are left on disk to keep
                large sharded benchmark runs from retaining unused test data.
        """
        self.benchmarks_dir = Path(benchmarks_dir)
        self.sandbox_manager = sandbox_manager
        self.use_sandbox = use_sandbox
        self.enabled_benchmarks = set(enabled_benchmarks) if enabled_benchmarks else None
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

        requested: Optional[Set[str]] = self.enabled_benchmarks
        for config_file in self.benchmarks_dir.glob("*.yaml"):
            if requested is not None and config_file.stem not in requested:
                continue
            try:
                benchmark = BenchmarkTask.from_config(str(config_file))
                if requested is not None and benchmark.name not in requested:
                    continue
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
            # Build enhanced task description with prompt-visible examples.
            # When prompt_test_cases is configured, evaluation still runs the
            # full test_cases set below. This lets benchmark configs keep a
            # hidden scoring set instead of handing every expected output to
            # the agent before it writes a solution.
            prompt_cases = benchmark.prompt_test_cases or benchmark.test_cases
            prompt_label = (
                "PUBLIC EXAMPLES"
                if benchmark.prompt_test_cases is not None
                else "OFFICIAL TEST CASES"
            )
            test_cases_text = f"\n\n{prompt_label}:\n"
            for i, test_case in enumerate(prompt_cases, 1):
                if _is_stdin_test_case(test_case):
                    test_cases_text += f"{i}. Program reads stdin and writes stdout\n"
                else:
                    func_name = test_case.get('function_name', 'function')
                    test_cases_text += f"{i}. Function: {func_name}\n"
                for j, (inp, exp) in enumerate(zip(test_case['inputs'], test_case['expected_outputs'])):
                    if _is_stdin_test_case(test_case):
                        test_cases_text += (
                            f"   {j+1}. Stdin:\n{inp}\n"
                            f"      Expected stdout:\n{exp}\n"
                        )
                    else:
                        test_cases_text += f"   {j+1}. Input: {inp} -> Expected: {exp}\n"

            enhanced_description = (
                f"{benchmark.task_prompt}{test_cases_text}"
                "\nFocus on the requested behavior and the examples above."
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
        solution = agent_result.get('solution', '')
        output = agent_result.get('output', '')
        agent_result.pop('conversation_history', None)
        if hasattr(agent, "conversation_history"):
            agent.conversation_history = []
        gc.collect()

        test_results = []
        for test_case in benchmark.test_cases:
            test_result = await self._run_test_case(
                solution,
                test_case,
                benchmark
            )
            test_results.append(test_result)
            gc.collect()

        return {
            'test_results': test_results,
            'output': output
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

    @staticmethod
    def _build_stdin_test_script(
        solution_file: str,
        raw_input: str,
        raw_expected: str,
        test_index: int,
        timeout: int,
        input_file: Optional[str] = None,
        expected_file: Optional[str] = None,
    ) -> str:
        """
        Build a self-contained Python test script for one stdin/stdout case.

        This mirrors LiveCodeBench's standard-input comparison closely enough
        for DGM benchmark YAMLs: output is compared line-by-line after trimming
        outer whitespace, and numeric whitespace-separated lines are compared as
        Decimals when exact string comparison fails.
        """
        if input_file is not None and expected_file is not None:
            input_setup = (
                f"_input_file = Path({repr(input_file)})\n"
                f"_expected_file = Path({repr(expected_file)})\n"
                "_raw_input = None\n"
                "_raw_expected = None\n"
            )
        else:
            input_setup = (
                "_input_file = None\n"
                "_expected_file = None\n"
                f"_raw_input = {repr(raw_input)}\n"
                f"_raw_expected = {repr(raw_expected)}\n"
            )

        return f"""
import json, os, subprocess, sys, tempfile, time
from decimal import Decimal
from pathlib import Path

_solution_file = {repr(solution_file)}
{input_setup}
_timeout = {repr(int(timeout))}
_test_index = {repr(test_index)}
_memory_limit_mb = {repr(_TEST_PROCESS_MEMORY_LIMIT_MB)}
_output_limit_bytes = {repr(_STDIN_OUTPUT_CAPTURE_LIMIT_BYTES)}
_stderr_limit_bytes = {repr(_STDIN_STDERR_CAPTURE_LIMIT_BYTES)}
_cleanup_paths = []


def _write_text_temp(prefix, value):
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as handle:
        handle.write(str(value))
    path = Path(name)
    _cleanup_paths.append(path)
    return path


if _input_file is None:
    _input_file = _write_text_temp("dgm_stdin_", _raw_input)
if _expected_file is None:
    _expected_file = _write_text_temp("dgm_expected_", _raw_expected)


def _new_temp_path(prefix):
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=".txt")
    os.close(fd)
    path = Path(name)
    _cleanup_paths.append(path)
    return path


def _cleanup():
    for path in _cleanup_paths:
        try:
            Path(path).unlink()
        except OSError:
            pass


def _emit(payload):
    print(json.dumps(payload))
    _cleanup()
    sys.exit(0)


def _limit_child_process_resources():
    try:
        import resource
    except ImportError:
        return
    limit_bytes = _memory_limit_mb * 1024 * 1024
    for limit_name in ("RLIMIT_AS", "RLIMIT_DATA"):
        limit_kind = getattr(resource, limit_name, None)
        if limit_kind is None:
            continue
        try:
            _soft, hard = resource.getrlimit(limit_kind)
            if hard in (-1, resource.RLIM_INFINITY):
                hard = limit_bytes
            resource.setrlimit(limit_kind, (min(limit_bytes, hard), hard))
        except (OSError, ValueError):
            continue


def _limit_child_process_by_pid(pid):
    try:
        import resource
    except ImportError:
        return
    prlimit = getattr(resource, "prlimit", None)
    if prlimit is None:
        return
    limit_bytes = _memory_limit_mb * 1024 * 1024
    for limit_name in ("RLIMIT_AS", "RLIMIT_DATA"):
        limit_kind = getattr(resource, limit_name, None)
        if limit_kind is None:
            continue
        try:
            _soft, hard = prlimit(pid, limit_kind)
            if hard in (-1, resource.RLIM_INFINITY):
                hard = limit_bytes
            prlimit(pid, limit_kind, (min(limit_bytes, hard), hard))
        except (OSError, ValueError, PermissionError):
            continue


def _read_child_memory_bytes(pid):
    status_path = Path("/proc") / str(pid) / "status"
    try:
        text = status_path.read_text(errors="replace")
    except OSError:
        return None

    values = {{}}
    for line in text.splitlines():
        if line.startswith(("VmRSS:", "VmSize:")):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    values[parts[0].rstrip(":")] = int(parts[1]) * 1024
                except ValueError:
                    pass
    return values or None


def _truncate(value, length=600):
    value = str(value)
    if len(value) <= length:
        return value
    return value[: length // 2] + "...(truncated)..." + value[-length // 2 :]


def _read_text_limited(path, limit_bytes):
    path = Path(path)
    with path.open("rb") as handle:
        data = handle.read(limit_bytes + 1)
    text = data[:limit_bytes].decode("utf-8", errors="replace")
    if len(data) > limit_bytes or path.stat().st_size > limit_bytes:
        return text + "...(truncated)..."
    return text


def _expected_preview():
    return _truncate(_read_text_limited(_expected_file, _output_limit_bytes).strip())


def _stripped_lines(value):
    value = str(value).strip()
    return [line.strip() for line in value.split("\\n")]


def _decimal_tokens(line):
    try:
        return [Decimal(part) for part in line.split()]
    except Exception:
        return None


def _compare_stdout(actual, expected):
    actual_lines = _stripped_lines(actual)
    expected_lines = _stripped_lines(expected)
    if len(actual_lines) != len(expected_lines):
        return (
            False,
            f"Wrong answer: mismatched output length "
            f"{{len(actual_lines)}} != {{len(expected_lines)}}",
        )

    for line_index, (actual_line, expected_line) in enumerate(
        zip(actual_lines, expected_lines)
    ):
        if actual_line == expected_line:
            continue

        actual_numbers = _decimal_tokens(actual_line)
        expected_numbers = _decimal_tokens(expected_line)
        if (
            actual_numbers is not None
            and expected_numbers is not None
            and actual_numbers == expected_numbers
        ):
            continue

        return (
            False,
            f"Wrong answer at line {{line_index}}: "
            f"{{_truncate(actual_line)!r}} != {{_truncate(expected_line)!r}}",
        )

    return True, None


_stdout_path = _new_temp_path("dgm_stdout_")
_stderr_path = _new_temp_path("dgm_stderr_")
_run_error = None

with Path(_input_file).open("rb") as _stdin_handle, _stdout_path.open("wb") as _stdout_handle, _stderr_path.open("wb") as _stderr_handle:
    _proc = subprocess.Popen(
        [sys.executable, _solution_file],
        stdin=_stdin_handle,
        stdout=_stdout_handle,
        stderr=_stderr_handle,
        preexec_fn=_limit_child_process_resources,
    )
    _limit_child_process_by_pid(_proc.pid)
    _deadline = time.monotonic() + _timeout
    _memory_limit_bytes = _memory_limit_mb * 1024 * 1024
    while _proc.poll() is None:
        try:
            _stdout_size = _stdout_path.stat().st_size
        except OSError:
            _stdout_size = 0
        try:
            _stderr_size = _stderr_path.stat().st_size
        except OSError:
            _stderr_size = 0

        if _stdout_size > _output_limit_bytes:
            _run_error = f"Output too large: {{_stdout_size}} bytes > {{_output_limit_bytes}}"
            _proc.kill()
            break
        if _stderr_size > _stderr_limit_bytes:
            _run_error = f"Stderr too large: {{_stderr_size}} bytes > {{_stderr_limit_bytes}}"
            _proc.kill()
            break
        _child_memory = _read_child_memory_bytes(_proc.pid)
        if _child_memory is not None:
            _child_vmsize = _child_memory.get("VmSize", 0)
            _child_rss = _child_memory.get("VmRSS", 0)
            if _child_vmsize > _memory_limit_bytes or _child_rss > _memory_limit_bytes:
                _run_error = (
                    "Memory limit exceeded: "
                    f"VmSize={{_child_vmsize}} bytes, "
                    f"VmRSS={{_child_rss}} bytes, "
                    f"limit={{_memory_limit_bytes}} bytes"
                )
                _proc.kill()
                break
        if time.monotonic() > _deadline:
            _run_error = f"Timeout after {{_timeout}}s"
            _proc.kill()
            break
        time.sleep(0.05)
    _proc.wait()

if _run_error is not None:
    _emit({{
        "success": False,
        "actual_output": _truncate(_read_text_limited(_stdout_path, _output_limit_bytes).strip()),
        "expected_output": _expected_preview(),
        "error": _run_error,
        "exit_code": _proc.returncode,
    }})

_stdout_size = _stdout_path.stat().st_size
_stderr_size = _stderr_path.stat().st_size
if _stdout_size > _output_limit_bytes:
    _emit({{
        "success": False,
        "actual_output": _truncate(_read_text_limited(_stdout_path, _output_limit_bytes).strip()),
        "expected_output": _expected_preview(),
        "error": f"Output too large: {{_stdout_size}} bytes > {{_output_limit_bytes}}",
        "exit_code": _proc.returncode,
    }})
if _stderr_size > _stderr_limit_bytes:
    _emit({{
        "success": False,
        "actual_output": _truncate(_read_text_limited(_stdout_path, _output_limit_bytes).strip()),
        "expected_output": _expected_preview(),
        "error": f"Stderr too large: {{_stderr_size}} bytes > {{_stderr_limit_bytes}}",
        "exit_code": _proc.returncode,
    }})

_stdout = _read_text_limited(_stdout_path, _output_limit_bytes)
_stderr = _read_text_limited(_stderr_path, _stderr_limit_bytes)
_raw_expected = _read_text_limited(_expected_file, _output_limit_bytes)

if _proc.returncode != 0:
    _emit({{
        "success": False,
        "actual_output": _truncate(_stdout.strip()),
        "expected_output": _expected_preview(),
        "error": "RuntimeError: " + _truncate(_stderr.strip() or f"exit code {{_proc.returncode}}"),
        "exit_code": _proc.returncode,
    }})

_success, _error = _compare_stdout(_stdout, _raw_expected)
_emit({{
    "success": _success,
    "actual_output": _truncate(_stdout.strip()),
    "expected_output": _expected_preview(),
    "error": _error,
    "exit_code": _proc.returncode,
}})
"""

    async def _run_test_case(
        self,
        solution: str,
        test_case: Dict[str, Any],
        benchmark: BenchmarkTask
    ) -> Dict[str, Any]:
        """Run a single test case with multiple inputs/outputs."""
        is_stdin_case = _is_stdin_test_case(test_case)
        function_name = test_case.get('function_name', 'solve')

        # --- Security: validate function_name before embedding in code ---
        if not is_stdin_case and not _is_valid_identifier(function_name):
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

        guard_error = _static_resource_guard_error(solution, test_case, benchmark)
        if guard_error is not None:
            logger.warning("%s in benchmark %s", guard_error, benchmark.name)
            return {
                'success': False,
                'individual_results': [{
                    'success': False,
                    'actual_output': None,
                    'expected_output': None,
                    'error': guard_error,
                    'input': '<skipped by resource guard>',
                }],
                'passed': 0,
                'total': 1,
                'short_circuited': True,
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

            def _result_payload(short_circuited: bool = False) -> Dict[str, Any]:
                payload = {
                    'success': overall_success,
                    'individual_results': results,
                    'passed': sum(1 for r in results if r.get('success', False)),
                    'total': len(results)
                }
                if short_circuited:
                    payload['short_circuited'] = True
                return payload

            sandbox_working_dir = getattr(
                getattr(self.sandbox_manager, "config", None),
                "working_dir",
                "/home/dgm_agent/workspace",
            )

            for i, (input_val, expected_val) in enumerate(zip(inputs, expected_outputs)):
                raw_input = str(input_val)
                raw_expected = str(expected_val)
                sandbox_solution_file = str(Path(sandbox_working_dir) / solution_path.name)

                if is_stdin_case:
                    input_path = workspace_path / f"stdin_{i}.txt"
                    expected_path = workspace_path / f"expected_{i}.txt"
                    input_path.write_text(raw_input)
                    expected_path.write_text(raw_expected)
                    sandbox_input_file = str(Path(sandbox_working_dir) / input_path.name)
                    sandbox_expected_file = str(Path(sandbox_working_dir) / expected_path.name)
                    test_code = self._build_stdin_test_script(
                        sandbox_solution_file if use_sandbox else solution_file,
                        raw_input,
                        raw_expected,
                        i,
                        benchmark.timeout,
                        input_file=sandbox_input_file if use_sandbox else str(input_path),
                        expected_file=(
                            sandbox_expected_file if use_sandbox else str(expected_path)
                        ),
                    )
                    subprocess_timeout = benchmark.timeout + 2
                else:
                    test_code = self._build_test_script(
                        sandbox_solution_file if use_sandbox else solution_file,
                        function_name,
                        raw_input,
                        raw_expected,
                        i
                    )
                    subprocess_timeout = benchmark.timeout
                test_script_path = workspace_path / f"test_case_{i}.py"
                test_script_path.write_text(test_code)

                if use_sandbox:
                    sandbox_result = await self.sandbox_manager.execute_in_sandbox(
                        command=f"{shlex.quote('python')} {shlex.quote(test_script_path.name)}",
                        workspace_path=str(workspace_path),
                        timeout=subprocess_timeout,
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
                        stderr=asyncio.subprocess.PIPE,
                        preexec_fn=_apply_test_process_resource_limits,
                    )

                    try:
                        stdout, stderr = await asyncio.wait_for(
                            proc.communicate(),
                            timeout=subprocess_timeout
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
                        if benchmark.scoring_method == 'pass_fail':
                            return _result_payload(short_circuited=True)
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
                    if benchmark.scoring_method == 'pass_fail':
                        return _result_payload(short_circuited=True)

            return _result_payload()

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
