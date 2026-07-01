# Live DGM Run: lcb50-qwen3-hardened-20260630-1

Run window: 2026-06-30 to 2026-07-01 UTC
Cloud run id: `lcb50-qwen3-hardened-20260630-1`
VM: `dgm-lcb50-qwen3-hardened-20260630-1` in `doittogether-prod/us-central1-a`
Source commit under test: `215e81d2c4d35b0c93159bc9ce42b0d182dcc1eb`
Config: `config/livecodebench_openrouter_loop50_qwen3_coder_selfmod_recovery.yaml`
Provider/model: OpenRouter `qwen/qwen3-coder`
GCS mirror: `gs://dgm-live-runs-doittogether-prod/lcb50-qwen3-hardened-20260630-1`

## Result

This run proves a full 50-generation live DGM loop on an ephemeral cloud VM against a real 12-problem LiveCodeBench segment:

- Completed: `true`
- Exit code: `0`
- Generations: `50`
- Runtime: `6.92` hours
- Agents created: `36`
- Archive size: `51`
- Valid evaluated agents: `37`
- Successful parent-relative improvements: `5`
- Base score: `0.4166666666666667` (`5/12`)
- Top score: `0.6666666666666666` (`8/12`)
- Best average delta: `+0.16666666666666663`
- Mutations with code changes: `36`
- No-op mutations: `14`
- Total benchmark improvements across parent/child comparisons: `12`
- Total benchmark regressions across parent/child comparisons: `65`

The run achieved live score movement from `5/12` to `8/12`, then plateaued at `8/12`. It did not reach `9/12`.

## Segment

- Segment id: `release_v6_atcoder_loop12`
- Benchmarks: `12`
- Tests: `512`
- Private tests: `480`
- Source: `https://huggingface.co/datasets/livecodebench/code_generation_lite`
- Upstream: `https://github.com/livecodebench/livecodebench`
- Prompt examples are public only; scored tests include private tests.

## Improvement Path

The scorecard records five parent-relative improvements:

- `dbe30f0e-a903-4988-9b92-75434fd069ce` (`5/12`) -> `38688397-bf70-4ebb-a3b0-797ac2425f17` (`6/12`), improving `livecodebench_abc387_c`.
- `dbe30f0e-a903-4988-9b92-75434fd069ce` (`5/12`) -> `0bbee3db-0f2f-4af9-8e55-8e573bb38f11` (`6/12`), improving `livecodebench_abc387_c`.
- `38688397-bf70-4ebb-a3b0-797ac2425f17` (`6/12`) -> `4cda3714-d6b0-4021-9f60-7e1461bbfd06` (`7/12`), improving `livecodebench_abc388_e`.
- `0bbee3db-0f2f-4af9-8e55-8e573bb38f11` (`6/12`) -> `0173925d-0778-43ad-8c74-e05ee18b3bf2` (`8/12`), improving `livecodebench_abc388_e` and `livecodebench_abc389_d`.
- `4cda3714-d6b0-4021-9f60-7e1461bbfd06` (`7/12`) -> `87bca0da-0a85-4a65-a076-aa3fb9f6f12e` (`8/12`), improving `livecodebench_abc389_d`.

The controller final report lists `87bca0da-0a85-4a65-a076-aa3fb9f6f12e`, `0173925d-0778-43ad-8c74-e05ee18b3bf2`, and `a22a6b70-9c72-4f21-8866-67de9e007c61` as tied top agents at `0.667`.

## Cost And Provider Telemetry

- HTTP POSTs: `3249`
- Usage events: `3241`
- Prompt tokens: `29,383,522`
- Completion tokens: `1,379,114`
- Total tokens: `30,762,636`
- Estimated model cost: `$8.946780`
- Provider API errors: `0`
- Provider timeouts: `29`
- Empty responses: `0`
- `finish_reason=length` occurrences: `106`
- Average completion latency: `6.82s`
- Max completion latency: `89.95s`

The pre-run budget gate estimated a worst-case cost of `$179.4655` under the approved `$220` cap.

## Artifact Manifest

- `plan.json`: Cloud VM create/stream/sync/teardown plan.
- `preflight_commands.txt`: Segment, Docker sandbox, and cost-gate commands run on the VM.
- `scorecard.json`: Archive score movement and improvement proof.
- `telemetry.json`: Provider, token, runtime, mutation, and score telemetry.
- `controller.log.gz`: Gzipped full controller log.
- `startup.log.gz`: Gzipped VM startup script log.
- `archive.tar.gz`: Archived agent lineage and mutation metadata.
- `exit_code`: VM run exit status.
- `artifact_hashes.sha256`: SHA-256 checksums for the committed proof files.

Artifact SHA-256 values from the committed proof set:

```text
63136c2dc29b25b9f1247ebdffc59a7abed69f818b745e831ff9432d0db67542  archive.tar.gz
a59d63c706b9fe67ecb2b3c40aeb88520afb8d20f1fad827c6233976d2a5ad18  controller.log.gz
9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa  exit_code
c28c21bf6c55d5ed0d62f1e8f445ee196d88c0d3be63763b474794160a0c8d49  plan.json
5ca1311fa14fd9dc8d9fde2be63fa50ac2ac48bce052931da1c24cf472b427c5  preflight_commands.txt
b4f5435afd80c24ac5314daf05d161995f5e407d48c386d29fdd30e2ce6beb55  scorecard.json
3a27c367e3c832001d0a4e51f7d13da011316e0fd628a812a199fb92449bc424  startup.log.gz
94e9b6e8a7dc01fb007fc5ec1844709fec0dbf2562b7c37af8659d3a237f735c  telemetry.json
```

## VM Teardown

The wrapper deleted the VM at the end of the run, and a follow-up `gcloud compute instances list --filter="name=dgm-lcb50-qwen3-hardened-20260630-1"` returned `Listed 0 items`.

## What This Proves

- The cloud VM lane can prepare a real LiveCodeBench segment, run sandbox preflights, execute a live OpenRouter-backed DGM loop, sync artifacts, and tear down the VM.
- DGM can run 50 live generations with mutation-proven child agents, archive selection, and external benchmark scoring.
- DGM produced real score improvement from `5/12` to `8/12` and rediscovered `8/12` through multiple tied top agents.
- The run produced a complete artifact bundle suitable for comparison and regression tracking.

## What This Does Not Yet Prove

- It does not prove improvement beyond the observed `8/12` ceiling.
- It does not prove monotonic improvement; many valid children regressed from their parents.
- It does not prove the current model/tool interface is stable enough for WDSLL-scale search. The log still shows malformed edit payloads, no-op mutations, timeouts, and length-finished responses.
- `Successful improvements` is parent-relative. It should not be read as five global-best improvements.

## Follow-Up Fixes From This Run

- Add an exploit-best lane that repeatedly mutates the best `8/12` parent instead of relying only on broad archive sampling.
- Add stronger structured repair for malformed `content_lines` and pseudo XML tool payloads from OpenRouter models.
- Add a model fallback or model matrix for the same 12-problem segment, using this run as the baseline.
- Add no-op clustering and failure-reason summaries so fast generations 42-46 style failures are explained without reading the full controller log.
