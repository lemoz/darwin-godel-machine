# Open Queue Triage - 2026-06-12

This packet records the current open GitHub queue and drafts Chris-facing replies
without posting them. The repository state was checked after `git pull --ff-only`
on `main`, and the local default suite passed with `159 passed, 7 skipped, 2 warnings`.

## Summary

| Item | State | CI | Action |
| --- | --- | --- | --- |
| PR #4: isolate benchmark tests in docker | Draft | `pytest` success | Chris decision: merge partial sandbox slice or wait for full runtime sandbox |
| PR #9: add live run cost gate | Draft | `pytest` success | Chris decision: approve default run, reduce run, or change estimate assumptions |
| Issue #1: WebUI/product direction | Open | n/a | Chris voice needed before posting roadmap/product commitments |

## PR #4 Decision Draft

Target: <https://github.com/lemoz/darwin-godel-machine/pull/4>

Recommended decision:

> Keep this PR draft until Chris decides whether partial benchmark-test isolation
> should merge before full agent/tool/self-modification isolation. It is useful
> and tested, but it changes the safety story and intentionally does not complete
> roadmap item 1.

Chris-ready review comment draft:

> This is a first sandboxing slice: generated benchmark test scripts can run in
> one-shot Docker containers with memory, CPU, timeout, working directory, and
> network settings, while the default path still works without Docker. It does
> **not** isolate full agent solving, tool use, or self-modification yet. I’m
> inclined to keep this as a separately reviewable step if you are comfortable
> with the docs explicitly saying the remaining runtime is still host-executed.
> If you want item 1 to land only when full runtime isolation is done, leave this
> draft open and stack the next sandbox PR on top.

## PR #9 Decision Draft

Target: <https://github.com/lemoz/darwin-godel-machine/pull/9>

Recommended decision:

> Treat this as the approval gate for roadmap item 5, not the live-run artifact.
> It should stay draft until Chris approves one of the cost options or asks for
> a different provider/model/scope estimate.

Chris-ready review comment draft:

> This PR does not execute a live DGM run. It adds a no-API estimator and a dated
> estimate for the current default `python run_dgm.py` path: 3 generations,
> Claude Sonnet 4.6, the default three benchmarks, 20 max steps, and an assumed
> 8,000 input tokens per request. The documented ceiling is about $45 using the
> 2026-06-12 Anthropic Sonnet 4.6 rates. Please approve either the default
> 3-generation run, a reduced 1-generation run, or a changed estimate before any
> API budget is spent.

## Issue #1 Reply Draft

Target: <https://github.com/lemoz/darwin-godel-machine/issues/1>

Issue asks about easier installation, WebUI, web search, knowledge learning, and
tool extension plans.

Chris-ready issue reply draft:

> Thanks for trying the project and for the kind words. I agree setup and first
> use need to be easier; the contributor setup and no-key test path have already
> been clarified, and CI now verifies the default suite.
>
> For WebUI, web search, knowledge learning, and broader tool-extension support,
> I’m treating those as larger product directions rather than committed near-term
> roadmap items. The current maintainer focus is making the implementation more
> credible and safer: sandboxing, stronger benchmarks, archive lineage visibility,
> and a documented live run with cost approval first.
>
> A WebUI could make sense after the runtime and safety boundaries are more solid.
> If you have a specific workflow in mind, please share it here so it can be
> scoped against that roadmap.

## Do Not Post Automatically

No GitHub comments were posted while preparing this packet. The drafts above
should be posted only after Chris approves the exact target and text.
