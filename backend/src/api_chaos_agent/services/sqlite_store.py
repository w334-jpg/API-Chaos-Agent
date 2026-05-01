"""SQLite-backed persistent store.

Drop-in replacement for InMemoryStore that persists data to a SQLite database.
Supports the same async interface with automatic serialization/deserialization.
Implements the StoreProtocol for interface consistency.
"""

from __future__ import annotations

import asyncio
import sqlite3
import uuid
from pathlib import Path

from api_chaos_agent.core.config import settings
from api_chaos_agent.models.report import Report, TestResult
from api_chaos_agent.models.scenario import ChaosScenario
from api_chaos_agent.models.schema import APISpec


class SQLiteStore:
    """Persistent store backed by SQLite.

    Features:
    - Full async interface matching InMemoryStore (StoreProtocol)
    - Automatic JSON serialization/deserialization of Pydantic models
    - Configurable database path
    - Thread-safe via asyncio.Lock
    - Automatic table creation on init
    - Pagination support (offset/limit) matching InMemoryStore
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or settings.store.sqlite_path
        self._lock = asyncio.Lock()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._init_db()

    def _init_db(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS schemas (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS scenarios (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS executions (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        self._conn.commit()

    def _insert(self, table: str, item_id: str, data: str) -> None:
        import time

        self._conn.execute(
            f"INSERT OR REPLACE INTO {table} (id, data, created_at) VALUES (?, ?, ?)",
            (item_id, data, time.time()),
        )
        self._conn.commit()

    def _get(self, table: str, item_id: str) -> str | None:
        cursor = self._conn.execute(f"SELECT data FROM {table} WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def _list(self, table: str) -> dict[str, str]:
        cursor = self._conn.execute(f"SELECT id, data FROM {table}")
        return {row[0]: row[1] for row in cursor.fetchall()}

    def _list_paginated(self, table: str, offset: int = 0, limit: int = 100) -> dict[str, str]:
        cursor = self._conn.execute(
            f"SELECT id, data FROM {table} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return {row[0]: row[1] for row in cursor.fetchall()}

    async def save_schema(self, spec: APISpec) -> str:
        async with self._lock:
            schema_id = str(uuid.uuid4())
            self._insert("schemas", schema_id, spec.model_dump_json())
            return schema_id

    async def get_schema(self, schema_id: str) -> APISpec | None:
        data = self._get("schemas", schema_id)
        if data is None:
            return None
        return APISpec.model_validate_json(data)

    async def list_schemas(self, offset: int = 0, limit: int = 100) -> dict[str, APISpec]:
        raw = self._list_paginated("schemas", offset, limit)
        return {k: APISpec.model_validate_json(v) for k, v in raw.items()}

    async def save_scenario(self, scenario: ChaosScenario) -> str:
        async with self._lock:
            if not scenario.id:
                scenario.id = str(uuid.uuid4())
            self._insert("scenarios", scenario.id, scenario.model_dump_json())
            return scenario.id

    async def get_scenario(self, scenario_id: str) -> ChaosScenario | None:
        data = self._get("scenarios", scenario_id)
        if data is None:
            return None
        return ChaosScenario.model_validate_json(data)

    async def list_scenarios(self, offset: int = 0, limit: int = 100) -> dict[str, ChaosScenario]:
        raw = self._list_paginated("scenarios", offset, limit)
        return {k: ChaosScenario.model_validate_json(v) for k, v in raw.items()}

    async def save_execution(self, result: TestResult) -> str:
        async with self._lock:
            if not result.id:
                result.id = str(uuid.uuid4())
            self._insert("executions", result.id, result.model_dump_json())
            return result.id

    async def get_execution(self, execution_id: str) -> TestResult | None:
        data = self._get("executions", execution_id)
        if data is None:
            return None
        return TestResult.model_validate_json(data)

    async def list_executions(self, offset: int = 0, limit: int = 100) -> dict[str, TestResult]:
        raw = self._list_paginated("executions", offset, limit)
        return {k: TestResult.model_validate_json(v) for k, v in raw.items()}

    async def save_report(self, report: Report) -> str:
        async with self._lock:
            if not report.id:
                report.id = str(uuid.uuid4())
            self._insert("reports", report.id, report.model_dump_json())
            return report.id

    async def get_report(self, report_id: str) -> Report | None:
        data = self._get("reports", report_id)
        if data is None:
            return None
        return Report.model_validate_json(data)

    async def list_reports(self, offset: int = 0, limit: int = 100) -> dict[str, Report]:
        raw = self._list_paginated("reports", offset, limit)
        return {k: Report.model_validate_json(v) for k, v in raw.items()}

    async def clear(self) -> None:
        async with self._lock:
            for table in ("schemas", "scenarios", "executions", "reports"):
                self._conn.execute(f"DELETE FROM {table}")
            self._conn.commit()

    def clear_sync(self) -> None:
        for table in ("schemas", "scenarios", "executions", "reports"):
            self._conn.execute(f"DELETE FROM {table}")
        self._conn.commit()

    async def iter_schemas(self):
        async with self._lock:
            cursor = self._conn.execute("SELECT id, data FROM schemas")
            for row in cursor.fetchall():
                yield row[0], APISpec.model_validate_json(row[1])

    async def iter_scenarios(self):
        async with self._lock:
            cursor = self._conn.execute("SELECT id, data FROM scenarios")
            for row in cursor.fetchall():
                yield row[0], ChaosScenario.model_validate_json(row[1])

    async def iter_executions(self):
        async with self._lock:
            cursor = self._conn.execute("SELECT id, data FROM executions")
            for row in cursor.fetchall():
                yield row[0], TestResult.model_validate_json(row[1])

    async def iter_reports(self):
        async with self._lock:
            cursor = self._conn.execute("SELECT id, data FROM reports")
            for row in cursor.fetchall():
                yield row[0], Report.model_validate_json(row[1])

    async def stats(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for table in ("schemas", "scenarios", "executions", "reports"):
            cursor = self._conn.execute(f"SELECT COUNT(*) FROM {table}")
            result[table] = cursor.fetchone()[0]
        return result

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
