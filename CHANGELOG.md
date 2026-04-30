# Changelog

All notable changes to API Chaos Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-04-30

### Added — Dual Licensing (BSL 1.1)

- **Business Source License 1.1** for Professional & Enterprise features
- **License Manager** with key verification, installation, and removal
- **Trial License** generation for 30-day evaluation
- **BSL Eligibility Check**: Small orgs (<50 employees, <$1M revenue), nonprofits, and academic users can use Pro features for free
- **License API Routes**: `/api/license/info`, `/api/license/install`, `/api/license/check-pro`, `/api/license/check-enterprise`
- **BSL License Headers** added to all 20 Phase 2 source files
- **Feature Gates**: 14 feature gates across Free/Pro/Enterprise tiers with `require_feature` and `require_plan` decorators
- **Plan Comparison API**: `/api/plans/features`, `/api/plans/compare`, `/api/plans/check-feature`
- **Pricing Page**: Frontend pricing and plan comparison page
- **Change Date**: BSL code automatically converts to Apache 2.0 on 2029-04-30

### Added — Professional & Enterprise Features

- **gRPC & GraphQL Schema Support**: Full schema parsing for Protocol Buffers (.proto) and GraphQL SDL, with automatic endpoint and method extraction
- **Distributed Execution Engine**: Master-Worker architecture with:
  - Worker registration, heartbeat monitoring, and auto-deregistration
  - Round-robin and least-loaded task distribution strategies
  - Execution plan management with progress tracking
- **Custom Fault Plugin Framework**: Extensible plugin system with:
  - 4 built-in plugins: Resource Exhaustion, Data Corruption, Dependency Failure, Network Partition
  - Plugin manifest validation and lifecycle management (enable/disable)
  - Configuration schema validation per plugin
- **CI/CD Integration**: Pipeline integration for:
  - GitHub Actions workflow generation
  - GitLab CI pipeline configuration
  - Webhook triggers for automated chaos testing
  - Quality gate enforcement (pass/fail criteria)
- **Team Collaboration & Multi-Tenancy**:
  - Tenant management with Free/Pro/Enterprise plans
  - Team member roles (Owner/Admin/Member/Viewer)
  - Invitation system with expiry and acceptance flow
  - Per-tenant quota enforcement
- **Advanced Analytics & Report Comparison**:
  - Historical trend analysis (daily/weekly/monthly)
  - Report comparison with new/resolved/changed findings
  - Endpoint risk scoring based on vulnerability density and severity
  - Pass rate and execution time trend tracking
- **Feature Gates & Tier System**:
  - 14 feature gates across Free/Pro/Enterprise tiers
  - Per-plan quota limits (schemas, scenarios, concurrency, team size, retention)
  - Plan comparison API and frontend pricing page
  - `require_feature` and `require_plan` decorators for API route protection
- **Frontend Phase 2 Pages**:
  - Distributed execution management page
  - Plugin marketplace and management page
  - CI/CD pipeline configuration page
  - Team and tenant management page
  - Analytics dashboard with trend charts
  - Pricing and plan comparison page
- **Testing**: 656 tests (84 new Phase 2 tests), all passing

### Fixed

- Fixed `VulnerabilityFinding` import error in analytics service (correct class: `Finding`)
- Fixed `vulnerability_findings` field references to match `findings` in Report model
- Fixed `vulnerability_type` field references to match `scenario_type` in Finding model
- Fixed gRPC parser regex to correctly handle nested braces in proto service definitions
- Fixed `distributed_engine.py` datetime/float comparison error in `list_active()`
- Fixed analytics router using local Store instance instead of global store
- Added missing `execution_time_ms` field to Report model

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
