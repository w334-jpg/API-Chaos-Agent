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
git clone https://github.com/w334-jpg/API-Chaos-Agent.git
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

All configuration is managed via environment variables. Copy `.env.example` to `.env` and adjust as needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVER_HOST` | `0.0.0.0` | Server host |
| `SERVER_PORT` | `8000` | Server port |
| `OPENAI_API_KEY` | (empty) | OpenAI API key |
| `ANTHROPIC_API_KEY` | (empty) | Anthropic API key |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `AUTH_SECRET_KEY` | (auto-generated) | JWT signing key |
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Token expiry time |

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
| `POST` | `/api/reports/generate` | Generate test report |
| `GET` | `/api/reports` | List test reports |
| `GET` | `/api/reports/{id}` | Get report details |
| `GET` | `/api/reports/{id}/export?format=html` | Export report (html/json/csv) |
| `POST` | `/api/postman/import` | Import Postman Collection |
| `POST` | `/api/postman/export` | Export as Postman Collection |
| `POST` | `/auth/token` | Get JWT token |
| `GET` | `/health` | Health check |

Full interactive API documentation is available at `/docs` (Swagger UI) when running the server.

## Testing

```bash
cd backend

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=api_chaos_agent --cov-report=html

# Run specific test modules
pytest tests/unit/ -v                # Unit tests
pytest tests/integration/ -v         # Integration tests
pytest tests/test_phase3_comprehensive.py -v  # E2E tests
```

## Security

| Requirement | Implementation |
|-------------|---------------|
| Schema stays local | All parsing done locally; only sanitized structural descriptions are sent to LLMs |
| API keys stored locally | Uses OS-level keychain (macOS Keychain / Windows Credential Manager / Linux Secret Service) |
| Test traffic isolation | Execution engine supports proxy configuration |
| Audit logging | All LLM calls logged to local audit trail |
| Schema sanitization | PII, credentials, and internal hostnames are automatically stripped |

## Project Structure

```
api-chaos-agent/
├── backend/
│   ├── src/api_chaos_agent/
│   │   ├── core/          # Config, security, logging, audit, sanitizer
│   │   ├── services/      # Schema parser, scenario generator, execution engine, etc.
│   │   ├── routers/       # API route handlers
│   │   └── main.py        # FastAPI application entry
│   ├── tests/             # Test suite (572 tests)
│   ├── scripts/           # Build & utility scripts
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/               # React components, pages, hooks
│   ├── Dockerfile
│   └── package.json
├── docs/                  # Documentation
│   ├── api.md
│   ├── architecture.md
│   ├── configuration.md
│   ├── getting-started.md
│   └── security.md
├── .github/               # GitHub templates & CI
│   ├── ISSUE_TEMPLATE/
│   ├── workflows/
│   └── pull_request_template.md
├── docker-compose.yml
├── LICENSE                # Apache 2.0
├── README.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── SECURITY.md
└── .env.example
```

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the [Apache License 2.0](LICENSE).

---

<a id="中文"></a>

## 概述

API Chaos Agent 是首个 AI 原生的 API 混沌测试工具。与 Postman/Apifox 专注功能测试不同，我们专注于混沌测试——故障注入、异常流量、依赖降级——帮助后端开发者、SRE 工程师和 QA 工程师在生产部署前发现系统的韧性盲区。

### 核心差异化

- **LLM 驱动的智能场景生成**：自动生成人类容易遗漏的边界故障场景
- **本地优先安全架构**：Schema 解析在本地完成，仅向 LLM 发送脱敏后的结构描述，API 规范不会离开你的机器
- **智能模型路由**：简单任务使用规则引擎（零成本），中等任务使用本地模型（Ollama），复杂任务使用云端大模型（GPT-4/Claude）
- **Postman 兼容**：支持导入/导出 Postman Collection v2.1 格式，无缝集成现有工作流

## 功能特性

| 功能模块 | 描述 | 状态 |
|---------|-------------|--------|
| Schema 解析器 | OpenAPI 3.0/3.1 规范导入与端点提取 | ✅ |
| 场景生成器 | LLM 驱动生成 4 类混沌场景（延迟、错误码、篡改、速率突增） | ✅ |
| 执行引擎 | 异步执行，支持串行/并行模式，可配置并发数与重试策略 | ✅ |
| 报告生成器 | HTML/JSON/CSV 格式报告，含漏洞分级（严重/高/中/低） | ✅ |
| Postman 兼容 | 导入/导出 Postman Collection v2.1 格式 | ✅ |
| LLM 路由器 | 智能路由：规则引擎 → 本地模型 → 云端模型 | ✅ |
| Schema 脱敏 | 在发送给 LLM 前自动剥离 PII 和凭据信息 | ✅ |
| 审计日志 | 完整的 LLM 调用审计追踪，支持查询与导出 | ✅ |
| 速率限制 | 滑动窗口速率限制中间件 | ✅ |
| JWT 认证 | 基于 JWT 的安全 API 访问控制 | ✅ |
| 离线部署 | Docker Compose 一键部署 + 离线安装包 | ✅ |

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 22+（前端构建）
- Docker 与 Docker Compose（容器化部署）
- Ollama（可选，用于本地 LLM）

### 方式一：Docker Compose 部署（推荐）

```bash
git clone https://github.com/w334-jpg/API-Chaos-Agent.git
cd api-chaos-agent

# 配置环境变量
cp .env.example .env
# 编辑 .env 添加你的 API 密钥（可选）

# 启动所有服务
docker compose up -d

# 访问应用
# 前端：http://localhost:3000
# 后端 API：http://localhost:8000
# API 文档：http://localhost:8000/docs
```

### 方式二：本地开发

```bash
# 后端安装
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 启动后端
uvicorn api_chaos_agent.main:app --reload

# 前端安装（新终端窗口）
cd frontend
npm install
npm run dev
```

### 方式三：离线安装

```bash
cd backend
bash scripts/build_offline.sh
# 离线安装包位于 dist/offline/ 目录
```

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     前端 (React + TypeScript)                    │
│   Schema 上传 │ 场景配置 │ 测试报告可视化                         │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTP/WebSocket
┌──────────────────────────────▼──────────────────────────────────┐
│                    API 网关 (FastAPI)                             │
│   认证/JWT │ 速率限制 │ 结构化日志                                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                    核心服务 (Python)                              │
│   Schema 解析器 │ 场景生成器 │ 执行引擎                            │
│                     LLM 路由层                                    │
│   简单 → 规则引擎 │ 中等 → Ollama │ 复杂 → 云端大模型             │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                        数据层                                     │
│   SQLite │ DiskCache │ 文件系统（报告）                            │
└─────────────────────────────────────────────────────────────────┘
```

## 配置说明

所有配置通过环境变量管理。复制 `.env.example` 为 `.env` 并根据需要调整：

| 变量名 | 默认值 | 说明 |
|----------|---------|-------------|
| `SERVER_HOST` | `0.0.0.0` | 服务器绑定地址 |
| `SERVER_PORT` | `8000` | 服务器端口 |
| `OPENAI_API_KEY` | （空） | OpenAI API 密钥 |
| `ANTHROPIC_API_KEY` | （空） | Anthropic API 密钥 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama 服务地址 |
| `AUTH_SECRET_KEY` | （自动生成） | JWT 签名密钥 |
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | 令牌过期时间（分钟） |

完整配置项请参见 [backend/src/api_chaos_agent/core/config.py](backend/src/api_chaos_agent/core/config.py).

## API 端点

| 方法 | 路径 | 说明 |
|--------|------|-------------|
| `POST` | `/api/schemas` | 上传并解析 OpenAPI Schema |
| `GET` | `/api/schemas` | 列出已上传的 Schema |
| `GET` | `/api/schemas/{id}` | 获取 Schema 详情 |
| `POST` | `/api/scenarios/generate` | 生成混沌测试场景 |
| `GET` | `/api/scenarios` | 列出场景 |
| `POST` | `/api/execution/run` | 执行混沌测试 |
| `POST` | `/api/reports/generate` | 生成测试报告 |
| `GET` | `/api/reports` | 列出测试报告 |
| `GET` | `/api/reports/{id}` | 获取报告详情 |
| `GET` | `/api/reports/{id}/export?format=html` | 导出报告（html/json/csv） |
| `POST` | `/api/postman/import` | 导入 Postman Collection |
| `POST` | `/api/postman/export` | 导出为 Postman Collection |
| `POST` | `/auth/token` | 获取 JWT 令牌 |
| `GET` | `/health` | 健康检查 |

服务运行时可通过 `/docs`（Swagger UI）访问交互式 API 文档。

## 测试

```bash
cd backend

# 运行全部测试
pytest tests/ -v

# 运行测试并生成覆盖率报告
pytest tests/ --cov=api_chaos_agent --cov-report=html

# 运行特定测试模块
pytest tests/unit/ -v                # 单元测试
pytest tests/integration/ -v         # 集成测试
pytest tests/test_phase3_comprehensive.py -v  # 端到端测试
```

## 安全设计

| 安全要求 | 实现方案 |
|---------|---------|
| Schema 不上传云端 | 所有解析在本地完成，仅发送脱敏后的结构描述 |
| API 密钥本地存储 | 使用操作系统密钥链（macOS Keychain / Windows 凭据管理器 / Linux Secret Service） |
| 测试流量隔离 | 执行引擎支持代理配置 |
| 审计日志 | 所有 LLM 调用记录本地审计日志 |
| Schema 脱敏 | 自动移除 PII、凭据、内部主机名 |

## 项目结构

```
api-chaos-agent/
├── backend/
│   ├── src/api_chaos_agent/
│   │   ├── core/          # 配置、安全、日志、审计、脱敏
│   │   ├── services/      # Schema 解析器、场景生成器、执行引擎等
│   │   ├── routers/       # API 路由处理器
│   │   └── main.py        # FastAPI 应用入口
│   ├── tests/             # 测试套件（572 个测试）
│   ├── scripts/           # 构建与工具脚本
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/               # React 组件、页面、Hooks
│   ├── Dockerfile
│   └── package.json
├── docs/                  # 文档
│   ├── api.md
│   ├── architecture.md
│   ├── configuration.md
│   ├── getting-started.md
│   └── security.md
├── .github/               # GitHub 模板与 CI 配置
│   ├── ISSUE_TEMPLATE/
│   ├── workflows/
│   └── pull_request_template.md
├── docker-compose.yml
├── LICENSE                # Apache 2.0
├── README.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── SECURITY.md
└── .env.example
```

## 贡献

欢迎贡献！请参阅 [CONTRIBUTING.md](CONTRIBUTING.md) 了解贡献指南。

## 许可证

本项目基于 [Apache License 2.0](LICENSE) 开源。
