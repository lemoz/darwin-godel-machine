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

### Sandboxing
- All agent code execution happens in Docker containers
- File system access is restricted to agent workspace
- Network access is controlled
- Time limits prevent infinite loops

### Input Validation
- All agent modifications are validated before execution
- Import restrictions prevent dangerous system calls
- Code size limits prevent excessive modifications

### Monitoring
- All agent activities are logged
- Modification history is tracked
- Performance metrics are recorded

## ⚠️ Security Warnings

### Development Environment
- Never run untrusted agent code outside sandbox
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