# Self-Elicitation and Capability Overhang

Status: broad credible experiment approved on 2026-07-14; launch remains subject to credential, model, budget, and cloud preflights.
Pricing snapshot: 2026-07-14, OpenRouter public model catalog.  
Initial evaluation surface: the existing 12-problem LiveCodeBench segment.

## Research question

How much of a model's best achievable agent capability appears through a
generic interface, without model-specific prompting or scaffolding? How good is
the model at discovering the changes that unlock its own capability?

DGM makes it possible to separate four properties that ordinary benchmark
scores collapse together:

1. **Native capability**: performance with the frozen shared agent and no
   mutations.
2. **Externally elicited capability**: performance after a common external
   mutator, such as GPT-5.6 Luna, changes the agent.
3. **Self-elicited capability**: performance when the runner model also acts as
   the mutator.
4. **Elicitation efficiency**: generations, tokens, dollars, and regressions
   required to reach the best reliable score.

The primary derived statistics should be:

```text
capability_overhang = reliable_self_elicited_score - median_native_score
native_realization = median_native_score / reliable_self_elicited_score
self_vs_external = reliable_self_elicited_score - reliable_external_score
```

`Reliable` must not mean the largest score observed once. A searched score
should either reproduce in an independent ladder or survive repeated
re-evaluation before it is treated as a model statistic.

## Experimental contract

Use the same benchmark, base agent, tools, schemas, context policy, and scoring
for every model. Compatibility repairs may normalize provider protocols, but
they must not add model-specific problem-solving instructions.

For model `M`, compare these arms:

- **Native**: `runner=M`, frozen generic agent, zero generations.
- **External elicitation**: `runner=M`, `mutator=openai/gpt-5.6-luna`.
- **Self-elicitation**: `runner=M`, `mutator=M`.

The first credible self-elicitation measurement should use:

- three native measurements per model;
- two independent self-elicitation ladders per model;
- 15 mutation generations per ladder;
- the existing 12 LiveCodeBench tasks;
- isolated archive, workspace, results, and artifacts for every ladder;
- both an equal-generation view and an equal-dollar view;
- exact model aliases, provider routing, reasoning settings, token ceilings,
  temperatures, tool schemas, and timeouts in the proof bundle.

Each 15-generation ladder already evaluates its native generation-zero agent.
Therefore, two ladders plus one additional frozen baseline produce three native
measurements and two independent search trajectories.

Report at least:

- native median and dispersion;
- reliable searched best and capability overhang;
- native realization ratio;
- generations, tokens, dollars, and wall time to best;
- malformed/no-op mutation rate;
- easy-task regression rate;
- provider failure and empty-response rate;
- repeatability across ladders.

### Approved execution contract

The approved first measurement is the full eight-model cross-provider matrix,
not the Qwen-only study. Its executable source of truth is
`config/livecodebench_self_elicitation_matrix.yaml`.

- Each model uses the same exact OpenRouter alias as runner and mutator, with
  separate fixed role prompts and shared generic agent scaffolding.
- The shared protocol does not request a model-specific reasoning mode; every
  endpoint uses its provider-default reasoning behavior.
- One extra zero-generation worker plus the generation-zero evaluation in each
  of two ladders yields three native observations per model.
- Two isolated 15-generation workers per model yield 16 ladders and a ceiling
  of 240 mutation generations.
- The empirical model estimate is $254.84. A 25% reserve produces a $318.55
  OpenRouter ceiling, and the all-in OpenRouter plus GCP approval is $325.
- The live watchdog stops below the approved ceiling and uses key-scoped usage
  accounting so polling overshoot has explicit headroom.

## Candidate model set and cost

The broad first matrix should include several Qwen scales rather than treating
Qwen as one point, plus frontier models from different providers:

| Model | OpenRouter input/output per MTok | One native 12-task eval | One native + 15-generation self ladder | Credible model total |
| --- | ---: | ---: | ---: | ---: |
| `qwen/qwen3-coder-30b-a3b-instruct` | $0.07 / $0.27 | $0.02 | $0.39 | $0.80 |
| `qwen/qwen3-coder` | $0.22 / $1.80 | $0.10 | $1.61 | $3.32 |
| `qwen/qwen3.5-397b-a17b` | $0.385 / $2.45 | $0.15 | $2.53 | $5.22 |
| `qwen/qwen3.7-max` | $1.25 / $3.75 | $0.39 | $6.53 | $13.46 |
| `google/gemini-3.5-flash` | $1.50 / $9.00 | $0.58 | $9.66 | $19.89 |
| `openai/gpt-5.6-sol` | $5.00 / $30.00 | $1.93 | $32.18 | $66.30 |
| `anthropic/claude-fable-5` | $10.00 / $50.00 | $3.63 | $60.34 | $124.30 |
| `x-ai/grok-4.5` | $2.00 / $6.00 | $0.63 | $10.46 | $21.54 |

The `credible model total` is two independent 15-generation ladders plus one
additional native evaluation. It yields three native observations in total.

Estimated model spend:

- one directional ladder for all eight models: **$123.70**;
- credible design before reserve: **$254.84**;
- credible design with a 25% provider/token reserve: **$318.55**;
- recommended all-in experiment cap including low-cost ephemeral VMs:
  **$325**.

A Qwen-only four-model study is much cheaper: about **$11.06** for one ladder
per model or **$22.80** for the credible two-ladder design before reserve. The
frontier matrix is expensive primarily because Fable and Sol account for about
75% of the estimated model spend.

### Cost basis and limitations

The estimate uses the completed Gemini 3.5 lane from the 2026-07-13 recovery
fleet as the empirical token profile:

- 15 mutation generations plus the generation-zero baseline;
- 4.019 million prompt tokens;
- 0.403 million completion tokens;
- 4.422 million total tokens;
- $9.53 measured cost with Gemini 3.5 as runner and Luna as mutator.

For costing a self-mutating model, all observed runner and mutator tokens are
repriced at that model's current input/output rates. Models can use materially
different token volumes, so the 25% reserve is part of the design, not optional
padding. The same recovery fleet stopped at an account-level delta of $79.52
against a $78 polling threshold, demonstrating that a watchdog can overshoot
between polls. A future proof should use a dedicated key or run-scoped usage
accounting and leave shutdown headroom below the approved cap.

Prices are a dated planning snapshot, not permanent facts. Refresh them from
the [OpenRouter model catalog](https://openrouter.ai/api/v1/models) before any
approval or launch.

## Proposed place inside Fort Labs

Fort Labs is the natural parent research program for this direction. Its
existing public work already separates the laboratory, evaluation protocol,
environment harness, evidence, and findings:

- **Fort Labs**: the umbrella research program and public findings layer.
- **Fort-Eval**: versioned evaluation profiles and comparable cohorts.
- **Fort-Gym**: the long-horizon Dwarf Fortress environment and replayable
  evidence harness.
- **Darwin Gödel Machine**: the adaptive elicitation and evolutionary search
  instrument for studying agent interfaces, self-improvement, and capability
  overhang.

DGM should remain a separate repository with its own upstream attribution,
tests, archives, and proof bundles. “Fort Labs subproject” should mean shared
research governance and a place in the Fort Labs project/research index, not a
monorepo merge or a claim that Fort Labs originated the underlying DGM paper.

The shared Fort Labs standard should be:

- predeclared protocol and budget;
- exact model and code versions;
- environment and agent-input boundaries;
- durable replay/log/archive evidence;
- explicit comparability limits;
- findings that distinguish a result, a failure, and an incomplete run.

No Fort Labs website, Fort-Eval protocol, or Fort-Gym repository change is
authorized by this note. Those surfaces should be updated only after the
project relationship and public wording are agreed.

## Decisions still to discuss

1. Whether Fort-Eval should define a reusable capability-overhang profile or
   DGM should publish the protocol first and graduate it later.
2. How DGM should appear on the Fort Labs site without implying ownership of
   the Sakana AI research project or universal comparability across budgets.

## Related projects

- [Fort Labs / Fort-Eval](https://fortgym.live/)
- [Fort-Gym](https://github.com/lemoz/fort-gym)
- [Darwin Gödel Machine](https://github.com/lemoz/darwin-godel-machine)
- [Original DGM research](https://sakana.ai/dgm/)
