# LiveCodeBench content-lines canary plan

Run ID: `lcb12-content-lines-canary-20260629-1`

Date: 2026-06-29

Purpose: validate the edit-tool `content_lines` fallback before spending on a
larger DGM LiveCodeBench run.

## Background

The previous Qwen overwrite-guard run completed on a cloud VM with stable
OpenRouter transport, but it did not improve beyond the 2/12 baseline. Its
dominant blocker was malformed `solution.py` write payloads: the model
repeatedly passed serialized/list fragments instead of raw Python source. The
guard protected files, but the model did not recover from the corrective error.

This canary should run after the edit tool accepts `content_lines` as an
alternative write/append payload and after the benchmark prompt explicitly tells
the model to retry rejected Python writes with `content_lines`.

## Default Path

- Benchmark: LiveCodeBench 12-problem segment.
- Runner: disposable cloud VM with artifact sync and teardown.
- Config: Qwen self-modification recovery config, or the nearest successor that
  keeps the same benchmark segment.
- Model: OpenRouter `qwen/qwen3-coder` for direct comparison with the previous
  run.
- Generations: 2 for the first canary; scale only after write reliability moves.

## Success Gates

- VM exits cleanly and is torn down after artifact sync.
- Provider telemetry still shows zero transport timeouts or empty responses.
- `solution.py` malformed serialized/list-fragment write rejections fall
  materially below the previous 90-count run.
- At least one generated child is mutation-proven as changed.
- Benchmark scoring reaches the baseline 2/12 or better.

## Scale Decision

If the canary still shows repeated malformed write payloads, do not scale Qwen
generations. Move to a model-matrix canary for Chinese open-source coding models
with stronger tool-call fidelity.

If malformed writes drop and the changed child is valid, run a 6-generation
cloud segment next. Only move to 12 generations after two consecutive canaries
show valid changed children and no transport instability.
