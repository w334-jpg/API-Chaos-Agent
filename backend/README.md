# API Chaos Agent

Chaos testing platform for REST APIs.

## Quick Start

```bash
pip install -e ".[dev]"
uvicorn api_chaos_agent.main:app --reload
```

## Configuration

Copy `.env.example` to `.env` and adjust values.

## Testing

```bash
pytest tests/ -v
```

## License

MIT
