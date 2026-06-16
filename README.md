# Darwin Gödel Machine

**A Self-Improving AI System for Evolutionary Code Enhancement**

[![GitHub](https://img.shields.io/badge/GitHub-lemoz%2Fdarwin--godel--machine-blue?logo=github)](https://github.com/lemoz/darwin-godel-machine)
[![CI](https://github.com/lemoz/darwin-godel-machine/actions/workflows/ci.yml/badge.svg)](https://github.com/lemoz/darwin-godel-machine/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-beta-orange.svg)

## 🧬 Overview

The Darwin Gödel Machine (DGM) is an innovative implementation of self-improving AI agents that iteratively modify their own Python codebase to enhance their coding capabilities. Unlike traditional approaches that rely on formal proofs, DGM uses empirical validation through coding benchmarks to drive evolutionary improvement.

Based on the research paper **"Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents"** ([arXiv:2505.22954](https://arxiv.org/abs/2505.22954)), this implementation demonstrates how AI systems can achieve self-referential self-improvement through population-based exploration and empirical validation.

For more details, see the [official blog post](https://sakana.ai/dgm/) from Sakana AI.

### 🔑 Key Features

- **🔄 Self-Referential Self-Improvement**: Agents modify their own source code to improve performance
- **📊 Empirical Validation**: Changes validated through coding benchmarks rather than formal proofs
- **🏗️ Population-Based Evolution**: Maintains archive of all valid agents for diverse exploration
- **🤖 Foundation Model Integration**: Supports Claude, Gemini, OpenAI, and OpenAI-compatible endpoints
- **🛠️ Tool-Equipped Agents**: Agents use Bash and file editing tools to solve problems
- **🏪 Agent Archive System**: Stores successful agents with performance and novelty metrics
- **🎯 Benchmark-Driven Evolution**: Uses custom coding challenges to measure improvement
- **🔒 Guarded Execution**: Workspace-scoped file access, command filtering, hard timeouts, and opt-in Docker isolation for benchmark test scripts, agent bash/edit operations, and modified-agent runtime load checks

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- API keys for supported Foundation Models (Claude, Gemini, OpenAI, or an OpenAI-compatible provider)

### Installation

1. **Clone the repository:**
```bash
git clone https://github.com/lemoz/darwin-godel-machine.git
cd darwin-godel-machine
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
```

3. **Verify the no-network demo path:**
```bash
python scripts/verify_demo_path.py
```

This checks benchmark loading, the HumanEval-style reference solution, the
score-movement demo, the committed live-run proof, and the archive-lineage demo
without API keys or model calls. It also checks that the full-process sandbox
runner exposes the explicit network, secret pass-through, discard-changes, and
optional audit-artifact flags used for safer local runs.

4. **Configure API keys:**
```bash
cp .env.example .env
# Edit .env with your API keys
```

5. **Run the system:**
```bash
python run_dgm.py
```

## 🔧 Configuration

The system uses YAML configuration files to control behavior:

```yaml
# config/dgm_config.yaml
fm_providers:
  primary: anthropic  # or 'gemini', 'openai'
  anthropic:
    model: claude-sonnet-4-6
    api_key: ${ANTHROPIC_API_KEY}
  gemini:
    model: gemini-2.5-flash-preview-05-20
    api_key: ${GEMINI_API_KEY}
  openai_compatible:
    model: moonshotai/kimi-k2.7-code
    api_key: ${OPENROUTER_API_KEY}
    base_url: https://openrouter.ai/api/v1

dgm_settings:
  max_iterations: 100
  pause_after_iteration: true
  sandbox_timeout: 300

evaluation:
  use_sandbox: false  # set true to run benchmark tests, agent tools, and runtime load checks in Docker when available

sandbox:
  image_name: dgm-sandbox
  auto_build_image: true
  memory_limit: 2g
  cpu_limit: "1"
  network_mode: none

benchmarks:
  enabled:
    - string_manipulation
    - list_processing  
    - simple_algorithm
```

## 🏗️ Architecture

### Core Components

#### 1. **DGM Controller** (`dgm_controller.py`)
Orchestrates the main evolution loop:
- Parent selection from archive
- Self-modification coordination
- Benchmark evaluation
- Archive management

#### 2. **Agent System** (`agent/`)
LLM-powered coding agents with:
- Foundation Model integration
- Tool usage capabilities (Bash, File editing)
- Task solving and self-modification abilities

#### 3. **Archive Management** (`archive/`)
- **Agent Archive**: Stores every valid agent (unbounded, per the paper) with full lineage
- **Parent Selector**: Implements the paper's selection rule — sigmoid-scaled performance times a 1/(1+children) exploration bonus, sampled categorically
- **Lineage Visualization**: Generate an SVG or HTML family tree from archive metadata

```bash
python scripts/generate_archive_lineage.py --archive-dir archive/agents --output docs/archive-lineage.html
```

![Archive lineage example](docs/archive-lineage-example.svg)

#### 4. **Evaluation System** (`evaluation/`)
- **Benchmark Runner**: Executes agents on coding challenges
- **Validator**: Ensures agents compile and maintain capabilities
- **Scorer**: Calculates performance metrics

#### 5. **Self-Modification** (`self_modification/`)
- **Diagnosis**: Analyzes agent performance issues
- **Proposal**: Generates improvement suggestions
- **Implementation**: Applies code modifications

## 📚 Memory Bank System

The DGM includes a sophisticated **Memory Bank** system that maintains development context and project knowledge across sessions. This is crucial for understanding the project's evolution and current state.

### Memory Bank Structure

The Memory Bank consists of five core files in the `memory-bank/` directory:

#### 📄 `productContext.md`
- **Purpose**: High-level project overview and goals
- **Contains**: Project description, key features, overall architecture
- **Updated**: When fundamental project aspects change

#### 📊 `activeContext.md`
- **Purpose**: Current project status and immediate context
- **Contains**: 
  - Current focus and priorities
  - Recent changes and progress
  - Open questions and issues
- **Updated**: Frequently during development

#### 🏛️ `systemPatterns.md`
- **Purpose**: Recurring architectural patterns and design standards
- **Contains**: 
  - Coding patterns and conventions
  - Architectural decisions and rationale
  - Testing and validation patterns
- **Updated**: When new patterns emerge or existing ones evolve

#### 📋 `decisionLog.md`
- **Purpose**: Record of significant architectural and implementation decisions
- **Contains**:
  - Decision descriptions with timestamps
  - Rationale and reasoning
  - Implementation details and implications
- **Updated**: When major technical decisions are made

#### ✅ `progress.md`
- **Purpose**: Task tracking and completion status
- **Contains**:
  - Completed tasks with timestamps
  - Current tasks in progress
  - Next steps and planned work
- **Updated**: As tasks are completed or priorities change

### Using the Memory Bank

The Memory Bank serves multiple purposes:

1. **Development Continuity**: Maintains context across development sessions
2. **Decision Tracking**: Records why architectural choices were made
3. **Progress Monitoring**: Tracks project evolution and completion
4. **Knowledge Preservation**: Captures lessons learned and patterns discovered
5. **Collaboration**: Helps team members understand project state and history

When working on the DGM, always consult the Memory Bank to understand current context and update it when making significant changes.

## 🔄 How It Works

### The DGM Evolution Loop

1. **Initialize**: Start with a base agent in the archive
2. **Select Parent**: Choose an agent based on performance and novelty
3. **Self-Modify**: Agent analyzes its performance and proposes improvements
4. **Implement**: Agent modifies its own code based on the proposal
5. **Evaluate**: Test the modified agent on coding benchmarks
6. **Archive**: If valid and performs well, add to the agent archive
7. **Repeat**: Continue the cycle to drive continuous improvement

### Agent Capabilities

Each agent is a complete coding system that can:
- **Solve Coding Problems**: Use LLM reasoning to understand and solve tasks
- **Use Tools**: Execute bash commands and edit files
- **Self-Analyze**: Review its own performance and identify weaknesses
- **Self-Modify**: Propose and implement improvements to its own code
- **Maintain Validity**: Preserve its core capabilities while evolving

### Benchmark Examples

The system includes several coding challenges:

```yaml
# String Manipulation Challenge
name: reverse_with_numbers
description: "Reverse alphabetic characters while keeping numbers in place"
inputs: ["abc123def", "hello5world"]
expected_outputs: ["fed123cba", "dlrow5olleh"]
```

For a harder no-network smoke path, see `config/benchmarks/humaneval_style.yaml`.
It contains HumanEval-style standalone function tasks with reference solutions
verified by the integration test suite; add `humaneval_style` to
`benchmarks.enabled` when you want the DGM loop to evaluate against it.

For live score-movement rehearsals, see
`config/benchmarks/humaneval_calibrated.yaml`. It uses 10 public prompt
examples and 50 scored evaluation cases across 10 standalone functions, so the
benchmark has broader hidden-case headroom than the earlier single-pack
`humaneval_headroom` rehearsal.

To demonstrate benchmark score movement without API keys or model calls, compare
the bundled weak and improved HumanEval-style demo solutions:

```bash
python scripts/compare_benchmark_solutions.py \
  --benchmark humaneval_style \
  --baseline docs/demo/humaneval_style_baseline.py \
  --candidate docs/demo/humaneval_style_improved.py \
  --output docs/demo/humaneval_score_movement.json
```

This local comparison should report a baseline score of `0.500`, a candidate
score of `1.000`, and `delta=+0.500`. It verifies the benchmark harness and
reporting path; it is not evidence of autonomous DGM self-improvement.

The planned live rehearsal uses the calibrated hidden-case benchmark. Its
no-network headroom check is:

```bash
python scripts/compare_benchmark_solutions.py \
  --benchmark humaneval_calibrated \
  --baseline docs/demo/humaneval_calibrated_baseline.py \
  --candidate docs/demo/humaneval_calibrated_improved.py \
  --output docs/demo/humaneval_calibrated_score_movement.json
```

This should report a baseline score of `0.600` (`30/50`), a candidate score of
`1.000` (`50/50`), and `delta=+0.400`. The live plan verifier requires the
baseline to stay in a calibrated `0.400` to `0.700` band so the task is neither
already saturated nor too weak to be a useful score-movement target.

For live DGM runs, summarize the generated archive metadata before claiming
score movement:

```bash
python scripts/summarize_archive_scores.py \
  --archive-metadata .dgm-live-runs/<run-id>/archive/archive_metadata.json \
  --output docs/live-runs/<run-id>/scorecard.json \
  --require-improvement
```

`--require-improvement` exits non-zero unless at least one valid child agent
improves on its parent by average benchmark score. The committed
`docs/live-runs/2026-06-12-proof/scorecard.json` intentionally records
`has_improvement=false` for the first live proof because both child agents tied
the already-perfect base score.

The planned live score-movement rehearsal is captured in
`config/live_score_movement.yaml`. It is bounded to two generations, five agent
steps, one benchmark (`humaneval_calibrated`), and a 2,048-token output cap per
model call. Before any live provider call, run the no-network plan check and
verify current provider pricing:

```bash
python scripts/verify_live_score_movement_plan.py
```

As checked against Anthropic's official pricing page on 2026-06-15,
`claude-sonnet-4-6` was listed at `$3 / MTok` input and `$15 / MTok` output.
With a conservative 50,000 input-token assumption per model call, estimate the
bounded rehearsal cost before asking for approval:

```bash
python scripts/estimate_live_run_cost.py \
  --input-price-per-mtok 3 \
  --output-price-per-mtok 15 \
  --assumed-input-tokens-per-call 50000 \
  --max-budget 5
```

After explicit approval, run it through the full-process sandbox runner:

```bash
python scripts/run_dgm_in_sandbox.py \
  --config config/live_score_movement.yaml \
  --generations 2 \
  --allow-network \
  --env ANTHROPIC_API_KEY \
  --audit-output .dgm-sandbox-runs/live-score-movement-audit.json
```

Then summarize the run archive with `scripts/summarize_archive_scores.py
--require-improvement` before claiming benchmark improvement.

### Dry-run model matrix

`config/live_model_matrix.yaml` captures the next comparison harness without
making provider calls. It estimates five bounded trials per model against the
same calibrated live-run shape: Claude Sonnet 4.6 through Anthropic and Kimi
K2.7 Code through an OpenAI-compatible OpenRouter endpoint. Run the verifier
before any live matrix spend:

```bash
python scripts/estimate_model_matrix_cost.py
```

As checked on 2026-06-16, the matrix uses Anthropic's published Claude Sonnet
4.6 pricing (`$3 / MTok` input, `$15 / MTok` output) and OpenRouter's Kimi K2.7
Code listing (`$0.75 / MTok` input, `$3.50 / MTok` output). With the existing
25-request live-run ceiling, a 50,000 input-token assumption per call, 2,048
output-token cap, and five trials per model, the dry-run estimate is
250 model-call slots and `$28.1735` total. This script performs no live calls
and does not require provider API keys.

## 🧪 Running Experiments

### Basic Evolution Run
```bash
# Run with default settings (3 generations)
python run_dgm.py

# Run with custom generation count
python run_dgm.py --generations 10

# Reset system state
python reset_dgm.py
```

### Monitoring Progress
```bash
# View archive contents
ls archive/agents/

# Check evaluation results
ls results/

# Monitor logs
tail -f dgm_run.log
```

### Testing Components
```bash
# Run the full test suite (no API keys needed)
python -m pytest

# Verify the no-network demo/setup path
python scripts/verify_demo_path.py

# Test specific components
python -m pytest tests/unit/test_agent.py
python -m pytest tests/integration/   # includes a full no-network DGM generation
```

## 📈 Performance Tracking

The system tracks several metrics:

- **Agent Performance**: Benchmark scores over time
- **Archive Growth**: Number of valid agents discovered
- **Improvement Rate**: Frequency of successful enhancements
- **Diversity Metrics**: Novelty and variation in agent approaches

Results are stored in the `results/` directory with detailed JSON reports.

## 🔒 Safety Features

- **Workspace Containment**: File edits and bash redirects are resolved and confined to the agent's workspace; path-traversal escapes are rejected
- **Command Filtering**: Dangerous commands are blocked before execution
- **Hard Timeouts**: Benchmark and tool subprocesses are killed (entire process group) on timeout
- **Opt-in Docker Command Isolation**: With `evaluation.use_sandbox: true`, generated benchmark test scripts plus agent bash and edit tool operations run in one-shot Docker containers with image, memory, CPU, timeout, and network settings from `sandbox`
- **Validation Checks**: Modified agents must parse, define a working Agent class, and pass a runtime load check before admission to the archive; with sandboxing enabled, the runtime load check runs in Docker
- **Opt-in Full-Process Runner**: `scripts/run_dgm_in_sandbox.py` can run the `run_dgm.py` controller process inside Docker with the project mounted as the sandbox workspace
- **Human Oversight**: Optional pause points for review
- **Comprehensive Logging**: Full audit trail of all changes

> **Note**: the default `python run_dgm.py` path still runs orchestration and controller/archive logic on the host. Use `scripts/run_dgm_in_sandbox.py` to move the full DGM process into Docker. The runner stages the checkout through `~/.cache/dgm-sandbox` for Docker-mounted execution and syncs successful writes/deletes back to the host checkout unless `--discard-changes` is set; live provider runs require explicit network and secret pass-through. For untrusted evolution experiments, keep using your own container or VM boundary.

### Full-Process Docker Runner

To run the DGM controller process itself inside Docker:

```bash
python scripts/run_dgm_in_sandbox.py \
  --config config/live_dgm_proof.yaml \
  --generations 2 \
  --allow-network \
  --env ANTHROPIC_API_KEY
```

The runner does not pass credentials into the container unless each variable is
named with `--env`, and `--env` is rejected unless `--allow-network` is also set.
Network access is forced off unless `--allow-network` is set, even if the project
config names a permissive Docker network mode. The checkout is copied into a
Docker-mountable cache workspace first, then
successful non-ignored writes and deletes are synced back, so generated
archives, results, workspaces, and logs still persist in the host checkout.
Add `--discard-changes` to keep successful writes/deletes inside the staged
workspace and remove them when the container run finishes.

Before the container starts, the runner prints an audit summary to stderr with
the effective network mode, requested environment variable names, sync mode,
timeout, and staged-workspace cache parent. It never prints environment values.
Add `--audit-output .dgm-sandbox-runs/audit.json` to also write the same
non-secret audit summary as JSON inside the project root. The artifact records
environment variable names only, never values.

To smoke-test the real Docker mount/sync path without API keys or model calls:

```bash
python scripts/verify_sandbox_docker.py
```

This optional check skips successfully when Docker or the `dgm-sandbox` image is
not ready. Add `--build-image --require` when you want the command to build a
missing image and fail instead of skipping.

## 🐛 Troubleshooting

### Common Issues

**API Connection Errors**
```bash
# Verify message formatting and provider config (no network needed)
python -m pytest tests/unit/test_fm_connection.py

# Check rate limits in provider console
```

**Agent Scoring 0.0**
```bash
# Check the benchmark harness end to end
python -m pytest tests/integration/test_benchmark_evaluation.py

# Verify agent code extraction
python -m pytest tests/unit/test_agent_code_extraction.py
```

### Debug Mode
```bash
# Enable verbose logging
export PYTHONPATH=.
python run_dgm.py --log-level DEBUG

# Dump full agent conversations to debug/ (set in config/dgm_config.yaml
# under the active provider): debug_conversation_dump: true
ls debug/conversation_history_*
```

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines:

1. **Fork the repository**
2. **Read the Memory Bank** to understand current context
3. **Create a feature branch**: `git checkout -b feature/amazing-feature`
4. **Update Memory Bank** when making architectural changes
5. **Add tests** for new functionality
6. **Submit a pull request**

### Development Setup

```bash
# Install dependencies (includes pytest)
pip install -r requirements.txt

# Run tests
python -m pytest

# Update Memory Bank
# Edit memory-bank/*.md files as needed
```

## 📖 Documentation

- **Architecture Overview**: `reference-design/dgm-mvp-architecture.md`
- **FM Integration**: `reference-design/fm-interaction-layer.md`
- **Tool Management**: `reference-design/tool-management.md`
- **Research Paper**: `dgm_research_paper.md`
- **Memory Bank**: `memory-bank/` directory

## 🧬 Research Context

This implementation is based on the research paper "Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents" which demonstrates:

- **Performance Improvements**: SWE-bench scores improved from ~20% to ~50%
- **Polyglot Gains**: Performance increased from ~14.2% to ~30.7%
- **Open-Ended Discovery**: Continuous generation of novel agent variants
- **Empirical Validation**: Practical alternative to formal proof requirements

## 📊 Benchmarks and Results

The system has achieved:
- ✅ **Functional Self-Improvement**: Agents successfully modify their own code
- ✅ **Benchmark Performance**: Proper scoring on coding challenges
- ✅ **Population Evolution**: Growing archive of diverse agent variants
- ✅ **Stable Operation**: Reliable execution without infinite loops
- ✅ **Tool Integration**: Effective use of bash and file editing capabilities

## 🔮 Future Enhancements

- **Advanced Benchmarks**: Integration with SWE-bench and HumanEval
- **Multi-Agent Collaboration**: Cooperative improvement strategies
- **Foundation Model Fine-tuning**: Custom model training integration
- **Web Interface**: GUI for monitoring and controlling evolution
- **Advanced Novelty Metrics**: More sophisticated diversity measures
- **Distributed Archive**: Scaling to larger agent populations

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Original DGM research team for the foundational concepts
- Anthropic, Google, and OpenAI for Foundation Model access
- The open-source AI community for tools and inspiration

## 📞 Support

- **Issues**: GitHub Issues tracker
- **Discussions**: GitHub Discussions
- **Documentation**: Check the `docs/` directory and Memory Bank
- **Memory Bank**: Always consult `memory-bank/` for current project context

---

**Ready to evolve some AI? Start with `python run_dgm.py` and watch your agents improve themselves!** 🚀
## 📚 References

### Original Research
- **Paper**: [Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents](https://arxiv.org/abs/2505.22954)
- **Authors**: Jenny Zhang, Shengran Hu, Cong Lu, Robert Lange, Jeff Clune (Sakana AI, UBC, Vector Institute)
- **Published**: arXiv:2505.22954 (2025)

### Additional Resources
- **Official Blog Post**: [Sakana AI - Darwin Gödel Machine](https://sakana.ai/dgm/)
- **Implementation**: This repository provides a complete open-source implementation
- **Related Work**: Gödel machine framework and self-improving artificial general intelligence

### Citation
```bibtex
@article{zhang2025darwin,
  title={Darwin G{\"o}del Machine: Open-Ended Evolution of Self-Improving Agents},
  author={Zhang, Jenny and Hu, Shengran and Lu, Cong and Lange, Robert Tjarko and Clune, Jeff},
  journal={arXiv preprint arXiv:2505.22954},
  year={2025}
}
```

---

## 👨‍💻 Author

**Implementation by**: [@cdossman](https://x.com/cdossman)

**Disclaimer**: This is an independent implementation based on the research paper. Not officially affiliated with Sakana AI.
