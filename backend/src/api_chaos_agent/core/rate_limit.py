"""Rate limiting middleware using an in-memory sliding-window counter."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from api_chaos_agent.core.config import settings


class _SlidingWindow:
    __slots__ = ("timestamps",)

    def __init__(self) -> None:
        self.timestamps: list[float] = []

    def record(self, now: float) -> int:
        window_start = now - 60.0
        self.timestamps = [t for t in self.timestamps if t > window_start]
        self.timestamps.append(now)
        return len(self.timestamps)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self._windows: dict[str, _SlidingWindow] = defaultdict(_SlidingWindow)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.rate_limit.enabled:
            return await call_next(request)

        client_id = request.client.host if request.client else "unknown"
        window = self._windows[client_id]
        count = window.record(time.monotonic())

        if count > settings.rate_limit.requests_per_minute:
            return Response(
                content='{"detail":"Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "60"},
            )

        return await call_next(request)
