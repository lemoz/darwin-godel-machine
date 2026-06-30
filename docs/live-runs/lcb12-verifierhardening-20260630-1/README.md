# Live DGM Run: lcb12-verifierhardening-20260630-1

Run date: 2026-06-30
Cloud run id: `lcb12-verifierhardening-20260630-1`
VM: `dgm-lcb12-verifierhardening-20260630-1` in `doittogether-prod/us-central1-a`
Source commit under test: `c371c6a374f0d668d819b117e07c21afa011e44c`
Config: `config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml`
Provider/model: OpenRouter `qwen/qwen3-coder`
GCS mirror: `gs://dgm-live-runs-doittogether-prod/lcb12-verifierhardening-20260630-1`

## Result

This run proves a live, externally scored DGM improvement on a 12-problem LiveCodeBench segment:

- Completed: `true`
- Exit code: `0`
- Generations: `12`
- Runtime: `2.04` hours
- Agents created: `7`
- Archive size: `13`
- Valid evaluated agents: `8`
- Successful improvements: `1`
- Base score: `0.5833333333333334` (`7/12`)
- Top score: `0.6666666666666666` (`8/12`)
- Best average delta: `+0.08333333333333326`
- Improving child: `f2e900e1-6e44-44b8-90ed-db74676b7c38`
- Parent: `ddec7d88-c9c9-4873-ac84-f561ec38feea`
- Improved benchmark: `livecodebench_abc388_e`
- Benchmark regressions in the improving child: none

The top child preserved the parent's solved set and added `livecodebench_abc388_e`.

## Cost And Provider Telemetry

- HTTP POSTs: `710`
- Usage events: `706`
- Prompt tokens: `6,557,965`
- Completion tokens: `281,328`
- Total tokens: `6,839,293`
- Estimated model cost: `$1.949143`
- Provider timeouts: `4`
- Empty responses: `0`
- `finish_reason=length` occurrences: `24`
- Average completion latency: `9.18s`
- Max completion latency: `85.05s`

## Artifact Manifest

- `plan.json`: Cloud VM create/stream/sync/teardown plan.
- `preflight_commands.txt`: Segment, Docker sandbox, and cost-gate commands run on the VM.
- `scorecard.json`: Archive score movement and improvement proof.
- `telemetry.json`: Provider, token, runtime, and score telemetry.
- `controller.log.gz`: Gzipped full controller log.
- `startup.log.gz`: Gzipped VM startup script log.
- `archive.tar.gz`: Archived agent lineage and mutation metadata.
- `exit_code`: VM run exit status.

Artifact SHA-256 values from the committed proof set:

```text
d9674b424fe4f10de0eea412e1db46f94aade5259bd3acb67219d64947a65549  controller.log.gz
5d33fa32040e655c2fe21435882b8dba1e8e94bde79485cb37d7b5f4d06bc5a4  startup.log.gz
9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa  exit_code
567d217236d4c8a49cf08e64275395fa5c26c7d289d0bdf75d5505d3d4f15fdb  scorecard.json
d92828bf5c199bc49cea93b45ecf1739cbd095730617e38638543d1079f38c13  telemetry.json
defa1e769cd4832a3389670a11a90becd51d3bc8c4f5b358d253bedc5d1c1c37  archive.tar.gz
fc636bdd052bfb982913108bc403333e507cc55aae24d314e82203e22796b19a  preflight_commands.txt
```

## VM Teardown

The wrapper deleted the VM at the end of the run, and a follow-up `gcloud compute instances list` returned `Listed 0 items`.

## What This Proves

- The cloud VM lane can prepare a real LiveCodeBench segment, run sandbox preflights, execute a live OpenRouter-backed DGM loop, sync artifacts, and tear down the VM.
- DGM can produce mutation-proven child agents and evaluate them against external benchmark scoring.
- The archive can select an improved child as the next parent.
- The run achieved a real score improvement, from `7/12` to `8/12`, on hidden benchmark scoring.

## What This Does Not Yet Prove

- It is not a 50-generation proof.
- It does not prove stable monotonic improvement; several valid children regressed.
- It does not prove model/tool-call stability. Qwen produced malformed edit payloads, repeated pseudo tool-call XML, and 24 length-finished responses.
- It does not prove the run used the later local hardening commits. This cloud run used `c371c6a374f0d668d819b117e07c21afa011e44c`; later commits in this branch harden stale fallback rejection, Python compile validation, and tie-selection handling.

## Follow-Up Fixes From This Run

- Block stale `solution.py` fallback after known-bad sample or unsafe-complexity evidence.
- Compile-check Python edits, not just `ast.parse`, to catch invalid control flow.
- Reject score-tied children during parent selection when configured, so equal-score descendants do not displace the base or a better ancestor.
- Add a stable model or fallback model lane before scaling to a 50-generation proof.
- Consider a structured repair layer for malformed tool payloads from OpenRouter models.
