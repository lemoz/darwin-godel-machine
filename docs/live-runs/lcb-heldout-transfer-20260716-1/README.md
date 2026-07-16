# Held-out mutation transfer proof

This bundle records a generation-zero replay of frozen agents from the broad
self-elicitation experiment on a disjoint 12-problem LiveCodeBench segment.
The experiment asked whether mutations discovered on `release_v6_atcoder_loop12`
preserve easy-task performance and improve unseen hard tasks, without allowing
any new mutation during the transfer run.

The answer is yes for all four selected mutation lineages. Their
replicate-averaged gains were `+1.0`, `+1.0`, `+1.5`, and `+1.0` problems out
of 12. Every selected mutation preserved or improved the four easy tasks, and
each gained at least half a problem on the held-out hard set.

## Result

Scores below are expected solved problems out of 12, obtained by summing the
per-problem pass rate across two independent evaluations. Half-points mean one
of two replicates passed; they are not partial credit within one evaluation.

| Runner and frozen lineage | Native | Mutated | Delta | Mutated easy /4 | Mutated medium /5 | Mutated hard /3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Gemini 3.5 Flash, solver policy | 7.5 | 7.0 | -0.5 | 3.5 | 2.5 | 1.0 |
| Gemini 3.5 Flash, selected top | 7.5 | 8.5 | **+1.0** | **4.0** | 3.0 | 1.5 |
| GPT-5.6 Sol, task hints | 9.0 | **10.0** | **+1.0** | **4.0** | 4.0 | 2.0 |
| GPT-5.6 Sol, generic verification | 8.0 | **9.5** | **+1.5** | **4.0** | 3.5 | 2.0 |
| Claude Fable 5, hard-problem strategy | 7.5 | 8.5 | **+1.0** | **4.0** | 3.0 | 1.5 |

The earlier Gemini solver-policy child is an important negative control from
the same archive: it lost half a point on an easy task and finished below its
native parent. The later selected Gemini child preserved all easy tasks and
improved both medium and hard performance. Selection quality therefore matters;
the result is not evidence that arbitrary self-edits transfer.

The task-hint Sol child moved `9.0 -> 10.0`, gaining half a point on both
`abc394_c` and hard problem `abc391_e`. The generic-verification Sol child had
the largest aggregate gain, `8.0 -> 9.5`, and moved easy performance from
`3.5 -> 4.0`; it also traded half a point away on `abc394_d` while gaining a
full point on `abc394_c`, so aggregate improvement is not per-task
non-regression. Fable's general hard-problem strategy kept easy and medium
scores fixed and moved the hard subset from `0.5 -> 1.5`.

## Protocol

- Source commit: `38fdabed97926f6f2f7866ca7c405367e0bca91f`
- Run: `heldout-t2-20260716b`
- Segment: `release_v6_atcoder_heldout12`
- Segment composition: 4 easy, 5 medium, 3 hard
- Tests: 507 total, including 480 private tests
- Evaluations: 216 agent-problem evaluations
- Replicates: 2 per frozen agent
- Mutation generations: 0
- Workers: 4 parallel ephemeral `e2-standard-2` VMs
- GCS root:
  `gs://dgm-live-runs-doittogether-prod/heldout-transfer-20260716b/`

The held-out question ids (`abc391_*` through `abc394_*`) do not occur in the
search segment (`abc387_*` through `abc390_*`). Both native and mutated agents
were seeded from the committed broad-experiment archives, pruned to the
declared ids, and evaluated under the same runner model within each lane. The
experiment measures transfer of already-discovered agent code; it does not
measure a new search or a cross-model external mutator.

## Reliability findings

All four workers returned exit code `0`, recovered complete local artifacts,
and deleted their VMs. This also live-proved the post-sync delay added in
`55962c1`: the SSH streamers observed terminal state instead of racing VM
self-deletion.

Provider behavior remained uneven during the 216 task evaluations:

- Gemini logged 54 empty OpenAI-compatible responses and 58 no-tool-call
  observations.
- Fable logged 34 length-finished empty responses, 34 no-tool-call
  observations, and five malformed tool-argument observations.
- GPT-5.6 Sol's generic lane had one 120-second provider timeout and retried;
  the two Sol lanes logged seven malformed tool-argument observations total.
- Every worker still completed and produced both replicate scores for every
  selected agent.

Because archive rescoring runs in required preflight before the zero-generation
DGM controller, the normal telemetry files report zero provider tokens and
cost. That is an instrumentation boundary, not a claim that the evaluations
were free. The launcher also observed a stale key-scoped usage value and
reported a zero budget delta.

## Cost

The account-level OpenRouter credits endpoint moved from total usage
`$1967.770834732` to `$1997.107261739`, an experiment delta of
`$29.336427007`. The account had `$77.892738261` remaining at closeout.
Account-level credits are the spend authority for this run because the
key-scoped usage endpoint and generation-zero telemetry did not capture the
transfer calls.

## Interpretation

This is credible evidence that the self-elicitation ladders discovered useful
agent changes rather than only overfitting the original 12 task ids. It is
also evidence for the user's proposed capability-overhang framing: the base
model's realized score depends materially on the agent code it previously
elicited from itself.

The evidence remains small-sample. It covers one held-out 12-problem AtCoder
slice and two replicates per agent, with visible stochastic variance. The next
scale step should repeat this frozen transfer protocol on additional disjoint
segments before spending on longer mutation ladders. Provider reliability
should be treated as a separate model characteristic rather than silently
discarded.

## Bundle contents

- `summary.json`: normalized result table and difficulty breakdowns.
- `endpoint-accounting.json`: account-level spend boundaries.
- `teardown.json`: post-run instance check.
- `aggregate.json` and `launch-plan.json`: cloud matrix result and exact source
  identity.
- `configs/`: the declared matrix, generated worker configs, and segment
  manifest.
- `workers/*/transfer.json`: exact two-replicate, per-problem transfer scores.
- `workers/*/seed-manifest.json`: exact seeded archive ids and checks.
- `workers/*`: scorecards, telemetry, archives, compressed logs, and exit
  codes for all four workers.
- `checksums.sha256`: SHA-256 integrity manifest.
