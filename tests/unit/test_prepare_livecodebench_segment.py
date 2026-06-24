import base64
import json
import pickle
import zlib
from pathlib import Path

import yaml

from scripts.prepare_livecodebench_segment import (
    LiveCodeBenchSegmentError,
    _build_parser,
    _decode_test_cases,
    _main,
    benchmark_name_for_question,
    prepare_livecodebench_segment,
)


def _encoded_tests(tests: list[dict]) -> str:
    payload = pickle.dumps(json.dumps(tests))
    return base64.b64encode(zlib.compress(payload)).decode("utf-8")


class _GlobalPayload:
    def __reduce__(self):
        return (eval, ("1 + 1",))


def _write_fixture_jsonl(path: Path) -> None:
    problems = [
        {
            "question_title": "Add",
            "question_content": "Read two integers and print their sum.",
            "platform": "atcoder",
            "question_id": "abc001_a",
            "contest_id": "abc001",
            "contest_date": "2025-01-01T00:00:00",
            "starter_code": "",
            "difficulty": "easy",
            "public_test_cases": json.dumps([
                {"input": "1 2\n", "output": "3\n", "testtype": "stdin"},
            ]),
            "private_test_cases": _encoded_tests([
                {"input": "10 20\n", "output": "30\n", "testtype": "stdin"},
                {"input": "-1 1\n", "output": "0\n", "testtype": "stdin"},
            ]),
            "metadata": "{}",
        },
        {
            "question_title": "Multiply",
            "question_content": "Read two integers and print their product.",
            "platform": "atcoder",
            "question_id": "abc001_b",
            "contest_id": "abc001",
            "contest_date": "2025-01-01T00:00:00",
            "starter_code": "",
            "difficulty": "medium",
            "public_test_cases": json.dumps([
                {"input": "2 3\n", "output": "6\n", "testtype": "stdin"},
            ]),
            "private_test_cases": json.dumps([
                {"input": "4 5\n", "output": "20\n", "testtype": "stdin"},
            ]),
            "metadata": "{}",
        },
    ]
    path.write_text(
        "\n".join(json.dumps(problem) for problem in problems) + "\n",
        encoding="utf-8",
    )


def _write_config(tmp_path: Path, jsonl_path: Path) -> Path:
    config = {
        "purpose": "livecodebench_segment",
        "approval_required": True,
        "live_calls_performed": 0,
        "source": {
            "dataset": "livecodebench/code_generation_lite",
            "source_file": "fixture.jsonl",
            "version_label": "fixture",
            "local_jsonl": str(jsonl_path.relative_to(tmp_path)),
        },
        "selection": {
            "segment_id": "fixture_segment",
            "output_dir": "generated/benchmarks",
            "manifest_path": "generated/manifest.json",
            "per_problem_timeout_seconds": 7,
            "question_ids": ["abc001_a", "abc001_b"],
        },
        "gates": {
            "min_problem_count": 2,
            "required_difficulties": ["easy", "medium"],
            "min_total_tests": 4,
            "min_private_tests": 3,
            "require_stdin_only": True,
        },
    }
    config_path = tmp_path / "segment.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return config_path


def test_benchmark_name_for_question_slugifies():
    assert benchmark_name_for_question("ABC-001_A") == "livecodebench_abc_001_a"


def test_prepare_livecodebench_segment_writes_hidden_test_benchmarks(tmp_path):
    jsonl_path = tmp_path / "fixture.jsonl"
    _write_fixture_jsonl(jsonl_path)
    config_path = _write_config(tmp_path, jsonl_path)

    manifest = prepare_livecodebench_segment(
        config_path,
        project_root=tmp_path,
        write=True,
    )

    assert manifest["benchmark_count"] == 2
    assert manifest["public_test_count"] == 2
    assert manifest["private_test_count"] == 3
    assert manifest["total_test_count"] == 5
    assert manifest["benchmark_names"] == [
        "livecodebench_abc001_a",
        "livecodebench_abc001_b",
    ]

    benchmark_path = tmp_path / "generated" / "benchmarks" / "livecodebench_abc001_a.yaml"
    payload = yaml.safe_load(benchmark_path.read_text(encoding="utf-8"))
    assert payload["name"] == "livecodebench_abc001_a"
    assert payload["scoring_method"] == "pass_fail"
    assert payload["timeout"] == 7
    assert payload["prompt_test_cases"][0]["inputs"] == ["1 2\n"]
    assert payload["test_cases"][0]["inputs"] == ["1 2\n", "10 20\n", "-1 1\n"]
    assert payload["metadata"]["private_test_count"] == 2


def test_decode_test_cases_rejects_pickle_globals():
    payload = pickle.dumps(_GlobalPayload())
    encoded = base64.b64encode(zlib.compress(payload)).decode("utf-8")

    try:
        _decode_test_cases(encoded, "private")
    except LiveCodeBenchSegmentError as exc:
        assert "Could not decode private test cases" in str(exc)
    else:
        raise AssertionError("expected encoded pickle global to be rejected")


def test_prepare_livecodebench_segment_check_only_does_not_write(tmp_path):
    jsonl_path = tmp_path / "fixture.jsonl"
    _write_fixture_jsonl(jsonl_path)
    config_path = _write_config(tmp_path, jsonl_path)

    manifest = prepare_livecodebench_segment(
        config_path,
        project_root=tmp_path,
        write=False,
    )

    assert manifest["status"] == "ok"
    assert not (tmp_path / "generated").exists()


def test_prepare_livecodebench_segment_cli_json(tmp_path, capsys):
    jsonl_path = tmp_path / "fixture.jsonl"
    _write_fixture_jsonl(jsonl_path)
    config_path = _write_config(tmp_path, jsonl_path)

    args = _build_parser().parse_args([
        "--config",
        str(config_path),
        "--project-root",
        str(tmp_path),
        "--check-only",
        "--json",
    ])

    exit_code = _main(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"benchmark_count": 2' in captured.out
    assert '"live_calls_performed": 0' in captured.out
