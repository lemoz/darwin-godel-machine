# Self-modification patch-contract canary - 2026-06-30

Run ID: `lcb12-selfmod-contract-20260630-1`

This two-generation cloud canary tested commit
`5fa05009591de4e6502abbcd85cb5d12969b9a2e`, which added a stricter
self-modification patch contract, self-modification system prompt, source-file
change detection, and mid-run/final-window nudges when a child spent its budget
without editing agent code.

## Launch

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/run_live_eval_on_cloud_vm.py \
  --project doittogether-prod \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --run-id lcb12-selfmod-contract-20260630-1 \
  --repo-url https://github.com/lemoz/darwin-godel-machine.git \
  --commit 5fa05009591de4e6502abbcd85cb5d12969b9a2e \
  --config config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml \
  --generations 2 \
  --secret OPENROUTER_API_KEY=openrouter-api-key \
  --artifact-dir .dgm-cloud-runs/lcb12-selfmod-contract-20260630-1/artifacts \
  --startup-script-path .dgm-cloud-runs/lcb12-selfmod-contract-20260630-1/startup.sh \
  --output .dgm-cloud-runs/lcb12-selfmod-contract-20260630-1/plan.json \
  --gcs-artifact-uri gs://dgm-live-runs-doittogether-prod/lcb12-selfmod-contract-20260630-1 \
  --fm-provider openrouter \
  --model qwen/qwen3-coder \
  --input-price-per-mtok 0.22 \
  --output-price-per-mtok 1.80 \
  --execute
```

Cloud VM:

- Project: `doittogether-prod`
- Zone: `us-central1-a`
- VM: `dgm-lcb12-selfmod-contract-20260630-1`
- Config: `config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml`
- GCS artifacts: `gs://dgm-live-runs-doittogether-prod/lcb12-selfmod-contract-20260630-1/`

The VM was deleted at the end of the run. A follow-up `gcloud compute instances
describe dgm-lcb12-selfmod-contract-20260630-1` returned `not found`.

## Preflight

All required preflights passed on the VM:

- LiveCodeBench segment generation: 12 benchmarks, 512 tests, 480 private tests
- Docker sandbox smoke: passed
- Cost gate: `requests<=1848`, `input_tokens<=92400000`,
  `output_tokens<=7569408`, `total=$33.9529`, under the `$45` cap

## Result

- Exit code: `0`
- Runtime: `918.988s` / `0.252h`
- Generations requested/reported: `2`
- Base/top agent: `83b9dc1e-8b88-47ad-83c4-7a07cafc2649`
- Base/top score: `0.5833333333` = `7/12`
- Archive total agents: `3`
- Valid agents: `1`
- Successful improvements: `0`
- Estimated provider cost: `$0.226110`
- OpenRouter posts: `84`
- Provider timeouts: `2`
- Empty responses: `0`
- Provider API errors: `0`
- Tokens: `750171` prompt, `33929` completion, `784100` total

Base solved:

- `livecodebench_abc387_b`
- `livecodebench_abc387_c`
- `livecodebench_abc388_b`
- `livecodebench_abc388_c`
- `livecodebench_abc389_a`
- `livecodebench_abc389_d`
- `livecodebench_abc390_b`

Base zero-scored:

- `livecodebench_abc388_d`
- `livecodebench_abc388_e`
- `livecodebench_abc389_e`
- `livecodebench_abc390_d`
- `livecodebench_abc390_e`

## Mutation Evidence

Mutation summary:

- `changed`: `0`
- `noop`: `2`
- no-op children:
  - `e296cccc-730c-4c3f-8db8-de11ec78db4e`
  - `1c2a6957-4575-4b63-9d9d-0a4060ee5bbb`
- valid improved children: `0`

The patch-contract nudges did fire:

- Generation 1: `SELF-MODIFICATION PATCH REQUIRED` after step 4/12 and
  `SELF-MODIFICATION FINAL PATCH WINDOW` after step 10/12.
- Generation 2: the same step 4/12 and step 10/12 nudges fired.

The nudges changed behavior from pure read-only exploration into attempted
`agent.py` edits, but both children failed to make concrete source changes.
The attempted edits used malformed or non-matching `modify` payloads such as
large serialized/list-shaped `search_text` values or exact strings that did not
exist in `agent.py`; both children then returned to more inspection and reached
the 12-step limit.

## Interpretation

This run confirms the patch contract is observable and active in a real cloud
run, but it is not sufficient. The next blocker is not VM routing or no-progress
detection; it is valid patch production.

Recommended next fix:

- Add a structural edit-repair path for self-modification, such as a dedicated
  "safe patch" tool or fallback that can apply a minimal append/replace edit
  from a short declarative patch when ordinary `modify` search text fails.
- Teach the agent to recover from `old_code not found` by reading a narrow line
  range and using exact `content_lines` or a line-targeted patch, not by
  generating larger serialized fragments.
- Keep Qwen3 Coder on small canaries until at least one self-modification child
  is mutation-proven `changed` and valid.

## Artifacts

Committed compact artifacts:

- `plan.json`
- `preflight_commands.txt`
- `exit_code`
- `scorecard.json`
- `telemetry.json`
- `archive.tar.gz`

Full logs remain in the local `.dgm-cloud-runs/.../artifacts/` directory and in
the GCS artifact prefix.
