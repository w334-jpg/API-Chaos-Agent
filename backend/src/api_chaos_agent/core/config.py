"""API Chaos Agent — application configuration.

All runtime-tunable parameters are read from environment variables with
sensible defaults so the application works out-of-the-box in development.

Configuration hierarchy:
  1. Environment variables (highest priority)
  2. config/default.toml file
  3. Hard-coded defaults (lowest priority)

Each sub-configuration is a frozen dataclass for immutability.
Use ConfigReloader for hot-reload scenarios.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    """Read a string environment variable with a default."""
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable with a default."""
    return int(os.environ.get(name, str(default)))


def _env_float(name: str, default: float) -> float:
    """Read a float environment variable with a default."""
    return float(os.environ.get(name, str(default)))


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable with a default.

    Accepts: 1/true/yes (True), 0/false/no (False).
    Falls back to *default* when the variable is unset.
    """
    val = os.environ.get(name, "").lower()
    if val in ("1", "true", "yes"):
        return True
    if val in ("0", "false", "no"):
        return False
    return default


@dataclass(frozen=True)
class StoreConfig:
    """Storage backend configuration.

    Controls capacity limits, TTL, and backend selection.
    Use 'memory' for development and 'sqlite' for persistence.
    """
    max_schemas: int = _env_int("STORE_MAX_SCHEMAS", 1000)
    max_scenarios: int = _env_int("STORE_MAX_SCENARIOS", 1000)
    max_executions: int = _env_int("STORE_MAX_EXECUTIONS", 1000)
    max_reports: int = _env_int("STORE_MAX_REPORTS", 1000)
    ttl_seconds: float = _env_float("STORE_TTL_SECONDS", 3600.0)
    backend: str = _env("STORE_BACKEND", "memory")
    sqlite_path: str = _env("STORE_SQLITE_PATH", "data/chaos_agent.db")


@dataclass(frozen=True)
class ExecutionConfig:
    """Chaos execution engine configuration.

    Controls request bursting, backoff strategy, and timing.
    """
    max_burst_requests: int = _env_int("EXEC_MAX_BURST_REQUESTS", 500)
    backoff_base: float = _env_float("EXEC_BACKOFF_BASE", 1.0)
    backoff_max: float = _env_float("EXEC_BACKOFF_MAX", 30.0)
    jitter_factor: float = _env_float("EXEC_JITTER_FACTOR", 0.1)
    max_delay_seconds: float = _env_float("EXEC_MAX_DELAY_SECONDS", 2.0)


@dataclass(frozen=True)
class LLMConfig:
    """LLM routing configuration.

    Manages API keys, model selection, caching, and circuit breaker settings.
    Supports OpenAI, Anthropic, and local Ollama models with automatic fallback.
    """
    cache_dir: str = _env("LLM_CACHE_DIR", "/tmp/llm_router_cache")
    cache_ttl: int = _env_int("LLM_CACHE_TTL", 3600)
    openai_api_key: str = _env("OPENAI_API_KEY", "")
    anthropic_api_key: str = _env("ANTHROPIC_API_KEY", "")
    openai_model: str = _env("OPENAI_MODEL", "gpt-4o")
    anthropic_model: str = _env("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    ollama_base_url: str = _env("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = _env("OLLAMA_MODEL", "llama3")
    ollama_timeout: float = _env_float("LLM_OLLAMA_TIMEOUT", 120.0)
    cloud_timeout: float = _env_float("LLM_CLOUD_TIMEOUT", 60.0)
    circuit_failure_threshold: int = _env_int("LLM_CIRCUIT_FAILURE_THRESHOLD", 5)
    circuit_reset_timeout: float = _env_float("LLM_CIRCUIT_RESET_TIMEOUT", 60.0)


@dataclass(frozen=True)
class ServerConfig:
    """HTTP server configuration.

    Controls host, port, debug mode, request size limits, and CORS origins.
    """
    host: str = _env("SERVER_HOST", "0.0.0.0")
    port: int = _env_int("SERVER_PORT", 8000)
    debug: bool = _env_bool("SERVER_DEBUG", False)
    max_request_body_size: int = _env_int("SERVER_MAX_REQUEST_BODY_SIZE", 10 * 1024 * 1024)
    max_upload_size: int = _env_int("SERVER_MAX_UPLOAD_SIZE", 10 * 1024 * 1024)
    cors_origins: list[str] = field(default_factory=lambda: _env(
        "SERVER_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(","))


_INSECURE_DEFAULT_KEYS = frozenset({
    "change-me-in-production-use-a-strong-key",
    "",
})


@dataclass(frozen=True)
class AuthConfig:
    """Authentication and authorization configuration.

    Controls JWT settings, admin credentials, and token expiry.
    Set AUTH_ENABLED=true and provide a strong AUTH_SECRET_KEY in production.
    """
    enabled: bool = _env_bool("AUTH_ENABLED", False)
    secret_key: str = _env("AUTH_SECRET_KEY", "")
    algorithm: str = _env("AUTH_ALGORITHM", "HS256")
    access_token_expire_minutes: int = _env_int("AUTH_ACCESS_TOKEN_EXPIRE_MINUTES", 30)
    admin_username: str = _env("AUTH_ADMIN_USERNAME", "")
    admin_password: str = _env("AUTH_ADMIN_PASSWORD", "")

    @property
    def is_insecure_key(self) -> bool:
        return self.secret_key in _INSECURE_DEFAULT_KEYS


@dataclass(frozen=True)
class RateLimitConfig:
    """Rate limiting configuration.

    Controls request throttling per client IP using token-bucket algorithm.
    """
    enabled: bool = _env_bool("RATE_LIMIT_ENABLED", True)
    requests_per_minute: int = _env_int("RATE_LIMIT_REQUESTS_PER_MINUTE", 60)
    burst: int = _env_int("RATE_LIMIT_BURST", 10)


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration.

    Controls log level, format (text or json), and JSON indentation.
    """
    level: str = _env("LOG_LEVEL", "INFO")
    format: str = _env("LOG_FORMAT", "text")
    json_indent: int = _env_int("LOG_JSON_INDENT", 2)


@dataclass(frozen=True)
class AppConfig:
    """Root application configuration aggregating all sub-configurations.

    Access via the module-level `settings` singleton or through
    dependency injection with `get_settings()`.
    """
    store: StoreConfig = field(default_factory=StoreConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


settings = AppConfig()
