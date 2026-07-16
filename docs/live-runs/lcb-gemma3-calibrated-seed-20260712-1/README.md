# Gemma 3 calibrated seed archive

This bundle replaces the incompatible Qwen-scored parent gate for hybrid
mutation experiments. The three focus parents were evaluated twice each with
`google/gemma-3-27b-it` on the same 12-problem, 512-test LiveCodeBench segment.
Per-benchmark scores are the mean of the two Gemma replicates.

Results:

- `a22a6b70-9c72-4f21-8866-67de9e007c61`: 0.291667 (3.5/12)
- `0173925d-0778-43ad-8c74-e05ee18b3bf2`: 0.250000 (3/12)
- `87bca0da-0a85-4a65-a076-aa3fb9f6f12e`: 0.000000 (0/12)

The archive contains only these calibrated roots. Their parent links were
cleared and their generations reset to zero. This makes subsequent
non-regression decisions compare Gemma children against Gemma parent scores;
the earlier 8/12 values remain valid Qwen proof, but are not a valid selection
threshold for a Gemma solver lane.

Artifacts:

- `archive.tar.gz`: three-agent calibrated seed archive
- `calibration.json`: replicated per-benchmark scores and model identity
- `scorecard.json`: archive summary
- `checksums.sha256`: integrity hashes

This is a calibration artifact, not evidence that Gemma achieved 8/12 or that
any frontier mutation improved the solver.
