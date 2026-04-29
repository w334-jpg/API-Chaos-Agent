# Architecture Overview

API Chaos Agent follows a layered architecture with clear separation of concerns.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Frontend (React + TypeScript)                │
│   Schema Upload │ Scenario Config │ Test Report Visualization   │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP/WebSocket
┌──────────────────────────────▼──────────────────────────────────┐
│                    API Gateway (FastAPI)                          │
│   Auth/JWT │ Rate Limiting │ Security Headers │ Request Logging  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                    Core Services (Python)                         │
│                                                                  │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│   │ Schema Parser │  │ Scenario Gen  │  │ Execution Engine     │  │
│   │ (prance)      │  │ (LLM-driven)  │  │ (httpx + asyncio)    │  │
│   └──────────────┘  └──────┬───────┘  └──────────────────────┘  │
│                             │                                    │
│   ┌────────────────────────▼──────────────────────────────────┐ │
│   │              LLM Router (Smart Model Selection)            │ │
│   │   Simple → Rule Engine │ Medium → Ollama │ Complex → Cloud │ │
│   └───────────────────────────────────────────────────────────┘ │
│                                                                  │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│   │ Report Gen    │  │ Postman Adptr │  │ Store (Memory/SQLite)│  │
│   └──────────────┘  └──────────────┘  └──────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                        Data Layer                                 │
│   SQLite │ DiskCache │ File System (Reports)                     │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### Schema Parser

Parses OpenAPI 3.0/3.1 specifications and extracts structured endpoint information.

- **Input**: YAML/JSON OpenAPI files or Postman Collection v2.1
- **Output**: `APISpec` containing `Endpoint` objects with parameters, request bodies, and responses
- **Library**: `prance` for spec resolution, `jsonschema` for validation

### Scenario Generator

Generates chaos test scenarios using a three-tier approach:

1. **Rule Engine** (zero cost): Standard patterns for latency injection, error codes, field tampering, and rate bursting
2. **Local LLM** (Ollama): Enhanced scenario generation with context-aware patterns
3. **Cloud LLM** (GPT-4/Claude): Complex scenario generation requiring deep API understanding

Each scenario includes:
- Target endpoint and method
- Scenario type and configuration
- Expected behavior description
- Severity classification

### Execution Engine

Asynchronous test execution with configurable concurrency.

- **Transport**: `httpx.AsyncClient` with mock transport support for testing
- **Concurrency**: `asyncio.Semaphore` for controlled parallel execution
- **Retry**: Exponential backoff with jitter
- **Injection Types**: Latency, error status, request tampering, rate burst

### Report Generator

Produces test reports with vulnerability classification.

- **Formats**: HTML, JSON, CSV
- **Severity**: Critical / High / Medium / Low / Info
- **Content**: Vulnerability description, reproduction steps, remediation advice

### LLM Router

Intelligent model selection based on task complexity.

- **Circuit Breaker**: Prevents cascading failures when a provider is down
- **Caching**: DiskCache for LLM response deduplication
- **Fallback Chain**: Rule Engine → Ollama → OpenAI → Anthropic

## Security Architecture

```
┌──────────────────────────────────────────────┐
│                Security Layer                 │
│                                               │
│  ┌─────────────┐  ┌────────────────────────┐ │
│  │ Sanitizer    │  │ Key Store              │ │
│  │ (PII/cred   │  │ (OS keychain:          │ │
│  │  stripping)  │  │  macOS Keychain,       │ │
│  └─────────────┘  │  Windows Credential,   │ │
│                    │  Linux Secret Service)  │ │
│  ┌─────────────┐  └────────────────────────┘ │
│  │ Audit Logger │                            │
│  │ (LLM call   │  ┌────────────────────────┐ │
│  │  tracking)   │  │ Rate Limiter           │ │
│  └─────────────┘  │ (Sliding window,       │ │
│                    │  per-client)            │ │
│                    └────────────────────────┘ │
└──────────────────────────────────────────────┘
```

### Data Flow Security

1. **Schema Upload**: Parsed locally, never sent to external services
2. **LLM Calls**: Only sanitized structural descriptions are sent (field names + types, no values)
3. **API Keys**: Stored in OS keychain, never in configuration files or logs
4. **Test Traffic**: Supports proxy configuration for isolated environments
5. **Audit Trail**: All LLM interactions logged with timestamp, model, token count, and sanitized prompt

## Data Flow

```
User → Upload Schema → Schema Parser → APISpec
                                            │
                                            ▼
                        Scenario Generator ← LLM Router
                                │
                                ▼
                          ChaosScenario[]
                                │
                                ▼
                        Execution Engine → httpx → Target API
                                │
                                ▼
                          TestResult
                                │
                                ▼
                        Report Generator → HTML/JSON/CSV
```

## Technology Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| Backend | FastAPI | 0.115+ | API framework |
| Runtime | Python | 3.11+ | Core language |
| Frontend | React | 19 | UI framework |
| Language | TypeScript | 5.x | Type safety |
| UI Library | shadcn/ui | latest | Component library |
| Styling | Tailwind CSS | 4.x | CSS framework |
| HTTP | httpx | 0.27+ | Async HTTP client |
| Parsing | prance | 23.0+ | OpenAPI parsing |
| LLM SDK | openai/anthropic | latest | Cloud LLM access |
| Local LLM | Ollama | 0.3+ | Local model serving |
| Storage | SQLite | built-in | Persistent storage |
| Cache | DiskCache | 5.6+ | LLM response cache |
| Testing | pytest | 8.0+ | Test framework |
| Containers | Docker | 24+ | Deployment |
