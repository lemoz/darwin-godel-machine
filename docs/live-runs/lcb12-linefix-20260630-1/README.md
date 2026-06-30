# Self-modification line-replace canary - 2026-06-30

Run ID: `lcb12-linefix-20260630-1`

This two-generation cloud canary tested commit
`9ea4aaab15f3ed1ee189502824c040160d93c660`, which added a line-targeted
`edit` mode for self-modification recovery:

- `action="line_replace"` with `line_number`, `line_count`, and
  `content_lines`
- self-modification edit-repair nudges after malformed edit payloads
- self-modification prompt guidance to prefer line replacement after reading a
  narrow line range

This run proves the VM lane can execute a real LiveCodeBench DGM loop, produce
mutation-proof child artifacts, and fully evaluate a changed child. It did not
yet prove net score improvement.

## Launch

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/run_live_eval_on_cloud_vm.py \
  --project doittogether-prod \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --run-id lcb12-linefix-20260630-1 \
  --repo-url https://github.com/lemoz/darwin-godel-machine.git \
  --commit 9ea4aaab15f3ed1ee189502824c040160d93c660 \
  --config config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml \
  --generations 2 \
  --secret OPENROUTER_API_KEY=openrouter-api-key \
  --artifact-dir .dgm-cloud-runs/lcb12-linefix-20260630-1/artifacts \
  --startup-script-path .dgm-cloud-runs/lcb12-linefix-20260630-1/startup.sh \
  --output .dgm-cloud-runs/lcb12-linefix-20260630-1/plan.json \
  --gcs-artifact-uri gs://dgm-live-runs-doittogether-prod/lcb12-linefix-20260630-1 \
  --fm-provider openrouter \
  --model qwen/qwen3-coder \
  --input-price-per-mtok 0.22 \
  --output-price-per-mtok 1.80 \
  --execute
```

Cloud VM:

- Project: `doittogether-prod`
- Zone: `us-central1-a`
- VM: `dgm-lcb12-linefix-20260630-1`
- Machine: `n2-standard-8`
- Config: `config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml`
- Model/provider: `qwen/qwen3-coder` via OpenRouter
- GCS artifacts: `gs://dgm-live-runs-doittogether-prod/lcb12-linefix-20260630-1/`

The VM was deleted at the end of the run. A follow-up
`gcloud compute instances describe dgm-lcb12-linefix-20260630-1` returned
`not found`.

## Preflight

All required VM preflights passed:

- LiveCodeBench segment generation: 12 benchmarks, 512 tests, 480 private tests
- Docker sandbox smoke: passed
- Cost gate: `requests<=1848`, `input_tokens<=92400000`,
  `output_tokens<=7569408`, `total=$33.9529`, under the `$45` cap

## Result

- Exit code: `0`
- Runtime: `1295.934s` / `0.3567h`
- Generations requested/reported: `2`
- Base/top agent: `1cf305e1-ebbd-4b08-b359-0cfc0ed64441`
- Base/top score: `0.500` = `6/12`
- Archive total agents: `3`
- Valid agents: `2`
- Successful improvements: `0`
- Best average delta: `+0.000`
- Estimated provider cost: `$0.335464`
- OpenRouter posts: `145`
- Provider timeouts: `3`
- Empty responses: `0`
- Provider API errors: `0`
- Tokens: `1049473` prompt, `58100` completion, `1107573` total

Score movement:

- Base agent solved `6/12`.
- Changed child `54cebc98-fa29-41b9-986b-79fd79d8b482` also solved `6/12`.
- The child improved `livecodebench_abc389_a`: `0 -> 1`.
- The child regressed `livecodebench_abc388_e`: `1 -> 0`.
- Ten benchmarks were unchanged.

Base solved:

- `livecodebench_abc387_b`
- `livecodebench_abc387_c`
- `livecodebench_abc388_b`
- `livecodebench_abc388_c`
- `livecodebench_abc388_e`
- `livecodebench_abc390_b`

Changed child solved:

- `livecodebench_abc387_b`
- `livecodebench_abc387_c`
- `livecodebench_abc388_b`
- `livecodebench_abc388_c`
- `livecodebench_abc389_a`
- `livecodebench_abc390_b`

## Mutation Evidence

Mutation summary:

- `changed`: `1`
- `noop`: `1`
- no-op child: `10dabaa1-faab-4516-a766-b0f16836c9ec`
- changed child: `54cebc98-fa29-41b9-986b-79fd79d8b482`
- changed code files: `agent.py`
- changed tree SHA-256:
  `657d9b2d322ea837895a29f02737f887544a16e616668699dbdc8fc94bd823ff`

The new line-replace path was exercised in the live self-modification loop:

- Generation 1 attempted `action="line_replace"` but first targeted a bad line
  range, then produced malformed `content_lines`, then syntax-invalid Python.
- The self-modification edit-repair nudge fired after malformed
  `content_lines`.
- Generation 2 again attempted `line_replace`; after malformed attempts, it
  produced a mutation-proven changed child.

The changed child was real but not yet the right kind of self-improvement. Its
patch landed in the task-solver system prompt/example text around the task
completion instructions, not in the intended `_extract_code_solution`
implementation. That changed the agent behavior surface enough to create
benchmark movement, but it was not a controlled functional fix.

## Interpretation

This run moves the project forward in three concrete ways:

- The cloud VM lane is working end to end: provision, preflight, live
  LiveCodeBench, artifact sync, and teardown.
- DGM can now produce a mutation-proven changed child under the Qwen3 Coder
  OpenRouter lane.
- The changed child can be fully evaluated and archived with parent-child
  benchmark deltas.

It does not satisfy the 0-to-50/WDSLL improvement goal yet. The blocker is now
more specific: changed children are possible, but edits are still poorly
targeted and benchmark-task repair is wasting steps on malformed tool payloads.

Recommended next gate before scaling beyond two generations:

- Add malformed-tool repair for ordinary benchmark tasks, not just self-mod
  tasks, so bad `content_lines` values trigger an immediate corrected retry.
- Add a stricter self-mod patch target contract: changed children must modify an
  executable method/function body or a declared prompt block, not arbitrary
  docstring/example text.
- Add syntax-error line-range repair for `line_replace` so a failed replacement
  prompts the model to read the exact affected range and retry a smaller patch.
- Re-run a 5-generation cloud gate and scale to 20/50 only after a changed child
  is non-regressing without offsetting benchmark regression.

## Artifacts

Committed compact artifacts:

- `plan.json`
- `preflight_commands.txt`
- `exit_code`
- `scorecard.json`
- `telemetry.json`
- `archive.tar.gz`

Full logs remain in `.dgm-cloud-runs/lcb12-linefix-20260630-1/artifacts/` and
in the GCS artifact prefix.
