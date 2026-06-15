# Security Guidelines

## 🔐 API Key Management

### Environment Variables
- **NEVER** commit `.env` files to git
- Always use `.env.example` as a template 
- Store actual API keys only in `.env` locally
- Use environment variables in production: `${VARIABLE_NAME}`

### Required API Keys
```bash
# Copy .env.example to .env and fill in your keys:
cp .env.example .env
```

- `ANTHROPIC_API_KEY` - Claude API access
- `GEMINI_API_KEY` - Google Gemini API access  
- `OPENAI_API_KEY` - OpenAI API access (optional)

## 🛡️ Security Measures

### Execution Guards (current)
- File edits are path-resolved and confined to the agent's workspace; traversal escapes (`../`) are rejected
- Bash output redirects are resolved against the workspace and blocked if they escape it; dangerous commands are filtered
- Benchmark and tool subprocesses run under hard timeouts, and the entire process group is killed on expiry
- Agent modifications must parse, define a working Agent class, and load successfully before archive admission

### Docker Command Isolation (opt-in)
- Set `evaluation.use_sandbox: true` to run generated benchmark test scripts and agent bash tool commands in one-shot Docker containers when Docker is available
- Sandbox containers use the configured memory, CPU, timeout, working directory, and `network_mode: none` defaults from `config/dgm_config.yaml`
- The sandbox image is built automatically when `sandbox.auto_build_image: true`
- If Docker or the sandbox image is unavailable, benchmark and bash command execution fall back to the direct subprocess path rather than failing the default no-Docker workflow

### Remaining Isolation Limits
- The model orchestration loop, file-edit tool, and archive/controller logic still execute in the configured workspace on the host
- Treat every evolution run as executing model-written code on your machine: run inside your own container or VM if that is not acceptable

### Input Validation
- All agent modifications are validated before execution
- Generated benchmark harness code validates function names before embedding them
- Code size limits prevent excessive modifications

### Monitoring
- All agent activities are logged
- Modification history is tracked
- Performance metrics are recorded

## ⚠️ Security Warnings

### Development Environment
- Agent execution is guarded but not fully isolated — run untrusted experiments in a container or VM
- Keep API usage within reasonable limits
- Monitor agent behavior for unexpected patterns

### Production Deployment
- Use environment variables for all secrets
- Enable audit logging
- Implement rate limiting
- Regular security updates

## 🚨 Incident Response

If you suspect a security issue:
1. Stop the DGM system immediately
2. Check logs for unusual activity
3. Rotate API keys if compromised
4. Report issues via GitHub Security tab

## 📋 Security Checklist

Before pushing to GitHub:
- [ ] `.env` file is not tracked by git
- [ ] No hardcoded API keys in source code
- [ ] `.env.example` has placeholder values only
- [ ] All secrets use environment variable references
- [ ] Security documentation is up to date

## 🔄 Regular Maintenance

- Rotate API keys quarterly
- Update dependencies regularly
- Review access logs monthly
- Test backup procedures
