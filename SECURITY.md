# Security Policy

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security vulnerability in API Chaos Agent, please report it responsibly.

### How to Report

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please:

1. Email your findings to security@api-chaos-agent.dev
2. Include a detailed description of the vulnerability
3. Provide steps to reproduce if possible
4. Include the impact assessment

We will acknowledge your report within 48 hours and provide a detailed response within 7 days.

### What We Consider Security Issues

- Authentication bypass
- API key exposure in logs or responses
- Schema data leakage to external services
- Injection vulnerabilities
- Privilege escalation
- Denial of service vulnerabilities

### What We Do NOT Consider Security Issues

- Missing rate limiting (configurable feature)
- Default configuration values (documented in configuration reference)
- Feature requests for additional security controls

## Security Architecture

API Chaos Agent is designed with security as a core principle:

- **Local-First**: Schema parsing happens locally; only sanitized structural descriptions are sent to LLMs
- **Key Management**: API keys stored in OS keychain, never in configuration files
- **Audit Logging**: All LLM interactions are logged locally
- **No Telemetry**: The application does not send any data to external services beyond configured LLM providers

For detailed security architecture, see [docs/security.md](docs/security.md).

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | ✅ |
| < 1.0   | ❌ |

## Security Best Practices for Deployment

1. Enable authentication in production (`AUTH_ENABLED=true`)
2. Generate a strong `AUTH_SECRET_KEY`
3. Keep rate limiting enabled
4. Configure CORS origins to your specific domain
5. Use HTTPS in production (via reverse proxy)
6. Regularly update dependencies
7. Review audit logs periodically
