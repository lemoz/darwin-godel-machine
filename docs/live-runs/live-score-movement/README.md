# Live score-movement rehearsal

Run date: 2026-06-15

This was a bounded live DGM run for `config/live_score_movement.yaml`. It was
intended to prove that the cost-gated, full-process Docker runner can execute a
real provider-backed DGM cycle against `humaneval_style` and then fail closed if
there is no parent-child score improvement.

Preflight gates passed before the live call:

- `python -m pytest`: 225 passed, 7 skipped
- `python scripts/verify_demo_path.py`
- `python scripts/verify_sandbox_docker.py --require`
- `python scripts/verify_live_score_movement_plan.py`
- `python scripts/estimate_live_run_cost.py --input-price-per-mtok 3 --output-price-per-mtok 15 --assumed-input-tokens-per-call 50000 --max-budget 5`

The current Anthropic pricing check used Claude Sonnet 4.6 at `$3 / MTok`
input and `$15 / MTok` output, producing the configured `$4.5180` estimate.

The live command was:

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/run_dgm_in_sandbox.py --config config/live_score_movement.yaml --generations 2 --allow-network --env ANTHROPIC_API_KEY --audit-output .dgm-sandbox-runs/live-score-movement-audit.json
```

Observed live evidence:

- The run executed in the full-process Docker sandbox with `network_mode=bridge`.
- The sandbox audit recorded only `ANTHROPIC_API_KEY` as an environment variable
  name and hid the value.
- The run logged successful `POST https://api.anthropic.com/v1/messages`
  responses from Anthropic.
- The DGM controller completed two generations and wrote
  `.dgm-live-runs/live-score-movement/results/dgm_report_20260615_154225.json`.

Outcome:

- The archive contained 3 valid agents.
- Top score remained `1.000`.
- Best parent-child average-score delta was `+0.000`.
- `scripts/summarize_archive_scores.py --require-improvement` failed as
  designed because `has_improvement` is `false`.

This proves a fully live, sandboxed, provider-backed DGM run completed. It does
not prove benchmark improvement. The configured benchmark still needs a live
score-movement setup where the initial parent has measurable headroom.
