# Cloud VM loop-12 live DGM run - 2026-06-28

This directory records a completed 10-generation DGM run on an ephemeral GCP
VM against a 12-problem LiveCodeBench-derived code-generation segment. The run
used real OpenRouter calls to `moonshotai/kimi-k2.7-code`, streamed artifacts to
GCS while running, completed with exit code `0`, and left enough telemetry to
measure score movement, token spend, timeouts, empty responses, and teardown.

## Command

The run was launched from the maintainer checkout with the cloud runner:

```bash
RUN_ID=loop12-cloud-20260628-1
PATH="$PWD/.venv/bin:$PATH" python scripts/run_live_eval_on_cloud_vm.py \
  --project doittogether-prod \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --run-id "$RUN_ID" \
  --repo-url https://github.com/lemoz/darwin-godel-machine.git \
  --commit a50e0bb5d7d6feeb909d9e6b29b5a76f58cbc1cd \
  --config config/livecodebench_openrouter_loop12_host.yaml \
  --generations 10 \
  --secret OPENROUTER_API_KEY=openrouter-api-key \
  --artifact-dir ".dgm-cloud-runs/$RUN_ID/artifacts" \
  --startup-script-path ".dgm-cloud-runs/$RUN_ID/startup.sh" \
  --output ".dgm-cloud-runs/$RUN_ID/plan.json" \
  --gcs-artifact-uri "gs://dgm-live-runs-doittogether-prod/$RUN_ID" \
  --fm-provider openrouter \
  --model moonshotai/kimi-k2.7-code \
  --input-price-per-mtok 0.74 \
  --output-price-per-mtok 3.50 \
  --execute
```

The cloud VM cloned the exact commit above, loaded the OpenRouter key from GCP
Secret Manager, ran the config preflight, executed `run_dgm.py`, wrote
`controller.log`, `scorecard.json`, `telemetry.json`, and `exit_code`, and
rsynced artifacts to GCS.

## Scope

- Segment config: `config/livecodebench_segment_loop12.yaml`
- Live run config: `config/livecodebench_openrouter_loop12_host.yaml`
- Segment ID: `release_v6_atcoder_loop12`
- Benchmark source: LiveCodeBench `code_generation_lite`
- Source dataset: `https://huggingface.co/datasets/livecodebench/code_generation_lite`
- Upstream project: `https://github.com/livecodebench/livecodebench`
- Problem count: 12
- Model: `moonshotai/kimi-k2.7-code` through OpenRouter
- Provider base URL: `https://openrouter.ai/api/v1`
- OpenRouter timeout: 60 seconds
- Generations completed: 10
- Max model turns per task: 5
- Cloud project: `doittogether-prod`
- Cloud zone: `us-central1-a`
- Machine type: `n2-standard-8`
- VM name: `dgm-loop12-cloud-20260628-1`

## Result

Final controller summary:

- Total runtime: 1.45 hours
- Generations: 10
- Agents created: 10, plus the base agent
- Archive size: 11
- Successful improvements: 3
- Improvement rate: 30.0%
- Base score: `0.5` (`6/12`)
- Best score: `0.5833333333333334` (`7/12`)
- Best delta from base: `+0.08333333333333337`
- Exit code: `0`

Loop-order score table:

| Loop | Gen metadata | Agent | Parent | Score | Solved |
| ---: | ---: | --- | --- | ---: | ---: |
| 0 | 0 | `d1dfb20c` | `-` | `0.500` | 6/12 |
| 1 | 1 | `2c6e7c87` | `d1dfb20c` | `0.583` | 7/12 |
| 2 | 1 | `0c50909a` | `d1dfb20c` | `0.583` | 7/12 |
| 3 | 1 | `ffed3d19` | `d1dfb20c` | `0.417` | 5/12 |
| 4 | 1 | `264c753f` | `d1dfb20c` | `0.417` | 5/12 |
| 5 | 1 | `e4a42731` | `d1dfb20c` | `0.583` | 7/12 |
| 6 | 2 | `ab2ae388` | `e4a42731` | `0.583` | 7/12 |
| 7 | 2 | `2dd2751c` | `e4a42731` | `0.500` | 6/12 |
| 8 | 2 | `ed0e60dc` | `e4a42731` | `0.583` | 7/12 |
| 9 | 2 | `72d09ae4` | `e4a42731` | `0.417` | 5/12 |
| 10 | 2 | `5e0eda66` | `e4a42731` | `0.500` | 6/12 |

Generation-best score movement:

| Generation | Agent | Score | Solved | Passed tasks |
| ---: | --- | ---: | ---: | --- |
| 0 | `d1dfb20c` | `0.500` | 6/12 | `abc387_b`, `abc388_b`, `abc388_c`, `abc388_e`, `abc389_a`, `abc390_b` |
| 1 | `2c6e7c87` | `0.583` | 7/12 | `abc387_b`, `abc388_b`, `abc388_c`, `abc389_a`, `abc389_d`, `abc390_b`, `abc390_e` |
| 2 | `ab2ae388` | `0.583` | 7/12 | `abc387_b`, `abc387_c`, `abc388_b`, `abc388_c`, `abc389_a`, `abc389_d`, `abc390_b` |

Accepted score improvements:

| Child | Parent | Score movement | Benchmark movement |
| --- | --- | ---: | --- |
| `2c6e7c87` | `d1dfb20c` | `6/12 -> 7/12` | Added `abc389_d`, `abc390_e`; lost `abc388_e` |
| `0c50909a` | `d1dfb20c` | `6/12 -> 7/12` | Added `abc389_d`, `abc390_e`; lost `abc388_e` |
| `e4a42731` | `d1dfb20c` | `6/12 -> 7/12` | Added `abc389_d`; no regressions |

The archive scorecard records both improvement and regression evidence. The
project should not interpret this run as a clean monotonic capability gain; it
does prove the live cloud lane can complete a multi-generation DGM run and
observe a best-score increase over the base agent.

## Telemetry

Provider and token summary:

- OpenRouter chat-completion POSTs: 413
- Usage events: 403
- Prompt tokens: 933,470
- Completion tokens: 192,063
- Total tokens: 1,125,533
- Estimated OpenRouter cost: `$1.362988`
- Timeout count: 10
- Empty/no-response count: 64
- Provider API errors: 0
- Max observed completion latency: 59.09 seconds
- Average observed completion latency: 10.40 seconds

Failure signals:

| Signal | Count |
| --- | ---: |
| Empty/no-response completions | 64 |
| Provider timeouts | 10 |
| Resource-guard rejections | 1 |
| Python tracebacks inside attempted solution commands | 2 |
| Provider API errors | 0 |

Zero-score counts by benchmark across the 11 archived agents:

| Benchmark | Zero-score count |
| --- | ---: |
| `livecodebench_abc387_c` | 9 |
| `livecodebench_abc388_c` | 1 |
| `livecodebench_abc388_d` | 11 |
| `livecodebench_abc388_e` | 8 |
| `livecodebench_abc389_d` | 6 |
| `livecodebench_abc389_e` | 11 |
| `livecodebench_abc390_d` | 11 |
| `livecodebench_abc390_e` | 7 |

The dominant reliability pattern was not provider hard errors. It was
successful HTTP responses that consumed the 2,048-token completion cap while
producing no usable assistant content or tool calls, followed by the current
max-step logic ending the task after step 1 of a 5-step run.

## Artifacts

Committed compact artifacts:

- `plan.json`
- `preflight_commands.txt`
- `scorecard.json`
- `telemetry.json`

Durable raw artifacts were streamed to:

- `gs://dgm-live-runs-doittogether-prod/loop12-cloud-20260628-1/controller.log`
- `gs://dgm-live-runs-doittogether-prod/loop12-cloud-20260628-1/startup.log`
- `gs://dgm-live-runs-doittogether-prod/loop12-cloud-20260628-1/scorecard.json`
- `gs://dgm-live-runs-doittogether-prod/loop12-cloud-20260628-1/telemetry.json`
- `gs://dgm-live-runs-doittogether-prod/loop12-cloud-20260628-1/preflight_commands.txt`
- `gs://dgm-live-runs-doittogether-prod/loop12-cloud-20260628-1/exit_code`

Teardown proof:

```text
Deleted [https://www.googleapis.com/compute/v1/projects/doittogether-prod/zones/us-central1-a/instances/dgm-loop12-cloud-20260628-1].
```

A follow-up `gcloud compute instances list` filtered to
`dgm-loop12-cloud-20260628-1` returned no rows.

## Verification

Checks completed for this proof:

- Cloud VM creation: passed
- Fresh VM clone and commit checkout: passed
- Config preflight on VM: passed
- Live OpenRouter DGM run: passed
- Continuous GCS artifact sync: passed
- Final artifact retrieval from GCS: passed via `gsutil`
- VM teardown: passed
- Exit code artifact: `0`

The local `gcloud storage cp` client crashed on macOS while retrieving
artifacts with `AttributeError: 'Lock' object has no attribute 'is_fork_ctx'`.
`gsutil -m cp` retrieved the same GCS artifacts successfully. This was a local
artifact retrieval issue after the run had completed, not a DGM run failure.

## Caveats

This is not a full LiveCodeBench leaderboard result. It is a local DGM harness
run over a recognizable LiveCodeBench-derived AtCoder segment with private
tests in the local scoring path.

The cloud startup path did not copy the generated `dgm_report_*.json` into the
final artifact directory. The committed `scorecard.json`, `telemetry.json`, and
raw controller log contain the authoritative run evidence for this card. The
runner should capture `dgm_report_*.json` in the next hardening pass.

The observed score movement is real in the archive scorecard, but mutation
quality remains weak: many self-modification attempts still spend most of their
budget reading code or producing no effective agent changes. The next project
priority is therefore reliability plus useful mutation pressure, not just
larger spending.
