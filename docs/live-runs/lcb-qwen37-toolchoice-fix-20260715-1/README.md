# Qwen 3.7 Max mutation-protocol repair proof

This bundle records the one-generation live proof for the Qwen 3.7 Max
tool-choice compatibility repair. In the broad self-elicitation matrix,
Alibaba rejected every mutation request with HTTP 400 because thinking mode
did not accept the shared required/object `tool_choice` setting. This run used
the provider-compatible `auto_read_then_workspace_change` policy.

## Result

The protocol repair worked: Qwen completed a live mutation attempt without the
previous tool-choice rejection. It made 62 HTTP posts, recorded five retried
timeouts, and had zero provider API errors. The base evaluation reached 9/12,
the highest fresh Qwen 3.7 observation in this experiment series.

Mutation quality did not improve. Qwen used its three allowed self-modification
steps to inspect the workspace but made no executable Python change. The
constrained mutation guard correctly classified and rejected the child as
`no-op`. The proof therefore establishes protocol compatibility, not a Qwen
capability gain.

## Run identity

- Source commit: `679d79004fdaca485ca83073ebe07aa1477f064c`
- Run: `qwenfix-q1-20260715a-qwen37-max`
- Model: `qwen/qwen3.7-max`
- Segment: `release_v6_atcoder_loop12`
- Generations: 1
- Base score: 9/12
- Admitted mutations: 0
- Mutation failure mode: `no-op`
- Provider requests: 62
- Provider timeouts: 5
- Provider API errors: 0
- Tokens: 231,057
- Telemetry price estimate: `$0.367511`
- Worker exit code: 0
- GCS root:
  `gs://dgm-live-runs-doittogether-prod/qwen37-toolchoice-fix-20260715/`

## Orchestration boundary

The recovered worker artifacts are terminal and the worker exit code is `0`,
but `aggregate.json` says `failed`. The original finish trap deleted the
ephemeral VM after GCS sync before the SSH streamer observed `exit_code`, so
the launcher reported a transport race even though it recovered the complete
bundle from GCS.

Commit `55962c1` added a 30-second post-sync delay before fallback self-delete.
The subsequent four-worker held-out transfer run live-proved that fix: every
worker streamed terminal state, recovered local artifacts, and deleted its VM.
The aggregate failure in this bundle must not be interpreted as a model or DGM
run failure.

## Bundle contents

- `aggregate.json` and `launch-plan.json`: exact orchestration result and
  source identity.
- `config.yaml`: exact generated worker configuration.
- `worker/mutation.json` and `worker/mutation.patch`: constrained-mutation
  admission proof; the patch is intentionally empty.
- `worker/scorecard.json` and `worker/telemetry.json`: score, request,
  timeout, token, and cost evidence.
- `worker/archive.tar.gz`, compressed logs, preflight commands, and exit code:
  complete recovered worker proof.
- `checksums.sha256`: SHA-256 integrity manifest.
