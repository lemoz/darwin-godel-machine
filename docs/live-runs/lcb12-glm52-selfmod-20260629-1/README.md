# GLM 5.2 self-mod recovery LiveCodeBench run - 2026-06-29

This run tested the follow-up to `lcb12-noop12-20260629-1`: keep benchmark
solving bounded at five turns, give self-modification twelve turns, and switch
from Kimi to `z-ai/glm-5.2` through OpenRouter.

It proved that the controller can now produce mutation-proven child agents on a
real cloud LiveCodeBench run. It did not prove score improvement: all changed
children regressed to `0/12`.

## Launch

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/run_live_eval_on_cloud_vm.py \
  --project doittogether-prod \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --run-id lcb12-glm52-selfmod-20260629-1 \
  --repo-url https://github.com/lemoz/darwin-godel-machine.git \
  --commit 5a2e131a50d0e4e4c94cba1eb8731da1ca3a538f \
  --config config/livecodebench_openrouter_loop12_glm52_selfmod_recovery.yaml \
  --generations 4 \
  --secret OPENROUTER_API_KEY=openrouter-api-key \
  --artifact-dir .dgm-cloud-runs/lcb12-glm52-selfmod-20260629-1/artifacts \
  --startup-script-path .dgm-cloud-runs/lcb12-glm52-selfmod-20260629-1/startup.sh \
  --output .dgm-cloud-runs/lcb12-glm52-selfmod-20260629-1/plan.json \
  --gcs-artifact-uri gs://dgm-live-runs-doittogether-prod/lcb12-glm52-selfmod-20260629-1 \
  --fm-provider openrouter \
  --model z-ai/glm-5.2 \
  --input-price-per-mtok 0.94 \
  --output-price-per-mtok 3.00 \
  --execute
```

Cloud VM:

- Project: `doittogether-prod`
- Zone: `us-central1-a`
- VM: `dgm-lcb12-glm52-selfmod-20260629-1`
- Commit: `5a2e131a50d0e4e4c94cba1eb8731da1ca3a538f`
- Config: `config/livecodebench_openrouter_loop12_glm52_selfmod_recovery.yaml`
- GCS artifacts: `gs://dgm-live-runs-doittogether-prod/lcb12-glm52-selfmod-20260629-1/`

The VM was deleted at the end of the run. A follow-up instance-list check for
`dgm-lcb12-glm52-selfmod-20260629-1` returned no rows.

## Preflight

All required preflights passed on the VM:

- LiveCodeBench segment generation: 12 benchmarks, 512 tests, 480 private tests
- Docker sandbox smoke: passed
- Cost gate: `requests<=696`, `input_tokens<=34800000`,
  `output_tokens<=1425408`, `total=$36.9882`, under the `$45` cap

## Result

- Exit code: `0`
- Runtime: `1348.49s` / `0.371h`
- Generations: `4`
- Base/top agent: `3dc35d58-7faf-43f4-b74c-1cb6aee2853c`
- Base/top score: `0.5833333333333334` = `7/12`
- Total agents in archive: `5`
- Valid agents: `4`
- Child agents created: `3`
- Successful improvements: `0`
- Best child score: `0/12`
- Best average delta: `-0.5833333333333334`

Base solved:

- `livecodebench_abc387_b`
- `livecodebench_abc387_c`
- `livecodebench_abc388_b`
- `livecodebench_abc388_c`
- `livecodebench_abc388_e`
- `livecodebench_abc389_a`
- `livecodebench_abc390_b`

Base zero-scored:

- `livecodebench_abc388_d`
- `livecodebench_abc389_d`
- `livecodebench_abc389_e`
- `livecodebench_abc390_d`
- `livecodebench_abc390_e`

## Mutation Evidence

Mutation summary:

- `changed_count`: `3`
- `noop_count`: `1`
- `unknown_count`: `0`

Loop-order agents:

| Agent | Status | Valid | Score |
| --- | --- | --- | --- |
| `3dc35d58-7faf-43f4-b74c-1cb6aee2853c` | base | yes | `7/12` |
| `6c246d3e-b940-45b9-bf27-a557430a01e7` | noop | no | not evaluated |
| `013d5730-7266-4b93-b064-cfc49e915940` | changed | yes | `0/12` |
| `f4a18953-bdde-46d6-806c-e47747aee4cf` | changed | yes | `0/12` |
| `ff25b06f-63d8-4b49-aef7-efb11c319477` | changed | yes | `0/12` |

All three changed children modified only `agent.py` and produced the same patch:

- `patch_sha256`: `1265b62602df7c5a51b0839c4fbaf389318580affe5a69df686fa0b0ec015163`
- `patch_size_bytes`: `3492`
- `changed_code_files`: `["agent.py"]`

The no-op child had an empty patch:

- `patch_sha256`: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- `patch_size_bytes`: `0`

## Failure Analysis

The controller fix worked mechanically: self-modification received 12 steps, and
three generations produced code changes instead of no-ops.

The mutation quality failed. The repeated patch deleted the
`base_instructions = """..."""` block in `agent.py` without replacing it. The
child still loaded, so validation passed, but benchmark solving then failed and
all changed children scored `0/12`.

Provider behavior was mixed:

- HTTP POSTs: `92`
- Usage events: `89`
- Prompt tokens: `891935`
- Completion tokens: `29443`
- Total tokens: `921378`
- Estimated actual cost: `$0.926748`
- Provider timeouts: `3`
- Empty responses: `9`
- Provider API errors: `0`
- Tracebacks: `0`

GLM 5.2 solved several base tasks, but also showed a model-specific output
pathology on harder tasks: repeated `finish_reason=length` empty responses where
almost the entire 2048-token completion budget was consumed by reasoning tokens.

## Conclusion

This run moves the blocker from mutation production to mutation quality:

- Fixed enough: the run is no longer stuck at mutation-proven no-ops.
- Not fixed: self-modification can produce syntactically loadable but behaviorally
  broken agents, and the current validator does not catch that before full eval.
- Also not fixed: GLM 5.2 needs output/reasoning controls or a different Chinese
  OpenRouter default before it is stable enough for larger runs.

Recommended next fix:

1. Add a deterministic child-agent smoke validation step that instantiates the
   mutated agent and exercises the benchmark solve path before full evaluation.
2. Tighten edit-tool or self-modification validation so a `modify` call without a
   replacement cannot delete critical source blocks silently.
3. Add OpenRouter reasoning/output controls for GLM 5.2 or run a small Qwen/GLM
   comparison canary for self-modification stability.

## Artifacts

Committed compact artifacts:

- `archive.tar.gz`
- `exit_code`
- `plan.json`
- `preflight_commands.txt`
- `scorecard.json`
- `telemetry.json`

Raw GCS artifacts:

- `gs://dgm-live-runs-doittogether-prod/lcb12-glm52-selfmod-20260629-1/archive.tar.gz`
- `gs://dgm-live-runs-doittogether-prod/lcb12-glm52-selfmod-20260629-1/controller.log`
- `gs://dgm-live-runs-doittogether-prod/lcb12-glm52-selfmod-20260629-1/exit_code`
- `gs://dgm-live-runs-doittogether-prod/lcb12-glm52-selfmod-20260629-1/preflight_commands.txt`
- `gs://dgm-live-runs-doittogether-prod/lcb12-glm52-selfmod-20260629-1/scorecard.json`
- `gs://dgm-live-runs-doittogether-prod/lcb12-glm52-selfmod-20260629-1/startup.log`
- `gs://dgm-live-runs-doittogether-prod/lcb12-glm52-selfmod-20260629-1/telemetry.json`
