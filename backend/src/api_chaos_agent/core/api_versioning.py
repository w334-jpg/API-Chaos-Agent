"""API versioning middleware and compatibility layer.

Adds an ``X-API-Version`` response header and provides deprecation
notices for legacy v1 endpoints so consumers can migrate gracefully.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_CURRENT_VERSION = "2.0.0"
_DEPRECATED_PREFIXES = ("/api/schemas", "/api/scenarios", "/api/executions", "/api/reports")
_V2_PREFIX = "/api/v2"


class APIVersionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-API-Version"] = _CURRENT_VERSION

        path = request.url.path
        if any(path.startswith(prefix) for prefix in _DEPRECATED_PREFIXES):
            response.headers["Deprecation"] = "true"
            response.headers["Sunset"] = "2026-12-31"
            v2_path = _V2_PREFIX + path[len("/api"):]
            response.headers["Link"] = (
                f'<{request.url.scheme}://{request.url.netloc}{v2_path}>; '
                f'rel="successor-version"'
            )

        return response
