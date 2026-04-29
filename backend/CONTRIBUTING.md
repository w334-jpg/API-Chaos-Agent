# Contributing to API Chaos Agent

Thank you for your interest in contributing! This document provides guidelines and instructions.

## Development Setup

```bash
# Clone and install
git clone <repo-url>
cd api-chaos-agent/backend
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env
```

## Development Workflow

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Run tests and linting
5. Commit with conventional commit messages
6. Push and create a Pull Request

## Code Standards

- **Python 3.11+** with type hints
- **Async-first**: Use `async/await` for I/O operations
- **Pydantic v2** for data models
- **Structured logging** via `structlog`
- **No bare `except`**: Always specify exception types
- **No mutable defaults**: Use `field(default_factory=...)` in dataclasses

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific phase
pytest tests/test_phase1_node.py -v
pytest tests/test_phase2_block.py -v
pytest tests/test_phase3_comprehensive.py -v

# Run with coverage
pytest tests/ --cov=api_chaos_agent --cov-report=html

# Run with strict warnings
pytest tests/ -W error::RuntimeWarning -W error::ResourceWarning
```

### Test Structure

- **Phase 1 (Node)**: Unit tests for each independent module
- **Phase 2 (Block)**: Integration tests for functional blocks
- **Phase 3 (Comprehensive)**: End-to-end tests with 5-round validation

## Commit Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add Postman collection import
fix: resolve TTL expiry race condition
docs: update API reference
refactor: extract store factory pattern
test: add schema sanitizer tests
chore: update dependencies
```

## Pull Request Process

1. Ensure all tests pass with zero errors and warnings
2. Update documentation if adding new features
3. Add tests for any new functionality
4. Keep PRs focused — one feature/fix per PR

## Reporting Issues

- Use GitHub Issues
- Include: Python version, OS, steps to reproduce, expected vs actual behavior
- Attach relevant logs with sensitive data redacted
