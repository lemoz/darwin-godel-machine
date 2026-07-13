# Fable 5 mutator + Gemma 3 evaluator: 64-generation proof

This bundle records a completed four-worker DGM run in which
`anthropic/claude-fable-5` proposed constrained mutations and
`google/gemma-3-27b-it` evaluated the fixed 12-problem LiveCodeBench segment.
The source commit was `a3c68079c6cf03cc1bbf608ee963b569fd6354b7`.

## Result

- Four ephemeral GCP workers completed 16 generations each with exit code 0.
- The fleet produced 63 changed mutations and one no-op.
- Every worker found a 4/12 child from the calibrated 3.5/12 seed score.
- The improving children gained `livecodebench_abc387_b` with no benchmark
  regression relative to their parent.
- Improved children were selected as parents in later generations, proving
  descendant exploitation rather than repeated mutation of only the seeds.
- The fleet plateaued at 4/12. It did not reach the 9/12 target and did not
  solve a new hard problem. `abc387_b` is an easy-task reliability gain.
- Exact telemetry totals 5,516,394 model tokens and an estimated $14.847543:
  $14.481920 for Fable 5 and $0.365623 for Gemma 3.
- There were zero provider API errors, zero provider timeouts, and zero empty
  responses. Two logged non-provider errors recovered; all workers still
  completed normally.
- All four VMs were absent after the run, confirming teardown.

The result is a partial success for constrained mutation: it preserves the
protocol, produces valid edits reliably, and compounds an improvement. It also
shows that generic prompt mutations alone are insufficient to cross the
hard-task plateau. The next experiment should make mutations failure-aware and
target the repeated hidden-test failures on the hard tasks.

## Run identity

- Base run: `fablemut-gemma-evo-p16-20260712a`
- Workers: `w01` through `w04`
- Config: `config/livecodebench_fable5_mutator_gemma3_parallel16.yaml`
- Calibrated seed: `docs/live-runs/lcb-gemma3-calibrated-seed-20260712-1/`
- GCS prefix: `gs://dgm-live-runs-doittogether-prod/fablemut-gemma-evo-p16-20260712a/`
- Segment: `release_v6_atcoder_loop12` (12 problems, public examples plus
  private scored tests)

## Bundle contents

- `aggregate.json`: fleet-level result and per-worker metrics.
- `workers/w*/scorecard.json`: lineage and benchmark deltas.
- `workers/w*/telemetry.json`: token, cost, provider, and runtime evidence.
- `workers/w*/archive.tar.gz`: complete final archive for each worker.
- `workers/w*/exit_code`: worker process exit status.
- `checksums.sha256`: SHA-256 integrity manifest.
