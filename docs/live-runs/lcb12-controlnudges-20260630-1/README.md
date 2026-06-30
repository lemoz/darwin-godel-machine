# LCB12 control-nudge canary - 2026-06-30

Run ID: `lcb12-controlnudges-20260630-1`

This five-generation cloud canary tested commit
`579db70e4cb1c7c0ec36dcd7c1bb5f50e8071b8e`, which added stronger benchmark
control nudges after the earlier edit-normalizer improvement run.

The run proves that the ephemeral cloud VM lane can execute a live
multi-generation DGM loop on the 12-problem LiveCodeBench segment, classify
changed versus no-op mutations, validate child agents, evaluate valid children,
capture telemetry, archive results, sync artifacts, and tear the VM down. It
does not prove stable improvement, 50-loop readiness, or robust D/E benchmark
solving.

## Launch

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/run_live_eval_on_cloud_vm.py \
  --project doittogether-prod \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --run-id lcb12-controlnudges-20260630-1 \
  --repo-url https://github.com/lemoz/darwin-godel-machine.git \
  --commit 579db70e4cb1c7c0ec36dcd7c1bb5f50e8071b8e \
  --config config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml \
  --generations 5 \
  --secret OPENROUTER_API_KEY=openrouter-api-key \
  --artifact-dir .dgm-cloud-runs/lcb12-controlnudges-20260630-1/artifacts \
  --startup-script-path .dgm-cloud-runs/lcb12-controlnudges-20260630-1/startup.sh \
  --output .dgm-cloud-runs/lcb12-controlnudges-20260630-1/plan.json \
  --gcs-artifact-uri gs://dgm-live-runs-doittogether-prod/lcb12-controlnudges-20260630-1 \
  --fm-provider openrouter \
  --model qwen/qwen3-coder \
  --input-price-per-mtok 0.22 \
  --output-price-per-mtok 1.80 \
  --execute
```

Cloud VM:

- Project: `doittogether-prod`
- Zone: `us-central1-a`
- VM: `dgm-lcb12-controlnudges-20260630-1`
- Machine: `n2-standard-8`
- Config: `config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml`
- Model/provider: `qwen/qwen3-coder` via OpenRouter
- GCS artifacts: `gs://dgm-live-runs-doittogether-prod/lcb12-controlnudges-20260630-1/`

The VM was deleted successfully at the end of the run.

## Preflight

All required VM preflights passed:

- LiveCodeBench segment generation
- Docker sandbox smoke with required Docker availability
- Cost gate under the `$60` cap

## Result

- Exit code: `0`
- Runtime: `2696.058s` observed, `0.7462h` reported
- Generations requested/reported: `5`
- Base agent: `57d7e30e-1779-4e28-8414-61f709a4e9ad`
- Base score: `0.583` = `7/12`
- Top agent: `57d7e30e-1779-4e28-8414-61f709a4e9ad`
- Top score: `0.583` = `7/12`
- Best average delta: `+0.000`
- Valid changed children: `3`
- No-op invalid children: `2`
- Successful improvements: `0`
- Archive size: `6`
- Estimated provider cost: `$0.871623`
- OpenRouter posts: `341`
- Provider timeouts/API errors/empty responses: `2/0/0`
- Tokens: `2,809,072` prompt, `140,904` completion, `2,949,976` total
- Finish reason `length`: `14`
- Tracebacks in log telemetry: `26`

Score movement:

| Loop Iteration | Agent | Parent | Mutation | Valid | Score | Notes |
| ---: | --- | --- | --- | --- | ---: | --- |
| 0 | `57d7e30e-1779-4e28-8414-61f709a4e9ad` | - | - | yes | `7/12` | Baseline |
| 1 | `4fb50010-cd36-4a80-888c-44011fb27aad` | `57d7e30e-1779-4e28-8414-61f709a4e9ad` | changed | yes | `7/12` | Improved `abc388_e`, regressed `abc389_d` |
| 2 | `9c63f48a-76b3-4843-8bd0-af6bac0b1450` | `57d7e30e-1779-4e28-8414-61f709a4e9ad` | noop | no | `0/12` | Invalid no-op mutation |
| 3 | `26aa8d06-adeb-4d5a-b7c3-68eb1b14cfe3` | `57d7e30e-1779-4e28-8414-61f709a4e9ad` | noop | no | `0/12` | Invalid no-op mutation |
| 4 | `5b40474d-c543-4d29-b2bf-ae8ddeaab70e` | `57d7e30e-1779-4e28-8414-61f709a4e9ad` | changed | yes | `6/12` | Regressed `abc389_d` |
| 5 | `b33d01a4-ede1-4ca9-9627-ce78eaf8d8f4` | `57d7e30e-1779-4e28-8414-61f709a4e9ad` | changed | yes | `6/12` | Regressed `abc389_d` |

The archive metadata records each child as generation `1` because every child
was produced from the generation-0 baseline parent. The table above uses loop
iteration order from the run.

Baseline solved benchmarks:

- `livecodebench_abc387_b`
- `livecodebench_abc387_c`
- `livecodebench_abc388_b`
- `livecodebench_abc388_c`
- `livecodebench_abc389_a`
- `livecodebench_abc389_d`
- `livecodebench_abc390_b`

Persistent zero-score pressure concentrated on:

- `livecodebench_abc388_d`: `4` zero-score attempts
- `livecodebench_abc388_e`: `3` zero-score attempts
- `livecodebench_abc389_d`: `3` zero-score attempts
- `livecodebench_abc389_e`: `4` zero-score attempts
- `livecodebench_abc390_d`: `4` zero-score attempts
- `livecodebench_abc390_e`: `4` zero-score attempts

## Mutation Evidence

Mutation summary:

- `changed`: `3`
- `noop`: `2`
- changed child `4fb50010-cd36-4a80-888c-44011fb27aad`
- changed child `5b40474d-c543-4d29-b2bf-ae8ddeaab70e`
- changed child `b33d01a4-ede1-4ca9-9627-ce78eaf8d8f4`
- noop child `9c63f48a-76b3-4843-8bd0-af6bac0b1450`
- noop child `26aa8d06-adeb-4d5a-b7c3-68eb1b14cfe3`

Archive selection behaved correctly: tied and regressed children did not
replace the baseline as top agent.

## Failure Modes

This run exposed the next blockers before attempting a 50-loop WDSLL run:

- Benchmark control nudges were active, but too soft. The model often continued
  testing or rewriting after sample-passing solutions.
- D/E solutions repeatedly passed public samples while failing private tests.
- The model stated unsafe complexity or memory behavior, then still converged
  on invalid solutions.
- The agent ran no-input shell tests such as `python3 solution.py`, producing
  avoidable `EOFError` failures.
- Qwen repeatedly emitted malformed edit payloads: serialized/list fragments,
  nested arrays, integers, dictionaries, and XML-ish pseudo tool calls after
  `finish_reason=length`.
- `finish_reason=length` occurred `14` times and caused large continuation
  churn.
- Self-modification still used broad full-file reads and late, brittle line
  replacements.
- Two loop iterations produced no valid agent-code change.
- OpenRouter was usable but not perfectly stable: `2` provider timeouts were
  observed.

## Follow-up Patch

The next local patch should prioritize reliability over larger loop count:

- Add hard no-stdin bash repair so sample checks use heredocs or `printf`.
- Track failed sample checks and block finalization until a later sample check
  passes.
- Escalate self-reported unsafe complexity, `MemoryError`, `EOFError`, and
  timeout evidence into verifier pressure that prevents sample-only finalization.
- Convert safe serialized full-source payloads into raw source locally instead
  of spending another LLM turn when possible.
- Strengthen self-modification read discipline and prevent broad replacement
  attempts without an exact local line range.
- Compare `qwen/qwen3-coder` against a more stable OpenRouter fallback before
  scaling to 50 loops.

## Artifacts

Committed compact artifacts:

- `plan.json`
- `preflight_commands.txt`
- `exit_code`
- `scorecard.json`
- `telemetry.json`
- `archive.tar.gz`

Full logs remain in `.dgm-cloud-runs/lcb12-controlnudges-20260630-1/artifacts/`
and in the GCS artifact prefix.
