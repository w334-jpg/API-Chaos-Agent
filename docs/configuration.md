# Configuration Reference

All configuration is managed through environment variables with sensible defaults.

## Environment Variables

### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVER_HOST` | `0.0.0.0` | Server bind address |
| `SERVER_PORT` | `8000` | Server bind port |
| `SERVER_MAX_REQUEST_BODY_SIZE` | `10485760` | Max request body size (10MB) |
| `SERVER_MAX_UPLOAD_SIZE` | `10485760` | Max file upload size (10MB) |
| `SERVER_CORS_ORIGINS` | `http://localhost:3000,...` | Comma-separated CORS origins |

### LLM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (empty) | OpenAI API key |
| `ANTHROPIC_API_KEY` | (empty) | Anthropic API key |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model name |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Anthropic model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3` | Ollama model name |
| `LLM_OLLAMA_TIMEOUT` | `120.0` | Ollama request timeout (seconds) |
| `LLM_CLOUD_TIMEOUT` | `60.0` | Cloud LLM request timeout (seconds) |
| `LLM_CACHE_DIR` | `/tmp/llm_router_cache` | LLM response cache directory |
| `LLM_CACHE_TTL` | `3600` | Cache TTL (seconds) |
| `LLM_CIRCUIT_FAILURE_THRESHOLD` | `5` | Circuit breaker failure threshold |
| `LLM_CIRCUIT_RESET_TIMEOUT` | `60.0` | Circuit breaker reset timeout (seconds) |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_ENABLED` | `false` | Enable JWT authentication |
| `AUTH_SECRET_KEY` | `change-me-in-production...` | JWT signing key |
| `AUTH_ALGORITHM` | `HS256` | JWT algorithm |
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Token expiry time |

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_ENABLED` | `true` | Enable rate limiting |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `60` | Requests per minute per client |
| `RATE_LIMIT_BURST` | `10` | Burst allowance |

### Store Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `STORE_MAX_SCHEMAS` | `1000` | Maximum stored schemas |
| `STORE_MAX_SCENARIOS` | `1000` | Maximum stored scenarios |
| `STORE_MAX_EXECUTIONS` | `1000` | Maximum stored executions |
| `STORE_MAX_REPORTS` | `1000` | Maximum stored reports |
| `STORE_TTL_SECONDS` | `3600` | Data TTL (seconds) |
| `STORE_BACKEND` | `memory` | Storage backend (`memory` or `sqlite`) |
| `STORE_SQLITE_PATH` | `data/chaos_agent.db` | SQLite database path |

### Execution Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `EXEC_MAX_BURST_REQUESTS` | `500` | Maximum burst requests |
| `EXEC_BACKOFF_BASE` | `1.0` | Exponential backoff base |
| `EXEC_BACKOFF_MAX` | `30.0` | Maximum backoff delay |
| `EXEC_JITTER_FACTOR` | `0.1` | Jitter factor for backoff |
| `EXEC_MAX_DELAY_SECONDS` | `2.0` | Maximum injection delay |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Log level |
| `LOG_FORMAT` | `text` | Log format (`text` or `json`) |
| `LOG_JSON_INDENT` | `2` | JSON log indentation |

## Docker Compose Configuration

When using Docker Compose, set variables in the `environment` section of `docker-compose.yml` or use a `.env` file:

```env
# .env
OPENAI_API_KEY=sk-your-key
ANTHROPIC_API_KEY=sk-ant-your-key
JWT_SECRET=your-production-secret
```

## Production Checklist

- [ ] Set `AUTH_ENABLED=true`
- [ ] Generate a strong `AUTH_SECRET_KEY`
- [ ] Set `RATE_LIMIT_ENABLED=true`
- [ ] Configure `SERVER_CORS_ORIGINS` to your domain
- [ ] Set `LOG_FORMAT=json` for structured logging
- [ ] Configure `STORE_BACKEND=sqlite` for persistence
- [ ] Set appropriate `STORE_TTL_SECONDS`
- [ ] Review `EXEC_MAX_BURST_REQUESTS` for your target APIs
