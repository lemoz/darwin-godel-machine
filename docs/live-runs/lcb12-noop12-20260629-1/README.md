# No-op-12 cloud VM LiveCodeBench DGM run - 2026-06-29

This directory records a follow-up live DGM run on an ephemeral GCP VM. The
experiment tested the simple recovery hypothesis that the previous no-op-3
proof stopped too early, so the same Kimi/OpenRouter LiveCodeBench lane was run
with the consecutive no-op mutation ceiling raised from `3` to `12`.

The result was negative for that hypothesis: all 12 self-modification attempts
were mutation-proven no-ops. The run completed cleanly, deleted the VM, and
preserved artifacts, but it produced no changed child, no validated child, and
no benchmarked improvement.

## Command

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/run_live_eval_on_cloud_vm.py \
  --project doittogether-prod \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --run-id lcb12-noop12-20260629-1 \
  --repo-url https://github.com/lemoz/darwin-godel-machine.git \
  --commit c5c8c0daff138cc899f953ddabd3f4159f44e6a9 \
  --config config/livecodebench_openrouter_loop12_noop12.yaml \
  --generations 12 \
  --secret OPENROUTER_API_KEY=openrouter-api-key \
  --artifact-dir .dgm-cloud-runs/lcb12-noop12-20260629-1/artifacts \
  --startup-script-path .dgm-cloud-runs/lcb12-noop12-20260629-1/startup.sh \
  --output .dgm-cloud-runs/lcb12-noop12-20260629-1/plan.json \
  --gcs-artifact-uri gs://dgm-live-runs-doittogether-prod/lcb12-noop12-20260629-1 \
  --fm-provider openrouter \
  --model moonshotai/kimi-k2.7-code \
  --input-price-per-mtok 0.74 \
  --output-price-per-mtok 3.50 \
  --execute
```

The run used current OpenRouter model metadata checked on 2026-06-29:
`moonshotai/kimi-k2.7-code` at `$0.74/MTok` prompt and `$3.50/MTok`
completion. The retry-inclusive preflight estimate remained `$74.2022`, under
the configured `$85` cap.

## Scope

- Segment config: `config/livecodebench_segment_loop12.yaml`
- Live run config: `config/livecodebench_openrouter_loop12_noop12.yaml`
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
- Max completion tokens: 2,048
- Generations requested: 12
- Max consecutive no-op mutations: 12
- Max model turns per task: 5
- Cloud project: `doittogether-prod`
- Cloud zone: `us-central1-a`
- Machine type: `n2-standard-8`
- VM name: `dgm-lcb12-noop12-20260629-1`

VM-side preflight commands:

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/prepare_livecodebench_segment.py --config config/livecodebench_segment_loop12.yaml
PATH="$PWD/.venv/bin:$PATH" python scripts/verify_sandbox_docker.py --build-image --require
PATH="$PWD/.venv/bin:$PATH" python scripts/estimate_live_run_cost.py --config config/livecodebench_openrouter_loop12_noop12.yaml --input-price-per-mtok 0.74 --output-price-per-mtok 3.50 --assumed-input-tokens-per-call 50000 --max-budget 85
```

## Result

Final controller summary:

- Exit code: `0`
- Observed runtime: `1,547.883` seconds, about `0.43` hours
- Controller generations completed: 12
- Stop reason: consecutive no-op mutation limit, `12/12`
- Valid agents: 1
- Archived agents: 13
- Invalid no-op children: 12
- Changed children: 0
- Successful improvements: 0
- Base score: `0.500` (`6/12`)
- Best score: `0.500` (`6/12`)
- Best delta from base: `0`
- Estimated provider cost from logged usage: `$0.294671`

Base agent solved:

```text
livecodebench_abc387_b
livecodebench_abc388_b
livecodebench_abc388_c
livecodebench_abc388_e
livecodebench_abc389_a
livecodebench_abc390_b
```

Base agent zero-scored:

```text
livecodebench_abc387_c
livecodebench_abc388_d
livecodebench_abc389_d
livecodebench_abc389_e
livecodebench_abc390_d
livecodebench_abc390_e
```

## Mutation Proof

Each invalid child includes `.dgm_metadata/mutation.json` and
`.dgm_metadata/mutation.patch` inside `archive.tar.gz`.

Mutation summary:

- `mutation_summary.status_counts.noop`: 12
- `mutation_summary.changed_count`: 0
- `mutation_summary.unknown_count`: 0
- Each no-op child has `has_changes: false`
- Each no-op child has `has_code_changes: false`
- Each no-op child has `changed_files: []`
- Each no-op child has `changed_code_files: []`
- Each sampled no-op child had empty patch SHA
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Each sampled no-op child had identical parent and child tree SHA:
  `1d4a8d908dc7cdfe55d47fe73a9b4935f7aa38805c2a0189ebfda4b86c9c93b2`

The child artifacts are real archived attempts, but none changed agent Python
source, so none were validated or benchmarked as candidate improvements.

## Provider Behavior

The run completed, but provider/model behavior remained noisy:

| Metric | Value |
| --- | ---: |
| HTTP POSTs | 105 |
| Usage events | 94 |
| Prompt tokens | 298,634 |
| Completion tokens | 21,052 |
| Total tokens | 319,686 |
| Estimated cost | `$0.294671` |
| Provider timeouts | 11 |
| Empty/no-response completions | 14 |
| Provider API errors | 0 |
| Tracebacks | 0 |

Several hard benchmark attempts timed out or spent 2,048 completion tokens
mostly as hidden reasoning with no visible answer. During self-modification,
Kimi repeatedly spent the five available agent turns on `ls`, `find`, and file
reads such as `agent.py`, `tools/bash_tool.py`, and
`fm_interface/message_formatter.py`. It also repeatedly tried shell commands
with `&&`, which the bash tool blocked. No self-mod attempt reached a Python
source write.

## Conclusion

Raising `max_consecutive_noop_mutations` from `3` to `12` was not enough. The
binding problem is not the early stop threshold. The next WDSLL-relevant cycle
should make self-modification produce an edit before scaling loops again:

- add a model/settings smoke matrix for Chinese OpenRouter candidates such as
  Kimi, GLM 5.2, and Qwen3 Coder;
- force or scaffold an early self-mod edit instead of allowing all five turns to
  be spent on discovery;
- feed richer failure and mutation context into the self-mod prompt;
- keep deterministic benchmark scoring as the judge, with LLM review only as an
  advisory audit.

## Artifacts

Committed compact artifacts:

- `archive.tar.gz`
- `exit_code`
- `plan.json`
- `preflight_commands.txt`
- `scorecard.json`
- `telemetry.json`

Durable raw artifacts were streamed to:

- `gs://dgm-live-runs-doittogether-prod/lcb12-noop12-20260629-1/archive.tar.gz`
- `gs://dgm-live-runs-doittogether-prod/lcb12-noop12-20260629-1/controller.log`
- `gs://dgm-live-runs-doittogether-prod/lcb12-noop12-20260629-1/startup.log`
- `gs://dgm-live-runs-doittogether-prod/lcb12-noop12-20260629-1/scorecard.json`
- `gs://dgm-live-runs-doittogether-prod/lcb12-noop12-20260629-1/telemetry.json`
- `gs://dgm-live-runs-doittogether-prod/lcb12-noop12-20260629-1/preflight_commands.txt`
- `gs://dgm-live-runs-doittogether-prod/lcb12-noop12-20260629-1/exit_code`

Local raw artifacts are under:

```text
.dgm-cloud-runs/lcb12-noop12-20260629-1/artifacts/
```

Teardown proof:

```text
Deleted [https://www.googleapis.com/compute/v1/projects/doittogether-prod/zones/us-central1-a/instances/dgm-lcb12-noop12-20260629-1].
```

## Verification

Checks completed for this proof:

- Cloud VM creation: passed
- Fresh VM clone and exact commit checkout: passed
- LiveCodeBench segment generation on VM: passed
- Docker sandbox build and smoke test on VM: passed
- Cost gate under `$85`: passed
- Live OpenRouter DGM run: passed
- Twelve no-op mutation artifacts written: passed
- No-op children skipped for benchmark evaluation: passed
- Consecutive no-op stop at 12: passed
- Continuous GCS artifact sync: passed
- Final artifact retrieval: passed
- VM teardown: passed
- Exit code artifact: `0`
