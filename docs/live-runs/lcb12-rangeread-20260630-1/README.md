# LCB12 ranged-read canary - 2026-06-30

Run ID: `lcb12-rangeread-20260630-1`

This two-generation cloud canary tested commit
`565894a466e5751b2aee0f63abe4804c5f0a6798`, which added ranged `edit.read`
support for self-modification repair loops.

The run proves the cloud VM lane, LiveCodeBench segment execution,
mutation-proven agent-code edits, valid child loading, child benchmark
evaluation, archive selection, telemetry capture, and VM teardown. It does not
prove benchmark improvement.

## Launch

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/run_live_eval_on_cloud_vm.py \
  --project doittogether-prod \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --run-id lcb12-rangeread-20260630-1 \
  --repo-url https://github.com/lemoz/darwin-godel-machine.git \
  --commit 565894a466e5751b2aee0f63abe4804c5f0a6798 \
  --config config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml \
  --generations 2 \
  --secret OPENROUTER_API_KEY=openrouter-api-key \
  --artifact-dir .dgm-cloud-runs/lcb12-rangeread-20260630-1/artifacts \
  --startup-script-path .dgm-cloud-runs/lcb12-rangeread-20260630-1/startup.sh \
  --output .dgm-cloud-runs/lcb12-rangeread-20260630-1/plan.json \
  --gcs-artifact-uri gs://dgm-live-runs-doittogether-prod/lcb12-rangeread-20260630-1 \
  --fm-provider openrouter \
  --model qwen/qwen3-coder \
  --input-price-per-mtok 0.22 \
  --output-price-per-mtok 1.80 \
  --execute
```

Cloud VM:

- Project: `doittogether-prod`
- Zone: `us-central1-a`
- VM: `dgm-lcb12-rangeread-20260630-1`
- Machine: `n2-standard-8`
- Config: `config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml`
- Model/provider: `qwen/qwen3-coder` via OpenRouter
- GCS artifacts: `gs://dgm-live-runs-doittogether-prod/lcb12-rangeread-20260630-1/`

The VM was deleted successfully at the end of the run.

## Preflight

All required VM preflights passed:

- LiveCodeBench segment generation: 12 benchmarks, 512 tests, 480 private tests
- Docker sandbox smoke: passed
- Cost gate: `requests<=2472`, `input_tokens<=123600000`,
  `output_tokens<=10125312`, `total=$45.4176`, under the `$60` cap

## Result

- Exit code: `0`
- Runtime: `2279.69s` observed, `0.6306h` reported
- Generations requested/reported: `2`
- Base/top agent: `0eb68433-4e0e-410c-b351-f71faa5de37d`
- Base/top score: `0.667` = `8/12`
- Valid changed children: `2`
- No-op invalid children: `0`
- Successful improvements: `0`
- Best average delta: `-0.167`
- Estimated provider cost: `$0.613658`
- OpenRouter posts: `247`
- Provider timeouts/API errors/empty responses: `1/0/0`
- Tokens: `1,681,477` prompt, `135,407` completion, `1,816,884` total
- Finish reason `length`: `13`

Score movement:

| Agent | Parent | Generation | Mutation | Valid | Score |
| --- | --- | ---: | --- | --- | ---: |
| `0eb68433-4e0e-410c-b351-f71faa5de37d` | - | 0 | - | yes | `8/12` |
| `fea45c30-f313-4d68-a2d2-31feb5682d00` | `0eb68433-4e0e-410c-b351-f71faa5de37d` | 1 | changed | yes | `6/12` |
| `78692e80-d21c-4f08-bd6e-62f382bb3f07` | `0eb68433-4e0e-410c-b351-f71faa5de37d` | 1 | changed | yes | `6/12` |

Baseline benchmark score split:

- Solved: `livecodebench_abc387_b`, `livecodebench_abc387_c`,
  `livecodebench_abc388_b`, `livecodebench_abc388_c`,
  `livecodebench_abc388_e`, `livecodebench_abc389_a`,
  `livecodebench_abc389_d`, `livecodebench_abc390_b`
- Failed: `livecodebench_abc388_d`, `livecodebench_abc389_e`,
  `livecodebench_abc390_d`, `livecodebench_abc390_e`

Child regressions:

- `fea45c30-f313-4d68-a2d2-31feb5682d00`: regressed
  `livecodebench_abc388_e` and `livecodebench_abc390_b`
- `78692e80-d21c-4f08-bd6e-62f382bb3f07`: regressed
  `livecodebench_abc388_e` and `livecodebench_abc389_d`

## Mutation Evidence

Mutation summary:

- `changed`: `2`
- `noop`: `0`
- changed child `fea45c30-f313-4d68-a2d2-31feb5682d00`
- changed child `78692e80-d21c-4f08-bd6e-62f382bb3f07`

Ranged `edit.read` worked during live self-modification repair. The agent used
bounded, numbered file context after malformed or rejected edits, produced real
agent-code changes, and both children loaded as valid agents.

Archive selection behaved correctly: both children regressed, so the baseline
agent remained the top selected agent.

## Failure Modes

The run still exposed the next blocker before any 50-generation scale-up:

- Repeated malformed `content_lines` payloads with nested arrays, dictionaries,
  booleans, or serialized fragments.
- Python-list-looking `content` fragments such as `[[0], [2]]`.
- XML-like pseudo-tool-call text after `finish_reason=length`.
- Long truncated assistant messages persisted in context and caused repeated
  length spirals.
- Public sample tests were too weak for the D/E tasks; several sample-passing
  solutions still failed private tests.

## Follow-up Patch

The next local patch should normalize or reject malformed edit payloads earlier
and compact `finish_reason=length` pseudo-tool output before it is appended to
conversation history. This should reduce token waste and malformed retry loops
before testing a larger generation count.

## Artifacts

Committed compact artifacts:

- `plan.json`
- `preflight_commands.txt`
- `exit_code`
- `scorecard.json`
- `telemetry.json`
- `archive.tar.gz`

Full logs remain in `.dgm-cloud-runs/lcb12-rangeread-20260630-1/artifacts/`
and in the GCS artifact prefix.
