# Gemma constrained-mutation pilot: lcb1-gemma3-constrained-20260712-1

Run date: 2026-07-12
Model: OpenRouter `google/gemma-3-27b-it`
Config: `config/livecodebench_openrouter_gemma3_27b_constrained.yaml`
Segment: `release_v6_atcoder_loop12` (12 benchmarks, 512 tests, 480 private)
Seed proof: `docs/live-runs/lcb50-qwen3-hardened-20260630-1/archive.tar.gz`

## Result

Gemma is inexpensive enough for scaled experimentation, and the constrained
interface now contains its protocol failures safely. It is not yet producing
useful DGM mutations on this task.

- Generations requested/completed: `1/1`
- Selected parent: `a22a6b70-9c72-4f21-8866-67de9e007c61` (`8/12`)
- Child: `dc44faf4-a1a8-49d6-a035-8fcc19c69be7`
- Provider failures: `0`
- Successful bounded source reads: `1`
- Syntactically valid in-place edits: `1`
- Admission result: rejected as `no-op`
- Admission reason: `mutation only changed imports and no executable behavior`
- Benchmark evaluations: `0` (correctly skipped)
- Top archive score after run: `8/12`
- Target reached: `false`

The model read lines 1-20 of the real parent `agent.py`, then commented out the
unused `re` import. The controller preserved that in-place edit instead of
overwriting the module with unrelated terminal example code. The admission gate
recognized that removing/commenting an import did not change executable agent
behavior and archived the child as invalid without spending twelve benchmark
evaluations.

## Cost

OpenRouter pricing checked on 2026-07-12:

- Input: `$0.08 / 1M tokens`
- Output: `$0.16 / 1M tokens`
- Final pilot input tokens: `11,016`
- Final pilot output tokens: `182`
- Estimated final pilot model cost: `$0.0009104`

The config retains a deliberately pessimistic safety gate: at most 12
generations and `$5` without reapproval. The estimator's worst-case result for
that ceiling was `$4.3574`. Current pricing source:
`https://openrouter.ai/api/v1/models`.

## Protocol findings

The short experiments isolated four separate layers:

1. Raw OpenRouter tool-call canaries succeeded for Gemma 3 27B and the free
   Gemma 4 31B endpoint.
2. With DGM's previous automatic tool selection, Gemma 3 emitted pseudo
   `tool_code` prose rather than native calls.
3. Requiring native calls exposed a stable payload mismatch: Gemma placed
   ranged replacement source in `replace_text`. The edit tool now repairs that
   unambiguous alias.
4. Requiring a bounded source read before mutation stopped blind line-number
   guesses. Real workspace edits now take precedence over terminal inline code,
   and import-only mutations are treated as semantic no-ops.

The free Gemma 4 Agent-stack canary encountered a provider failure after its raw
API canary succeeded, so free routing is not treated as the stable default.

## Offline A/B admission proof

The constrained gate was replayed against two children from the committed Qwen
exploit archive:

- Baseline admission accepted final child
  `7b4f36b4-9340-4fb1-86db-0dd344cb960e`, which changed
  `Agent._is_task_complete` and regressed an `8/12` parent to `0/12`.
- Constrained admission rejected the same child as
  `completion/protocol failure` before evaluation.
- Both baseline and constrained admission accepted
  `81dbbac2-494f-41e6-a22d-58e802882ba9`, the real `6/12 -> 7/12` child that
  recovered `livecodebench_abc389_d` without changing protected protocol code.

This proves the guard blocks the known catastrophic regression without blocking
the known useful mutation.

## Failure taxonomy

The controller and archive metadata now keep these modes distinct:

- `no-op`
- `malformed edit`
- `invalid Python`
- `unsafe complexity`
- `timeout/provider failure`
- `hidden-test failure`
- `completion/protocol failure`

## Scale decision

Do not run 50 generations yet. Cheap execution is proved, but productive Gemma
self-modification is not. The next scale gate should require at least one
behavior-changing, admission-passing mutation in a two-to-four-generation
pilot while easy tasks remain unchanged. Only then should the same config be
expanded within its 12-generation/$5 ceiling.

## What this proves

- Gemma 3 27B can use the real DGM edit interface through OpenRouter.
- A bounded read-before-write policy makes its tool use grounded in actual
  source rather than guessed line numbers.
- Malformed, invalid, protocol-damaging, and semantic no-op mutations can be
  stopped before benchmark evaluation.
- Gemma experimentation can be extremely inexpensive.

## What this does not prove

- No Gemma child improved a hard LiveCodeBench task.
- No Gemma child preserved and re-proved the full `8/12` score because no child
  passed mutation admission.
- The free Gemma endpoint is not proved stable for a DGM loop.
- `9/12` remains unproved.
