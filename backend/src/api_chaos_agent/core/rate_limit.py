"""Rate limiting middleware using a token-bucket algorithm.

Token bucket provides O(1) per-request processing with smooth burst
allowance, replacing the previous O(n) sliding-window implementation.

Includes periodic cleanup of stale buckets to prevent unbounded memory
growth in long-running deployments.
"""

from __future__ import annotations

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from api_chaos_agent.core.config import settings

_MAX_BUCKETS = 10_000
_STALE_THRESHOLD_SECONDS = 3600
_CLEANUP_INTERVAL_SECONDS = 300


class _TokenBucket:
    __slots__ = ("tokens", "max_tokens", "refill_rate", "last_refill", "last_used")

    def __init__(self, max_tokens: float, refill_rate: float) -> None:
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.tokens = max_tokens
        self.last_refill = time.monotonic()
        self.last_used = self.last_refill

    def consume(self, now: float, tokens: int = 1) -> bool:
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        self.last_used = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self._buckets: dict[str, _TokenBucket] = {}
        self._last_cleanup = time.monotonic()

    def _get_bucket(self, client_id: str) -> _TokenBucket:
        if client_id not in self._buckets:
            rpm = settings.rate_limit.requests_per_minute
            self._buckets[client_id] = _TokenBucket(
                max_tokens=float(rpm),
                refill_rate=rpm / 60.0,
            )
        return self._buckets[client_id]

    def _cleanup_stale(self, now: float) -> None:
        if now - self._last_cleanup < _CLEANUP_INTERVAL_SECONDS:
            return
        self._last_cleanup = now
        stale_cutoff = now - _STALE_THRESHOLD_SECONDS
        stale_keys = [k for k, b in self._buckets.items() if b.last_used < stale_cutoff]
        for k in stale_keys:
            del self._buckets[k]

        if len(self._buckets) > _MAX_BUCKETS:
            sorted_buckets = sorted(self._buckets.items(), key=lambda x: x[1].last_used)
            to_remove = len(self._buckets) - _MAX_BUCKETS
            for k, _ in sorted_buckets[:to_remove]:
                del self._buckets[k]

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.rate_limit.enabled:
            return await call_next(request)

        now = time.monotonic()
        client_id = request.client.host if request.client else "unknown"
        bucket = self._get_bucket(client_id)

        self._cleanup_stale(now)

        if not bucket.consume(now):
            return Response(
                content='{"detail":"Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "60"},
            )

        return await call_next(request)
