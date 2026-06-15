# WebUI Roadmap

This project should not start with a broad product UI. The core DGM loop now
has live-run proof, no-network demo verification, command-level Docker
isolation, and an opt-in full-process Docker runner. A WebUI can build on that
foundation, but it should remain a thin local control surface until the
execution boundary and benchmark story stay easy to verify.

## Current Position

- The default CLI remains the source of truth: `run_dgm.py`,
  `scripts/verify_demo_path.py`, and `scripts/run_dgm_in_sandbox.py`.
- The no-network path must keep working without API keys.
- Live runs still require explicit provider credentials and budget awareness.
- The full-process Docker runner is a staged-workspace boundary, not a
  disposable VM.

## First Useful WebUI

The first WebUI should be local-only and focused on observability, not new
agent capabilities:

1. Configure a bounded run from existing YAML files.
2. Start a no-network verifier or a sandboxed DGM run.
3. Stream logs and show run status.
4. Browse archive agents, lineage, benchmark scores, and result artifacts.
5. Surface the exact command that the UI is running.

The UI should call existing scripts or library entrypoints instead of creating
a second execution path. Any generated run output should remain in the same
archive/results/workspace directories used by the CLI.

## Not First

These requests are reasonable, but they should wait until the local run UI is
boring and reliable:

- Web search during agent runs.
- Knowledge learning or long-term memory products.
- New tool ecosystems or plugin marketplaces.
- Multi-user hosted service behavior.
- Remote execution or queueing.

Each of those expands the security boundary and should come with separate
design notes, tests, and opt-in configuration.

## Safety Requirements

Before a WebUI PR is mergeable, it should prove:

- It does not require API keys for the default test suite.
- It can run `scripts/verify_demo_path.py` from the UI or expose that check.
- It clearly distinguishes host CLI runs from sandboxed full-process runs.
- It does not pass provider secrets to Docker unless explicitly requested.
- It preserves README/SECURITY wording about staged-workspace limits.
- It includes tests for any command construction or process launching logic.

## Suggested Milestones

1. Local read-only status page for archive, results, and live-run proof docs.
2. Local controls for `scripts/verify_demo_path.py`.
3. Local controls for bounded sandboxed runs via
   `scripts/run_dgm_in_sandbox.py`.
4. Archive lineage and score progression browsing.
5. Optional live provider run setup with explicit cost and credential gates.

## Draft Issue Response

Thanks for the feedback. A WebUI is a good direction, especially for making
installation, verification, run monitoring, and archive browsing easier.

The current plan is to keep the WebUI behind the safety and repeatability work:
live-run proof, Docker command isolation, the full-process Docker runner, and
the no-network verifier. The first WebUI should be local-only and should wrap
the existing CLI/scripts rather than invent a new execution path. It should
start with run configuration, log/status viewing, benchmark results, and
archive/lineage browsing.

Web search, knowledge learning, and broader tool extension are useful ideas,
but they expand the security boundary. Those should be separate follow-up
designs after the local WebUI can reliably show and run the existing verified
paths.
