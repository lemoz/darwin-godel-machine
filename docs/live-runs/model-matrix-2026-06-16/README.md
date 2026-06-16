# Live model matrix run - 2026-06-16

This directory records the first committed live model-matrix evidence artifact
for the repository. The run used real provider calls through the Docker sandbox
runner and completed five trials each for Claude Sonnet 4.6 and Kimi K2.7 Code
through OpenRouter.

## Command

```bash
OPENROUTER_API_KEY=<redacted> .venv/bin/python scripts/run_model_matrix.py \
  --execute \
  --allow-network \
  --run-dir .dgm-live-runs/model-matrix-2026-06-16 \
  --audit-dir .dgm-sandbox-runs/model-matrix-2026-06-16 \
  --json
```

`ANTHROPIC_API_KEY` was already present in the local environment. The
OpenRouter key value was recovered from a private local backup file, validated
with OpenRouter's key endpoint, and was not committed.

## Scope

- Matrix config: `config/live_model_matrix.yaml`
- Base live-run config: `config/live_score_movement.yaml`
- Benchmark: `humaneval_calibrated`
- Models: 2
- Trials per model: 5
- Generations per trial: 2
- Total completed trials: 10 of 10
- Total request ceiling: 250
- Runtime output directory: `.dgm-live-runs/model-matrix-2026-06-16/`
- Sandbox audit directory: `.dgm-sandbox-runs/model-matrix-2026-06-16/`

The runtime directories remain ignored by git. This directory commits the stable
proof materials: aggregate summary, normalized scorecards, and redacted sandbox
audits.

## Cost Gate

The matrix runner produced a pre-run estimate of `$28.1735` against a configured
maximum of `$30.0000`.

| Model | Trials | Estimate per trial | Estimate total |
| --- | ---: | ---: | ---: |
| `claude-sonnet-4-6` | 5 | `$4.5180` | `$22.5900` |
| `moonshotai/kimi-k2.7-code` | 5 | `$1.1167` | `$5.5835` |

OpenRouter key metadata was checked before and after the OpenRouter leg. The
observed OpenRouter usage delta was `$0.280637273`. Anthropic invoice-grade
usage was not measured in this artifact; the committed Anthropic number is the
runner's conservative estimate.

## Result

| Model ID | Provider | Trials | Top scores | Mean top score | Improvement trials | Regression trials |
| --- | --- | ---: | --- | ---: | --- | --- |
| `claude-sonnet-4-6` | `anthropic` | 5 | `0.88, 0.88, 0.88, 0.88, 0.88` | `0.88` | 1 | 0 |
| `kimi-k2.7-code-openrouter` | `openai_compatible` | 5 | `0.92, 0.92, 0.92, 0.92, 0.92` | `0.92` | 0 | 3 |

Trial-level scorecard summary:

| Trial | Top score | Best average delta | Improvement | Regression |
| --- | ---: | ---: | --- | --- |
| `claude-sonnet-4-6-trial-01` | `0.88` | `0.88` | yes | no |
| `claude-sonnet-4-6-trial-02` | `0.88` | `0.00` | no | no |
| `claude-sonnet-4-6-trial-03` | `0.88` | `0.00` | no | no |
| `claude-sonnet-4-6-trial-04` | `0.88` | `0.00` | no | no |
| `claude-sonnet-4-6-trial-05` | `0.88` | `0.00` | no | no |
| `kimi-k2-7-code-openrouter-trial-01` | `0.92` | `0.00` | no | no |
| `kimi-k2-7-code-openrouter-trial-02` | `0.92` | `0.00` | no | yes |
| `kimi-k2-7-code-openrouter-trial-03` | `0.92` | `0.00` | no | no |
| `kimi-k2-7-code-openrouter-trial-04` | `0.92` | `0.00` | no | yes |
| `kimi-k2-7-code-openrouter-trial-05` | `0.92` | `-0.02` | no | yes |

Machine-readable details are in `summary.json`. Per-trial scorecards are in
`scorecards/`, and per-trial sandbox audits are in `audits/`.

## Evidence Notes

- All 10 trials exited successfully.
- All 10 scorecards reported 3 valid agents out of 3 total agents.
- All 10 sandbox audits recorded `env_values` as `hidden`.
- The audit files record environment variable names only:
  `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY`.
- Copied scorecards normalize `archive_metadata` to repo-relative ignored
  runtime paths instead of local absolute paths.
- Planner live calls remained at 0; provider calls happened only during the
  explicit `--execute --allow-network` run.

## Caveats

The scorecard `has_improvement` and `best_average_delta` fields describe
parent-child movement inside each isolated DGM run. They should not be read as a
cross-model ranking by themselves.

Kimi produced a higher top score than Claude in this matrix (`0.92` vs `0.88`),
but three of five Kimi trials also had parent-child regression flags and none had
a positive improvement trial. Claude was lower-scoring in this run but stable:
five of five trials ended at `0.88` with no regression flags.

This proves the live multi-provider matrix path executes under the sandbox and
produces reviewable scorecards. It does not prove unattended autonomous
improvement is ready for larger budgets.
