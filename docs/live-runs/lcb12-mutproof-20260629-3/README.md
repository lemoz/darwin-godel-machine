# Mutation-proof cloud VM LiveCodeBench 12-loop DGM run - 2026-06-29

This directory records a completed mutation-proof DGM proof cycle on an
ephemeral GCP VM against a 12-problem LiveCodeBench-derived AtCoder segment. The
run requested 12 generations, cloned exact commit
`6c22c6d132ba09d36206898590e169e43d9e9809`, used real OpenRouter calls to
`moonshotai/kimi-k2.7-code`, streamed artifacts to GCS, exited with code `0`,
and deleted the VM at teardown.

The run did not produce an improved child. It did prove the new mutation proof
and early-abort lane: three consecutive no-op self-modifications were archived
as invalid, skipped for benchmark scoring, and stopped the run at generation 3
instead of spending all 12 requested loops.

## Command

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/run_live_eval_on_cloud_vm.py \
  --project doittogether-prod \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --run-id lcb12-mutproof-20260629-3 \
  --repo-url https://github.com/lemoz/darwin-godel-machine.git \
  --commit 6c22c6d132ba09d36206898590e169e43d9e9809 \
  --config config/livecodebench_openrouter_loop12_nonregression.yaml \
  --generations 12 \
  --secret OPENROUTER_API_KEY=openrouter-api-key \
  --artifact-dir .dgm-cloud-runs/lcb12-mutproof-20260629-3/artifacts \
  --startup-script-path .dgm-cloud-runs/lcb12-mutproof-20260629-3/startup.sh \
  --output .dgm-cloud-runs/lcb12-mutproof-20260629-3/plan.json \
  --gcs-artifact-uri gs://dgm-live-runs-doittogether-prod/lcb12-mutproof-20260629-3 \
  --fm-provider openrouter \
  --model moonshotai/kimi-k2.7-code \
  --input-price-per-mtok 0.74 \
  --output-price-per-mtok 3.50 \
  --execute
```

The cost gate used the configured OpenRouter prices in
`config/livecodebench_openrouter_loop12_nonregression.yaml`: `$0.74/MTok` prompt
and `$3.50/MTok` completion. The retry-inclusive preflight estimate was capped
under `$85`.

## Scope

- Segment config: `config/livecodebench_segment_loop12.yaml`
- Live run config: `config/livecodebench_openrouter_loop12_nonregression.yaml`
- Segment ID: `release_v6_atcoder_loop12`
- Benchmark source: LiveCodeBench `code_generation_lite`
- Source dataset: `https://huggingface.co/datasets/livecodebench/code_generation_lite`
- Upstream project: `https://github.com/livecodebench/livecodebench`
- Problem count: 12
- Scoring: public examples in prompts, private tests included in deterministic scoring
- Model: `moonshotai/kimi-k2.7-code` through OpenRouter
- Provider base URL: `https://openrouter.ai/api/v1`
- OpenRouter timeout: 60 seconds
- Timeout retries: 1
- Timeout retry delay: 1 second
- Max completion tokens: 2,048
- Generations requested: 12
- Max consecutive no-op mutations: 3
- Max model turns per task: 5
- Cloud project: `doittogether-prod`
- Cloud zone: `us-central1-a`
- Machine type: `n2-standard-8`
- VM name: `dgm-lcb12-mutproof-20260629-3`

VM-side preflight commands:

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/prepare_livecodebench_segment.py --config config/livecodebench_segment_loop12.yaml
PATH="$PWD/.venv/bin:$PATH" python scripts/verify_sandbox_docker.py --build-image --require
PATH="$PWD/.venv/bin:$PATH" python scripts/estimate_live_run_cost.py --config config/livecodebench_openrouter_loop12_nonregression.yaml --input-price-per-mtok 0.74 --output-price-per-mtok 3.50 --assumed-input-tokens-per-call 50000 --max-budget 85
```

## Result

Final controller summary:

- Exit code: `0`
- Observed runtime: `1,704.749` seconds, about `0.47` hours
- Controller generations completed: 3
- Stop reason: consecutive no-op mutation limit, `3/3`
- Valid agents: 1
- Archived agents: 4
- Invalid no-op children: 3
- Changed children: 0
- Successful improvements: 0
- Base score: `0.3333333333333333` (`4/12`)
- Best score: `0.3333333333333333` (`4/12`)
- Best delta from base: `0`
- Estimated provider cost from logged usage: `$0.120101`

Loop-order table:

| Loop | Agent | Parent | Status | Score | Solved | Notes |
| ---: | --- | --- | --- | ---: | ---: | --- |
| 0 | `1c67073d` | `-` | valid base | `0.333` | 4/12 | Final top agent |
| 1 | `caa81061` | `1c67073d` | invalid no-op | `0.000` | 0/0 | No code changes; skipped evaluation |
| 2 | `f479a21b` | `1c67073d` | invalid no-op | `0.000` | 0/0 | No code changes; skipped evaluation |
| 3 | `070d9f6f` | `1c67073d` | invalid no-op | `0.000` | 0/0 | No code changes; triggered early stop |

Base agent solved:

```text
livecodebench_abc387_b
livecodebench_abc388_b
livecodebench_abc389_d
livecodebench_abc390_b
```

Base agent zero-scored:

```text
livecodebench_abc387_c
livecodebench_abc388_c
livecodebench_abc388_d
livecodebench_abc388_e
livecodebench_abc389_a
livecodebench_abc389_e
livecodebench_abc390_d
livecodebench_abc390_e
```

## Mutation Proof

Each no-op child includes `.dgm_metadata/mutation.json` and
`.dgm_metadata/mutation.patch` inside `archive.tar.gz`.

Mutation summary:

- `mutation_summary.status_counts.noop`: 3
- `mutation_summary.changed_count`: 0
- `mutation_summary.unknown_count`: 0
- Each no-op child has `has_changes: false`
- Each no-op child has `has_code_changes: false`
- Each no-op child has `changed_files: []`
- Each no-op child has `changed_code_files: []`
- Each no-op child has empty patch SHA
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Each no-op child has the same parent and child tree SHA:
  `1d4a8d908dc7cdfe55d47fe73a9b4935f7aa38805c2a0189ebfda4b86c9c93b2`

That means the no-op children were real archived artifacts, but they were not
counted as evaluated candidate improvements.

## Provider Behavior

The run completed, but Kimi/OpenRouter behavior was noisy enough to dominate the
score:

| Metric | Value |
| --- | ---: |
| HTTP POSTs | 54 |
| Usage events | 37 |
| Prompt tokens | 92,384 |
| Completion tokens | 14,782 |
| Total tokens | 107,166 |
| Estimated cost | `$0.120101` |
| Provider timeouts | 17 |
| Empty/no-response completions | 9 |
| Finish reasons counted as `length` | 9 |
| Provider API errors | 0 |
| Tracebacks | 0 |

Several benchmark attempts timed out after receiving HTTP 200, and one task
burned repeated 2,048-token completions almost entirely as reasoning tokens with
no visible answer. This run is therefore a strong signal that the next quality
cycle should tune provider/model settings before scaling Kimi runs.

## Setup Attempts

Two setup attempts were not counted as benchmark runs:

- `lcb12-mutproof-20260629-1`: failed before DGM because the fresh VM ran
  `verify_sandbox_docker.py --require` without `--build-image`.
- `lcb12-mutproof-20260629-2`: failed before DGM because the launch command used
  a malformed full commit SHA.

The counted run is `lcb12-mutproof-20260629-3`, launched after commit
`6c22c6d132ba09d36206898590e169e43d9e9809` fixed the fresh-VM sandbox image
preflight.

## Artifacts

Committed compact artifacts:

- `archive.tar.gz`
- `exit_code`
- `plan.json`
- `preflight_commands.txt`
- `scorecard.json`
- `telemetry.json`

Durable raw artifacts were streamed to:

- `gs://dgm-live-runs-doittogether-prod/lcb12-mutproof-20260629-3/archive.tar.gz`
- `gs://dgm-live-runs-doittogether-prod/lcb12-mutproof-20260629-3/controller.log`
- `gs://dgm-live-runs-doittogether-prod/lcb12-mutproof-20260629-3/startup.log`
- `gs://dgm-live-runs-doittogether-prod/lcb12-mutproof-20260629-3/scorecard.json`
- `gs://dgm-live-runs-doittogether-prod/lcb12-mutproof-20260629-3/telemetry.json`
- `gs://dgm-live-runs-doittogether-prod/lcb12-mutproof-20260629-3/preflight_commands.txt`
- `gs://dgm-live-runs-doittogether-prod/lcb12-mutproof-20260629-3/exit_code`

Local raw artifacts are under:

```text
.dgm-cloud-runs/lcb12-mutproof-20260629-3/artifacts/
```

Teardown proof:

```text
Deleted [https://www.googleapis.com/compute/v1/projects/doittogether-prod/zones/us-central1-a/instances/dgm-lcb12-mutproof-20260629-3].
```

A follow-up `gcloud compute instances describe` for
`dgm-lcb12-mutproof-20260629-3` returned `resource not found`.

## Verification

Checks completed for this proof:

- Cloud VM creation: passed
- Fresh VM clone and exact commit checkout: passed
- LiveCodeBench segment generation on VM: passed
- Docker sandbox build and smoke test on VM: passed
- Cost gate under `$85`: passed
- Live OpenRouter DGM run: passed
- Mutation metadata written for invalid no-op children: passed
- No-op children skipped for benchmark evaluation: passed
- Consecutive no-op early stop at 3: passed
- Continuous GCS artifact sync: passed
- Final artifact retrieval: passed
- VM teardown: passed
- Exit code artifact: `0`

## Caveats

This is not a proof that DGM improved on LiveCodeBench. It is a proof that the
cloud runner, real benchmark segment, mutation accounting, no-op quarantine, and
early stop all work together on a live provider-backed run.

The next WDSLL-relevant cycle should focus on making self-modification produce
real code changes and making provider settings stable enough that score changes
reflect agent quality rather than timeouts or hidden reasoning-token exhaustion.
