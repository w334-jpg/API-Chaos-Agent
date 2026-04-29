# Getting Started Guide

This guide walks you through installing, configuring, and running API Chaos Agent for the first time.

## Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Python | 3.11+ | Backend runtime |
| Node.js | 22+ | Frontend build |
| Docker | 24+ | Containerized deployment |
| Docker Compose | 2.20+ | Multi-container orchestration |
| Ollama | 0.3+ | Local LLM (optional) |

## Installation

### Option 1: Docker Compose (Recommended)

This is the simplest way to get started. Docker handles all dependencies automatically.

```bash
# Clone the repository
git clone https://github.com/your-org/api-chaos-agent.git
cd api-chaos-agent

# Configure environment
cp .env.example .env
# Edit .env to add your API keys (optional for local-only mode)

# Start all services
docker compose up -d

# Verify services are running
docker compose ps
curl http://localhost:8000/health
```

Access the application:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Option 2: Local Development

For contributors and developers who want to modify the code.

#### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Verify installation
pytest tests/ -q

# Start the server
uvicorn api_chaos_agent.main:app --reload --host 127.0.0.1 --port 8000
```

#### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

### Option 3: Offline Installation

For air-gapped environments without internet access.

```bash
cd backend

# Build offline package
bash scripts/build_offline.sh

# The package will be in dist/offline/
# Transfer to target machine and install
tar xzf api-chaos-agent-offline.tar.gz
cd api-chaos-agent-offline
bash install.sh
```

## Configuration

All configuration is managed through environment variables. See [Configuration Reference](configuration.md) for the complete list.

### Essential Configuration

```bash
# .env file
API_CHAOS_AGENT_HOST=127.0.0.1
API_CHAOS_AGENT_PORT=8000

# LLM Configuration (optional - works without cloud keys using rule engine + Ollama)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OLLAMA_BASE_URL=http://localhost:11434

# Security
AUTH_ENABLED=false
AUTH_SECRET_KEY=your-strong-secret-key-here
```

### LLM Model Routing

API Chaos Agent uses a three-tier routing strategy:

| Task Complexity | Model | Cost | When |
|----------------|-------|------|------|
| Simple | Rule Engine | Free | Standard chaos patterns (latency, error codes) |
| Medium | Ollama (Local) | Free | Custom scenario generation with local LLM |
| Complex | Cloud LLM | Paid | Complex API structures requiring deep understanding |

## Your First Chaos Test

### Step 1: Prepare Your API Schema

You need an OpenAPI 3.0/3.1 specification file (YAML or JSON). If you don't have one, use our example:

```bash
# Use the included Petstore example
cp backend/tests/fixtures/petstore_openapi.yaml ./my-api.yaml
```

### Step 2: Upload and Parse

```bash
# Upload the schema
curl -X POST http://localhost:8000/api/schemas \
  -F "file=@my-api.yaml"
```

Or use the web UI at http://localhost:3000/schema.

### Step 3: Generate Chaos Scenarios

```bash
# Generate scenarios for all endpoints
curl -X POST http://localhost:8000/api/scenarios/generate \
  -H "Content-Type: application/json" \
  -d '{
    "schema_id": "your-schema-id",
    "scenario_types": ["latency", "error_status", "tampering", "rate_burst"]
  }'
```

### Step 4: Execute Tests

```bash
# Run the generated scenarios against your API
curl -X POST http://localhost:8000/api/execution/run \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_ids": ["scenario-id-1", "scenario-id-2"],
    "base_url": "https://your-api.example.com",
    "concurrency": 10
  }'
```

### Step 5: View Reports

```bash
# Generate and export the report
curl http://localhost:8000/api/reports/{report_id}/export?format=html -o report.html

# Open in browser
open report.html
```

## Postman Integration

### Import from Postman

1. Export your Postman Collection as v2.1 JSON
2. Upload via API or web UI
3. API Chaos Agent converts it to internal format and generates chaos scenarios

### Export to Postman

1. Generate scenarios in API Chaos Agent
2. Export as Postman Collection v2.1
3. Import into Postman for further manual testing

## Troubleshooting

### Common Issues

**Ollama not connecting**
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve

# Pull a model
ollama pull llama3
```

**Port already in use**
```bash
# Find process using port 8000
lsof -i :8000

# Use a different port
API_CHAOS_AGENT_PORT=8080 uvicorn api_chaos_agent.main:app --reload
```

**Docker build fails**
```bash
# Rebuild without cache
docker compose build --no-cache

# Check Docker disk space
docker system df
docker system prune
```

### Getting Help

- [GitHub Issues](https://github.com/your-org/api-chaos-agent/issues) for bug reports
- [GitHub Discussions](https://github.com/your-org/api-chaos-agent/discussions) for questions
- [API Documentation](api.md) for endpoint details
