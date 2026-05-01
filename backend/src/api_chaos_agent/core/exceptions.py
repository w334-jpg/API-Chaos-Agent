"""Custom exception hierarchy for API Chaos Agent.

All application-specific exceptions inherit from ChaosAgentError,
enabling fine-grained error handling and consistent error responses.
"""

from __future__ import annotations


class ChaosAgentError(Exception):
    """Base exception for all API Chaos Agent errors."""

    def __init__(self, message: str = "", *, detail: str = "") -> None:
        self.detail = detail or message
        super().__init__(message)


class ExecutionError(ChaosAgentError):
    """Errors during chaos scenario execution."""


class ExecutionTimeoutError(ExecutionError):
    """A scenario execution timed out."""


class ExecutionConnectionError(ExecutionError):
    """Connection to the target API failed."""


class SchemaError(ChaosAgentError):
    """Errors related to API schema parsing or validation."""


class SchemaParseError(SchemaError):
    """Failed to parse an OpenAPI/GraphQL schema."""


class SchemaRefError(SchemaError):
    """Unresolvable $ref in schema."""


class LLMError(ChaosAgentError):
    """Errors from LLM routing or generation."""


class LLMUnavailableError(LLMError):
    """All LLM backends are unavailable."""


class LicenseError(ChaosAgentError):
    """License validation or installation errors."""


class PluginError(ChaosAgentError):
    """Plugin loading or execution errors."""


class PluginLoadError(PluginError):
    """Failed to load a plugin from directory or entrypoint."""


class SecurityError(ChaosAgentError):
    """Authorization or access control violation (403)."""


class AuthenticationError(ChaosAgentError):
    """Authentication failure — invalid or missing credentials (401)."""


class ConfigurationError(ChaosAgentError):
    """Invalid or missing configuration."""


class NotFoundError(ChaosAgentError):
    """Requested resource was not found."""


class RequestError(ChaosAgentError):
    """Invalid request parameters or validation failure."""
