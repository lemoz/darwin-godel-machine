# Cloud VM live eval lane

This lane moves expensive DGM live evaluations off the maintainer laptop and
onto a fresh, disposable cloud VM. The VM is a worker, not the source of truth:
it clones an exact commit, runs deterministic benchmark scoring, writes
continuous artifacts, and is torn down after artifact sync.

## Current runner

`scripts/run_live_eval_on_cloud_vm.py` builds a non-secret GCP plan and startup
script. It can also execute the plan when `--execute` is supplied.

The plan records:

- exact repository URL, commit, config, and generation count
- VM project, zone, machine type, image, and boot disk size
- required env var names and Secret Manager secret names, never secret values
- startup log, controller log, scorecard, telemetry, and local artifact paths
- create, stream-log, sync-artifact, and teardown commands
- optional `gs://...` destination for continuous artifact rsync from the VM

The startup script runs:

1. install runtime dependencies on a fresh Debian VM
2. clone the repo and `git checkout` the requested commit
3. create a Python virtualenv and install `requirements.txt`
4. load secrets from Secret Manager and/or `/etc/dgm-live.env`
5. run `python run_dgm.py --config ... --generations ...`
6. write `controller.log`, `scorecard.json`, and `telemetry.json`
7. continuously rsync artifacts to GCS when `--gcs-artifact-uri` is set
8. write an `exit_code` artifact and exit with the DGM process status

## Telemetry

`scripts/summarize_live_run_telemetry.py` converts durable run artifacts into a
single JSON report with:

- provider metadata from logs: model, base URL, timeout, POST count, timeouts,
  empty responses, API errors, finish reasons, and latency summary
- token usage events, prompt tokens, completion tokens, total tokens, and
  estimated cost from caller-supplied prices
- deterministic score movement from `scorecard.json`
- loop-order archive summaries and zero-score counts by benchmark from
  `archive_metadata.json`
- final DGM summary from `dgm_report_*.json`

The current per-task failure reason field is intentionally conservative. It
reports observed failure signals from logs plus zero-score counts by benchmark;
it does not claim to know root cause for each failed test unless the runner has
emitted that evidence.

## Example dry plan

```bash
python scripts/run_live_eval_on_cloud_vm.py \
  --project "$GCP_PROJECT" \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --run-id loop12-proof \
  --repo-url https://github.com/lemoz/darwin-godel-machine.git \
  --commit "$(git rev-parse HEAD)" \
  --config config/livecodebench_openrouter_loop12_host.yaml \
  --generations 10 \
  --secret OPENROUTER_API_KEY=openrouter-api-key \
  --artifact-dir .dgm-cloud-runs/loop12-proof/artifacts \
  --startup-script-path .dgm-cloud-runs/loop12-proof/startup.sh \
  --output .dgm-cloud-runs/loop12-proof/plan.json \
  --gcs-artifact-uri gs://my-dgm-runs/loop12-proof \
  --fm-provider openrouter \
  --model moonshotai/kimi-k2.7-code \
  --input-price-per-mtok 0.74 \
  --output-price-per-mtok 3.50
```

Add `--execute` only after reviewing the plan and confirming the service account
has Secret Manager access for the listed secret names.

## Completion bar for publication run cards

A completed cloud run should commit or publish:

- `plan.json` with non-secret launch details
- `startup.sh` or a checksum of the exact startup script
- `startup.log`
- `controller.log`
- `scorecard.json`
- `telemetry.json`
- `dgm_report_*.json`
- a README that states score movement, benchmark scope, exact commit, model,
  cost, timeout/empty-response counts, and caveats

Benchmark scoring remains deterministic. An LLM verifier can be added as an
advisory audit layer, but it is not the judge for pass/fail or score movement.
