# Security Design

API Chaos Agent is designed with a security-first approach, ensuring your API specifications and credentials never leave your machine.

## Principles

1. **Local-First**: All schema parsing happens locally. Only sanitized structural descriptions are sent to LLMs.
2. **Zero Trust**: API keys are stored in the OS keychain, never in configuration files.
3. **Audit Trail**: Every LLM interaction is logged with full context.
4. **Defense in Depth**: Multiple security layers protect against different threat vectors.

## Schema Sanitization

The `Sanitizer` class strips sensitive information before any data is sent to external LLM services.

### What Gets Removed

| Category | Examples | Handling |
|----------|---------|----------|
| PII | Names, emails, phone numbers | Replaced with placeholders |
| Credentials | API keys, passwords, tokens | Completely removed |
| Internal hosts | `internal.company.com` | Replaced with `example.com` |
| Business values | Specific amounts, IDs | Replaced with type-appropriate defaults |

### What Gets Preserved

| Category | Examples | Reason |
|----------|---------|--------|
| Field names | `user_id`, `order_count` | Needed for scenario context |
| Types | `string`, `integer` | Needed for tampering scenarios |
| Constraints | `minLength`, `maximum` | Needed for boundary testing |
| Endpoint paths | `/api/v1/users` | Needed for routing |

### Sanitization Flow

```
Original Schema → Sanitizer → Sanitized Description → LLM
                                    │
                                    ▼
                            Audit Log (sanitized prompt stored)
```

## Key Management

The `KeyStore` class uses the operating system's native credential storage:

| OS | Backend | Location |
|----|---------|----------|
| macOS | Keychain | `login` keychain |
| Windows | Credential Manager | Windows Credential Store |
| Linux | Secret Service | D-Bus Secret Service (e.g., GNOME Keyring) |

### Key Storage API

```python
from api_chaos_agent.core.key_store import KeyStore

store = KeyStore()

# Store a key
store.set("openai_api_key", "sk-...")

# Retrieve a key
key = store.get("openai_api_key")

# Delete a key
store.delete("openai_api_key")
```

### Fallback Behavior

If the OS keychain is unavailable (e.g., headless server without D-Bus), `KeyStore` falls back to an encrypted file stored at `~/.api-chaos-agent/keys.enc`.

## Audit Logging

Every LLM interaction is recorded in the local audit log.

### Log Entry Format

```json
{
  "timestamp": "2026-04-30T10:15:30Z",
  "model": "gpt-4o",
  "provider": "openai",
  "prompt_tokens": 450,
  "completion_tokens": 200,
  "total_tokens": 650,
  "sanitized_prompt_hash": "sha256:abc123...",
  "task_type": "scenario_generation",
  "duration_ms": 1200
}
```

### Audit API

```python
from api_chaos_agent.core.audit import AuditLogger

logger = AuditLogger()

# Query audit log
entries = logger.query(
    start_time="2026-04-30",
    end_time="2026-04-30",
    provider="openai"
)

# Export audit log
logger.export("audit_log.json")
```

## Network Security

### Rate Limiting

Sliding window rate limiting protects against abuse:

- **Default**: 60 requests/minute per client
- **Burst**: 10 requests above the rate limit
- **Identification**: By IP address or JWT subject

### Security Headers

All responses include security headers:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Cache-Control: no-store
```

### Request Size Limits

- Maximum request body: 10MB (configurable)
- Maximum file upload: 10MB (configurable)

## Authentication

JWT-based authentication with configurable enforcement:

| Mode | Behavior |
|------|----------|
| `AUTH_ENABLED=false` | All endpoints accessible without token |
| `AUTH_ENABLED=true` | JWT token required for all `/api/*` endpoints |

Health check endpoints (`/health`, `/health/live`, `/health/ready`) are always unauthenticated.

## Deployment Security

### Docker

- Runs as non-root user
- No sensitive data in image layers
- Secrets via environment variables or Docker secrets

### Offline/Air-Gapped

- Full functionality without internet access
- Local LLM via Ollama
- No telemetry or phone-home behavior
- All data stored locally
