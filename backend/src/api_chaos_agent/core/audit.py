"""Audit logging for LLM API calls.

Records every LLM interaction with full context for compliance,
debugging, and cost tracking. Supports structured query and export.
"""

from __future__ import annotations

import json
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from api_chaos_agent.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AuditEntry:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    provider: str = ""
    model: str = ""
    operation: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    status: str = "success"
    error_message: str = ""
    request_metadata: dict[str, Any] = field(default_factory=dict)
    response_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "provider": self.provider,
            "model": self.model,
            "operation": self.operation,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
            "status": self.status,
            "error_message": self.error_message,
            "request_metadata": self.request_metadata,
            "response_metadata": self.response_metadata,
        }


class AuditLogger:
    """In-memory audit log for LLM API calls with query and export capabilities."""

    MAX_ENTRIES = 10000

    def __init__(self, max_entries: int = MAX_ENTRIES) -> None:
        self._entries: deque[AuditEntry] = deque(maxlen=max_entries)
        self._max_entries = max_entries

    def record(
        self,
        provider: str,
        model: str,
        operation: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        latency_ms: float = 0.0,
        status: str = "success",
        error_message: str = "",
        request_metadata: dict[str, Any] | None = None,
        response_metadata: dict[str, Any] | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            provider=provider,
            model=model,
            operation=operation,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens or prompt_tokens + completion_tokens,
            latency_ms=latency_ms,
            status=status,
            error_message=error_message,
            request_metadata=request_metadata or {},
            response_metadata=response_metadata or {},
        )
        self._entries.append(entry)
        logger.info(
            "llm_audit",
            provider=provider,
            model=model,
            operation=operation,
            tokens=entry.total_tokens,
            latency_ms=latency_ms,
            status=status,
        )
        return entry

    def query(
        self,
        provider: str | None = None,
        model: str | None = None,
        operation: str | None = None,
        status: str | None = None,
        since: float | None = None,
        until: float | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        results: list[AuditEntry] = list(self._entries)
        if provider:
            results = [e for e in results if e.provider == provider]
        if model:
            results = [e for e in results if e.model == model]
        if operation:
            results = [e for e in results if e.operation == operation]
        if status:
            results = [e for e in results if e.status == status]
        if since:
            results = [e for e in results if e.timestamp >= since]
        if until:
            results = [e for e in results if e.timestamp <= until]
        return results[-limit:]

    def get_stats(self) -> dict[str, Any]:
        total = len(self._entries)
        if total == 0:
            return {
                "total_calls": 0,
                "total_tokens": 0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "avg_latency_ms": 0.0,
                "error_count": 0,
                "by_provider": {},
                "by_model": {},
            }

        total_prompt = sum(e.prompt_tokens for e in self._entries)
        total_completion = sum(e.completion_tokens for e in self._entries)
        total_tokens = sum(e.total_tokens for e in self._entries)
        avg_latency = sum(e.latency_ms for e in self._entries) / total
        error_count = sum(1 for e in self._entries if e.status == "error")

        by_provider: dict[str, int] = {}
        by_model: dict[str, int] = {}
        for e in self._entries:
            by_provider[e.provider] = by_provider.get(e.provider, 0) + 1
            by_model[e.model] = by_model.get(e.model, 0) + 1

        return {
            "total_calls": total,
            "total_tokens": total_tokens,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "avg_latency_ms": round(avg_latency, 2),
            "error_count": error_count,
            "by_provider": by_provider,
            "by_model": by_model,
        }

    def export_json(self) -> str:
        return json.dumps(
            [e.to_dict() for e in self._entries],
            indent=2,
            ensure_ascii=False,
        )

    def clear(self) -> None:
        self._entries.clear()


audit_logger = AuditLogger()
