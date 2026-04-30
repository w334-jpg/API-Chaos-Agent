# Contributing to API Chaos Agent

Thank you for your interest in contributing to API Chaos Agent! This document provides guidelines and instructions for contributing.

## Code of Conduct

Be respectful, constructive, and inclusive. We follow the [Contributor Covenant](https://www.contributor-covenant.org/) Code of Conduct.

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 22+
- Git
- Docker & Docker Compose (for integration testing)

### Development Setup

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/w334-jpg/API-Chaos-Agent.git
   cd api-chaos-agent
   ```

2. **Backend setup**
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   pre-commit install
   ```

3. **Frontend setup**
   ```bash
   cd frontend
   npm install
   ```

4. **Verify setup**
   ```bash
   # Backend tests
   cd backend && pytest tests/ -q

   # Frontend build
   cd frontend && npm run build
   ```

## Development Workflow

1. **Create a feature branch** from `main`
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following our code standards

3. **Write tests** for your changes
   - Unit tests for new functions/classes
   - Integration tests for new API endpoints
   - Maintain ≥80% code coverage

4. **Run the test suite**
   ```bash
   pytest tests/ -v --cov=api_chaos_agent
   ```

5. **Run linters**
   ```bash
   ruff check src/ tests/
   mypy src/
   ```

6. **Commit with conventional messages**
   ```
   feat: add new chaos scenario type
   fix: resolve timeout handling in execution engine
   docs: update API endpoint documentation
   test: add integration tests for report exporter
   refactor: simplify LLM router complexity classification
   ```

7. **Push and create a Pull Request**

## Code Standards

### Python (Backend)

- **Style**: Follow PEP 8, enforced by `ruff`
- **Type hints**: Required for all function signatures
- **Line length**: Maximum 100 characters
- **Imports**: Use `from __future__ import annotations` for modern type hints
- **Naming**:
  - Modules: `snake_case`
  - Classes: `PascalCase`
  - Functions/methods: `snake_case`
  - Constants: `UPPER_SNAKE_CASE`
- **Docstrings**: Required for all public classes and functions
- **No comments in code**: Code should be self-documenting; use descriptive names

### TypeScript (Frontend)

- **Style**: Follow the existing ESLint configuration
- **Type safety**: No `any` types; use proper interfaces and type definitions
- **Components**: Functional components with hooks
- **Naming**:
  - Components: `PascalCase`
  - Functions/variables: `camelCase`
  - Types/Interfaces: `PascalCase`
  - Constants: `UPPER_SNAKE_CASE`

### Shared Types

Place shared type definitions in `shared/types/` so both frontend and backend can reference the same contracts.

## Testing Guidelines

### Test Structure

```
tests/
├── test_phase1_node.py          # Unit tests for individual modules
├── test_phase2_block.py         # Integration tests for functional blocks
├── test_phase3_comprehensive.py # End-to-end tests
├── unit/                        # Additional unit test modules
│   ├── test_security_modules.py
│   ├── test_postman_adapter.py
│   ├── test_report_exporter.py
│   └── test_llm_router.py
└── integration/                 # Additional integration tests
```

### Test Requirements

- All new features must include tests
- Bug fixes must include regression tests
- Maintain the existing test coverage level (≥80%)
- Use `pytest-asyncio` for async test functions
- Use descriptive test names that explain the expected behavior

### Running Tests

```bash
# All tests
pytest tests/ -v

# Specific phase
pytest tests/test_phase1_node.py -v

# With coverage report
pytest tests/ --cov=api_chaos_agent --cov-report=html

# Only unit tests
pytest tests/ -m unit

# Only integration tests
pytest tests/ -m integration
```

## Pull Request Process

1. **PR title**: Use conventional commit format
2. **Description**: Explain what and why, reference related issues
3. **Checklist**:
   - [ ] Tests pass locally
   - [ ] New code has tests
   - [ ] Linting passes
   - [ ] Documentation updated (if applicable)
   - [ ] No sensitive data in code

4. **Review**: At least one maintainer approval required
5. **CI**: All CI checks must pass before merge

## Reporting Issues

### Bug Reports

Please include:
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, etc.)
- Relevant logs or error messages

### Feature Requests

Please include:
- Use case description
- Expected behavior
- Why existing features don't cover this need

## Architecture Overview

```
Backend (Python/FastAPI)
├── core/           # Cross-cutting concerns (config, security, logging)
├── services/       # Business logic (parsing, generation, execution, reporting)
└── main.py         # Application entry point

Frontend (React/TypeScript)
├── components/     # Reusable UI components
├── pages/          # Page-level components
├── hooks/          # Custom React hooks
├── services/       # API client services
└── types/          # TypeScript type definitions

Shared
└── types/          # Shared type contracts between frontend and backend
```

## License

By contributing to this project, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
