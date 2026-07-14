# Live Run Evidence

This directory contains committed evidence from DGM live runs. A run card is
not just a narrative summary: it should point to the exact config, scorecard,
telemetry, logs, archive, and launch plan needed to inspect the result.

## Canonical Proof Run

| Run | Benchmark | Model | Loop iterations | Score movement | Status |
| --- | --- | --- | ---: | ---: | --- |
| [`lcb50-qwen3-hardened-20260630-1`](lcb50-qwen3-hardened-20260630-1/) | LiveCodeBench lite, 12 problems | OpenRouter `qwen/qwen3-coder` | 50 | `5/12` to `8/12` | Complete, VM torn down |

This is the current proof bundle to cite first. It demonstrates:

- a live DGM loop launched on an ephemeral cloud VM
- real LiveCodeBench scoring with private tests
- mutation-proven child agents
- archive selection and parent-relative improvements
- committed logs, telemetry, scorecard, archive, and checksum manifest
- cloud worker teardown verification

Important nuance: `run_dgm.py --generations 50` controls loop iterations. The
archive lineage depth in this proof reached generation 4 because many loop
iterations explored siblings from existing parents.

## Research Matrix Proof

| Run | Benchmark | Models | Search | Result | Status |
| --- | --- | ---: | ---: | --- | --- |
| [`lcb-self-elicitation-broad8-20260714-1`](lcb-self-elicitation-broad8-20260714-1/) | LiveCodeBench, 12 problems | 8 across 5 providers | 16 ladders, 209 executed loops | Gemini +3 reliable overhang; Sol and Fable +1; Grok native 11/12 | Complete, all VMs torn down |

This is the canonical proof for the self-elicitation/capability-overhang research
direction. It keeps native variation, replicated achieved scores, one-off peaks,
provider incompatibilities, endpoint spend, and telemetry estimates separate.

## Earlier Runs

The other directories preserve the path that made the proof run possible:

- `lcb12-*`: focused 12-loop investigations around no-ops, edit repair,
  verifier hardening, model behavior, and score movement.
- `lcb24-*`: early cloud worker runs used to harden launch, artifact sync, and
  retry behavior.
- `livecodebench-openrouter-*`: earlier OpenRouter LiveCodeBench segment and
  scale runs.
- `2026-06-12-proof`: first live proof bundle. It is useful historically, but
  it did not show benchmark improvement because both child agents tied an
  already-perfect local benchmark score.

## Publication Checklist

Before a live run is treated as externally understandable evidence, commit or
publish:

- `README.md` with result, benchmark scope, caveats, and next fixes
- `plan.json` with non-secret cloud launch details
- `preflight_commands.txt`
- `scorecard.json`
- `telemetry.json`
- compressed controller and startup logs
- archive bundle or archive metadata
- `exit_code`
- checksum manifest
- VM teardown evidence

Benchmark scoring remains deterministic. LLM-based review can be useful as an
audit layer, but it is not the scoring authority for these proof bundles.
