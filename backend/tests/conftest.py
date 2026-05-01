"""Shared test fixtures."""

from __future__ import annotations

import os

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("AUTH_ENABLED", "false")

import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api_chaos_agent.main import app
from api_chaos_agent.services.store import InMemoryStore


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
def fresh_store() -> InMemoryStore:
    return InMemoryStore(
        max_schemas=10, max_scenarios=10, max_executions=10, max_reports=10, ttl_seconds=300
    )
