# LiveCodeBench OpenRouter segment run - 2026-06-24

This directory records a live, sandboxed DGM run against a generated
LiveCodeBench code-generation segment. The run used real OpenRouter calls to
`moonshotai/kimi-k2.7-code` and completed three DGM generations.

## Command

```bash
OPENROUTER_API_KEY=<redacted> PATH="$PWD/.venv/bin:$PATH" \
  python scripts/run_dgm_in_sandbox.py \
  --config config/livecodebench_openrouter_segment.yaml \
  --generations 3 \
  --allow-network \
  --env OPENROUTER_API_KEY \
  --timeout 7200 \
  --audit-output .dgm-sandbox-runs/livecodebench-openrouter-segment-audit.json
```

The runtime output directory is `.dgm-live-runs/livecodebench-openrouter-segment/`.
That directory remains ignored by git. This proof directory commits the stable
scorecard only.

## Scope

- Segment config: `config/livecodebench_segment.yaml`
- Live run config: `config/livecodebench_openrouter_segment.yaml`
- Segment ID: `release_v6_atcoder_balanced_24`
- Benchmark source: LiveCodeBench `code_generation_lite`
- Problem count: 24
- Generated scored tests: 1,025
- Generated private tests: 960
- Prompt examples: public tests only
- Scored tests: public and private tests
- Model: `moonshotai/kimi-k2.7-code` through OpenRouter
- Generations: 3
- Max model turns per task: 5
- Full-process runner: Docker sandbox with network enabled for provider calls

## Cost Gate

OpenRouter pricing was checked on 2026-06-24 before the run:

- Input price: `$0.74 / MTok`
- Output price: `$3.50 / MTok`
- Request ceiling: 495
- Assumed input tokens per call: 50,000
- Max output tokens per call: 4,096
- Estimated ceiling: `$25.4113`
- Configured max budget: `$30.0000`

The free OpenRouter `qwen/qwen3-coder:free` canary was attempted first but hit
upstream rate limiting. The run then used paid Kimi K2.7 Code.

## Result

Post-run scorecard command:

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/summarize_archive_scores.py \
  --archive-metadata .dgm-live-runs/livecodebench-openrouter-segment/archive/archive_metadata.json \
  --output .dgm-live-runs/livecodebench-openrouter-segment/scorecard.json \
  --require-improvement
```

Scorecard summary:

- Valid agents: 4 of 4
- Best score: `0.4583333333333333` (`11/24`)
- Base score: `0.375` (`9/24`)
- Best parent-child average-score delta: `+0.08333333333333331`
- Successful improvements: 1

| Generation | Agent ID | Score |
| --- | --- | ---: |
| 0 | `430e16c0-9bb7-45d2-b507-96631aef1a93` | `0.375` |
| 1 | `dc548800-00e3-4185-958a-c23db6aafec6` | `0.375` |
| 2 | `5cf1f383-a634-47cd-90c3-d8183990b0ee` | `0.4583333333333333` |
| 3 | `ee6c0494-1f65-4c30-95ff-980b207b08cd` | `0.4166666666666667` |

The generation 2 child improved over its generation 1 parent by recovering
`livecodebench_abc390_b` and adding `livecodebench_abc390_e`, with no benchmark
regressions relative to that parent. Generation 3 found a different hard pass
(`livecodebench_abc388_e`) but regressed other cases, so generation 2 remained
the top archived agent.

Machine-readable details are in `scorecard.json`.

## Verification

Preflight and verification commands run for this cycle:

- `python scripts/prepare_livecodebench_segment.py --config config/livecodebench_segment.yaml`
- `python scripts/verify_livecodebench_segment_plan.py --config config/livecodebench_openrouter_segment.yaml --require-generated`
- `python scripts/verify_sandbox_docker.py --require`
- `python scripts/estimate_live_run_cost.py --config config/livecodebench_openrouter_segment.yaml --input-price-per-mtok 0.74 --output-price-per-mtok 3.50 --assumed-input-tokens-per-call 50000 --max-budget 30`
- `python -m pytest`

Full pytest result after the live run:

- `277 passed, 7 skipped, 2 warnings`

## Caveats

This proves live score improvement on a bounded 24-problem LiveCodeBench
segment, not a full LiveCodeBench leaderboard result. The segment is generated
from known LiveCodeBench data and includes private tests in scoring, but the
run is still a local DGM harness evaluation.

Several harness limits remain visible: models sometimes wrote `solve.py` rather
than `solution.py`, shell safety blocked common pipe and semicolon test commands,
and medium/hard tasks often consumed the provider timeout. Those are good next
targets before scaling to larger segments.
