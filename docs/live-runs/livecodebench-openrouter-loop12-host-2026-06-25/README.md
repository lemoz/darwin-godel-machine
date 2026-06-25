# LiveCodeBench OpenRouter loop-12 host run - 2026-06-25

This directory records a live 10-generation DGM run against a 12-problem
LiveCodeBench-derived code-generation segment. The run used real OpenRouter
calls to `moonshotai/kimi-k2.7-code` and completed all planned generations.

## Command

The completed run used the host-controller config:

```bash
OPENROUTER_API_KEY=<redacted> PATH="$PWD/.venv/bin:$PATH" \
  python run_dgm.py \
  --config config/livecodebench_openrouter_loop12_host.yaml \
  --generations 10
```

The run was launched inside `tmux` through a local helper that loaded the
OpenRouter key from the user's local auth files. The runtime output directory
was `.dgm-live-runs/livecodebench-openrouter-loop12-host/`, which remains
ignored by git. This proof directory commits normalized artifacts only.

## Scope

- Segment config: `config/livecodebench_segment_loop12.yaml`
- Live run config: `config/livecodebench_openrouter_loop12_host.yaml`
- Segment ID: `release_v6_atcoder_loop12`
- Benchmark source: LiveCodeBench `code_generation_lite`
- Source dataset: `https://huggingface.co/datasets/livecodebench/code_generation_lite`
- Upstream project: `https://github.com/livecodebench/livecodebench`
- Problem count: 12
- Difficulty mix: 4 easy, 5 medium, 3 hard
- Generated scored tests: 512
- Generated private tests: 480
- Prompt examples: public tests only
- Scored tests: public and private tests
- Model: `moonshotai/kimi-k2.7-code` through OpenRouter
- Generations completed: 10
- Max model turns per task: 5
- Controller runner: host Python process
- Candidate execution: per-test subprocess guards, static resource guard, and
  benchmark timeouts

## Cost Gate

OpenRouter pricing was checked on 2026-06-25 before the run through
`https://openrouter.ai/api/v1/models`:

- Input price: `$0.74 / MTok`
- Output price: `$3.50 / MTok`
- Request ceiling: 710
- Assumed input tokens per call: 50,000
- Max output tokens per call: 2,048
- Estimated ceiling: `$31.3593`
- Configured max budget: `$35.0000`

## Result

Final controller summary:

- Total runtime: 1.663 hours
- Generations: 10
- Agents created: 10
- Final archive size: 11, including the base agent
- Successful improvements: 2
- Improvement rate: 20.0%
- Base score: `0.4166666666666667` (`5/12`)
- Best score: `0.5833333333333334` (`7/12`)
- Best delta from base: `+0.16666666666666669`

Loop-order score table:

| Loop | Gen metadata | Agent | Score | Solved | Passed tasks |
| ---: | ---: | --- | ---: | ---: | --- |
| 0 | 0 | `8c630aad` | `0.417` | 5/12 | `abc387_b`, `abc388_b`, `abc389_a`, `abc390_b`, `abc388_c` |
| 1 | 1 | `c781c0b6` | `0.500` | 6/12 | `abc387_b`, `abc388_b`, `abc389_a`, `abc390_b`, `abc388_c`, `abc390_e` |
| 2 | 2 | `efc9b7ab` | `0.417` | 5/12 | `abc387_b`, `abc388_b`, `abc389_a`, `abc390_b`, `abc390_e` |
| 3 | 2 | `46997da2` | `0.417` | 5/12 | `abc387_b`, `abc388_b`, `abc389_a`, `abc390_b`, `abc388_c` |
| 4 | 1 | `b02fbd88` | `0.583` | 7/12 | `abc387_b`, `abc388_b`, `abc389_a`, `abc390_b`, `abc388_c`, `abc388_e`, `abc390_e` |
| 5 | 2 | `97e71a49` | `0.417` | 5/12 | `abc387_b`, `abc388_b`, `abc389_a`, `abc390_b`, `abc388_c` |
| 6 | 2 | `49eaebed` | `0.500` | 6/12 | `abc387_b`, `abc388_b`, `abc389_a`, `abc390_b`, `abc388_c`, `abc390_d` |
| 7 | 2 | `06d6be2d` | `0.583` | 7/12 | `abc387_b`, `abc388_b`, `abc389_a`, `abc390_b`, `abc388_c`, `abc389_d`, `abc390_d` |
| 8 | 2 | `fdef9055` | `0.417` | 5/12 | `abc387_b`, `abc388_b`, `abc389_a`, `abc390_b`, `abc388_c` |
| 9 | 2 | `160c26ef` | `0.333` | 4/12 | `abc387_b`, `abc388_b`, `abc389_a`, `abc390_b` |
| 10 | 2 | `b7c86a5a` | `0.417` | 5/12 | `abc387_b`, `abc388_b`, `abc389_a`, `abc390_b`, `abc388_c` |

Accepted non-regression improvements:

| Child | Parent | Score movement | Accepted movement |
| --- | --- | ---: | --- |
| `c781c0b6` | `8c630aad` | `5/12 -> 6/12` | Added `abc390_e`; no regressions |
| `b02fbd88` | `8c630aad` | `5/12 -> 7/12` | Added `abc388_e` and `abc390_e`; no regressions |

The run also produced one 7/12 tie, `06d6be2d`, but it was not
non-regression-eligible: it added `abc389_d` and `abc390_d` while losing
`abc388_e` and `abc390_e` relative to its parent.

Machine-readable details are in:

- `scorecard.json`
- `dgm_report_20260625_112714.json`
- `segment_manifest.json`

## Live Evidence

The controller log for the completed host run contained:

- `344` OpenRouter chat-completion POSTs
- `34` OpenRouter-compatible request timeouts
- `1` static resource-guard rejection before executing a risky solution
- `0` Python tracebacks
- `DGM run completed successfully!`

The key operational result is that this was not a one-loop check. It completed
10 full DGM self-modification generations and left a complete archive and
scorecard.

## Runner Notes

Three earlier execution routes were tested before the completed host run:

- Staged Docker sandbox: reached late generations but did not sync the archive
  back after abnormal termination because staged sync only occurs on successful
  completion.
- Direct Docker bind mount from the external `/Volumes/...` checkout: Docker
  Desktop mounted that path as empty on this machine.
- Direct Docker bind mount from a persistent copy under `/Users/...`: proved
  live OpenRouter execution, then exited with Docker `ExitCode 137` and
  `OOMKilled=true`. Docker Desktop was capped at roughly 1.9 GiB on this Mac.

The committed successful proof therefore uses the host-controller config. The
generated benchmark solutions still run under local per-test subprocess guards,
and the `abc390_d` static resource guard fired once during generation 10.

## Verification

Commands run for this cycle:

- `PATH="$PWD/.venv/bin:$PATH" python scripts/prepare_livecodebench_segment.py --config config/livecodebench_segment_loop12.yaml`
- `PATH="$PWD/.venv/bin:$PATH" python scripts/estimate_live_run_cost.py --config config/livecodebench_openrouter_loop12_host.yaml --input-price-per-mtok 0.74 --output-price-per-mtok 3.50 --assumed-input-tokens-per-call 50000 --max-budget 35`
- `PATH="$PWD/.venv/bin:$PATH" python scripts/summarize_archive_scores.py --archive-metadata .dgm-live-runs/livecodebench-openrouter-loop12-host/archive/archive_metadata.json --output .dgm-live-runs/livecodebench-openrouter-loop12-host/scorecard.json`
- `git diff --check`
- `PATH="$PWD/.venv/bin:$PATH" python scripts/verify_sandbox_docker.py --require`
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest -q`

Results:

- Segment preparation: passed, 12 benchmarks, 512 tests, 480 private tests
- Cost estimate: passed, `$31.3593` ceiling under `$35.0000`
- Scorecard: passed, 11 valid archived agents, top score `0.583`, improvements 2
- `git diff --check`: passed
- Docker sandbox smoke: passed
- Full pytest: `301 passed, 7 skipped, 2 warnings`

The older `scripts/verify_livecodebench_segment_plan.py` checker is not a pass
condition for this config. It is hardcoded for the earlier 3-generation,
24-problem `livecodebench_openrouter_segment` plan with 4,096 max output tokens
and a 2026-06-24 pricing date, while this run intentionally uses a 10-generation
loop-12 host-controller config with 2,048 max output tokens.

## Caveats

This is not a full LiveCodeBench leaderboard result. It is a local DGM harness
run over a recognizable LiveCodeBench-derived AtCoder segment with private
tests in the local scoring path.

The run exposed a scale-up blocker: repeated 60-second OpenRouter-compatible
timeouts affected medium and hard tasks. Before spending on larger segments,
the provider timeout/retry policy should be tuned and measured separately from
model quality.
