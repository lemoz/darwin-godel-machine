# Decision Log

This file records architectural and implementation decisions using a list format.
2025-05-30 11:22:45 - Log of updates made.

*

## Decision

*   [2025-05-30 12:19:49] - Adopt the core Darwin Gödel Machine (DGM) approach for self-improving AI.
*   [2025-05-30 12:19:49] - Utilize empirical validation via coding benchmarks (SWE-bench, Polyglot) instead of formal proofs for self-modifications.
*   [2025-05-30 12:19:49] - Implement a population-based open-ended exploration strategy by maintaining an archive of discovered agents.
*   [2025-05-30 12:19:49] - The DGM will be a coding agent implemented in Python, modifying its own codebase.
*   [2025-05-30 12:19:49] - Initial agent will use frozen pretrained Foundation Models (FMs) with tool use capabilities.
*   [2025-05-30 12:19:49] - Focus of self-improvement will initially be on the design of coding agents (prompts, workflows, tools) rather than FM retraining.

*   [2025-05-31 12:01:09] - The MVP will utilize API-based commercial Foundation Models (FMs) rather than locally-run open-source models.
*   [2025-05-31 12:05:04] - For the MVP, Gemini 2.5 Pro (or similar Gemini model) will be the primary target for both agent core tasks and diagnosis/self-improvement. The system architecture should also support user configuration for models from Anthropic, OpenAI, and Google.
*   [2025-05-31 12:06:18] - The computational budget for API calls during MVP development is not a major constraint, and the timeline for completing the MVP is flexible.
*   [2025-05-31 12:07:58] - The MVP benchmark will consist of a set of 3-5 very simple, self-contained Python coding challenges.
*   [2025-05-31 12:09:59] - The MVP's scope for self-modification will focus on the agent's Python code (including its logic, tool use, and prompts sent to FMs), and will exclude FM retraining.
*   [2025-05-31 12:11:18] - For the MVP, parent selection for self-modification will be based on a combination of benchmark performance improvement and a simple novelty metric (e.g., detectable difference in agent code structure).
*   [2025-05-31 12:13:02] - The MVP will include an option for users to pause and review the DGM's state after each full iteration (select parent, self-modify, evaluate, archive update).
## Rationale

*   [2025-05-30 12:19:49] - DGM approach: Aligns with the project goal of creating a self-improving system based on the provided research paper.
*   [2025-05-30 12:19:49] - Empirical Validation: Practical alternative to the infeasible formal proof requirement of the original Gödel Machine. Allows for observable progress and adaptation.
*   [2025-05-30 12:19:49] - Population-based Open-Ended Exploration: Helps avoid local optima, encourages discovery of diverse solutions, and allows for "stepping stones" to future innovations, as demonstrated in the DGM paper.
*   [2025-05-30 12:19:49] - Python Implementation: Turing-complete language suitable for self-modification and aligns with common AI development practices.
*   [2025-05-30 12:19:49] - Frozen FMs with Tool Use: Leverages existing powerful FMs while focusing self-improvement on the agent's design, which is computationally more tractable than FM retraining for initial phases. This is consistent with the paper's experimental setup.
*   [2025-05-30 12:19:49] - Focus on Agent Design: Allows for rapid iteration and tangible improvements in coding capabilities without the immense computational cost and complexity of FM retraining, which is cited as future work in the paper.
*   [2025-05-31 12:01:09] - API-based FMs for MVP: Leverages higher capabilities of commercial models for the initial MVP to accelerate development and demonstrate core DGM functionality more effectively. Addresses potential limitations of smaller, locally-run models for the complex tasks involved, even in a simplified MVP. The trade-off is a dependency on API keys and potential costs, which is accepted for the MVP stage.
*   [2025-05-31 12:05:04] - Specific FM Choice (Gemini 2.5 Pro for MVP) & Multi-Provider Support: Targeting a high-capability model like Gemini 2.5 Pro for the MVP ensures robust performance for core functionalities. Designing for multi-provider support (Anthropic, OpenAI, Google) from the outset provides long-term flexibility and allows users to leverage their preferred models or manage costs according to their needs. This aligns with the open-source nature of the project.
*   [2025-05-31 12:06:18] - Flexible Budget/Timeline for MVP: Allows for more thorough development and testing of the core DGM functionalities for the MVP without being unduly constrained by immediate cost or time pressures. This supports the goal of a robust initial open-source release.
*   [2025-05-31 12:09:59] - MVP Self-Modification Scope (Agent Code/Prompts, No FM Retraining): Aligns with the DGM paper's implemented approach, which explicitly states FM retraining as a future, computationally expensive direction not covered in their experiments. Focusing on agent code/prompt modification keeps the MVP scope manageable and consistent with the source material.
*   [2025-05-31 12:13:02] - MVP Human Oversight (Optional Pause After Iterations): Provides a valuable checkpoint for users of the open-source MVP to observe the system's behavior, understand its state, and potentially intervene if desired. This enhances transparency and control for initial users and developers, even if the DGM paper describes a fully automated process.
*   [2025-05-31 12:11:18] - MVP Parent Selection (Performance + Simple Novelty): Balances rewarding effective agents with encouraging some exploration of different solutions, without introducing excessive complexity for the MVP. A simple novelty metric (e.g., different code structure) is preferred over more complex calculations or just keeping all variants.
*   [2025-05-31 12:07:58] - MVP Benchmark (3-5 Simple Python Challenges): Provides a focused, manageable, and clearly measurable way to evaluate agent performance and improvement for the MVP. Avoids the complexity of larger benchmarks like SWE-bench for the initial release, aligning with the MVP's goal of demonstrating the core DGM loop.

## Implementation Details

*   [2025-05-30 12:19:49] - Initial Agent Tools: Start with a Bash tool and an Edit tool as described in Appendix A.1 of the DGM paper.
*   [2025-05-30 12:19:49] - Parent Selection: Implement parent selection mechanism as described in Appendix A.2 (proportional to performance and novelty bonus based on children count).
*   [2025-05-30 12:19:49] - Self-Improvement Prompts: Utilize an FM (like OpenAI's o1, as per paper) with prompts similar to those in Appendix A.3 to diagnose issues and propose improvements.
*   [2025-05-30 12:19:49] - DGM Algorithm: Follow pseudocode from Appendix A.4 (Initialize archive, loop: SelectParents, SelfModify, Evaluate, AddToArchive if valid).
*   [2025-05-30 12:19:49] - Benchmarks: Use SWE-bench (Verified subset) and Polyglot for evaluation, with a staged evaluation strategy as outlined in Section 4.2 and Appendix B.
*   [2025-05-31 13:32:35] - Adopt modular architecture with clear separation of concerns for DGM MVP: DGM Controller, Agent Architecture, Self-Modification Module, Evaluation Module, and Archive Management.
*   [2025-05-31 13:32:35] - Use provider-agnostic FM interface layer with abstract ApiHandler and concrete implementations for each provider (Gemini, Anthropic, OpenAI).
*   [2025-05-31 13:32:35] - Implement tool system with individual tool classes, central registry/dispatch, and clear parameter schemas for FM integration.
*   [2025-05-31 13:32:35] - Use Docker containers for sandboxed agent execution with resource limits and network isolation.
*   [2025-05-31 13:32:35] - Structure project with dedicated directories for each major module (agent/, self_modification/, evaluation/, archive/, sandbox/).
*   [2025-05-31 13:32:35] - Implement 5-phase development plan: Core Infrastructure (Week 1-2), DGM Core Loop (Week 3-4), Self-Modification (Week 5-6), Benchmarks & Evaluation (Week 7-8), Polish & Release (Week 9-10).
## Rationale

*   [2025-05-31 13:32:55] - Modular Architecture: Enables parallel development, easier testing, and clear boundaries between DGM components. Each module has a specific responsibility, making the system more maintainable and extensible.
*   [2025-05-31 13:32:55] - Provider-Agnostic FM Interface: Allows seamless switching between different FM providers, reduces vendor lock-in, and enables cost optimization by choosing appropriate models for different tasks.
*   [2025-05-31 13:32:55] - Tool System Design: Based on proven patterns from Roo-Code, provides flexibility for adding new tools, clear contract between FM and tools, and centralized error handling.
*   [2025-05-31 13:32:55] - Docker Sandboxing: Ensures safe execution of self-modifying code, prevents resource exhaustion, and provides reproducible execution environments.
*   [2025-05-31 13:32:55] - Structured Project Layout: Clear organization aids navigation, supports team collaboration, and follows Python best practices for package structure.
*   [2025-05-31 13:32:55] - Phased Development Plan: Allows incremental progress validation, early risk identification, and provides clear milestones for tracking progress toward MVP completion.

## Implementation Details

*   [2025-05-31 13:32:55] - DGM Controller will use asyncio for concurrent operations and implement the main loop as described in the DGM paper's Appendix A.4.
*   [2025-05-31 13:32:55] - FM Interface will follow the adapter pattern with a base ApiHandler abstract class and provider-specific implementations.
*   [2025-05-31 13:32:55] - Tools will inherit from a BaseTool class that defines execute() method and parameter schema validation.
*   [2025-05-31 13:32:55] - Sandboxing will use Docker SDK for Python with predefined resource limits (CPU: 1 core, Memory: 2GB, Disk: 1GB, Network: none).
*   [2025-05-31 13:32:55] - Configuration will use YAML files with environment variable substitution for sensitive values like API keys.
*   [2025-05-31 13:32:55] - All modules will have comprehensive unit tests with pytest, aiming for >80% code coverage before MVP release.
*   [2025-05-30 12:19:49] - Safety: Implement sandboxing for agent execution and self-modification, time limits, and monitoring, as discussed in Section 5.
[2025-05-31 14:25:00] - Created self-modification module with three-stage approach: diagnosis (analyzes performance issues), proposal (generates specific code changes), and implementation (executes modifications with rollback capability)
[2025-05-31 17:27:00] - Updated foundation model configurations to latest versions: Gemini 2.5 Flash Preview (gemini-2.5-flash-preview-05-20) and Claude Sonnet 4 (claude-sonnet-4-20250514). This ensures the DGM uses the most current and capable models available. Also updated Anthropic provider validation to include Claude 4 model variants.
[2025-05-31 17:53:15] - Discovered critical security issue: .env.example contained exposed API keys instead of placeholders. Created verification test to confirm user's actual API keys are being used by making timestamped unique requests traceable in API consoles.
[2025-05-31 21:03:07] - Completed Phase 4.1 Integration Testing - Fixed multiple integration issues including parameter mismatches, import errors, missing configurations, and attribute naming inconsistencies to achieve full test suite passage
[2025-06-01 10:28:42] - Fixed initial agent implementation: Changed from returning direct values to generating Python code. The benchmark system expects agents to generate code with function definitions that match the benchmark requirements. This resolves the 0.000 scoring issue.
[2025-01-06 10:37:24] - Fixed BenchmarkTask attribute error in initial agent
- Root cause: Type mismatch - agent expected Dict but received BenchmarkTask object
- Solution: Updated type hints to Any and used getattr() for safe attribute access
- This resolves the "'BenchmarkTask' object has no attribute 'get'" error
[2025-01-06 11:02:54] - Identified root cause of BenchmarkTask.get() error
- Error comes from old workspace agents treating task as dict instead of object
- Found additional bugs in benchmark runner test execution
- System has architectural confusion between framework Agent and self-modifying agents
[2025-01-06 12:33:16] - Fixed BenchmarkTask.get() error with minimal design change
- Root cause: dgm_controller passed BenchmarkTask dataclass to scorer expecting dict
- Fix: Create minimal config dict at call site with expected structure
- Avoided adding dual support or changing core abstractions
- Kept fix localized to prevent design drift in fresh project
[2025-06-01 12:59:00] - Identified connection error root cause: Anthropic handler not passing timeout config to client
  - Issue: AsyncAnthropic client initialized without timeout parameter
  - Impact: Default timeout causes connection errors during intensive API usage
  - Solution: Pass timeout and implement better retry configuration
[2025-06-01 13:15:00] - Retry strategy needs more aggressive delays for rate limiting
  - Current backoff too low: 0.4s → 0.8s → 1.7s
  - Recommendation: Start at 5s minimum for rate limit retries
  - Consider implementing delay between API calls to prevent hitting limits
[2025-06-01 13:28:30] - Fixed import error introduced by attempting to use non-existent Retry class
  - Issue: Tried to import 'Retry' from anthropic library which doesn't exist in installed version
  - Solution: Reverted to simple max_retries=5 parameter instead of custom retry configuration
  - Lesson: Always verify API availability before implementing advanced features
[2025-06-01 14:21:00] - **Decision: Agent Iteration Pattern Issue**
- **Context**: Enhanced logging revealed agent stops using tools after ~34 iterations during self-modification
- **Problem**: Agent gets confused about conversation history and enters repetitive planning without action
- **Evidence**: Iterations 1-34 show tool usage, iterations 35+ show "planning" without tool calls
- **Rationale**: Long conversation history may be overwhelming the agent's context understanding
- **Next Steps**: Need to implement conversation history management or iteration limits to prevent context confusion
[2025-06-01 14:54:00] - **Clarified Agent Architecture Confusion**
- **Context**: User correctly identified that hardcoded responses contradict DGM's purpose
- **Finding**: The DGM correctly uses the proper Agent class (`agent/agent.py`) with LLM and tools
- **Confusion source**: `agents/initial/agent_0.py` appears to be an unused stub file
- **Real issue**: The LLM-powered Agent is scoring 0.0, suggesting it's not generating proper code solutions
- **Next step**: Need to investigate why the Agent with LLM/tools still fails benchmarks
[2025-06-01 15:16:00] - **Fixed Agent-Benchmark Output Format Mismatch**
- **Problem**: Agent was returning full conversational responses instead of just Python code
- **Solution**: Updated system instructions to request markdown code blocks and added code extraction
- **Implementation**: 
  - Modified system prompt to instruct LLM to format solutions in markdown code blocks
  - Added `_extract_code_solution()` method to extract Python code from markdown blocks
  - Maintains backward compatibility with fallback code detection
- **Impact**: This should resolve the 0.0 benchmark scores by ensuring benchmarks receive executable Python code
[2025-06-01 15:53:00] - Fixed benchmark task description bug in evaluation/benchmark_runner.py
Decision: Updated BenchmarkTask to include task_prompt field and modified run_single_benchmark to pass task_prompt instead of generic description to agents
Rationale: Agents were receiving only generic descriptions like "Tests agent's ability to implement basic algorithms" instead of actual task details, causing them to be confused and score 0.000
Impact: Agents should now receive proper task instructions and be able to generate solutions that actually address the benchmark requirements
[2025-06-01 17:26:20] - Implemented EditTool functionality to fix agent execution failures. Agent was attempting to use 'edit' tool which returned "not implemented" errors, causing infinite retry loops. Implemented write/read/append/modify actions for basic file operations.
[2025-06-02 08:38:00] - Critical Discovery: DGM using wrong agent type. The implementation uses a hardcoded dummy agent (agent_0.py) instead of the FM-powered agent (agent/agent.py) described in the research paper. This explains the 0.0 scores - the dummy agent cannot properly solve tasks or self-improve. Decision: Configure DGM to use the real LLM-based agent as the initial agent, aligning with the paper's specification.
[2025-06-02 09:26:00] - Agent Architecture Clarification: Confirmed DGM requires single unified agent design
- Decision: Each agent must be self-contained and capable of both solving coding tasks AND self-modifying
- Rationale: Paper explicitly states "single system" (line 40) without separate meta-agent (line 41)
- Implications: Must resolve relative import issue while preserving unified architecture
- Key insight: Self-modification IS a coding task - agents modify their own code using same capabilities
[2025-01-06 10:34:00] - Chose Option 2 (Fix Loading Mechanism) over Option 1 (Self-Contained Agents)
- Decision: Fix the DGM's agent loading mechanism to support modular agents with imports
- Rationale: 
  - Avoids massive code duplication (each agent would be 2000+ lines)
  - Preserves modern software engineering benefits (modularity, testing, maintenance)
  - Gets us to a working system faster to validate core DGM concepts
  - The paper's goal is self-improvement, not specific architecture
  - Can always build a "compiler" later to create self-contained agents if needed
- Implications:
  - Need to modify dgm_controller.py to properly set Python paths when loading agents
  - Archive will contain modular agents that depend on the framework
  - Agents can still self-modify their core logic while sharing framework code
[2025-01-06 11:03:00] - Clean up agent architecture and create AgentLoader abstraction
- Decision: Remove dummy agents and create a clean abstraction layer for agent loading
- Components to remove:
  - agents/initial/ directory containing hardcoded dummy agents
  - Any test agent implementations that don't use the LLM framework
- Components to create:
  - AgentLoader class to handle Python path resolution and module loading
  - Clean separation between agent logic and loading mechanism
- Rationale:
  - Eliminates confusion between dummy and real agents
  - Provides clean abstraction for handling import issues
  - Maintains single source of truth for agent implementation
  - Enables future extensibility while keeping code DRY
## [2025-06-02 15:44:00] - Agent Execution Model: Multiple LLM Calls Per Iteration

**Decision**: Changed agent architecture from 1 LLM call per iteration to multiple calls within each iteration

**Rationale**:
- Current constraint prevented agents from reacting to tool execution results
- Agents wrote solutions but couldn't verify or debug before declaring completion
- Caused infinite loops as agents never got chance to signal completion after seeing results

**Implementation**:
- Added inner loop within each iteration for multiple LLM calls (max 10 steps per iteration)
- Included safety mechanisms: step limits, nudging for stuck agents
- Updated system prompt to clarify agents can refine solutions before declaring complete

**Benefits**:
- More natural development workflow (write → test → debug → complete)
- Higher quality solutions through iterative refinement
- Eliminates infinite loop problem while maintaining architectural integrity
[2025-06-02 17:11:00] - Fixed agent self-confusion issue by implementing two solutions: (1) Enhanced system prompt to prevent test case invention, (2) Modified benchmark runner to include official test cases in task description, preventing agents from creating contradictory expectations