# Benchmark edit-repair canary - 2026-06-30

Run ID: `lcb12-editrepair-20260630-1`

This two-generation cloud canary tested commit `a2515fd`, which added benchmark
edit-repair nudges after malformed `solution.py` writes and tightened the
self-modification prompt target contract.

The run proves the cloud VM lane, mutation proof, child validation, and full
LiveCodeBench child evaluation are working. It does not prove benchmark
improvement.

## Launch

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/run_live_eval_on_cloud_vm.py \
  --project doittogether-prod \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --run-id lcb12-editrepair-20260630-1 \
  --repo-url https://github.com/lemoz/darwin-godel-machine.git \
  --commit a2515fd \
  --config config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml \
  --generations 2 \
  --secret OPENROUTER_API_KEY=openrouter-api-key \
  --artifact-dir .dgm-cloud-runs/lcb12-editrepair-20260630-1/artifacts \
  --startup-script-path .dgm-cloud-runs/lcb12-editrepair-20260630-1/startup.sh \
  --output .dgm-cloud-runs/lcb12-editrepair-20260630-1/plan.json \
  --gcs-artifact-uri gs://dgm-live-runs-doittogether-prod/lcb12-editrepair-20260630-1 \
  --fm-provider openrouter \
  --model qwen/qwen3-coder \
  --input-price-per-mtok 0.22 \
  --output-price-per-mtok 1.80 \
  --execute
```

Cloud VM:

- Project: `doittogether-prod`
- Zone: `us-central1-a`
- VM: `dgm-lcb12-editrepair-20260630-1`
- Machine: `n2-standard-8`
- Config: `config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml`
- Model/provider: `qwen/qwen3-coder` via OpenRouter
- GCS artifacts: `gs://dgm-live-runs-doittogether-prod/lcb12-editrepair-20260630-1/`

The VM was deleted successfully at the end of the run.

## Preflight

All required VM preflights passed:

- LiveCodeBench segment generation: 12 benchmarks, 512 tests, 480 private tests
- Docker sandbox smoke: passed
- Cost gate: `requests<=1848`, `input_tokens<=92400000`,
  `output_tokens<=7569408`, `total=$33.9529`, under the `$45` cap

## Result

- Exit code: `0`
- Runtime: `1551.634s` observed, `0.4278h` reported
- Generations requested/reported: `2`
- Base/top agent: `01620557-5ca3-4e6c-a6e7-7f5dbe117042`
- Base/top score: `0.667` = `8/12`
- Valid changed child: `f0b5a035-f1b6-4f2f-ba5c-5b3cfb583b82`
- Changed child score: `0.417` = `5/12`
- Invalid changed child: `b71bca2b-2ab8-45d2-853d-3f578a468c70`
- Successful improvements: `0`
- Best average delta: `-0.250`
- Estimated provider cost: `$0.281577`
- OpenRouter posts: `138`
- Provider timeouts/API errors/empty responses: `0`
- Tokens: `799547` prompt, `58709` completion, `858256` total

Parent-child score movement:

- Regressed `livecodebench_abc387_b`: `1 -> 0`
- Regressed `livecodebench_abc388_e`: `1 -> 0`
- Regressed `livecodebench_abc389_d`: `1 -> 0`
- No benchmark improved.

## Mutation Evidence

Mutation summary:

- `changed`: `2`
- `noop`: `0`
- invalid changed child: `b71bca2b-2ab8-45d2-853d-3f578a468c70`
- valid changed child: `f0b5a035-f1b6-4f2f-ba5c-5b3cfb583b82`

Generation 1 made a real source edit but failed child validation with
`'await' outside async function`.

Generation 2 made a real source edit, loaded successfully, and completed the
12-benchmark LiveCodeBench evaluation. The child was valid but regressed.

## Live Findings

The run exposed three harness issues:

- The benchmark edit-repair nudge caught edit-tool errors like
  `content_lines parameter must contain only strings`, but missed ToolRegistry
  validation errors such as `Parameter 'content_lines' must be an array, got str`
  and `Unknown parameter ... Valid parameters`.
- Several benchmark turns spent one or more steps emitting XML-like
  `<tool_call>` text after `finish_reason=length` instead of making a real tool
  call.
- Five benchmark steps were too tight when a problem needed one malformed edit
  repair plus testing plus finalization. Some tasks used the final step for
  extra tests or risky rewrites instead of finalizing a working `solution.py`.

## Follow-up Patch

The next local patch after this run:

- Broadened edit-repair matching for ToolRegistry parameter errors.
- Strengthened the length-truncation nudge to reject pseudo-tool-call text.
- Added benchmark instructions to finalize after provided examples pass and to
  avoid risky final-step rewrites.
- Raised the Qwen recovery config's benchmark step cap from `5` to `7` and its
  worst-case cost gate from `$45` to `$60`.

## Artifacts

Committed compact artifacts:

- `plan.json`
- `preflight_commands.txt`
- `exit_code`
- `scorecard.json`
- `telemetry.json`
- `archive.tar.gz`

Full logs remain in `.dgm-cloud-runs/lcb12-editrepair-20260630-1/artifacts/`
and in the GCS artifact prefix.
