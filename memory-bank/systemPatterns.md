# System Patterns *Optional*

This file documents recurring patterns and standards used in the project.
It is optional, but recommended to be updated as the project evolves.
2025-05-30 11:22:52 - Log of updates made.

*

## Coding Patterns

*   [2025-05-30 12:20:16] - Self-modifying Python code: The DGM agent's core logic is in Python and it modifies its own codebase.
*   [2025-05-30 12:20:16] - Tool Use via FMs: Agents utilize external tools (Bash, Editor initially) through an FM, which decides the action and tool. Tool definitions include name, description, and JSON input schema.
*   [2025-05-30 12:20:16] - Prompts for Self-Improvement: Specific prompts are used with an FM (e.g., o1) to analyze evaluation logs and suggest improvements for the agent.

## Architectural Patterns

      *   [2025-05-31 13:14:03] - **Roo-Code Prompting Strategy:**
          *   **Dynamic Assembly:** System prompts are constructed modularly from various static and dynamically generated sections (e.g., role definition, tool descriptions, rules, capabilities, custom instructions).
          *   **Explicit Tool Enablement:** Tool descriptions, including names, parameters, and schemas, are explicitly injected into the prompt, enabling the FM to correctly format tool calls.
          *   **Contextual Grounding:** Prompts are rich with context like OS, CWD, current mode, and user settings.
          *   **Layered Customization:** Supports global custom instructions, mode-specific base instructions, and complete override via custom prompt files (e.g., `.roo/prompts/<mode_slug>.md`).
          *   **Separation of Concerns:** Prompt assembly logic (`system.ts`) is distinct from the content of individual prompt sections (imported from `./sections/`).
          *   **File-based Overrides:** If a custom prompt file exists for a mode, it's prioritized. These custom files are expected to manage their own tool instructions if tools are to be used.

      *   [2025-05-31 13:15:13] - **Roo-Code FM Response Parsing Strategy (`parseAssistantMessageV2.ts`):**
          *   **Iterative Index-Based Parsing:** Efficiently processes the FM's raw string output by iterating with an index, avoiding character-by-character accumulation.
          *   **XML-like Tag Detection:** Uses `startsWith` with offsets to detect opening/closing tags for tools and parameters (e.g., `<tool_name>`, `</param_name>`). Precomputed Maps of valid tags enhance lookup speed.
          *   **Structured Output:** Converts the raw string into an array of `AssistantMessageContent` objects, distinguishing between `TextContent` and `ToolUse` blocks.
          *   **State Management:** Tracks the start indices of current text, tool use, and parameter blocks to enable accurate slicing when a block is closed.
          *   **Robustness:** Includes special handling for `write_to_file`'s `content` parameter (using `indexOf` and `lastIndexOf` for the content tags within the tool's slice) and marks incomplete blocks (ending at string termination) as `partial: true`.

*   [2025-05-30 12:20:16] - DGM Core Loop: Iterative cycle of Parent Selection -> Self-Modification -> Evaluation -> Archive Update.
*   [2025-05-30 12:20:16] - Population Archive: Maintaining a growing archive of all valid discovered agents to enable open-ended exploration and serve as stepping stones.
*   [2025-05-30 12:20:16] - Staged Evaluation: Using smaller benchmark subsets for initial validation and progressively larger subsets for stronger candidates to manage computational cost.
*   [2025-05-30 12:20:16] - Sandboxed Execution: Running agent execution and self-modification in isolated environments for safety.

*   [2025-05-31 12:36:33] - FM Provider Abstraction Layer: Inspired by Roo-Code, implement a layer that abstracts interactions with different Foundation Models. This involves a common interface (e.g., `ApiHandler`) with specific implementations for each provider (e.g., `GeminiHandler`, `AnthropicHandler`). This allows for flexibility in choosing FMs and centralizes provider-specific logic, including message transformation and SDK usage.
*   [2025-05-31 12:36:33] - Centralized Task Object for FM Interaction: Encapsulate individual FM interactions within a `Task`-like object that holds the current API handler and manages the operation's lifecycle.
*   [2025-05-31 12:36:33] - Standardized Internal Message Format with Transformation: Adopt a consistent internal message format (e.g., similar to Anthropic's) and implement transformation functions to convert this to/from provider-specific formats.
## Testing Patterns

*   [2025-05-30 12:20:16] - Empirical Validation on Benchmarks: Using established coding benchmarks (SWE-bench, Polyglot) to test agent performance and validate self-modifications.
*   [2025-05-30 12:20:16] - Pass@1 Evaluation: Agents are evaluated without seeing ground-truth test results during the attempt (for Polyglot, specifically).
*   [2025-05-30 12:20:16] - Agent Validity Check: Ensuring agents compile and retain codebase-editing functionality before being added to the archive.