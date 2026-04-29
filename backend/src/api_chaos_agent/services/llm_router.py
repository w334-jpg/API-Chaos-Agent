"""
LLM Router Service — routes prompts to the appropriate backend based on task
complexity:

  SIMPLE  → rule engine (no LLM call)
  MEDIUM  → local model (Ollama)
  COMPLEX → cloud model (OpenAI / Anthropic)

Enhanced with:
- Async httpx client with connection pooling for Ollama calls
- Circuit breaker pattern for cloud model resilience
- Proper cache TTL enforcement
- Configurable timeouts and retry limits
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from enum import Enum
from typing import Any

import diskcache
import httpx
from anthropic import Anthropic
from openai import OpenAI

from api_chaos_agent.core.config import settings
from api_chaos_agent.core.logging import get_logger

logger = get_logger(__name__)


class TaskComplexity(str, Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


_SIMPLE_KEYWORDS: list[str] = [
    "change field type", "change type", "field type", "boundary value",
    "boundary", "null", "empty string", "replace with null",
    "replace with empty", "type mutation", "type change", "mutate type",
]

_COMPLEX_KEYWORDS: list[str] = [
    "multi-step", "chained", "chain", "scenario", "adversarial",
    "business logic", "exploit", "privilege escalation",
    "authentication bypass", "design", "analyze", "reason", "complex",
]

_RULE_MUTATIONS: dict[str, str] = {
    "integer": "string", "int": "string", "number": "string",
    "float": "string", "double": "string", "boolean": "string",
    "string": "integer", "str": "int",
}

_BOUNDARY_VALUES: dict[str, list[str]] = {
    "integer": ["-1", "0", "1", "2147483647", "-2147483648"],
    "number": ["-0.001", "0.0", "0.001", "1e308", "-1e308"],
    "string": ["", " ", "a", "A" * 1000],
    "boolean": ["true", "false", "null"],
}


class CircuitBreaker:
    """Simple circuit breaker for cloud LLM calls."""

    def __init__(
        self,
        failure_threshold: int | None = None,
        reset_timeout: float | None = None,
    ) -> None:
        cfg = settings.llm
        self._failure_threshold = failure_threshold or cfg.circuit_failure_threshold
        self._reset_timeout = reset_timeout or cfg.circuit_reset_timeout
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._state = "closed"

    @property
    def state(self) -> str:
        if self._state == "open":
            if time.monotonic() - self._last_failure_time > self._reset_timeout:
                self._state = "half-open"
        return self._state

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self._failure_threshold:
            self._state = "open"
            logger.warning("Circuit breaker opened due to %d consecutive failures", self._failure_count)

    def is_available(self) -> bool:
        return self.state != "open"


class LLMRouter:
    """Route LLM requests to the most appropriate backend.

    Features:
    - Circuit breaker for cloud model resilience
    - Connection pooling for Ollama calls
    - Configurable timeouts
    - Disk-based caching with TTL
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        llm_cfg = settings.llm

        self._cache_dir: str = cfg.get("cache_dir", llm_cfg.cache_dir)
        self._cache_ttl: int = cfg.get("cache_ttl", llm_cfg.cache_ttl)
        self._cache: diskcache.Cache = diskcache.Cache(self._cache_dir)

        self._openai_api_key: str = cfg.get("openai_api_key", llm_cfg.openai_api_key)
        self._anthropic_api_key: str = cfg.get("anthropic_api_key", llm_cfg.anthropic_api_key)
        self._openai_model: str = cfg.get("openai_model", llm_cfg.openai_model)
        self._anthropic_model: str = cfg.get("anthropic_model", llm_cfg.anthropic_model)

        self._ollama_base_url: str = cfg.get("ollama_base_url", llm_cfg.ollama_base_url)
        self._ollama_model: str = cfg.get("ollama_model", llm_cfg.ollama_model)

        self._openai_client: OpenAI | None = None
        self._anthropic_client: Anthropic | None = None

        self._circuit_breaker = CircuitBreaker()

        self._http_client: httpx.AsyncClient | None = None

        if self._openai_api_key:
            self._openai_client = OpenAI(api_key=self._openai_api_key)
        if self._anthropic_api_key:
            self._anthropic_client = Anthropic(api_key=self._anthropic_api_key)

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.llm.ollama_timeout),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._http_client

    def close(self) -> None:
        self._cache.close()
        if self._http_client is not None and not self._http_client.is_closed:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._http_client.aclose())
                else:
                    loop.run_until_complete(self._http_client.aclose())
            except Exception:
                pass

    def __del__(self) -> None:
        try:
            self._cache.close()
        except Exception:
            pass
        if self._http_client is not None and not self._http_client.is_closed:
            try:
                self._http_client.sync_close()
            except Exception:
                pass

    async def route(
        self,
        prompt: str,
        system_prompt: str = "",
        complexity: TaskComplexity | None = None,
    ) -> str:
        if complexity is None:
            complexity = self.classify_complexity(prompt)

        cache_key = self._get_cache_key(prompt, system_prompt, complexity)

        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached

        try:
            if complexity == TaskComplexity.SIMPLE:
                result = await self._call_rule_engine(prompt)
            elif complexity == TaskComplexity.MEDIUM:
                result = await self._call_local_model(prompt, system_prompt)
            else:
                result = await self._call_cloud_model(prompt, system_prompt)
        except Exception:
            result = await self._call_rule_engine(prompt)

        self._save_to_cache(cache_key, result)
        return result

    async def batch_route(
        self,
        prompts: list[tuple[str, TaskComplexity]],
        system_prompt: str = "",
    ) -> list[str]:
        results: list[str] = []
        for prompt, complexity in prompts:
            result = await self.route(prompt, system_prompt=system_prompt, complexity=complexity)
            results.append(result)
        return results

    def classify_complexity(self, prompt: str) -> TaskComplexity:
        lower = prompt.lower()

        simple_score = sum(1 for kw in _SIMPLE_KEYWORDS if kw in lower)
        complex_score = sum(1 for kw in _COMPLEX_KEYWORDS if kw in lower)

        if simple_score > 0 and complex_score == 0:
            return TaskComplexity.SIMPLE
        if complex_score > 0:
            return TaskComplexity.COMPLEX
        return TaskComplexity.MEDIUM

    async def _call_rule_engine(self, prompt: str) -> str:
        lower = prompt.lower()

        if any(kw in lower for kw in ("change field type", "change type", "field type", "type mutation", "type change", "mutate type")):
            return self._generate_type_mutation(prompt)

        if "boundary" in lower:
            return self._generate_boundary_values(prompt)

        if "null" in lower:
            return json.dumps({"mutation": "null", "value": None})
        if "empty string" in lower:
            return json.dumps({"mutation": "empty_string", "value": ""})

        return json.dumps({"mutation": "generic_simple", "prompt": prompt})

    async def _call_local_model(self, prompt: str, system_prompt: str = "") -> str:
        payload: dict[str, Any] = {
            "model": self._ollama_model,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt

        client = await self._get_http_client()
        try:
            resp = await client.post(
                f"{self._ollama_base_url}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
        except httpx.HTTPStatusError as exc:
            logger.warning("Ollama returned HTTP %d: %s", exc.response.status_code, exc)
            raise
        except httpx.ConnectError as exc:
            logger.warning("Cannot connect to Ollama at %s: %s", self._ollama_base_url, exc)
            raise

    async def _call_cloud_model(self, prompt: str, system_prompt: str = "") -> str:
        if not self._circuit_breaker.is_available():
            logger.warning("Circuit breaker is open, falling back to rule engine")
            return await self._call_rule_engine(prompt)

        try:
            if self._openai_client is not None:
                result = await self._call_openai(prompt, system_prompt)
            elif self._anthropic_client is not None:
                result = await self._call_anthropic(prompt, system_prompt)
            else:
                raise RuntimeError("No cloud LLM client configured")
            self._circuit_breaker.record_success()
            return result
        except Exception as exc:
            self._circuit_breaker.record_failure()
            logger.warning("Cloud LLM call failed: %s", exc)
            raise

    async def _call_openai(self, prompt: str, system_prompt: str = "") -> str:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        loop = asyncio.get_running_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: self._openai_client.chat.completions.create(
                    model=self._openai_model,
                    messages=messages,
                ),
            ),
            timeout=settings.llm.cloud_timeout,
        )
        return response.choices[0].message.content or ""

    async def _call_anthropic(self, prompt: str, system_prompt: str = "") -> str:
        loop = asyncio.get_running_loop()
        kwargs: dict[str, Any] = {
            "model": self._anthropic_model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: self._anthropic_client.messages.create(**kwargs),
            ),
            timeout=settings.llm.cloud_timeout,
        )
        return response.content[0].text

    def _get_cache_key(self, prompt: str, system_prompt: str, complexity: TaskComplexity) -> str:
        raw = f"{complexity.value}::{system_prompt}::{prompt}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _get_from_cache(self, key: str) -> str | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        return entry

    def _save_to_cache(self, key: str, response: str) -> None:
        self._cache.set(key, response, expire=self._cache_ttl)

    def _generate_type_mutation(self, prompt: str) -> str:
        lower = prompt.lower()

        source_type = None
        for src in _RULE_MUTATIONS:
            if src in lower:
                source_type = src
                break

        if source_type is None:
            source_type = "string"

        target_type = _RULE_MUTATIONS.get(source_type, "string")

        field_match = re.search(r"['\"](\w+)['\"]", prompt)
        field_name = field_match.group(1) if field_match else "field"

        return json.dumps({
            "mutation": "type_change",
            "field": field_name,
            "from_type": source_type,
            "to_type": target_type,
            "value_hint": f"<{target_type}_value>",
        })

    def _generate_boundary_values(self, prompt: str) -> str:
        lower = prompt.lower()
        for type_name, values in _BOUNDARY_VALUES.items():
            if type_name in lower:
                return json.dumps({"mutation": "boundary_values", "type": type_name, "values": values})
        return json.dumps({"mutation": "boundary_values", "type": "integer", "values": _BOUNDARY_VALUES["integer"]})
