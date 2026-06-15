# Contributing to Darwin Gödel Machine

Thank you for your interest in contributing to the Darwin Gödel Machine project! This document provides guidelines for contributing to this open-source implementation of self-improving AI agents.

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- Docker is optional. The current opt-in Docker path isolates generated benchmark test scripts, agent bash/edit tool operations, and modified-agent runtime load checks; use your own container or VM for untrusted evolution runs.
- API keys for foundation models (Claude, Gemini, or OpenAI) are needed for live DGM runs, not for the default test suite.

### Setup
1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/darwin-godel-machine.git
   cd darwin-godel-machine
   ```
3. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
4. Install dependencies:
   ```bash
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   ```
5. Run the full default test suite:
   ```bash
   python -m pytest
   ```

### Live DGM Runs

Only configure API keys when you are ready to run the system against foundation model providers:

```bash
cp .env.example .env
# Edit .env with your API keys, then run:
python run_dgm.py
```

## 📋 How to Contribute

### Reporting Issues
- Use GitHub Issues for bug reports and feature requests
- Include steps to reproduce for bugs
- Provide context and use cases for feature requests
- For larger product-direction requests such as WebUI, web search, knowledge learning, or new tool ecosystems, open an issue with the intended workflow first so maintainers can scope it before implementation.

### Code Contributions
1. Create a feature branch: `git checkout -b feature/your-feature-name`
2. Make your changes following our coding standards
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request with a clear description

### Documentation
- Update docstrings for new functions/classes
- Update README.md for significant changes
- Add examples for new features

## 🔧 Development Guidelines

### Code Style
- Follow PEP 8 Python style guidelines
- Use type hints where appropriate
- Write clear, descriptive commit messages
- Keep functions focused and well-documented

### Testing
- Write unit tests for new functionality
- Include integration tests for complex features
- Test both success and failure cases
- Maintain test coverage above 80%

### Security
- Never commit API keys or secrets
- Follow security guidelines in SECURITY.md
- Treat model-written code as untrusted. The built-in Docker path does not yet isolate the model orchestration loop or controller/archive logic.
- Report security issues privately via GitHub Security tab

## 🏗️ Architecture

### Core Components
- **Agent**: Self-modifying Python agents powered by foundation models
- **Archive**: Population-based storage of discovered agents
- **Evaluation**: Benchmark-driven validation of agent performance
- **Self-Modification**: Diagnosis and proposal system for improvements
- **Execution Guards**: Workspace containment, command filtering, hard timeouts, and validation before archive admission

### Key Patterns
- Environment variable configuration
- Tool-based agent architecture
- Empirical validation over formal proofs
- Population-based evolutionary approach

## 🧪 Research Areas

We welcome contributions in these areas:
- Novel benchmarks for coding agent evaluation
- Improved self-modification algorithms
- Enhanced safety and security measures
- Performance optimizations
- Integration with additional foundation models

## 📝 Pull Request Process

1. **Fork & Branch**: Create a feature branch from main
2. **Develop**: Implement your changes with tests
3. **Test**: Ensure all tests pass locally
4. **Document**: Update relevant documentation
5. **Submit**: Create a pull request with:
   - Clear title and description
   - Link to related issues
   - Screenshots/examples if applicable
   - Test results summary

### Review Process
- Maintainers will review within 48 hours
- Address feedback promptly
- Ensure CI/CD checks pass
- Squash commits before merging

## 🎯 Research Goals

This project aims to:
- Implement the DGM paper's core algorithms
- Achieve significant improvements on coding benchmarks
- Provide a platform for self-improvement research
- Maintain safety and security standards

## 🤝 Community

- Be respectful and inclusive
- Help others learn and contribute
- Share knowledge and best practices
- Follow our Code of Conduct

## 📚 Resources

- [Research Paper](dgm_research_paper.md)
- [Architecture Documentation](reference-design/)
- [Memory Bank System](memory-bank/)
- [Security Guidelines](SECURITY.md)

## ❓ Questions?

- Open a GitHub Discussion for general questions
- Use Issues for bug reports and feature requests
- Check existing documentation first
- Be specific and provide context

Thank you for contributing to advancing self-improving AI research! 🚀
