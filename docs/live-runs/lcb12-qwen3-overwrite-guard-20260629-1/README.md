# LiveCodeBench Qwen overwrite guard canary

Run ID: `lcb12-qwen3-overwrite-guard-20260629-1`

Date: 2026-06-29

Commit: `b239e8301ad47fecc6e6fb7ae6f91eec8c9c7420`

Cloud VM: `dgm-lcb12-qwen3-overwrite-guard-20260629-1` in `doittogether-prod/us-central1-a`

GCS artifacts: `gs://dgm-live-runs-doittogether-prod/lcb12-qwen3-overwrite-guard-20260629-1`

Model path: OpenRouter `qwen/qwen3-coder`

Config: `config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml`

## Result

The run completed successfully on a cloud VM and the wrapper deleted the VM after artifact sync.

- Exit code: `0`
- Runtime: 0.251 hours
- Generations: 2
- Total archive agents: 3
- Valid agents: 2
- Base score: 0.166667, 2/12 solved
- Top score: 0.166667, 2/12 solved
- Improvements: 0
- Regressions: 0
- OpenRouter HTTP posts: 143
- Provider timeouts: 0
- Empty responses: 0
- Tokens: 759854 prompt, 64105 completion, 823959 total
- Estimated OpenRouter cost: `$0.282557`

## Mutation Evidence

Generation 1 produced a real changed child:

- Parent: `ff11cdf1-5e39-4962-8e0a-c530063a1209`
- Child: `f7807e87-1702-461b-b8ae-f555ee8693e4`
- Mutation status: `changed`
- Code change: added a coding-practices, debugging, and completion-checklist block to the agent prompt.
- Child score: 0.166667, 2/12 solved
- Delta: +0.000

Generation 2 selected the changed child as parent but produced an invalid no-op child:

- Child: `964b5a76-0faa-4040-a2b9-872efd293da3`
- Mutation status: `noop`
- Valid: false
- Benchmarks run: 0

## Interpretation

Raising the no-op/self-modification ceiling to 12 was useful, but it did not solve the blocker. The run produced one real changed child, yet the changed prompt did not improve the benchmark score. The dominant failure mode was not cloud VM capacity, OpenRouter transport, timeout handling, or mutation proofing.

The controller log contains 90 rejected `solution.py` writes where the model supplied serialized/list-fragment content instead of raw Python source. The guard prevented bad writes, but Qwen repeatedly failed to recover from the corrective tool error. This means the next scaling blocker is model/tool-call argument fidelity for code-write actions.

## Artifacts

- `plan.json`: cloud runner plan and launch parameters.
- `preflight_commands.txt`: VM preflight command transcript.
- `exit_code`: wrapper exit status.
- `scorecard.json`: score, archive, mutation, and parent-child delta summary.
- `telemetry.json`: provider, token, runtime, and failure telemetry.
- `archive.tar.gz`: archived base, changed child, invalid no-op child, and mutation metadata.

## Next Recommendation

Do not scale this exact Qwen path to a 12-generation run. The next cycle should fix tool-call/code-write reliability first:

1. Add a write-repair layer that can recover serialized/list-fragment tool arguments into raw Python only when reconstruction is unambiguous.
2. Add a model matrix canary for Chinese open-source models with better tool-call fidelity, keeping Qwen as one data point rather than the default.
3. Gate larger LiveCodeBench spends on a small canary proving fewer malformed writes and at least one nontrivial task beyond the B-level baseline.
