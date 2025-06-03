# Contributing to Darwin Gödel Machine

Thank you for your interest in contributing to the Darwin Gödel Machine project! This document provides guidelines for contributing to this open-source implementation of self-improving AI agents.

## 🚀 Getting Started

### Prerequisites
- Python 3.8+
- Docker (for sandboxed execution)
- API keys for foundation models (Claude, Gemini, or OpenAI)

### Setup
1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/darwin_godel_machine.git`
3. Install dependencies: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and add your API keys
5. Run tests: `python -m pytest tests/`

## 📋 How to Contribute

### Reporting Issues
- Use GitHub Issues for bug reports and feature requests
- Include steps to reproduce for bugs
- Provide context and use cases for feature requests

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
- Test agent modifications in sandboxed environments
- Report security issues privately via GitHub Security tab

## 🏗️ Architecture

### Core Components
- **Agent**: Self-modifying Python agents powered by foundation models
- **Archive**: Population-based storage of discovered agents
- **Evaluation**: Benchmark-driven validation of agent performance
- **Self-Modification**: Diagnosis and proposal system for improvements
- **Sandbox**: Secure execution environment for agent code

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