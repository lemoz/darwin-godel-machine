# Qwen3 Coder guarded-write LiveCodeBench canary - 2026-06-29

This two-generation cloud canary tested the Python write-content guard from
commit `1af790a62d51b55a941a2ba53676c41941a4d635` on the Qwen3 Coder
OpenRouter path.

The run proved that the first guard prevented many list-fragment writes from
poisoning `solution.py`, but it did not make Qwen recover reliably from
malformed tool arguments. It also exposed a second guard gap: some whole-file
Python fragments are syntactically valid, such as `import re` or a dict literal,
but are still not complete replacement modules.

## Launch

```bash
PATH="$PWD/.venv/bin:$PATH" python scripts/run_live_eval_on_cloud_vm.py \
  --project doittogether-prod \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --run-id lcb12-qwen3-guard-20260629-1 \
  --repo-url https://github.com/lemoz/darwin-godel-machine.git \
  --commit 1af790a62d51b55a941a2ba53676c41941a4d635 \
  --config config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml \
  --generations 2 \
  --secret OPENROUTER_API_KEY=openrouter-api-key \
  --artifact-dir .dgm-cloud-runs/lcb12-qwen3-guard-20260629-1/artifacts \
  --startup-script-path .dgm-cloud-runs/lcb12-qwen3-guard-20260629-1/startup.sh \
  --output .dgm-cloud-runs/lcb12-qwen3-guard-20260629-1/plan.json \
  --gcs-artifact-uri gs://dgm-live-runs-doittogether-prod/lcb12-qwen3-guard-20260629-1 \
  --fm-provider openrouter \
  --model qwen/qwen3-coder \
  --input-price-per-mtok 0.22 \
  --output-price-per-mtok 1.80 \
  --execute
```

Cloud VM:

- Project: `doittogether-prod`
- Zone: `us-central1-a`
- VM: `dgm-lcb12-qwen3-guard-20260629-1`
- Config: `config/livecodebench_openrouter_loop12_qwen3_coder_selfmod_recovery.yaml`
- GCS artifacts: `gs://dgm-live-runs-doittogether-prod/lcb12-qwen3-guard-20260629-1/`

The VM was deleted at the end of the run. A follow-up instance-list check for
`dgm-lcb12-qwen3-guard-20260629-1` returned no rows.

## Preflight

All required preflights passed on the VM:

- LiveCodeBench segment generation: 12 benchmarks, 512 tests, 480 private tests
- Docker sandbox smoke: passed
- Cost gate: `requests<=1848`, `input_tokens<=92400000`,
  `output_tokens<=7569408`, `total=$33.9529`, under the `$45` cap

## Result

- Exit code: `0`
- Runtime: `398.017s` / `0.107h`
- Generations requested/reported: `2`
- Base/top agent: `b9b2012c-fe0c-4861-945c-0d76ea1f07e2`
- Base/top score: `0.1666666667` = `2/12`
- Archive total agents: `3`
- Valid agents: `1`
- Successful improvements: `0`
- Estimated provider cost: `$0.130831`
- OpenRouter posts: `77`
- Provider timeouts: `0`
- Empty responses: `1`
- Provider API errors: `0`
- Tokens: `349264` prompt, `29996` completion, `379260` total

Base solved:

- `livecodebench_abc387_b`
- `livecodebench_abc388_b`

Base zero-scored:

- `livecodebench_abc387_c`
- `livecodebench_abc388_c`
- `livecodebench_abc388_d`
- `livecodebench_abc388_e`
- `livecodebench_abc389_a`
- `livecodebench_abc389_d`
- `livecodebench_abc389_e`
- `livecodebench_abc390_b`
- `livecodebench_abc390_d`
- `livecodebench_abc390_e`

## Mutation Evidence

Mutation summary:

- `changed`: `1`
- `noop`: `1`
- changed child: `1b457243-a922-4257-9f04-f909d7570358`
- no-op child: `848215b4-0ca3-4c22-9d6d-bbd0a394422f`
- changed files: `agent.py`
- valid improved children: `0`

The changed child was invalid. Its mutation patch replaced the full `agent.py`
module with a 9-byte fragment, `import re`, and validator rejected it:

```text
Modified agent validation failed: ["No class with 'Agent' in name found in file"]
```

The no-op child spent its self-modification budget reading files and produced no
Python agent code changes. It was archived invalid with `mutation_status=noop`.

During benchmark solving, the new list-fragment guard rejected many malformed
`solution.py` writes like `[[0], [2]]` and partial serialized code fragments.
However, Qwen usually repeated the same bad tool argument after the correction
message. Later in the run, dict-shaped fragments could still pass syntax checks
because a dict literal is valid Python source, even though it is not a real
program.

## Interpretation

This canary answers the immediate scale question:

- Do not scale Qwen3 Coder to a 12-generation run under this harness yet.
- The provider path is stable enough: no timeouts, no API errors, and low cost.
- The blocker is model/tool-call quality, not cloud VM routing or OpenRouter
  transport.
- The first write guard is useful for evidence and damage control, but it is
  not sufficient for model recovery.

Follow-up fix committed after this run:

- `288f29b` `codex: reject partial python overwrites`
- Rejects whole-file collection expressions, not only list literals.
- Rejects replacing a substantial existing Python module with a tiny fragment.
- Rejects replacing an existing module that defines an `Agent` class with one
  that does not.

The next live step should be a small post-`288f29b` canary. If Qwen still
repeats malformed tool arguments, switch to a model matrix or add a provider
formatting fallback before any 12-generation spend.

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
