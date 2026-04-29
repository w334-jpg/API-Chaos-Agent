# Changelog

All notable changes to API Chaos Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-30

### Added

- **Schema Parser**: OpenAPI 3.0/3.1 specification parsing with endpoint extraction, parameter inference, and request body analysis
- **Scenario Generator**: LLM-driven chaos scenario generation with 4 scenario types:
  - Latency injection scenarios
  - Error status code scenarios (4xx/5xx)
  - Request body tampering scenarios
  - Rate limit burst scenarios
- **Execution Engine**: Asynchronous test execution with configurable concurrency, retry with exponential backoff, and mock transport support
- **Report Generator**: Multi-format report output (HTML/JSON/CSV) with vulnerability severity classification (Critical/High/Medium/Low/Info)
- **Postman Compatibility**: Import/export Postman Collection v2.1 format
- **LLM Router**: Three-tier intelligent model routing:
  - Simple tasks → Rule engine (zero cost)
  - Medium tasks → Local LLM via Ollama
  - Complex tasks → Cloud LLM (OpenAI/Anthropic)
  - Circuit breaker for provider failover
  - DiskCache for LLM response caching
- **Security**:
  - Schema sanitization (PII/credential stripping before LLM calls)
  - OS keychain integration for API key storage (macOS/Windows/Linux)
  - Audit logging for all LLM interactions
  - JWT authentication (optional)
  - Rate limiting middleware (sliding window)
  - Security headers middleware
  - Request size limit middleware
- **Frontend**: React + TypeScript web interface with:
  - Schema upload and endpoint visualization
  - Scenario configuration and generation
  - Test execution with real-time progress (WebSocket)
  - Report viewing and export
  - Dashboard with statistics
- **Deployment**:
  - Docker Compose configuration (backend + frontend + Ollama)
  - Backend Dockerfile
  - Frontend Dockerfile with Nginx
  - Offline installation package builder
- **Testing**: 572 tests across unit, integration, and E2E phases
- **Documentation**: README (bilingual EN/CN), CONTRIBUTING guide, API docs, architecture docs, security docs, configuration reference
