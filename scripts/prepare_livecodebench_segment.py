#!/usr/bin/env python3
"""Prepare a bounded LiveCodeBench-lite segment as DGM benchmark YAML files."""

from __future__ import annotations

import argparse
import base64
import io
import json
import pickle
import re
import sys
import urllib.request
import zlib
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Iterator

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "livecodebench_segment.yaml"


class LiveCodeBenchSegmentError(RuntimeError):
    """Raised when the LiveCodeBench segment cannot be prepared safely."""


class _RestrictedUnpickler(pickle.Unpickler):
    """Unpickle built-in container payloads without resolving arbitrary classes."""

    def find_class(self, module: str, name: str) -> Any:
        raise pickle.UnpicklingError(f"Unsupported pickle global: {module}.{name}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveCodeBenchSegmentError(message)


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise LiveCodeBenchSegmentError(f"Missing config: {path}") from exc
    except yaml.YAMLError as exc:
        raise LiveCodeBenchSegmentError(f"Invalid YAML in {path}: {exc}") from exc
    _require(isinstance(data, dict), f"Config must be a mapping: {path}")
    return data


def _project_path(path_text: str | Path, project_root: Path) -> Path:
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = project_root / path
    try:
        relative_path = path.resolve().relative_to(project_root.resolve())
    except ValueError as exc:
        raise LiveCodeBenchSegmentError(f"{path_text} must stay inside the project root") from exc
    return project_root.resolve() / relative_path


def _project_relative(path: Path, project_root: Path) -> str:
    return str(path.resolve().relative_to(project_root.resolve()))


def benchmark_name_for_question(question_id: str) -> str:
    """Return the DGM benchmark name for one LiveCodeBench question id."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", question_id).strip("_").lower()
    _require(bool(slug), "question_id must contain at least one alphanumeric character")
    return f"livecodebench_{slug}"


def expected_benchmark_names(config: dict[str, Any]) -> list[str]:
    """Return benchmark names implied by a segment config without network access."""
    selection = config.get("selection", {})
    question_ids = selection.get("question_ids", [])
    _require(isinstance(question_ids, list) and question_ids, "selection.question_ids must be non-empty")
    return [benchmark_name_for_question(str(question_id)) for question_id in question_ids]


def _source_url(source: dict[str, Any]) -> str:
    if source.get("url"):
        return str(source["url"])
    dataset = str(source.get("dataset", "livecodebench/code_generation_lite"))
    source_file = str(source.get("source_file", "test6.jsonl"))
    return f"https://huggingface.co/datasets/{dataset}/resolve/main/{source_file}"


def _iter_jsonl(source: dict[str, Any], project_root: Path) -> Iterator[dict[str, Any]]:
    local_jsonl = source.get("local_jsonl")
    if local_jsonl:
        path = _project_path(str(local_jsonl), project_root)
        _require(path.is_file(), f"Missing local JSONL source: {_project_relative(path, project_root)}")
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)
        return

    request = urllib.request.Request(
        _source_url(source),
        headers={"User-Agent": "darwin-godel-machine-livecodebench-segment/1.0"},
    )
    with urllib.request.urlopen(request, timeout=int(source.get("download_timeout", 120))) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if line:
                yield json.loads(line)


def _decode_test_cases(value: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(value, list):
        decoded = value
    else:
        _require(isinstance(value, str), f"{label} test cases must be JSON or encoded string")
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            try:
                compressed = base64.b64decode(value.encode("utf-8"))
                pickled_payload = zlib.decompress(compressed)
                payload = _RestrictedUnpickler(io.BytesIO(pickled_payload)).load()
                if isinstance(payload, bytes):
                    payload = payload.decode("utf-8")
                decoded = json.loads(payload)
            except Exception as exc:
                raise LiveCodeBenchSegmentError(
                    f"Could not decode {label} test cases"
                ) from exc

    _require(isinstance(decoded, list), f"{label} test cases must decode to a list")
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(decoded):
        _require(isinstance(raw, dict), f"{label} test case {index} must be a mapping")
        testtype = str(raw.get("testtype", "")).lower()
        _require(testtype == "stdin", f"{label} test case {index} must use stdin")
        _require("input" in raw and "output" in raw, f"{label} test case {index} missing input/output")
        normalized.append(
            {
                "input": str(raw["input"]),
                "output": str(raw["output"]),
                "testtype": "stdin",
            }
        )
    return normalized


def _task_prompt(problem: dict[str, Any], source: dict[str, Any]) -> str:
    dataset = source.get("dataset", "livecodebench/code_generation_lite")
    version = source.get("version_label", source.get("source_file", "unknown"))
    return (
        "You are solving a LiveCodeBench code-generation problem. "
        "Write a complete Python program that reads from stdin and writes to stdout.\n\n"
        f"Source: {dataset} ({version})\n"
        f"Platform: {problem.get('platform')}\n"
        f"Question ID: {problem.get('question_id')}\n"
        f"Difficulty: {problem.get('difficulty')}\n"
        f"Contest date: {problem.get('contest_date')}\n\n"
        f"### Question\n{problem.get('question_content', '').strip()}\n\n"
        "### Format\n"
        "Return only Python code. The program must read the official inputs from "
        "stdin and print the official outputs to stdout."
    )


def _benchmark_yaml(
    *,
    problem: dict[str, Any],
    public_tests: list[dict[str, Any]],
    private_tests: list[dict[str, Any]],
    source: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    question_id = str(problem["question_id"])
    all_tests = public_tests + private_tests
    return {
        "name": benchmark_name_for_question(question_id),
        "description": (
            f"LiveCodeBench {source.get('version_label', source.get('source_file'))} "
            f"{problem.get('platform')} {question_id}: {problem.get('question_title')}"
        ),
        "task_prompt": _task_prompt(problem, source),
        "prompt_test_cases": [
            {
                "testtype": "stdin",
                "inputs": [test["input"] for test in public_tests],
                "expected_outputs": [test["output"] for test in public_tests],
            }
        ],
        "test_cases": [
            {
                "testtype": "stdin",
                "inputs": [test["input"] for test in all_tests],
                "expected_outputs": [test["output"] for test in all_tests],
            }
        ],
        "timeout": timeout,
        "scoring_method": "pass_fail",
        "metadata": {
            "source": source.get("dataset", "livecodebench/code_generation_lite"),
            "source_file": source.get("source_file", "test6.jsonl"),
            "version_label": source.get("version_label", "unknown"),
            "dataset_url": source.get(
                "dataset_url",
                "https://huggingface.co/datasets/livecodebench/code_generation_lite",
            ),
            "question_id": question_id,
            "question_title": problem.get("question_title"),
            "platform": problem.get("platform"),
            "difficulty": problem.get("difficulty"),
            "contest_date": problem.get("contest_date"),
            "public_test_count": len(public_tests),
            "private_test_count": len(private_tests),
            "total_test_count": len(all_tests),
            "test_policy": "public_examples_prompt_private_tests_scored",
        },
    }


def _select_problems(config: dict[str, Any], project_root: Path) -> list[dict[str, Any]]:
    source = config.get("source", {})
    selection = config.get("selection", {})
    _require(isinstance(source, dict), "source must be a mapping")
    _require(isinstance(selection, dict), "selection must be a mapping")

    question_ids = [str(item) for item in selection.get("question_ids", [])]
    _require(question_ids, "selection.question_ids must be non-empty")
    requested = set(question_ids)
    found: dict[str, dict[str, Any]] = {}

    for problem in _iter_jsonl(source, project_root):
        question_id = str(problem.get("question_id", ""))
        if question_id not in requested or question_id in found:
            continue
        public_tests = _decode_test_cases(problem.get("public_test_cases"), "public")
        private_tests = _decode_test_cases(problem.get("private_test_cases"), "private")
        found[question_id] = {
            "problem": problem,
            "public_tests": public_tests,
            "private_tests": private_tests,
        }
        if len(found) == len(requested):
            break

    missing = [question_id for question_id in question_ids if question_id not in found]
    _require(not missing, f"Source did not contain requested question_ids: {missing}")
    return [found[question_id] for question_id in question_ids]


def prepare_livecodebench_segment(
    config_path: Path = DEFAULT_CONFIG,
    *,
    project_root: Path = PROJECT_ROOT,
    write: bool = True,
) -> dict[str, Any]:
    """Prepare benchmark YAMLs and return a manifest dictionary."""
    project_root = project_root.resolve()
    config_path = config_path if config_path.is_absolute() else project_root / config_path
    config = _load_yaml(config_path)
    _require(
        config.get("purpose") == "livecodebench_segment",
        "Segment config must declare livecodebench_segment purpose",
    )
    _require(config.get("approval_required") is True, "Segment config must require approval")
    _require(config.get("live_calls_performed") == 0, "Segment preparation must perform zero live calls")

    source = config.get("source", {})
    selection = config.get("selection", {})
    gates = config.get("gates", {})
    _require(isinstance(source, dict), "source must be a mapping")
    _require(isinstance(selection, dict), "selection must be a mapping")
    _require(isinstance(gates, dict), "gates must be a mapping")

    output_dir = _project_path(
        selection.get("output_dir", ".dgm-live-runs/livecodebench-segment/benchmarks"),
        project_root,
    )
    manifest_path = _project_path(
        selection.get("manifest_path", ".dgm-live-runs/livecodebench-segment/manifest.json"),
        project_root,
    )
    timeout = int(selection.get("per_problem_timeout_seconds", 10))
    _require(timeout > 0, "selection.per_problem_timeout_seconds must be positive")

    selected = _select_problems(config, project_root)
    benchmark_payloads = [
        _benchmark_yaml(
            problem=item["problem"],
            public_tests=item["public_tests"],
            private_tests=item["private_tests"],
            source=source,
            timeout=timeout,
        )
        for item in selected
    ]

    difficulty_counts = Counter(
        str(item["problem"].get("difficulty", "unknown")) for item in selected
    )
    public_test_count = sum(len(item["public_tests"]) for item in selected)
    private_test_count = sum(len(item["private_tests"]) for item in selected)
    total_test_count = public_test_count + private_test_count
    benchmark_names = [payload["name"] for payload in benchmark_payloads]

    min_problem_count = int(gates.get("min_problem_count", 1))
    min_total_tests = int(gates.get("min_total_tests", 1))
    min_private_tests = int(gates.get("min_private_tests", 1))
    required_difficulties = {str(item) for item in gates.get("required_difficulties", [])}
    _require(len(benchmark_payloads) >= min_problem_count, "Segment has too few problems")
    _require(total_test_count >= min_total_tests, "Segment has too few total tests")
    _require(private_test_count >= min_private_tests, "Segment has too few private tests")
    _require(
        required_difficulties.issubset(difficulty_counts),
        f"Segment missing required difficulties: {sorted(required_difficulties - set(difficulty_counts))}",
    )

    if write:
        output_dir.mkdir(parents=True, exist_ok=True)
        for old_file in output_dir.glob("*.yaml"):
            old_file.unlink()
        for payload in benchmark_payloads:
            path = output_dir / f"{payload['name']}.yaml"
            path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    manifest = {
        "name": "livecodebench_segment",
        "status": "ok",
        "config": _project_relative(config_path, project_root),
        "approval_required": True,
        "live_calls_performed": 0,
        "source": {
            "dataset": source.get("dataset", "livecodebench/code_generation_lite"),
            "source_file": source.get("source_file", "test6.jsonl"),
            "version_label": source.get("version_label", "unknown"),
            "url": _source_url(source),
        },
        "segment_id": selection.get("segment_id"),
        "output_dir": _project_relative(output_dir, project_root),
        "manifest_path": _project_relative(manifest_path, project_root),
        "benchmark_count": len(benchmark_payloads),
        "benchmark_names": benchmark_names,
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "public_test_count": public_test_count,
        "private_test_count": private_test_count,
        "total_test_count": total_test_count,
        "per_problem_timeout_seconds": timeout,
        "test_policy": "public examples are prompt-visible; public plus private tests are scored",
        "problems": [
            {
                "benchmark": payload["name"],
                "question_id": payload["metadata"]["question_id"],
                "question_title": payload["metadata"]["question_title"],
                "platform": payload["metadata"]["platform"],
                "difficulty": payload["metadata"]["difficulty"],
                "contest_date": payload["metadata"]["contest_date"],
                "public_test_count": payload["metadata"]["public_test_count"],
                "private_test_count": payload["metadata"]["private_test_count"],
                "total_test_count": payload["metadata"]["total_test_count"],
            }
            for payload in benchmark_payloads
        ],
    }

    if write:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return manifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Decode and validate the segment without writing benchmark YAML files.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def _main(args: argparse.Namespace) -> int:
    try:
        manifest = prepare_livecodebench_segment(
            Path(args.config),
            project_root=Path(args.project_root),
            write=not args.check_only,
        )
    except LiveCodeBenchSegmentError as exc:
        if args.json:
            print(json.dumps({"status": "failed", "error": str(exc)}, indent=2))
        else:
            print(f"[fail] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        mode = "check-only" if args.check_only else "write"
        print(
            "[ok] livecodebench_segment "
            f"mode={mode} "
            f"benchmarks={manifest['benchmark_count']} "
            f"tests={manifest['total_test_count']} "
            f"private_tests={manifest['private_test_count']} "
            f"manifest={manifest['manifest_path']}"
        )
    return 0


def main() -> int:
    return _main(_build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
