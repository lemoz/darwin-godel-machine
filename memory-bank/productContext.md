# Product Context

This file provides a high-level overview of the project and the expected product that will be created. Initially it is based upon projectBrief.md (if provided) and all other available project-related information in the working directory. This file is intended to be updated as the project evolves, and should be used to inform all other modes of the project's goals and context.
2025-05-30 11:22:08 - Log of updates made will be appended as footnotes to the end of this file.

*

## Project Goal

**Darwin Gödel Machine Implementation**: Implement the Darwin Gödel Machine (DGM), a self-improving AI system that iteratively modifies its own Python codebase to enhance its coding capabilities, empirically validating changes using coding benchmarks (SWE-bench, Polyglot), as detailed in the research paper "Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents".

## Key Features

*   **Self-Referential Self-Improvement:**
    *   Agents modify their own Python codebase to improve coding abilities.
    *   Self-improvement is treated as a coding task.
*   **Empirical Validation:**
    *   Changes validated against coding benchmarks (SWE-bench, Polyglot) instead of formal proofs.
    *   Performance on benchmarks reflects both downstream task-solving and self-improvement capability.
*   **Population-Based Open-Ended Exploration:**
    *   Maintains a growing archive of all discovered (valid) coding agents, starting from a single initial agent.
    *   Parent agents are selected from the archive (proportional to performance and novelty) to generate new agents.
    *   Aims to accumulate diverse "stepping stones" for future breakthroughs.
*   **Core DGM Loop:**
    *   **Self-Modification Phase:** Selected parent agent analyzes its evaluation logs, proposes a new feature/improvement, and implements it into its own codebase, creating a child agent.
    *   **Evaluation Phase:** Child agent is tested on benchmarks; if valid (compiles, retains editing ability), it's added to the archive with its score.
*   **Agent Architecture (Initial):**
    *   Powered by frozen pretrained Foundation Models (e.g., Claude 3.5 Sonnet, o3-mini).
    *   Equipped with tool use capabilities (initial tools: Bash, Edit).
*   **Performance Targets (as per paper):**
    *   SWE-bench: Improve from ~20.0% to ~50.0%.
    *   Polyglot: Improve from ~14.2% to ~30.7%.

## Overall Architecture

*   **DGM System:** A single system that acts as a coding agent.
*   **Coding Agent:**
    *   Implemented as a Python code repository.
    *   Powered by a frozen Foundation Model (FM).
    *   Utilizes tools (e.g., Bash for execution, Editor for file manipulation).
    *   Receives task prompts (problem description, test description, repo location).
*   **Archive:** A collection of all valid (compilable, can edit code) agents generated during the DGM run, along with their performance scores.
*   **Self-Modification Module:**
    *   Takes a parent agent and its evaluation logs as input.
    *   Uses an FM (e.g., o1 model) to diagnose issues and propose improvements (feature suggestion, problem description).
    *   The parent agent then attempts to implement this proposal on its own codebase.
*   **Evaluation Module:**
    *   Takes a newly generated agent and a benchmark suite (e.g., SWE-bench, Polyglot) as input.
    *   Runs the agent on benchmark tasks.
    *   Scores the agent based on task completion.
    *   Validates agent (compilation, retains editing ability).
*   **Parent Selection Module:**
    *   Selects agents from the archive based on performance and novelty (inverse of children count).
*   **Iterative Loop:** Continuously cycles through parent selection, self-modification, and evaluation to grow the archive.
*   **Safety Mechanisms:** Sandboxing, time limits, monitoring, traceable lineage of modifications.
2025-05-30 12:18:58 - Populated Project Goal, Key Features, and Overall Architecture based on the full DGM research paper.