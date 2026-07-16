# Broad credible self-elicitation matrix

This bundle records the completed eight-model, cross-provider DGM
self-elicitation experiment. Each model was evaluated three times with the
frozen generation-zero agent and ran two independent 15-generation
self-mutation ladders on the same 12-problem LiveCodeBench segment.

The source commit was `522ace0a78dda031ffab8f575c34738d723f653a`. All 16
evolution workers produced terminal scorecards, telemetry, archives, and exit
code `0`. Early no-op stopping reduced the executed loop count from the
240-generation ceiling to 209. The GCP teardown check found no remaining
`dgm-sebc-*` instances.

## Result

The conservative statistic uses the median of three native observations and
the lower of the two ladder-top scores. The reliable score is the greater of
those two values. A one-off peak is reported separately and is not treated as
the model statistic.

| Model | Native observations | Native median | Ladder tops | Peak | Reliable | Overhang | Native realization | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `qwen/qwen3-coder-30b-a3b-instruct` | 5, 3, 4 | 4 | 3, 4 | 4 | 4 | 0 | 100% | No valid self-edit |
| `qwen/qwen3-coder` | 5, 6, 7 | 6 | 6, 7 | 7 | 6 | 0 | 100% | Measured |
| `qwen/qwen3.5-397b-a17b` | 9, 6, 6 | 6 | 6, 6 | 6 | 6 | 0 | 100% | No valid self-edit |
| `qwen/qwen3.7-max` | 9, 8, 8 | 8 | 8, 8 | 8 | 8 | — | — | Protocol blocked |
| `google/gemini-3.5-flash` | 7, 7, 10 | 7 | 10, 10 | 10 | 10 | **+3** | 70% | Measured |
| `openai/gpt-5.6-sol` | 10, 9, 9 | 9 | 11, 10 | **11** | 10 | **+1** | 90% | Measured |
| `anthropic/claude-fable-5` | 6, 8, 9 | 8 | 10, 9 | 10 | 9 | **+1** | 88.9% | Measured |
| `x-ai/grok-4.5` | 11, 10, 11 | **11** | 10, 11 | **11** | **11** | 0 | 100% | Measured |

The strongest native result was Grok 4.5 at a median 11/12. It did not produce
a parent-relative improvement. GPT-5.6 Sol also reached 11/12, but only in one
ladder, so its reliable result remains 10/12.

Gemini 3.5 Flash showed the largest measured gap: one ladder moved 7/12 to
10/12 while the other began at 10/12 and preserved it. Sol moved 9/12 to 11/12
in one ladder and 9/12 to 10/12 in the other. Fable moved 8/12 to 10/12 in one
ladder while its other ladder began and remained at 9/12. These independently
reproduced achieved-score thresholds do not mean both searches discovered the
same mutation. Native dispersion contributes to the statistic and is visible
in the table.

## Mutation findings

All selected best improvements preserved every task solved by their parent.
The exact patches are committed in `mutations/`.

- Gemini's selected lineage first moved 7/12 to 9/12 by adding a benchmark
  solver-control policy, then moved 9/12 to 10/12 with task-specific guidance.
- Sol moved 9/12 to 11/12 by adding task-specific algorithm hints for the
  remaining D/E problems. Its second ladder used generic verification guidance
  to move 9/12 to 10/12.
- Fable moved 8/12 to 10/12 with a general hard-problem strategy emphasizing
  constraints, operation counts, complexity, DP state, and stress testing.
- A separate non-selected Fable child moved 8/12 to 9/12 but lost
  `livecodebench_abc389_e`. Archive selection preserved the clean 10/12 child.

The best Sol and Gemini patches contain benchmark-specific hints. This is valid
adaptive search under the declared contract, but it is benchmark elicitation,
not evidence that the mutations transfer to unseen tasks. Fable's best patch is
more general, but transfer was not measured here.

## Search and protocol reliability

Across the 16 evolution ladders:

- 209 generation loops executed from a ceiling of 240;
- 81 changed mutations and 87 semantic no-ops were recorded;
- 94 of 184 archived agents were valid;
- four ladders contained a parent-relative improvement;
- 27 invalid-Python mutations, one malformed edit, and 333 hidden-test
  failures were classified by the mutation guard;
- provider telemetry recorded 41 timeouts, 98 API errors, and 658 empty or
  no-text response observations.

Qwen 3.7 Max is not a valid negative capability result. Alibaba returned HTTP
400 for every mutation request because thinking mode rejected the shared
required/object `tool_choice` setting. Both ladders still evaluated their base
agents and exited cleanly, but no mutation was admitted. Qwen 3 Coder 30B and
Qwen 3.5 produced only semantic no-ops, while Qwen 3 Coder produced three
changed children without a reliable score gain.

The failure classifier also has a documented observability gap. Its final
`timeout/provider failure` counter was zero even though provider telemetry
recorded the 98 API errors and 41 timeouts above. Likewise, the mutation-level
`unsafe complexity` counter was zero; solver-side resource-guard events are a
different signal. Provider telemetry and mutation classification must remain
separate until the classifier is repaired.

## Cost and runtime

OpenRouter's key-usage endpoint moved from `$358.439322897` before the valid
native phase to `$366.236475173` at evolution launch and `$565.881637000` at
closeout. The endpoint-accounted experiment delta was therefore `$207.442314103`
(`$7.797152276` native plus `$199.645161827` evolution), below the `$300` live
watchdog and the `$318.545104` approved OpenRouter ceiling.

Artifact telemetry contains 29,244,628 tokens and a pinned-price estimate of
`$220.752797` across native and evolution requests. This does not equal the
endpoint bill because telemetry reprices logged tokens at the declared catalog
rates while the endpoint reflects actual routing and billing. Endpoint usage is
the spend authority; telemetry is the per-model analytical estimate.

The runs accumulated 19.562 worker-hours. At the config's `$0.067/hour`
`e2-standard-2` estimate, that is about `$1.31` of VM time; it is an estimate,
not a cloud invoice.

## Scope and interpretation

This proof measures native and self-elicited performance. It does not run the
predeclared fixed-external-mutator arm, so `self_vs_external` is not reported.
The 12-task segment is deliberately small and has visible native variance. The
result supports a capability-overhang research direction, but it is not a
general model ranking or a publishable population estimate.

The next credible experiment should repair Qwen 3.7 tool-choice compatibility,
classify provider failures correctly, and test the discovered mutations on a
held-out segment before spending on longer ladders.

## Run identity

- Evolution base run: `sebc-e1-20260714b`
- Matrix: `config/livecodebench_self_elicitation_matrix.yaml`
- Segment: `release_v6_atcoder_loop12` (12 problems, 512 tests, 480 private)
- Evolution workers: 16, two per model
- Generations per worker: 15 ceiling
- GCS root:
  `gs://dgm-live-runs-doittogether-prod/self-elicitation-broad-credible-20260714/`

## Bundle contents

- `summary.json`: reproducible aggregate and per-model measurements.
- `run-contract.json`: exact source, budget, run, and metric contract.
- `endpoint-accounting.json`: endpoint-observed provider spend boundaries.
- `teardown.json`: read-only post-run GCP instance check.
- `evolution-plan.json` and `configs/`: non-secret launch plan and materialized
  model configs.
- `native/*`: the eight extra generation-zero runs, including scorecards,
  telemetry, archives, compressed logs, and exit codes.
- `workers/*`: all 16 evolution ladders with the same durable artifacts.
- `mutations/*`: five exact patches from the selected improving lineages.
- `checksums.sha256`: SHA-256 integrity manifest.

Regenerate the normalized summary from the recovered source artifacts with:

```bash
python3 scripts/summarize_self_elicitation_matrix.py \
  --matrix config/livecodebench_self_elicitation_matrix.yaml \
  --artifacts-root .dgm-live-runs/self-elicitation-broad-credible-20260714 \
  --output docs/live-runs/lcb-self-elicitation-broad8-20260714-1/summary.json
```
