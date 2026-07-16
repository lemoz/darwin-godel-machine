# LiveCodeBench runner recovery baseline: 2026-07-13

Run window: 2026-07-13 16:31-16:44 America/New_York  
Run type: four concurrent local, provider-backed native baselines  
Segment: `release_v6_atcoder_loop12`  
Generations: `0`  
Mutation model reserved for the next phase: OpenRouter `openai/gpt-5.6-luna`

## Result

The corrected runner protocol changes turned the earlier Gemini 3.5 and GPT-5.6 Sol zeroes into valid high scores. All four configured providers completed the same 12-task LiveCodeBench segment against private tests.

| Rank | Runner model | Score | Missed tasks | Runtime |
| ---: | --- | ---: | --- | ---: |
| 1 | `google/gemini-3.5-flash` | **11/12** | `abc389_d` | 0.072 h |
| 2 | `openai/gpt-5.6-sol` | **10/12** | `abc388_e`, `abc390_d` | 0.113 h |
| 3 | `anthropic/claude-fable-5` | **8/12** | `abc388_d`, `abc389_d`, `abc389_e`, `abc390_e` | 0.218 h |
| 4 | `google/gemini-2.5-flash` | **5/12** | `abc387_c`, `abc388_c`, `abc388_d`, `abc389_d`, `abc389_e`, `abc390_d`, `abc390_e` | 0.120 h |

Gemini 3.5 and Sol are complementary: Sol solved `abc389_d`, the only task Gemini 3.5 missed. This makes both useful evolution runners even though Gemini 3.5 has the higher aggregate score.

## Protocol repairs under test

- Gemini tool declarations now include an `items` schema for array-valued `content_lines`. The prior Gemini 3.5 zero was an HTTP 400 tool-schema rejection, not model performance.
- Unsafe-command classification now scans tool results rather than input parameters. The prior Sol zero was caused by interpreting the benign parameter `timeout: 30` as a timeout failure.
- Empty optional edit defaults no longer override the one substantive edit payload. This repaired Sol calls that supplied `content: ""` alongside valid `content_lines`.
- Provider errors include bounded, recursively redacted response bodies.

Gemini 2.5, Gemini 3.5, and Fable started from commit `4056c2d8af7422d87f56d6dca8726e78ed97605f`. The corrected Sol rerun used commit `3dac14f48bc49daf00be27ac910b213dffe6a0d9`, which contains the empty-default repair. The other three runs did not encounter that Sol-specific payload shape.

## Fable reliability note

Fable completed the segment and scored 8/12, so it is a valid runner. It was less protocol-efficient on hard tasks: `abc389_e` repeatedly ended at the 2,048-token limit with an empty response, and `abc390_e` produced a NumPy-dependent solution that failed private evaluation. These events are preserved in `combined-local-baselines.log.gz`.

## Cost

OpenRouter account usage was queried immediately before and after this baseline group:

- Start: `$1662.818047`
- End: `$1672.016051594`
- Account-level delta: **`$9.198004594`**

The delta is an upper bound for this proof because it is an account-level counter and could include unrelated concurrent OpenRouter traffic. It leaves the planned `$78` evolution watchdog within the approved `$100` experiment envelope, including estimated VM overhead.

## Proof boundaries

This bundle proves provider-backed runner performance and the protocol repairs on the real 12-task segment. It is local execution, not a cloud-VM proof, and it contains no mutations because each lane ran with zero generations.

An attempted cloud baseline launch created no VM and spent `$0` because local GCP credentials required browser reauthentication. These scores are exclusively from the local parallel baselines and are not presented as cloud results.

## Artifacts

- `aggregate-scorecard.json`: ranked cross-model result and account-level usage delta.
- `<model>/scorecard.json`: exact per-task scores for the model.
- `<model>/dgm_report_*.json`: controller report and runtime.
- `<model>/<model>-evolution.yaml`: exact model/evolution configuration prepared for the next phase.
- `livecodebench_luna_recovery_runner_matrix.yaml`: four-model experiment contract and budget.
- `manifest.json`: materialized config manifest.
- `combined-local-baselines.log.gz`: combined concurrent run log, including the preserved aborted pre-repair Sol attempt and corrected rerun.

## Next phase

Run one 15-generation constrained-mutation worker per model in parallel, all using `openai/gpt-5.6-luna` as the mutator. The fleet shares a `$78` OpenRouter watchdog and targets 12/12 while preserving the easy-task scores.
