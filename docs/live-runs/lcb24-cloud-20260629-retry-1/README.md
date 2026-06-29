# Retry-enabled cloud VM LiveCodeBench 24-problem DGM run - 2026-06-29

This directory records a completed 3-generation DGM run on an ephemeral GCP VM
against the 24-problem LiveCodeBench-derived AtCoder segment. The run used real
OpenRouter calls to `moonshotai/kimi-k2.7-code`, cloned commit
`6037e5530bbbd614c2a89813c4266d3a93da51d8`, streamed artifacts to GCS, exited
with code `0`, and deleted the VM at teardown.

This was the direct retry-enabled follow-up to `lcb24-cloud-20260628-2`. It
proved the cloud runner and telemetry path on the reliability-fix branch, but it
did not improve the benchmark score. The base remained the top archived agent.

## Command

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/run_live_eval_on_cloud_vm.py \
  --project doittogether-prod \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --run-id lcb24-cloud-20260629-retry-1 \
  --repo-url https://github.com/lemoz/darwin-godel-machine.git \
  --commit 6037e5530bbbd614c2a89813c4266d3a93da51d8 \
  --config config/livecodebench_openrouter_segment.yaml \
  --generations 3 \
  --secret OPENROUTER_API_KEY=openrouter-api-key \
  --artifact-dir .dgm-cloud-runs/lcb24-cloud-20260629-retry-1/artifacts \
  --startup-script-path .dgm-cloud-runs/lcb24-cloud-20260629-retry-1/startup.sh \
  --output .dgm-cloud-runs/lcb24-cloud-20260629-retry-1/plan.json \
  --gcs-artifact-uri gs://dgm-live-runs-doittogether-prod/lcb24-cloud-20260629-retry-1 \
  --fm-provider openrouter \
  --model moonshotai/kimi-k2.7-code \
  --input-price-per-mtok 0.74 \
  --output-price-per-mtok 3.50 \
  --execute
```

OpenRouter pricing for `moonshotai/kimi-k2.7-code` was checked on
2026-06-29: `$0.74/MTok` prompt, `$3.50/MTok` completion. The retry-inclusive
cost estimate was capped by preflight under `$60`.

## Scope

- Segment config: `config/livecodebench_segment.yaml`
- Live run config: `config/livecodebench_openrouter_segment.yaml`
- Segment ID: `release_v6_atcoder_balanced_24`
- Benchmark source: LiveCodeBench `code_generation_lite`
- Source dataset: `https://huggingface.co/datasets/livecodebench/code_generation_lite`
- Upstream project: `https://github.com/livecodebench/livecodebench`
- Problem count: 24
- Segment composition: 8 easy, 8 medium, 8 hard AtCoder tasks
- Scoring: public examples in prompts, private tests included in deterministic scoring
- Model: `moonshotai/kimi-k2.7-code` through OpenRouter
- Provider base URL: `https://openrouter.ai/api/v1`
- OpenRouter timeout: 90 seconds
- Timeout retries: 1
- Timeout retry delay: 1 second
- Max completion tokens: 4,096
- Generations requested: 3
- Max model turns per task: 5
- Cloud project: `doittogether-prod`
- Cloud zone: `us-central1-a`
- Machine type: `n2-standard-8`
- VM name: `dgm-lcb24-cloud-20260629-retry-1`

VM-side preflight commands:

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/prepare_livecodebench_segment.py --config config/livecodebench_segment.yaml
PATH="$PWD/.venv/bin:$PATH" python scripts/verify_livecodebench_segment_plan.py --config config/livecodebench_openrouter_segment.yaml --require-generated
PATH="$PWD/.venv/bin:$PATH" python scripts/verify_sandbox_docker.py --build-image --require
PATH="$PWD/.venv/bin:$PATH" python scripts/estimate_live_run_cost.py --config config/livecodebench_openrouter_segment.yaml --input-price-per-mtok 0.74 --output-price-per-mtok 3.50 --assumed-input-tokens-per-call 50000 --max-budget 60
```

## Result

Final controller summary:

- Total observed runtime: 11,333.93 seconds, about 3.15 hours
- Controller generations completed: 3
- Agents created: 3, plus the base agent
- Archive size: 4
- Successful improvements: 0
- Base score: `0.5833333333333334` (`14/24`)
- Best score: `0.5833333333333334` (`14/24`)
- Best delta from base: `0`
- Best child delta from base: `-0.04166666666666674`
- Exit code: `0`

Loop-order score table:

| Loop | Agent | Parent | Score | Solved | Notes |
| ---: | --- | --- | ---: | ---: | --- |
| 0 | `8c9297d8` | `-` | `0.583` | 14/24 | Base and final top |
| 1 | `e9384c6e` | `8c9297d8` | `0.500` | 12/24 | Gained `abc388_d`; lost `abc388_e`, `abc389_d`, `abc390_e` |
| 2 | `94442148` | `8c9297d8` | `0.542` | 13/24 | Gained `abc388_d`; lost `abc389_d`, `abc390_e` |
| 3 | `24400539` | `8c9297d8` | `0.458` | 11/24 | Lost `abc387_c`, `abc388_e`, `abc390_c` |

Parent selection behaved conservatively: after each child regressed, the next
generation selected the base parent (`8c9297d8`) instead of building on a worse
child. That protected the archive top score, but it did not produce a new
improvement.

## Before/After

Direct comparison against `lcb24-cloud-20260628-2`:

| Metric | `lcb24-cloud-20260628-2` | `lcb24-cloud-20260629-retry-1` |
| --- | ---: | ---: |
| Commit | `55f80017` | `6037e553` |
| Exit code | `0` | `0` |
| Base score | 13/24 | 14/24 |
| Top score | 17/24 | 14/24 |
| Successful improvements | 1 | 0 |
| Best child delta | `+4` tasks | `-1` task |
| Observed runtime | about 1.10 hours | about 3.15 hours |
| OpenRouter POSTs | 302 | 336 |
| Usage events | 297 | 264 |
| Prompt tokens | 693,062 | 636,632 |
| Completion tokens | 222,888 | 190,820 |
| Total tokens | 915,950 | 827,452 |
| Estimated cost | `$1.292974` | `$1.138978` |
| Provider timeouts | 5 | 71 |
| Empty/no-response completions | 33 | 59 |
| Resource-guard rejections | 4 | 4 |
| Python tracebacks inside attempted solutions | 2 | 1 |
| Provider API errors | 0 | 0 |

The reliability-fix branch made retries and recovery more visible, but this run
was worse as a DGM search result. The top score dropped from 17/24 in the prior
cloud run to 14/24 here. The higher timeout count is partly expected because
each timed-out request now gets a second attempt, but the second attempts often
timed out too.

## Score Details

Base agent solved:

```text
abc387_a, abc387_b, abc387_c,
abc388_a, abc388_b, abc388_c, abc388_e,
abc389_a, abc389_b, abc389_d,
abc390_a, abc390_b, abc390_c, abc390_e
```

Best child solved:

```text
abc387_a, abc387_b, abc387_c,
abc388_a, abc388_b, abc388_c, abc388_d, abc388_e,
abc389_a, abc389_b,
abc390_a, abc390_b, abc390_c
```

Accepted benchmark-level improvements across children:

| Child | Score movement | Improvements | Regressions |
| --- | ---: | --- | --- |
| `e9384c6e` | `14/24 -> 12/24` | `abc388_d` | `abc388_e`, `abc389_d`, `abc390_e` |
| `94442148` | `14/24 -> 13/24` | `abc388_d` | `abc389_d`, `abc390_e` |
| `24400539` | `14/24 -> 11/24` | None | `abc387_c`, `abc388_e`, `abc390_c` |

Zero-score counts across the 4 archived agents:

| Benchmark | Zero-score count |
| --- | ---: |
| `livecodebench_abc387_c` | 1 |
| `livecodebench_abc387_f` | 4 |
| `livecodebench_abc388_d` | 2 |
| `livecodebench_abc388_e` | 2 |
| `livecodebench_abc388_f` | 4 |
| `livecodebench_abc388_g` | 4 |
| `livecodebench_abc389_d` | 2 |
| `livecodebench_abc389_e` | 4 |
| `livecodebench_abc389_f` | 4 |
| `livecodebench_abc389_g` | 4 |
| `livecodebench_abc390_c` | 1 |
| `livecodebench_abc390_d` | 4 |
| `livecodebench_abc390_e` | 2 |
| `livecodebench_abc391_d` | 4 |
| `livecodebench_abc392_d` | 4 |

## Telemetry

Provider and token summary:

- OpenRouter chat-completion POSTs: 336
- Usage events: 264
- Prompt tokens: 636,632
- Completion tokens: 190,820
- Total tokens: 827,452
- Estimated OpenRouter cost: `$1.138978`
- Timeout count: 71
- Empty/no-response count: 59
- Provider API errors: 0
- Max observed completion latency: 88.81 seconds
- Average observed completion latency: 17.13 seconds

Failure signals:

| Signal | Count |
| --- | ---: |
| Empty/no-response completions | 59 |
| Provider timeouts | 71 |
| Resource-guard rejections | 4 |
| Python tracebacks inside attempted solution commands | 1 |
| Provider API errors | 0 |

Observed reliability behavior:

- Timeout retry plumbing worked: logs show `attempt: 1/2` and `attempt: 2/2`.
- Retries sometimes recovered enough to produce code, but many second attempts
  still timed out, especially in the hard tail.
- Empty-response recovery worked: the agent re-asked after empty `stop` or
  `length` responses and sometimes converted the task afterward.
- Tool-written solution fallback mattered: several tasks scored only because
  `solution.py` was used after no final inline answer arrived.
- `abc390_d` repeatedly generated subset-DP set-per-mask solutions and was
  rejected by the deterministic resource guard in all 4 archived agents.
- `abc392_d` repeatedly completed with plausible code but scored 0, indicating
  an answer-quality failure rather than provider or sandbox failure.

## Artifacts

Committed compact artifacts:

- `exit_code`
- `plan.json`
- `preflight_commands.txt`
- `scorecard.json`
- `telemetry.json`

Durable raw artifacts were streamed to:

- `gs://dgm-live-runs-doittogether-prod/lcb24-cloud-20260629-retry-1/controller.log`
- `gs://dgm-live-runs-doittogether-prod/lcb24-cloud-20260629-retry-1/startup.log`
- `gs://dgm-live-runs-doittogether-prod/lcb24-cloud-20260629-retry-1/scorecard.json`
- `gs://dgm-live-runs-doittogether-prod/lcb24-cloud-20260629-retry-1/telemetry.json`
- `gs://dgm-live-runs-doittogether-prod/lcb24-cloud-20260629-retry-1/preflight_commands.txt`
- `gs://dgm-live-runs-doittogether-prod/lcb24-cloud-20260629-retry-1/exit_code`

Teardown proof:

```text
Deleted [https://www.googleapis.com/compute/v1/projects/doittogether-prod/zones/us-central1-a/instances/dgm-lcb24-cloud-20260629-retry-1].
```

A follow-up `gcloud compute instances list` filtered to
`dgm-lcb24-cloud-20260629-retry-1` returned no rows.

## Verification

Checks completed for this proof:

- Cloud VM creation: passed
- Fresh VM clone and exact commit checkout: passed
- LiveCodeBench segment generation on VM: passed
- Segment plan verification: passed
- Docker sandbox build and smoke test on VM: passed
- Cost gate under `$60`: passed
- Live OpenRouter DGM run: passed
- Continuous GCS artifact sync: passed
- Final artifact retrieval from GCS: passed via `gsutil`
- VM teardown: passed
- Exit code artifact: `0`

## Caveats

This is not a full LiveCodeBench leaderboard result. It is a DGM harness run
over a recognizable LiveCodeBench-derived AtCoder segment with local private
test scoring.

The `telemetry.json` `dgm_report` field is stale in this artifact and points at
an older one-generation report. The controller log, `scorecard.json`,
`telemetry.json` `run`/`score` sections, and final runner summary all agree
that this run completed the requested 3 generations. The telemetry extraction
should be fixed so the embedded `dgm_report` pointer is not stale.

## Next Work

The next engineering target is not simply "add another retry". This run shows:

- Hard-tail timeouts are the dominant reliability blocker under
  `moonshotai/kimi-k2.7-code` at 90 seconds.
- Empty-response re-asks and `solution.py` fallback are necessary and working,
  but they are not sufficient for score improvement.
- Parent selection protected the archive from regressed children.
- Resource-guard rejection on `abc390_d` is deterministic and needs either
  better prompting/tool feedback or a stronger verification/remediation loop.
- Score variance on the same base parent is high enough that future claims need
  multiple seeds/runs or larger benchmark segments before treating a one-run
  score movement as stable.
