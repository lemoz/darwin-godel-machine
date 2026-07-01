# DGM Roadmap

This roadmap tracks the path from "DGM can run" to "DGM can keep searching at
scale and produce externally understandable benchmark improvement." The current
definition of WDSLL-scale success is not a single lucky child agent. It is a
repeatable system that can launch live benchmark workers, preserve artifacts,
explain failures, promote useful mutations, and continue search without relying
on a maintainer laptop.

## Current Position

`main` contains a real live-run proof:

- `lcb50-qwen3-hardened-20260630-1` completed 50 DGM loop iterations on a
  disposable GCP VM.
- The run used OpenRouter `qwen/qwen3-coder` against a 12-problem
  LiveCodeBench code-generation-lite segment.
- The best score moved from `5/12` to `8/12`.
- The proof bundle includes launch plan, logs, telemetry, scorecard, archive,
  checksums, and VM teardown evidence.

Primary evidence:

- [`docs/live-runs/lcb50-qwen3-hardened-20260630-1/`](docs/live-runs/lcb50-qwen3-hardened-20260630-1/)
- [`docs/cloud-vm-live-evals.md`](docs/cloud-vm-live-evals.md)
- [`docs/live-runs/README.md`](docs/live-runs/README.md)

## Completed Gates

- **Contributor baseline**: local install, no-network smoke path, tests, and
  sandbox runner are documented.
- **Live benchmark selection**: LiveCodeBench code-generation-lite segment is
  prepared from public upstream sources and scored with private tests.
- **Cloud execution lane**: live runs can move to an ephemeral GCP VM with
  Secret Manager-based credentials and durable artifact sync.
- **Artifact discipline**: scorecards, telemetry, compressed logs, archives,
  and SHA-256 hashes are committed for proof runs.
- **First 50-loop improvement proof**: a live DGM run improved from `5/12` to
  `8/12` and tore down the worker VM.

## Active Priorities

1. **Exploit the best parent**

   The 50-loop run reached `8/12` quickly and then plateaued. The next run
   should repeatedly mutate the best `8/12` agents instead of relying only on
   broad archive sampling. Success means a same-segment run either reaches
   `9/12+` or produces enough failure evidence to explain the ceiling.

2. **Stabilize model/tool interaction**

   The run succeeded, but the logs still show malformed edit payloads,
   mutation-proven no-ops, timeouts, and `finish_reason=length` responses.
   Improve structured tool-call repair, edit normalization, and retry behavior
   before expanding to larger benchmark segments.

3. **Add model fallback and matrix runs**

   Keep OpenRouter as the cheap live-eval route, but stop betting the whole run
   on one model. The next matrix should compare the current Qwen baseline with
   at least one stronger or more stable coding model, using the same
   LiveCodeBench segment and the same artifact schema.

4. **Explain no-ops and regressions automatically**

   A human should not need to read a 170k-line controller log to understand a
   failed run. Add no-op clustering, failure-reason summaries, and per-problem
   improvement/regression tables to the committed run cards.

5. **Scale the cloud worker loop**

   Move from "one disposable VM run" to a small controlled worker fleet:
   repeatable launch plans, budget gates, artifact sync, teardown verification,
   and promotion criteria for mutations that deserve follow-up.

## WDSLL Gate

The project is at the first real proof gate: live self-modifying search works
end to end and can improve on a known external benchmark segment. It is not yet
at WDSLL. The remaining gate is sustained autonomous search:

- Launch multiple cloud workers from `main`.
- Run known benchmark segments with deterministic scoring.
- Promote successful mutations and retry promising parents.
- Use fallback models when the primary model fails structurally.
- Preserve enough evidence for another researcher to understand the result.
- Show repeated score movement across runs, not only within one run.

## Benchmark Track

LiveCodeBench is the main public benchmark track for the next cycle because it
is known to other researchers, harder than MBPP-style smoke tests, and includes
private scored tests. The current segment remains useful because it has known
headroom from `8/12` to `12/12`.

Near-term benchmark plan:

- Keep the current 12-problem segment as the regression and exploitation lane.
- Add adjacent LiveCodeBench segments once the tool path is stable.
- Keep MBPP/HumanEval-style tasks only as smoke tests and calibration checks.
- Consider SWE-bench style tasks later, after DGM can reliably mutate and
  preserve improvements across multiple LiveCodeBench runs.

## Publication Bar

A run is publishable only when it includes:

- exact repo commit, config, model, provider, and benchmark segment
- cloud worker plan and teardown evidence
- scorecard with parent-relative and global-best movement
- telemetry with token usage, cost, latency, timeouts, and provider errors
- compressed logs and archive bundle
- checksum manifest
- a README that states what the run proves and what it does not prove

## Next Recommended Cycle

Run an exploit-best LiveCodeBench worker from `main`:

- same 12-problem segment
- 50 loop iterations minimum
- best-parent selection biased toward the `8/12` lineages
- Qwen3 Coder plus one fallback/model-matrix lane
- no-op and malformed-edit summaries in the final run card
- success target: `9/12+`, or a clear explanation of why the current approach
  stalls at `8/12`
