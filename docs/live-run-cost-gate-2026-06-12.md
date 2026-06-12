# Live Run Cost Gate - 2026-06-12

This is the approval gate for the roadmap item "Documented live run." No live
DGM run has been executed for this estimate.

## Configuration Snapshot

- Entry point: `python run_dgm.py`
- Generations: 3, as hard-coded in `run_dgm.py`
- Provider/model: `anthropic` / `claude-sonnet-4-6`
- Enabled benchmarks: `string_manipulation`, `list_processing`, `simple_algorithm`
- Agent max steps per task: 20
- Max output tokens per request: 8,192

## Pricing Snapshot

Anthropic's official pricing pages list Claude Sonnet 4.6 at $3 per million
input tokens and $15 per million output tokens as of 2026-06-12:

- https://docs.anthropic.com/en/docs/about-claude/pricing
- https://www.anthropic.com/claude/sonnet

Re-check pricing before executing a live run; provider pricing can change.

## Estimate Command

```bash
python scripts/estimate_live_run_cost.py \
  --generations 3 \
  --avg-input-tokens-per-call 8000 \
  --input-usd-per-mtok 3 \
  --output-usd-per-mtok 15
```

## Estimate

- Agent tasks: 15 (3 base evaluation + 3 generations x 4)
- Request upper bound: 300 (20 max steps per task)
- Assumed input tokens: 2,400,000 (8,000 average per request)
- Output token ceiling: 2,457,600 (8,192 max output per request)
- Estimated input cost: $7.2000
- Estimated output ceiling cost: $36.8640
- Estimated total ceiling: $44.0640

This is an upper-bound-style estimate for output tokens, not a forecast. Actual
usage can be lower when agents finish before `max_steps` or emit less than
`max_tokens`, and can differ if prompt growth pushes average input tokens above
the 8,000-token assumption.

## Approval Needed

Before running `python run_dgm.py`, Chris should approve one of:

- Approve the default 3-generation run with a soft budget ceiling of $45.
- Reduce scope to 1 generation before the flagship run.
- Change provider/model, max steps, or benchmark set and regenerate this estimate.
