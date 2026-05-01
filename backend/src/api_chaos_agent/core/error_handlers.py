"""Global exception handlers for FastAPI application.

Ensures every error — whether raised by our code, a validation library,
or an unhandled exception — is returned in a consistent JSON envelope:

    {
        "error": {
            "type": "error_class",
            "detail": "Human-readable message",
            "status": 422
        }
    }

Status code mapping follows HTTP semantics:
  - SchemaError / ConfigurationError / ValueError  → 400
  - SecurityError                                   → 401
  - LicenseError                                    → 403
  - ExecutionTimeoutError                           → 408
  - ExecutionConnectionError                        → 502
  - LLMUnavailableError                             → 503
  - Other ChaosAgentError                           → 500
"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from api_chaos_agent.core.config import settings
from api_chaos_agent.core.exceptions import (
    AuthenticationError,
    ChaosAgentError,
    ConfigurationError,
    ExecutionConnectionError,
    ExecutionTimeoutError,
    LLMUnavailableError,
    LicenseError,
    NotFoundError,
    RequestError,
    SchemaError,
    SecurityError,
)
from api_chaos_agent.core.logging import get_logger

logger = get_logger(__name__)


def _error_body(
    error_type: str,
    detail: str,
    status_code: int,
) -> dict[str, Any]:
    return {
        "error": {
            "type": error_type,
            "detail": detail,
            "status": status_code,
        }
    }


_STATUS_MAP: dict[type[Exception], int] = {
    SchemaError: status.HTTP_400_BAD_REQUEST,
    ConfigurationError: status.HTTP_400_BAD_REQUEST,
    RequestError: status.HTTP_400_BAD_REQUEST,
    ValueError: status.HTTP_400_BAD_REQUEST,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    SecurityError: status.HTTP_403_FORBIDDEN,
    LicenseError: status.HTTP_400_BAD_REQUEST,
    ExecutionTimeoutError: status.HTTP_408_REQUEST_TIMEOUT,
    ExecutionConnectionError: status.HTTP_502_BAD_GATEWAY,
    LLMUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _resolve_status(exc: ChaosAgentError) -> int:
    for exc_type, code in _STATUS_MAP.items():
        if isinstance(exc, exc_type):
            return code
    return status.HTTP_500_INTERNAL_SERVER_ERROR


async def _chaos_agent_error_handler(request: Request, exc: ChaosAgentError) -> JSONResponse:
    status_code = _resolve_status(exc)
    return JSONResponse(
        status_code=status_code,
        content=_error_body(type(exc).__name__, exc.detail, status_code),
    )


async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    detail = "; ".join(
        f"{'.'.join(str(l) for l in e.get('loc', []))}: {e.get('msg', '')}"
        for e in errors
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_error_body("ValidationError", detail, status.HTTP_422_UNPROCESSABLE_ENTITY),
    )


async def _pydantic_validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
    errors = exc.errors()
    detail = "; ".join(
        f"{'.'.join(str(l) for l in e.get('loc', []))}: {e.get('msg', '')}"
        for e in errors
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_error_body("ValidationError", detail, status.HTTP_422_UNPROCESSABLE_ENTITY),
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        method=request.method,
        path=str(request.url.path),
        exception=type(exc).__name__,
        message=str(exc),
        traceback=traceback.format_exc() if settings.server.debug else None,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body(
            "InternalServerError",
            "An unexpected error occurred" if not settings.server.debug else str(exc),
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ChaosAgentError, _chaos_agent_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(ValidationError, _pydantic_validation_error_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
