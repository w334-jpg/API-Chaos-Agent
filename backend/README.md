# API Chaos Agent

Enterprise-grade chaos testing platform for REST, gRPC, and GraphQL APIs.
Automatically discovers vulnerabilities and resilience weaknesses through
intelligent fault injection.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│   Frontend   │────▶│  FastAPI API  │────▶│  Execution Engine │
│  (React/TS)  │     │  (v1 + v2)   │     │  (Distributed)    │
└─────────────┘     └──────┬───────┘     └────────┬─────────┘
                           │                       │
              ┌────────────┼───────────────┐       │
              ▼            ▼               ▼       ▼
        ┌──────────┐ ┌──────────┐  ┌──────────┐ ┌──────────┐
        │  Schema  │ │ Scenario │  │   LLM    │ │  Plugin  │
        │  Parser  │ │Generator │  │  Router  │ │Framework │
        └──────────┘ └──────────┘  └──────────┘ └──────────┘
                           │                       │
              ┌────────────┼───────────────┐       │
              ▼            ▼               ▼       ▼
        ┌──────────┐ ┌──────────┐  ┌──────────┐ ┌──────────┐
        │  Store   │ │ Security │  │  Report  │ │  Sanitizer│
        │ (Memory/ │ │  (JWT)   │  │Generator │ │ (PII/Key)│
        │  SQLite) │ │          │  │          │ │          │
        └──────────┘ └──────────┘  └──────────┘ └──────────┘
```

### Core Modules

| Module | Path | Description |
|--------|------|-------------|
| **API Server** | `main.py` | FastAPI app with middleware stack |
| **Schema Parser** | `services/schema_parser.py` | OpenAPI 2/3, Swagger parsing |
| **gRPC/GraphQL Parser** | `services/grpc_graphql_parser.py` | Proto + GraphQL schema parsing |
| **Scenario Generator** | `services/scenario_generator.py` | LLM-powered chaos scenario creation |
| **Execution Engine** | `services/execution_engine.py` | Concurrent fault injection runner |
| **Distributed Engine** | `services/distributed_engine.py` | Multi-worker distributed execution |
| **LLM Router** | `services/llm_router.py` | Cloud/local/rule-based LLM routing with circuit breaker |
| **Plugin Framework** | `services/plugin_framework.py` | Custom fault plugin system |
| **Store** | `services/store.py` | In-memory + SQLite persistence backends |
| **Security** | `core/security.py` | JWT authentication with key management |
| **Sanitizer** | `core/sanitizer.py` | PII, credential, and internal hostname scrubbing |
| **Report Generator** | `services/report_generator.py` | JSON + HTML report generation |

## Quick Start

```bash
# Install with development dependencies
pip install -e ".[dev]"

# Start the server
uvicorn api_chaos_agent.main:app --reload

# Open Swagger UI
open http://localhost:8000/docs
```

## Configuration

Copy `.env.example` to `.env` and adjust values. Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_ENABLED` | `false` | Enable JWT authentication |
| `AUTH_SECRET_KEY` | — | JWT signing key (required in production) |
| `AUTH_ADMIN_USERNAME` | — | Admin username |
| `AUTH_ADMIN_PASSWORD` | — | Admin password |
| `STORE_BACKEND` | `memory` | Storage backend: `memory` or `sqlite` |
| `STORE_SQLITE_PATH` | `data/chaos_agent.db` | SQLite database path |
| `RATE_LIMIT_ENABLED` | `true` | Enable rate limiting |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `60` | Requests per minute per client |
| `OPENAI_API_KEY` | — | OpenAI API key for LLM-powered scenarios |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `SERVER_DEBUG` | `false` | Enable debug mode |

## API Endpoints

### v1 (REST/OpenAPI)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/schemas/upload` | Upload OpenAPI schema |
| `GET` | `/api/schemas/` | List schemas |
| `GET` | `/api/schemas/{id}` | Get schema |
| `POST` | `/api/scenarios/generate/{schema_id}` | Generate chaos scenarios |
| `GET` | `/api/scenarios/` | List scenarios |
| `POST` | `/api/executions/` | Execute scenarios |
| `GET` | `/api/executions/{id}` | Get execution result |
| `POST` | `/api/reports/generate/{execution_id}` | Generate report |
| `GET` | `/api/reports/{id}` | Get report |

### v2 (gRPC/GraphQL + Plugins)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v2/schemas/parse` | Auto-detect and parse schema |
| `POST` | `/api/v2/schemas/parse/grpc` | Parse gRPC proto file |
| `POST` | `/api/v2/schemas/parse/graphql` | Parse GraphQL schema |
| `GET` | `/api/v2/plugins` | List plugins |
| `POST` | `/api/v2/plugins/{name}/execute` | Execute plugin |
| `POST` | `/api/v2/plugins/load/directory` | Load plugins from directory |
| `POST` | `/api/v2/plugins/load/entrypoint` | Load plugin from entrypoint |

### Auth

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/token` | OAuth2 token endpoint |

## Error Handling

All errors return a consistent JSON envelope:

```json
{
  "error": {
    "type": "NotFoundError",
    "detail": "Schema not found",
    "status": 404
  }
}
```

Status code mapping:

| Exception | HTTP Status |
|-----------|-------------|
| `SchemaError` / `RequestError` / `ConfigurationError` | 400 |
| `AuthenticationError` | 401 |
| `SecurityError` | 403 |
| `NotFoundError` | 404 |
| `ExecutionTimeoutError` | 408 |
| `ExecutionConnectionError` | 502 |
| `LLMUnavailableError` | 503 |

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test categories
pytest tests/unit/ -v          # Unit tests
pytest tests/integration/ -v   # Integration tests
pytest tests/e2e/ -v           # End-to-end tests
pytest tests/security/ -v      # Security tests
pytest tests/boundary/ -v      # Boundary condition tests
pytest tests/perf/ -v          # Performance tests
```

## License

Business Source License 1.1 (BSL 1.1). See [LICENSE.BSL](LICENSE.BSL) for details.

**Change Date:** 2029-04-30 — On or after this date, the work will be available
under Apache License 2.0.

Use of this software in production requires a valid commercial license unless
your organization qualifies under the Additional Use Grant.
