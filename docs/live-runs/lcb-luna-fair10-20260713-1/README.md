# Luna mutator + ten-model runner matrix

This bundle records the budget-bounded DGM experiment that used
`openai/gpt-5.6-luna` as the fixed mutator and ten runner models from Alibaba,
DeepSeek, Moonshot, Z.ai, Google, xAI, Anthropic, and OpenAI. The source commit
was `ef98255da1523849e181f7f084fc93fe30aaeebb`.

## Result

- The fair scheduler launched one worker for every runner model before starting
  second replicates. Fifteen of 30 planned workers launched and completed 81
  fully scored generations before the shared budget stop; the other 15 were
  skipped.
- Eight of ten runner models produced at least one child that improved over its
  fresh native base. Five workers emitted terminal scorecards and ten stopped
  mid-run with durable controller logs.
- The best lane was `x-ai/grok-4.5`: Luna changed only
  `AgentConfig.max_iterations` from 10 to 14, moving a fresh 10/12 base to
  11/12 by gaining `livecodebench_abc388_e` with no regression.
- `z-ai/glm-5.2` moved 6/12 to 9/12 with the same 10-to-14 mutation, gaining
  `abc387_c`, `abc388_c`, and `abc389_d` with no regression.
- `qwen/qwen3.7-max` moved 7/12 to 9/12 with a 10-to-15 mutation, gaining
  `abc388_e` and `abc389_d` with no regression. Its other replicate produced a
  9/12 child that traded `abc390_e` for `abc389_d`; archive selection preserved
  the non-regressing 9/12 parent.
- The budget-stopped logs also show improvements for Qwen 3 Coder (6/12 to
  7/12 in two replicates), Qwen 3.5 (4/12 to 7/12 and 7/12 to 8/12), DeepSeek
  V4 Pro (7/12 to 8/12), Kimi K2.7 Code (7/12 to 8/12 in two replicates), and
  Claude Sonnet 5 (5/12 to 6/12).
- Gemini 3.5 Flash completed all 15 generations at 0/12. GPT-5.6 Sol remained
  at 0/12 through nine completed generations. Their traces contain plausible
  solutions, so these zeroes are evidence of runner/protocol incompatibility,
  not a general capability ranking.

The experiment exceeded the ideal 9/12 goal and produced the first clean
11/12 result on this segment. It also identified a narrow, reproducible mutation
family: modestly increasing tool-turn depth helps several runners while
preserving easy tasks. Unbounded increases are unsafe: later mutations proposed
30, 32, 40, 45, and 48 turns without corresponding score evidence.

## Provider and protocol findings

The 15 recovered logs contain 28,911,060 model tokens, 6,659 chat-completion
posts, 106 provider timeouts, 1,271 empty responses, and 134 HTTP provider
errors. Pinned-price telemetry estimates $54.246223 for requests represented in
the logs. The endpoint-reported fair-run delta was $58.190871 because billing
also includes in-flight and otherwise unlogged requests.

- DeepSeek produced 608 empty responses across two workers; Sonnet produced
  478; GLM produced 68. Extra iteration depth magnified this provider behavior.
- Qwen 3.5 recorded 61 timeouts across two workers. Qwen 3.7 recorded 19, Qwen
  3 Coder 17, Kimi 5, GPT-5.6 Sol 2, Grok 1, and DeepSeek 1.
- Gemini produced 120 HTTP 400 responses, Qwen 3.5 produced one, and Qwen 3.7
  produced 13 HTTP 429 responses across its two workers.
- The benchmark interface repaired or blocked 167 malformed edit payloads, 65
  invalid tool-parameter calls, 212 unsafe-complexity completion attempts, 300
  public-sample failures, and 407 step-limit completions.
- Generation reports distinctly tagged 509 hidden-test failures and five
  invalid-Python mutations. The other configured mutation categories remained
  separate zero-count fields rather than being folded into hidden-test failure.

## Budget and teardown

An initial FIFO launch was stopped after it started three Qwen 3 Coder and three
Qwen 3.5 workers before other models. It consumed $14.150621, derived from the
next run's exact starting balance. Commit `ef98255` changed scheduling to
round-robin by worker number before the fair run.

The corrected run consumed an endpoint-reported $58.190871. Total OpenRouter
spend across the aborted and corrected runs was therefore $72.341492, below the
matrix's $82 OpenRouter allocation and the $100 total experiment ceiling. The
fair workers account for an estimated 23.196 VM-hours, or $1.554 at the pinned
`e2-standard-2` estimate. All experiment VMs were absent after teardown.

## Important caveat and follow-up

The materialized evolution configs inherited `target_performance: 0.75`.
Workers that reached 9/12 or better stopped after their current generation,
despite the requested full-depth experiment. This was not a cost gate; it was a
configuration mistake. The follow-up change sets the matrix target to 1.0 and
adds a static 24-turn mutation admission bound. The bound preserves the
demonstrated 10-to-14 and 10-to-15 wins while rejecting the observed
32-to-48 amplification.

## Run identity

- Fair base run: `luna-fair10-p15-20260713a`
- Aborted FIFO run: `luna-native10-p15-20260713a`
- Matrix: `config/livecodebench_luna_runner_matrix.yaml`
- Mutator: `openai/gpt-5.6-luna`
- Segment: `release_v6_atcoder_loop12` (12 problems, 512 tests, 480 private)
- Fair GCS prefix:
  `gs://dgm-live-runs-doittogether-prod/luna-fair10-p15-20260713a/`

## Bundle contents

- `summary.json`: normalized results for all 15 launched workers.
- `run-aggregate.json`: terminal launcher aggregate and budget state.
- `aborted-live-state.json`: last local state from the stopped FIFO run.
- `workers/*`: terminal scorecards, telemetry, and archives for the five cleanly
  completed workers.
- `telemetry/*`: log-derived telemetry for all completed and partial workers.
- `mutations/*`: exact patches for the three strongest terminal improvements and
  the Qwen 3.7 regression case.
- `logs/*.log.gz`: durable controller logs for every launched worker.
- `checksums.sha256`: SHA-256 integrity manifest.
