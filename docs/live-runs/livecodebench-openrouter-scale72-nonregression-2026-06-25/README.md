# LiveCodeBench OpenRouter scale-72 non-regression shard run - 2026-06-25

This directory records a live DGM run against shard 1 of the generated
72-problem LiveCodeBench code-generation segment. The run used real OpenRouter
calls to `moonshotai/kimi-k2.7-code`, completed the base evaluation and one
self-modification generation, and kept the best tracked score at the base
parent under the non-regression scorecard.

## Command

```bash
OPENROUTER_API_KEY=<redacted> PATH="$PWD/.venv/bin:$PATH" \
  python -u scripts/run_livecodebench_shards.py \
  --config config/livecodebench_openrouter_scale72_nonregression.yaml \
  --execute \
  --resume \
  --max-shards 1 \
  --generations 1 \
  --allow-network \
  --env OPENROUTER_API_KEY \
  --timeout 10800
```

The runtime output directory is
`.dgm-live-runs/livecodebench-openrouter-scale72-nonregression/`. That directory
remains ignored by git. This proof directory commits normalized scorecards and
the final DGM report for the completed shard.

## Scope

- Segment config: `config/livecodebench_segment_scale72.yaml`
- Live run config: `config/livecodebench_openrouter_scale72_nonregression.yaml`
- Segment ID: `release_v6_atcoder_balanced_72`
- Benchmark source: LiveCodeBench `code_generation_lite`
- Source dataset: `https://huggingface.co/datasets/livecodebench/code_generation_lite`
- Upstream project: `https://github.com/livecodebench/livecodebench`
- Planned benchmark count: 72
- Executed shard: `shard-01`
- Executed benchmark count: 24
- Prompt examples: public tests only
- Scored tests: public and private tests
- Model: `moonshotai/kimi-k2.7-code` through OpenRouter
- Generations completed: 1
- Max model turns per task: 5
- Full-process runner: Docker sandbox with network enabled for provider calls

## Result

Post-run aggregate summary:

```text
[ok] shard-01 top_score=0.542 best_delta=-0.042 improvements=0
[ok] aggregate status=partial completed=1/3 weighted_base=0.542 weighted_best=0.542 delta=+0.000
```

Shard scorecard summary:

- Base agent: `b899a99f-377a-47b5-86c5-d89eda3e3e8b`
- Base score: `0.5416666666666666` (`13/24`)
- Generation 1 child: `34e0ad9e-64e9-4fc2-a087-400741446cae`
- Generation 1 score: `0.5` (`12/24`)
- Best average delta: `-0.04166666666666663`
- Successful improvements: `0`
- Top tracked agent: base agent
- Runtime: `0.82887012` hours

Parent-child movement:

| Benchmark movement | Count | Details |
| --- | ---: | --- |
| Improvements | 1 | `livecodebench_abc389_d`: `0.0 -> 1.0` |
| Regressions | 2 | `livecodebench_abc388_e`: `1.0 -> 0.0`; `livecodebench_abc390_e`: `1.0 -> 0.0` |
| Unchanged | 21 | See `shard-01-scorecard.json` |

The child was archived as a valid generation 1 agent, but its metadata records
`selection_non_regression_eligible: false`. The aggregate scorecard therefore
keeps `weighted_best_shard_score` equal to the base score.

Machine-readable details are in:

- `aggregate_scorecard.json`
- `shard-01-scorecard.json`
- `dgm_report_20260625_101503.json`

## Resource Proof

This run crossed the two previous hard-failure points in both the base pass and
generation 1 without Docker exit 137:

| Pass | Benchmark | Score |
| --- | --- | ---: |
| Base | `livecodebench_abc388_d` | `0.000` |
| Base | `livecodebench_abc390_d` | `0.000` |
| Generation 1 | `livecodebench_abc388_d` | `0.000` |
| Generation 1 | `livecodebench_abc390_d` | `0.000` |

During polling, sampled container memory stayed in the roughly 138-158 MiB
range. The successful run did not exercise the static subset-DP guard on
`abc390_d`; the model timed out before emitting that dangerous solution shape in
this run. The static guard is covered by unit tests, and this live run proves
the outer DGM process can now complete the shard instead of dying at those
benchmarks.

## Verification

Verification commands run after the live run:

- `git diff --check`
- `PATH="$PWD/.venv/bin:$PATH" python scripts/verify_sandbox_docker.py --require`
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest -q`

Results:

- `git diff --check`: passed
- Docker sandbox smoke: passed
- Full pytest: `301 passed, 7 skipped, 2 warnings`

## Caveats

This is a partial scale-72 proof: one completed 24-problem shard out of the
planned three shards. The aggregate scorecard is therefore `partial`, and its
weighted score is only for the completed shard.

This is not a full LiveCodeBench leaderboard result. It is a local DGM harness
run over a recognizable LiveCodeBench-derived segment with private tests in the
local scoring path.

Many later hard tasks were limited by provider behavior: the model often
returned 4,096-token completions with no usable response or hit the configured
90-second OpenRouter-compatible timeout. That is part of the model/runtime
evidence, not a harness pass claim.
