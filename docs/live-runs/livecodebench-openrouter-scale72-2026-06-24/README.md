# LiveCodeBench OpenRouter scale-72 run - 2026-06-24

This directory records a live, sandboxed DGM run against a generated
72-problem LiveCodeBench code-generation segment. The run used real OpenRouter
calls to `moonshotai/kimi-k2.7-code`, completed three DGM generations per
shard, and aggregated three 24-problem shards.

## Command

```bash
OPENROUTER_API_KEY=<redacted> PATH="$PWD/.venv/bin:$PATH" \
  python -u scripts/run_livecodebench_shards.py \
  --config config/livecodebench_openrouter_scale72.yaml \
  --execute \
  --resume \
  --generations 3 \
  --allow-network \
  --env OPENROUTER_API_KEY \
  --timeout 10800
```

The runtime output directory is `.dgm-live-runs/livecodebench-openrouter-scale72/`.
That directory remains ignored by git. This proof directory commits normalized
scorecards only.

## Scope

- Segment config: `config/livecodebench_segment_scale72.yaml`
- Live run config: `config/livecodebench_openrouter_scale72.yaml`
- Segment ID: `release_v6_atcoder_balanced_72`
- Benchmark source: LiveCodeBench `code_generation_lite`
- Source file: `test6.jsonl`
- Problem count: 72
- Difficulty split: 24 easy, 24 medium, 24 hard
- Generated scored tests: 3,034
- Generated private tests: 2,834
- Prompt examples: public tests only
- Scored tests: public and private tests
- Model: `moonshotai/kimi-k2.7-code` through OpenRouter
- Generations: 3 per shard
- Max model turns per task: 5
- Shards: 3 shards, 24 benchmarks each
- Full-process runner: Docker sandbox with network enabled for provider calls

## Cost Gate

OpenRouter pricing was checked on 2026-06-24 before the run:

- Input price: `$0.74 / MTok`
- Output price: `$3.50 / MTok`
- Request ceiling: 1,455
- Assumed input tokens per call: 50,000
- Max output tokens per call: 4,096
- Estimated ceiling: `$74.6939`
- Configured max budget: `$90.0000`

Pricing source recorded in the config:
`https://openrouter.ai/api/v1/models`.

## Result

Post-run aggregate command:

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/run_livecodebench_shards.py \
  --config config/livecodebench_openrouter_scale72.yaml \
  --aggregate-only
```

Aggregate scorecard summary:

- Completed shards: 3 of 3
- Weighted base score: `0.625` (`45/72`)
- Weighted best shard score: `0.625` (`45/72`)
- Weighted delta: `+0.000`

| Shard | Benchmarks | Base score | Top score | Best parent-child delta | Improvement? | Regression? |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `shard-01` | 24 | `0.5416666666666666` | `0.5416666666666666` | `+0.08333333333333331` | yes | yes |
| `shard-02` | 24 | `0.7083333333333334` | `0.7083333333333334` | `0.0` | no | yes |
| `shard-03` | 24 | `0.625` | `0.625` | `-0.04166666666666663` | no | yes |

The weighted best shard score is a shard-portfolio aggregate, not a single
agent evaluated across all 72 problems. The run did not beat the weighted base
score overall. Shard 1 did contain one successful parent-child improvement:
`d07f14f1-e5bf-4d1d-befa-4c0ad7dd5cbe` improved from `0.4583333333333333`
to `0.5416666666666666`, adding passes for `livecodebench_abc389_d`,
`livecodebench_abc390_c`, and `livecodebench_abc390_e` while regressing
`livecodebench_abc388_d`.

Machine-readable details are in `aggregate_scorecard.json` and
`shards_summary.json`.

## Verification

Preflight and verification commands run for this cycle:

- `PATH="$PWD/.venv/bin:$PATH" python scripts/prepare_livecodebench_segment.py --config config/livecodebench_segment_scale72.yaml`
- `PATH="$PWD/.venv/bin:$PATH" python scripts/verify_livecodebench_segment_plan.py --config config/livecodebench_openrouter_scale72.yaml --require-generated`
- `PATH="$PWD/.venv/bin:$PATH" python scripts/verify_sandbox_docker.py --require`
- `PATH="$PWD/.venv/bin:$PATH" python scripts/estimate_live_run_cost.py --config config/livecodebench_openrouter_scale72.yaml --input-price-per-mtok 0.74 --output-price-per-mtok 3.50 --assumed-input-tokens-per-call 50000 --max-budget 90`
- `PATH="$PWD/.venv/bin:$PATH" python scripts/run_livecodebench_shards.py --config config/livecodebench_openrouter_scale72.yaml --plan-only`
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/unit/test_agent.py tests/unit/test_tools.py tests/unit/test_run_livecodebench_shards.py tests/unit/test_verify_livecodebench_segment_plan.py tests/unit/test_prepare_livecodebench_segment.py tests/unit/test_openai_compatible_provider.py -q`

Focused pytest result after the live run:

- `80 passed, 1 warning`

Full pytest result after the live run:

- `286 passed, 7 skipped, 2 warnings`

## Caveats

This proves a fully live, sharded 72-problem DGM run on a bounded
LiveCodeBench segment. It is not a full LiveCodeBench leaderboard result, and
each shard is an independent shard-local DGM run.

The result is also a useful negative result: the scaled run did not produce
aggregate improvement. The most important next harness work is to prevent
benchmark-objective selection from promoting regressed children, because every
shard observed regressions. Repeated OpenRouter 90-second provider timeouts and
4,096-token completions also limited hard tasks. One OpenRouter-compatible tool
call arrived with wrapped arguments and had to be corrected by the model on the
next step.
