<div align="center">

# API Chaos Agent

**AI-Native API Chaos Testing Platform**

[English](#english) | [中文](#中文)

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev)

</div>

---

<a id="english"></a>

## Overview

API Chaos Agent is the first AI-native chaos testing tool for REST APIs. Unlike Postman/Apifox which focus on functional testing, we specialize in chaos testing — fault injection, anomalous traffic, and dependency degradation — helping backend developers, SRE engineers, and QA engineers discover resilience blind spots before production deployment.

### Key Differentiators

- **LLM-Driven Scenario Generation**: Automatically generates intelligent fault scenarios using AI, covering edge cases humans miss
- **Local-First Security**: Schema parsing happens locally; only sanitized structural descriptions are sent to LLMs — your API specs never leave your machine
- **Smart Model Routing**: Simple tasks use rule engines (zero cost), medium tasks use local models (Ollama), complex tasks use cloud LLMs (GPT-4/Claude)
- **Postman Compatible**: Import/export Postman Collection v2.1 format for seamless workflow integration

## Features

| Feature | Description | Status |
|---------|-------------|--------|
| Schema Parser | OpenAPI 3.0/3.1 spec import with endpoint extraction | ✅ |
| Scenario Generator | LLM-driven generation of 4 chaos types (latency, error codes, tampering, rate burst) | ✅ |
| Execution Engine | Async execution with serial/parallel modes, configurable concurrency & retries | ✅ |
| Report Generator | HTML/JSON/CSV reports with vulnerability classification (Critical/High/Medium/Low) | ✅ |
| Postman Compatibility | Import/export Postman Collection v2.1 format | ✅ |
| LLM Router | Smart routing: rule engine → local model → cloud model | ✅ |
| Schema Sanitization | Strip PII/credentials before sending to LLMs | ✅ |
| Audit Logging | Full LLM call audit trail with query and export | ✅ |
| Rate Limiting | Sliding window rate limit middleware | ✅ |
| JWT Authentication | Secure API access with JWT tokens | ✅ |
| Offline Deployment | Docker Compose + offline install package | ✅ |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 22+ (for frontend)
- Docker & Docker Compose (for containerized deployment)
- Ollama (optional, for local LLM)

### Option 1: Docker Compose (Recommended)

```bash
git clone https://github.com/your-org/api-chaos-agent.git
cd api-chaos-agent

# Set environment variables
cp .env.example .env
# Edit .env with your API keys (optional)

# Start all services
docker compose up -d

# Access the application
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### Option 2: Local Development

```bash
# Backend setup
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Start backend
uvicorn api_chaos_agent.main:app --reload

# Frontend setup (separate terminal)
cd frontend
npm install
npm run dev
```

### Option 3: Offline Installation

```bash
cd backend
bash scripts/build_offline.sh
# The offline package will be in dist/offline/
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Frontend (React + TypeScript)                │
│   Schema Upload │ Scenario Config │ Test Report Visualization   │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP/WebSocket
┌──────────────────────────────▼──────────────────────────────────┐
│                    API Gateway (FastAPI)                          │
│   Auth/JWT │ Rate Limiting │ Structured Logging                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                    Core Services (Python)                         │
│   Schema Parser │ Scenario Generator │ Execution Engine          │
│                     LLM Router Layer                              │
│   Simple → Rule Engine │ Medium → Ollama │ Complex → Cloud LLM  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                        Data Layer                                 │
│   SQLite │ DiskCache │ File System (Reports)                     │
└─────────────────────────────────────────────────────────────────┘
```

## Configuration

All configuration is managed via environment variables with the prefix `API_CHAOS_AGENT_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `API_CHAOS_AGENT_HOST` | `127.0.0.1` | Server host |
| `API_CHAOS_AGENT_PORT` | `8000` | Server port |
| `API_CHAOS_AGENT_LLM__OPENAI_API_KEY` | - | OpenAI API key |
| `API_CHAOS_AGENT_LLM__ANTHROPIC_API_KEY` | - | Anthropic API key |
| `API_CHAOS_AGENT_LLM__OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `API_CHAOS_AGENT_SECURITY__JWT_SECRET` | (auto-generated) | JWT signing key |
| `API_CHAOS_AGENT_SECURITY__JWT_EXPIRE_MINUTES` | `60` | Token expiry time |

See [backend/src/api_chaos_agent/core/config.py](backend/src/api_chaos_agent/core/config.py) for the full configuration schema.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/schemas` | Upload & parse OpenAPI schema |
| `GET` | `/api/schemas` | List uploaded schemas |
| `GET` | `/api/schemas/{id}` | Get schema details |
| `POST` | `/api/scenarios/generate` | Generate chaos scenarios |
| `GET` | `/api/scenarios` | List scenarios |
| `POST` | `/api/execution/run` | Execute chaos tests |
| `GET` | `/api/reports` | List test reports |
| `GET` | `/api/reports/{id}` | Get report details |
| `GET` | `/api/reports/{id}/export?format=html` | Export report (html/json/csv) |
| `POST` | `/api/postman/import` | Import Postman Collection |
| `POST` | `/api/postman/export` | Export as Postman Collection |
| `POST` | `/api/auth/token` | Get JWT token |
| `GET` | `/health` | Health check |

Full interactive API documentation available at `/docs` (Swagger UI) when running the server.

## Testing

```bash
cd backend

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=api_chaos_agent --cov-report=html

# Run specific test phases
pytest tests/test_phase1_node.py      # Unit tests (126 tests)
pytest tests/test_phase2_block.py     # Integration tests (23 tests)
pytest tests/test_phase3_comprehensive.py  # E2E tests (31 tests)
```

## Project Structure

```
api-chaos-agent/
├── backend/
│   ├── src/api_chaos_agent/
│   │   ├── core/          # Config, security, logging, audit, sanitizer
│   │   ├── services/      # Schema parser, scenario generator, execution engine, etc.
│   │   └── main.py        # FastAPI application entry
│   ├── tests/             # Test suite (572 tests)
│   ├── scripts/           # Build & utility scripts
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/               # React components, pages, hooks
│   ├── Dockerfile
│   └── package.json
├── shared/
│   └── types/             # Shared TypeScript type definitions
├── docker-compose.yml
├── LICENSE                # Apache 2.0
├── CONTRIBUTING.md
└── README.md
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the [Apache License 2.0](LICENSE).

---

<a id="中文"></a>

## 概述

API Chaos Agent 是首个AI原生的API混沌测试工具。与 Postman/Apifox 专注功能测试不同，我们专注于混沌测试——故障注入、异常流量、依赖降级——帮助后端开发者、SRE工程师和QA工程师在生产部署前发现系统的韧性盲区。

### 核心差异化

- **LLM驱动的智能场景生成**：自动生成人类容易遗漏的边界故障场景
- **本地优先安全架构**：Schema解析在本地完成，仅向LLM发送脱敏后的结构描述，API规范不会离开你的机器
- **智能模型路由**：简单任务→规则引擎（零成本），中等任务→本地模型（Ollama），复杂任务→云端大模型
- **Postman兼容**：支持导入/导出Postman Collection v2.1格式

## 快速开始

### Docker Compose 部署（推荐）

```bash
git clone https://github.com/your-org/api-chaos-agent.git
cd api-chaos-agent
docker compose up -d

# 前端：http://localhost:3000
# 后端API：http://localhost:8000
# API文档：http://localhost:8000/docs
```

### 本地开发

```bash
# 后端
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn api_chaos_agent.main:app --reload

# 前端（新终端）
cd frontend
npm install && npm run dev
```

## 安全设计

| 安全要求 | 实现方案 |
|---------|---------|
| Schema不上传云端 | 所有解析在本地完成，仅发送脱敏后的结构描述 |
| API密钥本地存储 | 使用操作系统密钥链 |
| 测试流量隔离 | 执行引擎支持代理配置 |
| 审计日志 | 所有LLM调用记录本地审计日志 |
| Schema脱敏 | 自动移除PII、凭据、内部主机名 |

## 贡献

欢迎贡献！请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

本项目基于 [Apache License 2.0](LICENSE) 开源。
