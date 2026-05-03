"""Tests for RateLimitMiddleware — token-bucket rate limiting."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from api_chaos_agent.core.rate_limit import RateLimitMiddleware, _TokenBucket


class TestTokenBucket:
    def test_initial_tokens_equal_max(self):
        bucket = _TokenBucket(max_tokens=10.0, refill_rate=1.0)
        assert bucket.tokens == 10.0

    def test_consume_within_capacity(self):
        bucket = _TokenBucket(max_tokens=10.0, refill_rate=1.0)
        assert bucket.consume(now=time.monotonic(), tokens=5) is True
        assert bucket.tokens == 5.0

    def test_consume_exact_capacity(self):
        bucket = _TokenBucket(max_tokens=10.0, refill_rate=1.0)
        assert bucket.consume(now=time.monotonic(), tokens=10) is True
        assert bucket.tokens == 0.0

    def test_consume_exceeds_capacity(self):
        bucket = _TokenBucket(max_tokens=5.0, refill_rate=1.0)
        assert bucket.consume(now=time.monotonic(), tokens=6) is False

    def test_refill_over_time(self):
        bucket = _TokenBucket(max_tokens=10.0, refill_rate=60.0)
        now = time.monotonic()
        bucket.consume(now=now, tokens=10)
        assert bucket.tokens == 0.0
        later = now + 1.0
        assert bucket.consume(now=later, tokens=1) is True

    def test_refill_capped_at_max(self):
        bucket = _TokenBucket(max_tokens=10.0, refill_rate=100.0)
        now = time.monotonic()
        bucket.consume(now=now, tokens=5)
        later = now + 100.0
        bucket.consume(now=later, tokens=0)
        assert bucket.tokens <= 10.0

    def test_last_used_updated(self):
        bucket = _TokenBucket(max_tokens=10.0, refill_rate=1.0)
        now = time.monotonic()
        bucket.consume(now=now, tokens=1)
        assert bucket.last_used == now

    def test_consume_fails_when_zero_tokens(self):
        bucket = _TokenBucket(max_tokens=1.0, refill_rate=0.001)
        now = time.monotonic()
        bucket.consume(now=now, tokens=1)
        assert bucket.tokens == 0.0
        assert bucket.consume(now=now, tokens=1) is False

    def test_slow_refill_insufficient_for_consume(self):
        bucket = _TokenBucket(max_tokens=1.0, refill_rate=1.0 / 60.0)
        now = time.monotonic()
        bucket.consume(now=now, tokens=1)
        slightly_later = now + 0.001
        assert bucket.consume(now=slightly_later, tokens=1) is False


class TestRateLimitMiddleware:
    def _make_app_and_config(self, enabled=True, rpm=60):
        from fastapi import FastAPI

        from api_chaos_agent.core.config import AppConfig, RateLimitConfig

        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"ok": True}

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        config = AppConfig(rate_limit=RateLimitConfig(enabled=enabled, requests_per_minute=rpm))
        app.add_middleware(RateLimitMiddleware)
        return app, config

    def test_request_allowed_within_limit(self):
        app, config = self._make_app_and_config(enabled=True, rpm=100)
        with patch("api_chaos_agent.core.rate_limit.settings", config):
            client = TestClient(app)
            response = client.get("/test")
            assert response.status_code == 200

    def test_rate_limit_disabled_passes_through(self):
        app, config = self._make_app_and_config(enabled=False)
        with patch("api_chaos_agent.core.rate_limit.settings", config):
            client = TestClient(app)
            response = client.get("/test")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_returns_429_when_bucket_empty(self):
        from starlette.requests import Request
        from starlette.responses import Response

        middleware = RateLimitMiddleware(MagicMock())
        bucket = middleware._get_bucket("127.0.0.1")
        bucket.tokens = 0.0
        bucket.last_refill = time.monotonic()

        from api_chaos_agent.core.config import AppConfig, RateLimitConfig
        config = AppConfig(rate_limit=RateLimitConfig(enabled=True, requests_per_minute=60))

        async def call_next(request):
            return Response(content='{"ok": true}', media_type="application/json")

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
        request = Request(scope)

        with patch("api_chaos_agent.core.rate_limit.settings", config):
            response = await middleware.dispatch(request, call_next)
        assert response.status_code == 429
        assert b"Rate limit exceeded" in response.body

    @pytest.mark.asyncio
    async def test_dispatch_429_has_retry_after_header(self):
        from starlette.requests import Request
        from starlette.responses import Response

        middleware = RateLimitMiddleware(MagicMock())
        bucket = middleware._get_bucket("127.0.0.1")
        bucket.tokens = 0.0
        bucket.last_refill = time.monotonic()

        from api_chaos_agent.core.config import AppConfig, RateLimitConfig
        config = AppConfig(rate_limit=RateLimitConfig(enabled=True, requests_per_minute=60))

        async def call_next(request):
            return Response(content='{"ok": true}', media_type="application/json")

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
        request = Request(scope)

        with patch("api_chaos_agent.core.rate_limit.settings", config):
            response = await middleware.dispatch(request, call_next)
        assert response.status_code == 429
        assert "retry-after" in dict(response.headers)

    @pytest.mark.asyncio
    async def test_dispatch_passes_when_tokens_available(self):
        from starlette.requests import Request
        from starlette.responses import Response

        middleware = RateLimitMiddleware(MagicMock())
        bucket = middleware._get_bucket("127.0.0.1")
        assert bucket.tokens > 0

        from api_chaos_agent.core.config import AppConfig, RateLimitConfig
        config = AppConfig(rate_limit=RateLimitConfig(enabled=True, requests_per_minute=60))

        async def call_next(request):
            return Response(content='{"ok": true}', media_type="application/json")

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
        request = Request(scope)

        with patch("api_chaos_agent.core.rate_limit.settings", config):
            response = await middleware.dispatch(request, call_next)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_dispatch_disabled_passes_through(self):
        from starlette.requests import Request
        from starlette.responses import Response

        middleware = RateLimitMiddleware(MagicMock())

        from api_chaos_agent.core.config import AppConfig, RateLimitConfig
        config = AppConfig(rate_limit=RateLimitConfig(enabled=False, requests_per_minute=60))

        async def call_next(request):
            return Response(content='{"ok": true}', media_type="application/json")

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
        request = Request(scope)

        with patch("api_chaos_agent.core.rate_limit.settings", config):
            response = await middleware.dispatch(request, call_next)
        assert response.status_code == 200

    def test_get_bucket_creates_new(self):
        middleware = RateLimitMiddleware(MagicMock())
        bucket = middleware._get_bucket("client-1")
        assert bucket is not None
        assert bucket.max_tokens > 0

    def test_get_bucket_reuses_existing(self):
        middleware = RateLimitMiddleware(MagicMock())
        b1 = middleware._get_bucket("client-1")
        b2 = middleware._get_bucket("client-1")
        assert b1 is b2

    def test_cleanup_stale_removes_old_buckets(self):
        middleware = RateLimitMiddleware(MagicMock())
        bucket = middleware._get_bucket("old-client")
        bucket.last_used = time.monotonic() - 7200
        now = time.monotonic()
        middleware._last_cleanup = now - 600
        middleware._cleanup_stale(now)
        assert "old-client" not in middleware._buckets

    def test_cleanup_stale_skips_if_too_recent(self):
        middleware = RateLimitMiddleware(MagicMock())
        now = time.monotonic()
        middleware._last_cleanup = now
        middleware._get_bucket("client")
        middleware._cleanup_stale(now)
        assert "client" in middleware._buckets

    def test_cleanup_stale_enforces_max_buckets(self):
        from api_chaos_agent.core.config import AppConfig, RateLimitConfig
        from api_chaos_agent.core.rate_limit import _MAX_BUCKETS

        config = AppConfig(rate_limit=RateLimitConfig(enabled=True, requests_per_minute=60))
        with patch("api_chaos_agent.core.rate_limit.settings", config):
            middleware = RateLimitMiddleware(MagicMock())
            for i in range(_MAX_BUCKETS + 10):
                middleware._get_bucket(f"client-{i}")
            now = time.monotonic()
            middleware._last_cleanup = now - 600
            middleware._cleanup_stale(now)
            assert len(middleware._buckets) <= _MAX_BUCKETS
