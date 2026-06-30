# LCB12 edit-normalizer improvement canary - 2026-06-30

Run ID: `lcb12-editnorm-20260630-1`

This three-generation cloud canary tested commit
`65238b36fea28b1bf70321328c8455eae603f107`, which repaired malformed edit
payload loops and compacted truncated pseudo-tool assistant history after
`finish_reason=length`.

The run proves the cloud VM lane, LiveCodeBench segment execution,
mutation-proven agent-code edits, valid child loading, child benchmark
evaluation, archive selection, telemetry capture, VM teardown, and one live
benchmark improvement. It does not prove 50-loop stability or robust
open-ended improvement.

## Launch

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/run_live_eval_on_cloud_vm.py \
  --project doittogether-prod \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --run-id lcb12-editnorm-20260630-1 \
  --repo-url https://github.com/lemoz/darwin-godel-machine.git \
  --commit 65238b36fea28b1bf70321328c8455eae603f107 \
  --config config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml \
  --generations 3 \
  --secret OPENROUTER_API_KEY=openrouter-api-key \
  --artifact-dir .dgm-cloud-runs/lcb12-editnorm-20260630-1/artifacts \
  --startup-script-path .dgm-cloud-runs/lcb12-editnorm-20260630-1/startup.sh \
  --output .dgm-cloud-runs/lcb12-editnorm-20260630-1/plan.json \
  --gcs-artifact-uri gs://dgm-live-runs-doittogether-prod/lcb12-editnorm-20260630-1 \
  --fm-provider openrouter \
  --model qwen/qwen3-coder \
  --input-price-per-mtok 0.22 \
  --output-price-per-mtok 1.80 \
  --execute
```

Cloud VM:

- Project: `doittogether-prod`
- Zone: `us-central1-a`
- VM: `dgm-lcb12-editnorm-20260630-1`
- Machine: `n2-standard-8`
- Config: `config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml`
- Model/provider: `qwen/qwen3-coder` via OpenRouter
- GCS artifacts: `gs://dgm-live-runs-doittogether-prod/lcb12-editnorm-20260630-1/`

The VM was deleted successfully at the end of the run.

## Preflight

All required VM preflights passed:

- LiveCodeBench segment generation: 12 benchmarks, 512 tests, 480 private tests
- Docker sandbox smoke: passed
- Cost gate: `requests<=2472`, `input_tokens<=123600000`,
  `output_tokens<=10125312`, `total=$45.4176`, under the `$60` cap

## Result

- Exit code: `0`
- Runtime: `2285.209s` observed, `0.6315h` reported
- Generations requested/reported: `3`
- Base agent: `662011c6-b71d-4c90-be9b-ef2db1bc930a`
- Base score: `0.500` = `6/12`
- Top child: `fa87699b-6b93-4f57-af55-eeff48092ed6`
- Top score: `0.667` = `8/12`
- Best average delta: `+0.167`
- Valid changed children: `3`
- No-op invalid children: `0`
- Successful improvements: `1`
- Archive size: `4`
- Estimated provider cost: `$0.710410`
- OpenRouter posts: `343`
- Provider timeouts/API errors/empty responses: `2/0/0`
- Tokens: `2,194,954` prompt, `126,400` completion, `2,321,354` total
- Finish reason `length`: `6`

Score movement:

| Agent | Parent | Loop Iteration | Mutation | Valid | Score |
| --- | --- | ---: | --- | --- | ---: |
| `662011c6-b71d-4c90-be9b-ef2db1bc930a` | - | 0 | - | yes | `6/12` |
| `7a14195d-002b-435c-ab49-b1cab7a5ff34` | `662011c6-b71d-4c90-be9b-ef2db1bc930a` | 1 | changed | yes | `5/12` |
| `c100dab7-7e97-45b7-b3f2-ecb0e1293bf8` | `662011c6-b71d-4c90-be9b-ef2db1bc930a` | 2 | changed | yes | `5/12` |
| `fa87699b-6b93-4f57-af55-eeff48092ed6` | `662011c6-b71d-4c90-be9b-ef2db1bc930a` | 3 | changed | yes | `8/12` |

The archive metadata records all three children as generation `1` because each
child was produced from the generation-0 baseline parent. The table above uses
loop iteration order from the run.

Baseline benchmark split:

- Solved: `livecodebench_abc387_b`, `livecodebench_abc387_c`,
  `livecodebench_abc388_b`, `livecodebench_abc388_c`,
  `livecodebench_abc388_e`, `livecodebench_abc389_a`
- Failed: `livecodebench_abc388_d`, `livecodebench_abc389_d`,
  `livecodebench_abc389_e`, `livecodebench_abc390_b`,
  `livecodebench_abc390_d`, `livecodebench_abc390_e`

Top-child benchmark split:

- Solved: `livecodebench_abc387_b`, `livecodebench_abc387_c`,
  `livecodebench_abc388_b`, `livecodebench_abc388_c`,
  `livecodebench_abc388_e`, `livecodebench_abc389_a`,
  `livecodebench_abc389_d`, `livecodebench_abc390_b`
- Failed: `livecodebench_abc388_d`, `livecodebench_abc389_e`,
  `livecodebench_abc390_d`, `livecodebench_abc390_e`

Improved benchmarks for the top child:

- `livecodebench_abc389_d`: `0 -> 1`
- `livecodebench_abc390_b`: `0 -> 1`

Regressed child attempts:

- `7a14195d-002b-435c-ab49-b1cab7a5ff34`: `5/12`, regressed
  `livecodebench_abc388_e`
- `c100dab7-7e97-45b7-b3f2-ecb0e1293bf8`: `5/12`, improved
  `livecodebench_abc390_b` but regressed `livecodebench_abc388_c` and
  `livecodebench_abc388_e`

## Mutation Evidence

Mutation summary:

- `changed`: `3`
- `noop`: `0`
- changed child `7a14195d-002b-435c-ab49-b1cab7a5ff34`
- changed child `c100dab7-7e97-45b7-b3f2-ecb0e1293bf8`
- changed child `fa87699b-6b93-4f57-af55-eeff48092ed6`

The edit-normalizer patch worked live: malformed nested or stringified edit
payloads were either repaired into complete source or rejected with clearer
errors, and syntactically invalid Python rewrites were blocked before replacing
working files.

The history compaction patch also worked live: truncated pseudo-tool output
after `finish_reason=length` was compacted before the next model step instead
of being preserved as a large malformed assistant message.

Archive selection behaved correctly: the first two children regressed and did
not become top agents; the third changed child improved the segment and became
the top archived agent.

## Failure Modes

This run still exposed the next blockers before a 50-loop WDSLL run:

- Self-modification still targeted completion-detection behavior instead of
  benchmark solver strategy, verifier quality, or tool discipline.
- Self-modification still used large full-file reads, causing roughly
  30k-token self-mod prompts.
- Qwen still emitted malformed edit payloads, including nested arrays,
  integers, dictionaries, and serialized source fragments.
- Several benchmark attempts passed public samples but failed hidden tests due
  to weak algorithms or poor complexity analysis.
- Some sample-passing solutions were later rewritten and broken, showing the
  need for a late sample-pass finalization guard.
- E-level tasks exposed missing complexity verification; public samples were
  not sufficient evidence of correctness.
- The agent sometimes ran poor shell tests, including no-input executions and
  shell patterns that are not robust across environments.
- Provider behavior was usable but not perfectly stable: `2` provider timeouts
  and `6` length finishes were observed.

## Follow-up Patch

The next local patch should focus on verifier/control reliability before
scaling generation count:

- Add a late sample-pass finalization guard to avoid risky rewrites near the
  step limit.
- Add a constraint and complexity critique after sample pass, especially for
  D/E tasks.
- Escalate repeated edit-format failures into a fresh complete-source rewrite
  instruction.
- Prohibit brittle shell testing patterns and prefer heredocs or `printf`.
- Bias self-modification toward benchmark solver controls, verifier quality,
  tool discipline, and token-efficient reads rather than completion detection.

## Artifacts

Committed compact artifacts:

- `plan.json`
- `preflight_commands.txt`
- `exit_code`
- `scorecard.json`
- `telemetry.json`
- `archive.tar.gz`

Full logs remain in `.dgm-cloud-runs/lcb12-editnorm-20260630-1/artifacts/`
and in the GCS artifact prefix.
