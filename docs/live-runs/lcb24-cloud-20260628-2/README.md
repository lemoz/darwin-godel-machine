# Cloud VM LiveCodeBench 24-problem DGM run - 2026-06-28/29

This directory records a completed 3-generation DGM run on an ephemeral GCP VM
against a 24-problem LiveCodeBench-derived AtCoder code-generation segment. The
run used real OpenRouter calls to `moonshotai/kimi-k2.7-code`, streamed
artifacts to GCS while running, completed with exit code `0`, deleted the VM at
the end, and captured score movement plus provider/tokens/failure telemetry.

This is the first cloud-VM run card for the balanced 24-problem segment. It is
the strongest current proof that the DGM harness can run live, off-laptop,
against a recognizable benchmark slice and produce a measurable best-score
increase.

## Command

The run was launched from the maintainer checkout with the cloud runner:

```bash
RUN_ID=lcb24-cloud-20260628-2
PATH="$PWD/.venv/bin:$PATH" python scripts/run_live_eval_on_cloud_vm.py \
  --project doittogether-prod \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --run-id "$RUN_ID" \
  --repo-url https://github.com/lemoz/darwin-godel-machine.git \
  --commit 55f80017acfb76f2fede73c92993396fd6068339 \
  --config config/livecodebench_openrouter_segment.yaml \
  --generations 3 \
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
Secret Manager, ran the configured preflight, executed `run_dgm.py`, wrote
`controller.log`, `scorecard.json`, `telemetry.json`, and `exit_code`, and
rsynced artifacts to GCS throughout the run.

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
- Max completion tokens: 4,096
- Generations requested: 3
- Max model turns per task: 5
- Cloud project: `doittogether-prod`
- Cloud zone: `us-central1-a`
- Machine type: `n2-standard-8`
- VM name: `dgm-lcb24-cloud-20260628-2`

VM-side preflight commands:

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/prepare_livecodebench_segment.py --config config/livecodebench_segment.yaml
PATH="$PWD/.venv/bin:$PATH" python scripts/verify_livecodebench_segment_plan.py --config config/livecodebench_openrouter_segment.yaml --require-generated
PATH="$PWD/.venv/bin:$PATH" python scripts/verify_sandbox_docker.py --build-image --require
PATH="$PWD/.venv/bin:$PATH" python scripts/estimate_live_run_cost.py --config config/livecodebench_openrouter_segment.yaml --input-price-per-mtok 0.74 --output-price-per-mtok 3.50 --assumed-input-tokens-per-call 50000 --max-budget 30
```

The Docker sandbox preflight built and smoke-tested the sandbox image on the VM
before the live run began.

## Result

Final controller summary:

- Total observed runtime: 3,975.42 seconds, about 1.10 hours
- Controller generations completed: 3
- Agents created: 3, plus the base agent
- Archive size: 4
- Successful improvements: 1
- Base score: `0.5416666666666666` (`13/24`)
- Best score: `0.7083333333333334` (`17/24`)
- Best delta from base: `+0.16666666666666674`
- Exit code: `0`

Loop-order score table:

| Loop | Agent | Parent | Score | Solved | Notes |
| ---: | --- | --- | ---: | ---: | --- |
| 0 | `9019e5ac` | `-` | `0.542` | 13/24 | Base |
| 1 | `d0130054` | `9019e5ac` | `0.542` | 13/24 | Tied base |
| 2 | `ce9ef80f` | `9019e5ac` | `0.708` | 17/24 | Top improvement |
| 3 | `5c099ed7` | `9019e5ac` | `0.458` | 11/24 | Regression |

The archive metadata labels all three child agents as generation `1` because
each child selected the base agent as parent. The controller progress log still
ran three requested generation attempts. This parent-selection behavior is a
follow-up investigation item: the third attempt did not build on the improved
second child.

Accepted best-score improvement:

| Child | Parent | Score movement | Added solved tasks | Regressions |
| --- | --- | ---: | --- | --- |
| `ce9ef80f` | `9019e5ac` | `13/24 -> 17/24` | `abc388_d`, `abc388_e`, `abc389_e`, `abc389_f` | None |

The best child kept all base-passing tasks and added four medium/hard tasks.
This is a real deterministic benchmark-score improvement inside the configured
DGM archive, not an LLM judge verdict.

## Score Details

Base agent solved:

```text
abc387_a, abc387_b, abc387_c,
abc388_a, abc388_b, abc388_c,
abc389_a, abc389_b, abc389_d,
abc390_a, abc390_b, abc390_c, abc390_e
```

Top agent solved:

```text
abc387_a, abc387_b, abc387_c,
abc388_a, abc388_b, abc388_c, abc388_d, abc388_e,
abc389_a, abc389_b, abc389_d, abc389_e, abc389_f,
abc390_a, abc390_b, abc390_c, abc390_e
```

Zero-score counts across the 4 archived agents:

| Benchmark | Zero-score count |
| --- | ---: |
| `livecodebench_abc387_c` | 2 |
| `livecodebench_abc387_f` | 4 |
| `livecodebench_abc388_d` | 3 |
| `livecodebench_abc388_e` | 1 |
| `livecodebench_abc388_f` | 4 |
| `livecodebench_abc388_g` | 4 |
| `livecodebench_abc389_d` | 1 |
| `livecodebench_abc389_e` | 3 |
| `livecodebench_abc389_f` | 3 |
| `livecodebench_abc389_g` | 4 |
| `livecodebench_abc390_c` | 1 |
| `livecodebench_abc390_d` | 4 |
| `livecodebench_abc391_d` | 4 |
| `livecodebench_abc392_d` | 4 |

## Telemetry

Provider and token summary:

- OpenRouter chat-completion POSTs: 302
- Usage events: 297
- Prompt tokens: 693,062
- Completion tokens: 222,888
- Total tokens: 915,950
- Estimated OpenRouter cost: `$1.292974`
- Timeout count: 5
- Empty/no-response count: 33
- Provider API errors: 0
- Max observed completion latency: 88.70 seconds
- Average observed completion latency: 10.68 seconds

Failure signals:

| Signal | Count |
| --- | ---: |
| Empty/no-response completions | 33 |
| Provider timeouts | 5 |
| Resource-guard rejections | 4 |
| Python tracebacks inside attempted solution commands | 2 |
| Provider API errors | 0 |

The dominant reliability pattern was not provider hard errors. It was
successful HTTP responses that consumed the 4,096-token completion cap while
producing no usable assistant content or no successful task completion, plus a
smaller number of 90-second provider timeouts and malformed tool-call argument
payloads.

## Artifacts

Committed compact artifacts:

- `exit_code`
- `plan.json`
- `preflight_commands.txt`
- `scorecard.json`
- `telemetry.json`

Durable raw artifacts were streamed to:

- `gs://dgm-live-runs-doittogether-prod/lcb24-cloud-20260628-2/controller.log`
- `gs://dgm-live-runs-doittogether-prod/lcb24-cloud-20260628-2/startup.log`
- `gs://dgm-live-runs-doittogether-prod/lcb24-cloud-20260628-2/scorecard.json`
- `gs://dgm-live-runs-doittogether-prod/lcb24-cloud-20260628-2/telemetry.json`
- `gs://dgm-live-runs-doittogether-prod/lcb24-cloud-20260628-2/preflight_commands.txt`
- `gs://dgm-live-runs-doittogether-prod/lcb24-cloud-20260628-2/exit_code`

Teardown proof:

```text
Deleted [https://www.googleapis.com/compute/v1/projects/doittogether-prod/zones/us-central1-a/instances/dgm-lcb24-cloud-20260628-2].
```

A follow-up `gcloud compute instances list` filtered to
`dgm-lcb24-cloud-20260628-2` returned no rows.

## Verification

Checks completed for this proof:

- Cloud VM creation: passed
- Fresh VM clone and exact commit checkout: passed
- LiveCodeBench segment generation on VM: passed
- Segment plan verification: passed
- Docker sandbox build and smoke test on VM: passed
- Cost gate under `$30`: passed
- Live OpenRouter DGM run: passed
- Continuous GCS artifact sync: passed
- Final artifact retrieval from GCS: passed via `gsutil`
- VM teardown: passed
- Exit code artifact: `0`

## Caveats

This is not a full LiveCodeBench leaderboard result. It is a DGM harness run
over a recognizable LiveCodeBench-derived AtCoder segment with local private
test scoring.

The first 24-problem cloud attempt (`lcb24-cloud-20260628-1`) failed the Docker
sandbox preflight and was not counted as a benchmark run. Commit
`55f80017acfb76f2fede73c92993396fd6068339` hardened the preflight by building
the sandbox image on the VM before the live run.

The telemetry file's `run.dgm_report` and `dgm_report` fields are not
authoritative for this card; the generated `dgm_report_*.json` was not copied
into final artifacts, and the summarizer found stale report metadata. Use the
committed `scorecard.json`, `telemetry.score`, `telemetry.tokens`,
`telemetry.provider`, the raw controller log in GCS, and `exit_code` as the
source of truth.

The observed score movement is real, but mutation quality remains weak. The
run exposed empty/no-response completions, malformed tool-call argument payloads,
timeouts, resource-guard rejections, and parent-selection behavior that did not
build on the improved child in the next attempt. Those are the next reliability
targets before simply scaling spend.
