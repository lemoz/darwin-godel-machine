# DGM MVP Architecture Plan

**Document Version:** 1.0  
**Created:** 2025-05-31  
**Status:** Draft for Review

## Executive Summary

This document outlines the detailed architecture for the Darwin Gödel Machine (DGM) Minimum Viable Product (MVP). The MVP will demonstrate the core DGM loop: self-improving AI agents that iteratively modify their own Python codebase using Foundation Models (FMs) to enhance their coding capabilities, with empirical validation through custom benchmarks.

## 1. System Overview

### 1.1 Core Concept
The DGM MVP implements a self-referential self-improvement system where:
- Agents are Python codebases that can modify themselves
- Foundation Models drive the self-improvement process
- Changes are validated empirically through coding benchmarks
- A population-based approach explores diverse solutions

### 1.2 MVP Scope
- **Primary FM:** Gemini 2.5 Pro (with support for Anthropic, OpenAI)
- **Benchmarks:** 3-5 simple, self-contained Python coding challenges
- **Self-modification:** Agent code and prompts only (no FM retraining)
- **Parent Selection:** Performance + simple novelty metric
- **Human Oversight:** Optional pause after each iteration

## 2. Architecture Components

### 2.1 Core Modules

#### 2.1.1 DGM Controller (`dgm_controller.py`)
**Responsibilities:**
- Orchestrates the main DGM loop
- Manages the agent archive
- Coordinates between modules
- Handles iteration control and optional pausing

**Key Classes:**
```python
class DGMController:
    def __init__(self, config: DGMConfig):
        self.archive = AgentArchive()
        self.parent_selector = ParentSelector()
        self.self_modifier = SelfModifier()
        self.evaluator = Evaluator()
        self.config = config
    
    def run_iteration(self) -> IterationResult:
        # Main DGM loop logic
```

#### 2.1.2 Agent Architecture (`agent/`)
**Structure:**
```
agent/
├── __init__.py
├── agent.py          # Main agent class
├── tools/            # Tool implementations
│   ├── bash_tool.py
│   ├── edit_tool.py
│   └── base_tool.py
├── fm_interface/     # FM interaction layer
│   ├── api_handler.py
│   ├── providers/
│   │   ├── gemini.py
│   │   ├── anthropic.py
│   │   └── openai.py
│   └── message_formatter.py
└── prompts/          # Prompt templates
    └── system_prompt.py
```

**Key Design Decisions:**
- Modular tool system based on Roo-Code patterns
- Provider-agnostic FM interface
- Dynamic prompt construction
- Clear separation of concerns

#### 2.1.3 Self-Modification Module (`self_modification/`)
**Components:**
- `diagnose.py`: Analyzes agent performance logs
- `propose.py`: Generates improvement suggestions
- `implement.py`: Applies modifications to agent code

**Key Classes:**
```python
class SelfModifier:
    def diagnose_issues(self, agent: Agent, logs: List[EvaluationLog]) -> Diagnosis:
        # Use FM to analyze failure patterns
    
    def propose_improvement(self, diagnosis: Diagnosis) -> Proposal:
        # Generate specific improvement suggestion
    
    def implement_modification(self, agent: Agent, proposal: Proposal) -> Agent:
        # Agent modifies its own code
```

#### 2.1.4 Evaluation Module (`evaluation/`)
**Components:**
- `benchmark_runner.py`: Executes agents on benchmarks
- `validator.py`: Checks agent validity (compiles, can edit)
- `scorer.py`: Calculates performance scores

**Benchmark Structure:**
```python
class Benchmark:
    def __init__(self, name: str, description: str, test_cases: List[TestCase]):
        self.name = name
        self.description = description
        self.test_cases = test_cases
    
    def evaluate(self, agent: Agent) -> BenchmarkResult:
        # Run agent on benchmark
```

#### 2.1.5 Archive Management (`archive/`)
**Components:**
- `agent_archive.py`: Stores all valid agents
- `parent_selector.py`: Implements selection logic
- `novelty_calculator.py`: Computes agent novelty

**Selection Algorithm:**
```python
def select_parent(self, archive: List[ArchivedAgent]) -> Agent:
    # Probability proportional to:
    # score * (1 + novelty_bonus)
    # where novelty_bonus = 1 / (1 + child_count)
```

### 2.2 Supporting Infrastructure

#### 2.2.1 Configuration Management
```yaml
# config/dgm_config.yaml
fm_providers:
  primary: gemini
  gemini:
    model: gemini-2.5-pro
    api_key: ${GEMINI_API_KEY}
  anthropic:
    model: claude-3-5-sonnet
    api_key: ${ANTHROPIC_API_KEY}

benchmarks:
  - name: string_manipulation
    timeout: 30
  - name: list_processing
    timeout: 30
  - name: simple_algorithm
    timeout: 60

dgm_settings:
  max_iterations: 100
  pause_after_iteration: true
  sandbox_timeout: 300
```

#### 2.2.2 Sandboxing & Safety
- Docker containers for agent execution
- Resource limits (CPU, memory, disk)
- Network isolation
- Time limits for all operations
- Comprehensive logging and monitoring

## 3. Data Flow

### 3.1 Main DGM Loop
```
1. Initialize Archive with seed agent
2. While iteration < max_iterations:
   a. Select parent from archive (performance + novelty)
   b. Self-Modification:
      - Diagnose issues from evaluation logs
      - Propose improvement using FM
      - Parent implements proposed change
   c. Evaluate child agent:
      - Run on benchmark suite
      - Validate compilation & editing ability
   d. If valid, add to archive with scores
   e. Optional: Pause for human review
```

### 3.2 Agent Execution Flow
```
1. Agent receives task (problem description, tests, repo)
2. Agent analyzes task using FM
3. Agent uses tools (Bash, Edit) to solve problem
4. Solution validated against test cases
5. Performance logged for future diagnosis
```

## 4. File Structure

```
darwin_godel_machine/
├── dgm_controller.py
├── config/
│   ├── dgm_config.yaml
│   └── benchmarks/
│       ├── string_manipulation.yaml
│       ├── list_processing.yaml
│       └── simple_algorithm.yaml
├── agent/
│   ├── __init__.py
│   ├── agent.py
│   ├── tools/
│   ├── fm_interface/
│   └── prompts/
├── self_modification/
│   ├── __init__.py
│   ├── diagnose.py
│   ├── propose.py
│   └── implement.py
├── evaluation/
│   ├── __init__.py
│   ├── benchmark_runner.py
│   ├── validator.py
│   └── scorer.py
├── archive/
│   ├── __init__.py
│   ├── agent_archive.py
│   ├── parent_selector.py
│   └── novelty_calculator.py
├── sandbox/
│   ├── Dockerfile
│   └── sandbox_manager.py
├── utils/
│   ├── logging.py
│   └── metrics.py
├── tests/
│   └── (unit tests for all modules)
├── scripts/
│   ├── setup.sh
│   └── run_dgm.py
├── docs/
│   ├── user_guide.md
│   └── developer_guide.md
└── requirements.txt
```

## 5. Key Design Patterns

### 5.1 FM Provider Abstraction (from Roo-Code)
- Abstract `ApiHandler` interface
- Concrete implementations for each provider
- Centralized message transformation
- Configuration-driven provider selection

### 5.2 Tool Management (from Roo-Code)
- Individual tool classes with standard interface
- Central tool registry and dispatch
- Clear parameter schemas for FM
- Context injection from orchestrator

### 5.3 Dynamic Prompt Construction
- Modular prompt sections
- Context-aware assembly
- Tool descriptions embedded in prompts
- Support for custom prompt overrides

### 5.4 Robust FM Response Parsing
- XML-like tag parsing for tool calls
- Graceful handling of malformed responses
- Structured output conversion
- Partial response detection

## 6. Implementation Phases

### Phase 1: Core Infrastructure
- [ ] Set up project structure
- [ ] Implement FM provider abstraction
- [ ] Create basic agent architecture
- [ ] Develop tool system (Bash, Edit)
- [ ] Build sandboxing infrastructure

### Phase 2: DGM Core Loop
- [ ] Implement DGM controller
- [ ] Create archive management
- [ ] Develop parent selection logic
- [ ] Build basic evaluation framework
- [ ] Add configuration management

### Phase 3: Self-Modification
- [ ] Implement diagnosis module
- [ ] Create proposal generation
- [ ] Build modification implementation
- [ ] Add safety checks and validation
- [ ] Test self-modification loop

### Phase 4: Benchmarks & Evaluation
- [ ] Design MVP benchmark suite
- [ ] Implement benchmark runner
- [ ] Create scoring system
- [ ] Add performance logging
- [ ] Build evaluation analytics

### Phase 5: Polish & Release
- [ ] Comprehensive testing
- [ ] Documentation
- [ ] Example runs and demos
- [ ] Performance optimization
- [ ] Open-source release preparation

## 7. Success Metrics

### 7.1 Technical Metrics
- Agent improvement over iterations
- Benchmark solve rates
- Modification success rate
- Archive diversity
- System stability

### 7.2 MVP Goals
- Demonstrate 5+ successful self-improvement iterations
- Show measurable performance gains
- Maintain agent validity throughout
- Generate diverse solution approaches
- Provide clear progression visualization

## 8. Risk Mitigation

### 8.1 Technical Risks
- **Risk:** Agents break themselves
  - **Mitigation:** Robust validation, rollback capability
- **Risk:** FM costs escalate
  - **Mitigation:** Rate limiting, budget caps, efficient prompting
- **Risk:** Infinite loops or hangs
  - **Mitigation:** Timeouts, resource limits, monitoring

### 8.2 Safety Considerations
- Sandboxed execution environment
- No network access during agent runs
- Audit trail of all modifications
- Human review checkpoints
- Clear stopping conditions

## 9. Future Enhancements (Post-MVP)

- Support for more complex benchmarks (SWE-bench)
- Advanced novelty metrics
- Multi-agent collaboration
- FM fine-tuning integration
- Distributed archive management
- Web UI for monitoring and control

## 10. Next Steps

1. Review and approve this architecture plan
2. Set up development environment
3. Begin Phase 1 implementation
4. Establish testing framework
5. Create initial seed agent

## Appendix A: Example Agent Structure

```python
# agent/agent.py
class Agent:
    def __init__(self, agent_id: str, codebase_path: str):
        self.agent_id = agent_id
        self.codebase_path = codebase_path
        self.fm_interface = FMInterface()
        self.tools = ToolRegistry()
        
    def solve_task(self, task: Task) -> Solution:
        # Main problem-solving logic
        prompt = self.build_prompt(task)
        
        while not task.is_complete():
            response = self.fm_interface.get_completion(prompt)
            tool_calls = self.parse_tool_calls(response)
            
            for tool_call in tool_calls:
                result = self.tools.execute(tool_call)
                prompt.add_tool_result(result)
        
        return task.get_solution()
```

## Appendix B: Sample Benchmark

```yaml
# config/benchmarks/string_manipulation.yaml
name: String Reversal with Constraints
description: |
  Write a function that reverses a string but keeps 
  numbers in their original positions.
  
test_cases:
  - input: "abc123def"
    expected: "fed123cba"
  - input: "hello5world"
    expected: "dlrow5olleh"
  - input: "123"
    expected: "123"
    
timeout: 30
max_attempts: 3
points: 10
```

This architecture provides a solid foundation for the DGM MVP while incorporating best practices from both the research paper and Roo-Code analysis. The modular design allows for iterative development and easy extension as the project evolves.
