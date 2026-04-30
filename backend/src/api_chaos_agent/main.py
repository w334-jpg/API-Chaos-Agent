"""API Chaos Agent — FastAPI application entry point.

Includes:
- CORS middleware (configurable origins)
- Security headers middleware
- Request body size limit middleware
- Rate limiting middleware
- Request logging middleware
- Structured logging setup
- JWT authentication (optional)
- Health check endpoints with dependency status
- WebSocket endpoint for real-time execution progress
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from api_chaos_agent.core.config import settings
from api_chaos_agent.core.logging import setup_logging, get_logger
from api_chaos_agent.core.rate_limit import RateLimitMiddleware
from api_chaos_agent.core.security import create_access_token
from api_chaos_agent.routers import schema, scenarios, execution, reports
from api_chaos_agent.routers import schemas_v2, distributed, plugins, cicd, tenants, analytics
from api_chaos_agent.routers import plans
from api_chaos_agent.services.store import store

logger = get_logger(__name__)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.headers.get("content-length"):
            try:
                content_length = int(request.headers["content-length"])
                if content_length > settings.server.max_request_body_size:
                    return Response(
                        content='{"detail":"Request body too large"}',
                        status_code=413,
                        media_type="application/json",
                    )
            except ValueError:
                pass
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "request_completed",
            method=request.method,
            path=str(request.url.path),
            status=response.status_code,
            elapsed_ms=round(elapsed_ms, 2),
        )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    logger.info("application_starting", host=settings.server.host, port=settings.server.port)
    yield
    await store.clear()
    logger.info("application_stopped")


app = FastAPI(
    title="API Chaos Agent",
    description="Chaos testing platform for REST, gRPC, and GraphQL APIs",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.server.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(RateLimitMiddleware)

app.include_router(schema.router)
app.include_router(scenarios.router)
app.include_router(execution.router)
app.include_router(reports.router)
app.include_router(schemas_v2.router)
app.include_router(distributed.router)
app.include_router(plugins.router)
app.include_router(cicd.router)
app.include_router(tenants.router)
app.include_router(analytics.router)
app.include_router(plans.router)


_ws_connections: list[WebSocket] = []


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    store_stats = await store.stats()
    checks: dict[str, str] = {"store": "ok"}

    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            ollama_url = f"{settings.llm.ollama_base_url}/api/tags"
            resp = await client.get(ollama_url)
            checks["ollama"] = "ok" if resp.status_code == 200 else "degraded"
    except Exception:
        checks["ollama"] = "unavailable"

    return {
        "status": "healthy",
        "store_stats": store_stats,
        "checks": checks,
        "auth_enabled": settings.auth.enabled,
        "rate_limit_enabled": settings.rate_limit.enabled,
    }


@app.get("/health/ready", tags=["health"])
async def readiness_check() -> dict:
    store_stats = await store.stats()
    return {"status": "ready", "store_stats": store_stats}


@app.get("/health/live", tags=["health"])
async def liveness_check() -> dict:
    return {"status": "alive"}


@app.post("/auth/token", tags=["auth"])
async def login(username: str, password: str) -> dict:
    if not settings.auth.enabled:
        return {"access_token": "disabled", "token_type": "bearer"}
    if username == "admin" and password == "admin":
        token = create_access_token(subject=username)
        return {"access_token": token, "token_type": "bearer"}
    from fastapi import HTTPException
    raise HTTPException(status_code=401, detail="Invalid credentials")


@app.websocket("/ws/executions/{execution_id}")
async def ws_execution_progress(websocket: WebSocket, execution_id: str) -> None:
    await websocket.accept()
    _ws_connections.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                result = await store.get_execution(execution_id)
                if result:
                    await websocket.send_json({
                        "type": "execution_status",
                        "execution_id": execution_id,
                        "total": result.total_scenarios,
                        "completed": result.completed_scenarios,
                        "failed": result.failed_scenarios,
                    })
                else:
                    await websocket.send_json({"type": "error", "message": "Execution not found"})
    except WebSocketDisconnect:
        _ws_connections.remove(websocket)
    except Exception:
        if websocket in _ws_connections:
            _ws_connections.remove(websocket)


async def broadcast_progress(execution_id: str, data: dict) -> None:
    message = {"type": "progress", "execution_id": execution_id, **data}
    dead: list[WebSocket] = []
    for ws in _ws_connections:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_connections.remove(ws)
