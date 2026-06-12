# Live DGM Run Proof - 2026-06-12

This directory contains the first committed live-run proof artifact for this
repository. The run used real Anthropic API calls, not mocks, and completed two
DGM generations.

## Command

```bash
PATH="$PWD/.venv/bin:$PATH" python run_dgm.py \
  --config config/live_dgm_proof.yaml \
  --generations 2
```

The full captured transcript is in `transcript.txt`.

## Scope

- Provider/model: `anthropic` / `claude-sonnet-4-6`
- Benchmark: `list_processing`
- Generations: 2
- Max model turns per task: 5
- Max output tokens per call: 2,048
- Runtime output directory: `.dgm-live-runs/2026-06-12-proof/`

The runtime directory is intentionally ignored by git. It contains copied agent
workspaces and the generated JSON report. This directory commits the stable proof
materials instead.

## Cost Gate

Pricing was checked against Anthropic's official pricing page on 2026-06-12:
Claude Sonnet 4.6 was listed at $3 / MTok input and $15 / MTok output.

- <https://platform.claude.com/docs/en/about-claude/pricing>
- <https://www.anthropic.com/claude/sonnet>

Pre-run ceiling estimate for this bounded config:

- Agent tasks: 5
- Request upper bound: 25
- Assumed input tokens: 200,000
- Output token ceiling: 51,200
- Estimated ceiling: $1.3680

Measured usage from the transcript:

- API calls: 20
- Input tokens: 81,943
- Output tokens: 3,333
- Estimated spend at listed rates: $0.295824

## Result

| Generation | Agent ID | Benchmark | Score |
| --- | --- | --- | --- |
| 0 | `686d489b-7bcb-4d8d-a007-d971ddafcfdd` | `list_processing` | 1.000 |
| 1 | `08150f6d-25ca-4bce-93ef-3172cc3a5a0d` | `list_processing` | 1.000 |
| 2 | `321422b4-3747-4896-af61-c2060fcf6884` | `list_processing` | 1.000 |

Final report summary:

- Total generations: 2
- Agents created: 2
- Final archive size: 3
- Successful improvements: 0
- Top score: 1.000

## Evidence Notes

- The transcript includes successful `POST https://api.anthropic.com/v1/messages`
  responses and per-call token usage.
- The controller redacted API keys before logging config.
- The bash tool removed credential-like environment variables from subprocesses
  before the run.
- A post-run scan of `transcript.txt` and `dgm_run.log` found no live API key or
  token strings.

## Caveats

This proves a real multi-generation DGM execution path: base evaluation, parent
selection, live self-modification attempts, validation, modified-agent
evaluation, archive update, and final report generation.

It does not prove benchmark improvement. Both child agents matched the already
perfect base score on the selected benchmark. It also does not complete full
Docker sandboxing; the live agent still ran on the host with the current tool
safety restrictions.
