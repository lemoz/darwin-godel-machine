# Qwen3 Coder self-mod LiveCodeBench canary - 2026-06-29

This two-generation cloud canary tested the new reusable Qwen3 Coder recovery
config from commit `b4e4a5584f0484d174ed172b88d27733a7625b70`.

The run proved that the Qwen/OpenRouter path is mechanically stable on the
cloud VM lane, but it did not produce an improvement. The dominant failure mode
was not timeout, empty response, or hidden-reasoning exhaustion. It was malformed
tool write content: the model repeatedly wrote list-shaped fragments instead of
complete Python files, and its changed self-modification patch was rejected by
validation with a syntax error.

## Launch

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/run_live_eval_on_cloud_vm.py \
  --project doittogether-prod \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --run-id lcb12-qwen3-coder-canary-20260629-1 \
  --repo-url https://github.com/lemoz/darwin-godel-machine.git \
  --commit b4e4a5584f0484d174ed172b88d27733a7625b70 \
  --config config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml \
  --generations 2 \
  --secret OPENROUTER_API_KEY=openrouter-api-key \
  --artifact-dir .dgm-cloud-runs/lcb12-qwen3-coder-canary-20260629-1/artifacts \
  --startup-script-path .dgm-cloud-runs/lcb12-qwen3-coder-canary-20260629-1/startup.sh \
  --output .dgm-cloud-runs/lcb12-qwen3-coder-canary-20260629-1/plan.json \
  --gcs-artifact-uri gs://dgm-live-runs-doittogether-prod/lcb12-qwen3-coder-canary-20260629-1 \
  --fm-provider openrouter \
  --model qwen/qwen3-coder \
  --input-price-per-mtok 0.22 \
  --output-price-per-mtok 1.80 \
  --execute
```

Cloud VM:

- Project: `doittogether-prod`
- Zone: `us-central1-a`
- VM: `dgm-lcb12-qwen3-coder-canary-20260629-1`
- Config: `config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml`
- GCS artifacts: `gs://dgm-live-runs-doittogether-prod/lcb12-qwen3-coder-canary-20260629-1/`

The VM was deleted at the end of the run. A follow-up instance-list check for
`dgm-lcb12-qwen3-coder-canary-20260629-1` returned no rows.

## Preflight

All required preflights passed on the VM:

- LiveCodeBench segment generation: 12 benchmarks, 512 tests, 480 private tests
- Docker sandbox smoke: passed
- Cost gate: `requests<=1848`, `input_tokens<=92400000`,
  `output_tokens<=7569408`, `total=$33.9529`, under the `$45` cap

OpenRouter pricing was checked on 2026-06-29 through
`https://openrouter.ai/api/v1/models`: `qwen/qwen3-coder` at `$0.22/MTok`
prompt and `$1.80/MTok` completion.

## Result

- Exit code: `0`
- Runtime: `581.592s` / `0.158h`
- Generations requested/reported: `2`
- Base/top agent: `dc4d7fee-3cd1-4784-983b-5507023540f2`
- Base/top score: `0.1666666667` = `2/12`
- Archive total agents: `3`
- Valid agents: `1`
- Successful improvements: `0`
- Estimated provider cost: `$0.159939`
- OpenRouter posts: `83`
- Provider timeouts: `0`
- Empty responses: `0`
- Provider API errors: `0`
- Tokens: `469078` prompt, `31523` completion, `500601` total

Base solved:

- `livecodebench_abc387_b`
- `livecodebench_abc388_b`

Base zero-scored:

- `livecodebench_abc387_c`
- `livecodebench_abc388_c`
- `livecodebench_abc388_d`
- `livecodebench_abc388_e`
- `livecodebench_abc389_a`
- `livecodebench_abc389_d`
- `livecodebench_abc389_e`
- `livecodebench_abc390_b`
- `livecodebench_abc390_d`
- `livecodebench_abc390_e`

## Mutation Evidence

Mutation summary:

- `noop`: `1`
- `changed`: `1`
- changed child: `097cd68c-13c2-4b44-9f73-555eb3700e2e`
- changed files: `agent.py`
- valid improved children: `0`

The no-op child had no changed code files and was archived invalid with
`mutation_status=noop`.

The changed child produced a real patch, but validation rejected it:

```text
Modified agent validation failed: ['Syntax error: unterminated string literal (detected at line 499) (<unknown>, line 499)']
```

The patch evidence shows the same list-fragment corruption seen during benchmark
solution writes: the model replaced the beginning of `_build_system_message` with
a list-shaped string fragment instead of valid Python source. The validator
prevented this child from being evaluated.

## Interpretation

This run answers the immediate model question:

- Qwen3 Coder is stable enough at the provider layer for this lane.
- It is not ready to scale to a 12-generation DGM run under the current harness.
- The next blocker is tool-output quality and mutation safety, not VM isolation
  or OpenRouter timeout behavior.

Recommended next step: add a write-content sanity gate for Python writes
(`solution.py` and agent source files) that rejects obvious list-fragment or
non-Python content and feeds a precise corrective error back to the model, then
rerun a two-generation canary before any 12-generation spend.

## Artifacts

Committed compact artifacts:

- `plan.json`
- `preflight_commands.txt`
- `exit_code`
- `scorecard.json`
- `telemetry.json`
- `archive.tar.gz`

Full logs remain in the local `.dgm-cloud-runs/.../artifacts/` directory and in
the GCS artifact prefix.
