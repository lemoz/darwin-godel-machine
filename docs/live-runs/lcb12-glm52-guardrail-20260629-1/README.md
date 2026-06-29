# GLM 5.2 edit-guardrail LiveCodeBench canary - 2026-06-29

This two-generation cloud canary tested commit
`9c1f447ba779990c326a3dd40c7265fca69bc25c`, which hardened self-modification by:

- rejecting `edit.modify` calls that omit `replace_text`
- adding prompt-build smoke validation for DGM-style child agents

The run proved the edit guardrail live. It did not produce an improvement.

## Launch

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/run_live_eval_on_cloud_vm.py \
  --project doittogether-prod \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --run-id lcb12-glm52-guardrail-20260629-1 \
  --repo-url https://github.com/lemoz/darwin-godel-machine.git \
  --commit 9c1f447ba779990c326a3dd40c7265fca69bc25c \
  --config config/livecodebench_openrouter_loop12_glm52_selfmod_recovery.yaml \
  --generations 2 \
  --secret OPENROUTER_API_KEY=openrouter-api-key \
  --artifact-dir .dgm-cloud-runs/lcb12-glm52-guardrail-20260629-1/artifacts \
  --startup-script-path .dgm-cloud-runs/lcb12-glm52-guardrail-20260629-1/startup.sh \
  --output .dgm-cloud-runs/lcb12-glm52-guardrail-20260629-1/plan.json \
  --gcs-artifact-uri gs://dgm-live-runs-doittogether-prod/lcb12-glm52-guardrail-20260629-1 \
  --fm-provider openrouter \
  --model z-ai/glm-5.2 \
  --input-price-per-mtok 0.94 \
  --output-price-per-mtok 3.00 \
  --execute
```

Cloud VM:

- Project: `doittogether-prod`
- Zone: `us-central1-a`
- VM: `dgm-lcb12-glm52-guardrail-20260629-1`
- Commit: `9c1f447ba779990c326a3dd40c7265fca69bc25c`
- Config: `config/livecodebench_openrouter_loop12_glm52_selfmod_recovery.yaml`
- GCS artifacts: `gs://dgm-live-runs-doittogether-prod/lcb12-glm52-guardrail-20260629-1/`

The VM was deleted at the end of the run. A follow-up instance-list check for
`dgm-lcb12-glm52-guardrail-20260629-1` returned no rows.

## Preflight

All required preflights passed on the VM:

- LiveCodeBench segment generation: 12 benchmarks, 512 tests, 480 private tests
- Docker sandbox smoke: passed
- Cost gate: `requests<=696`, `input_tokens<=34800000`,
  `output_tokens<=1425408`, `total=$36.9882`, under the `$45` cap

## Result

- Exit code: `0`
- Runtime: `1723.867s` / `0.476h`
- Generations: `2`
- Base/top agent: `96991c98-8a49-4957-8c15-68274a879d19`
- Base/top score: `0.5` = `6/12`
- Total agents in archive: `3`
- Valid agents: `1`
- Child agents created: `0`
- Successful improvements: `0`
- Consecutive no-op mutations: `2`
- Estimated actual provider cost: `$0.590888`

Base solved:

- `livecodebench_abc387_b`
- `livecodebench_abc388_b`
- `livecodebench_abc388_e`
- `livecodebench_abc389_a`
- `livecodebench_abc390_b`
- `livecodebench_abc390_e`

Base zero-scored:

- `livecodebench_abc387_c`
- `livecodebench_abc388_c`
- `livecodebench_abc388_d`
- `livecodebench_abc389_d`
- `livecodebench_abc389_e`
- `livecodebench_abc390_d`

## Guardrail Evidence

Generation 1 used all 12 self-modification steps reading files and produced no
source change:

- `Mutation proof: status=noop changed_code_files=0 changed_files=0`
- Archived invalid child: `b65d1f64-f959-4db9-93ec-b4767ee56f06`

Generation 2 reached the dangerous mutation path and the edit guardrail rejected
it repeatedly:

- `replace_text parameter is required for modify action; use an explicit empty string only for intentional deletion`
- The same error appeared five times during generation 2.
- Final mutation proof: `status=noop changed_code_files=0 changed_files=0`
- Archived invalid child: `54d96a0f-2c67-49e5-a929-ecfe3999dc60`

This proves the prior failure mode no longer silently deletes source text. The
child was not benchmarked because no Python agent code changed.

## Provider Evidence

GLM 5.2 was not stable enough for a larger run under this config:

- HTTP POSTs: `82`
- Usage events: `79`
- Prompt tokens: `468835`
- Completion tokens: `50061`
- Total tokens: `518896`
- Provider timeouts: `3`
- Empty responses: `30`
- Provider API errors: `0`
- Finish reasons for empty responses: `length`

Observed model failure modes:

- repeated empty `finish_reason=length` responses with most completion tokens
  consumed as reasoning tokens
- malformed tool arguments nested under `arguments`
- `edit.write` calls that put code in `replace_text` instead of `content`,
  resulting in empty `solution.py`
- repeated `edit.modify` attempts without `replace_text`

## Conclusion

The guardrail fix is live-proven. The next blocker is no longer the old silent
destructive edit; it is model/harness robustness:

1. Add stricter write/modify parameter validation and targeted recovery messages
   for malformed tool calls.
2. Add OpenRouter reasoning/output controls for GLM 5.2, or switch the default
   Chinese OpenRouter model to a more stable candidate.
3. Re-run a two-generation canary before scaling beyond this segment.

## Artifacts

Committed compact artifacts:

- `archive.tar.gz`
- `exit_code`
- `plan.json`
- `preflight_commands.txt`
- `scorecard.json`
- `telemetry.json`

Raw GCS artifacts:

- `gs://dgm-live-runs-doittogether-prod/lcb12-glm52-guardrail-20260629-1/archive.tar.gz`
- `gs://dgm-live-runs-doittogether-prod/lcb12-glm52-guardrail-20260629-1/controller.log`
- `gs://dgm-live-runs-doittogether-prod/lcb12-glm52-guardrail-20260629-1/exit_code`
- `gs://dgm-live-runs-doittogether-prod/lcb12-glm52-guardrail-20260629-1/preflight_commands.txt`
- `gs://dgm-live-runs-doittogether-prod/lcb12-glm52-guardrail-20260629-1/scorecard.json`
- `gs://dgm-live-runs-doittogether-prod/lcb12-glm52-guardrail-20260629-1/startup.log`
- `gs://dgm-live-runs-doittogether-prod/lcb12-glm52-guardrail-20260629-1/telemetry.json`
