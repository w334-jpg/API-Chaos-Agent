"""Extended tests for LLMRouter — covering missing code paths."""

from __future__ import annotations

import json
import time

import pytest

from api_chaos_agent.services.llm_router import CircuitBreaker, LLMRouter, TaskComplexity


@pytest.fixture
def router() -> LLMRouter:
    return LLMRouter(
        config={
            "openai_api_key": "",
            "anthropic_api_key": "",
            "ollama_base_url": "http://localhost:99999",
        }
    )


class TestRuleEngineEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_string_mutation(self, router: LLMRouter):
        result = await router.route("replace with empty string", complexity=TaskComplexity.SIMPLE)
        parsed = json.loads(result)
        assert parsed["mutation"] == "empty_string"
        assert parsed["value"] == ""

    @pytest.mark.asyncio
    async def test_generic_simple_fallback(self, router: LLMRouter):
        result = await router.route("null check", complexity=TaskComplexity.SIMPLE)
        parsed = json.loads(result)
        assert parsed["mutation"] == "null"

    @pytest.mark.asyncio
    async def test_generic_simple_no_keyword_match(self, router: LLMRouter):
        result = await router.route("simple test without keywords", complexity=TaskComplexity.SIMPLE)
        parsed = json.loads(result)
        assert parsed["mutation"] == "generic_simple"

    @pytest.mark.asyncio
    async def test_type_mutation_without_field_name(self, router: LLMRouter):
        result = await router.route("change field type integer", complexity=TaskComplexity.SIMPLE)
        parsed = json.loads(result)
        assert parsed["mutation"] == "type_change"
        assert parsed["from_type"] == "integer"
        assert parsed["to_type"] == "string"

    @pytest.mark.asyncio
    async def test_type_mutation_default_to_string(self, router: LLMRouter):
        result = await router.route("change field type unknown_type", complexity=TaskComplexity.SIMPLE)
        parsed = json.loads(result)
        assert parsed["mutation"] == "type_change"
        assert parsed["from_type"] == "string"

    @pytest.mark.asyncio
    async def test_boundary_values_number(self, router: LLMRouter):
        result = await router.route("boundary value for number field", complexity=TaskComplexity.SIMPLE)
        parsed = json.loads(result)
        assert parsed["mutation"] == "boundary_values"
        assert parsed["type"] == "number"

    @pytest.mark.asyncio
    async def test_boundary_values_default_integer(self, router: LLMRouter):
        result = await router.route("boundary value for custom_type", complexity=TaskComplexity.SIMPLE)
        parsed = json.loads(result)
        assert parsed["mutation"] == "boundary_values"
        assert parsed["type"] == "integer"


class TestCircuitBreakerExtended:
    def test_initial_state(self):
        cb = CircuitBreaker(failure_threshold=3, reset_timeout=1.0)
        assert cb.state == "closed"
        assert cb.is_available()

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker(failure_threshold=5, reset_timeout=1.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "closed"

    def test_opens_at_threshold(self):
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=1.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        assert not cb.is_available()

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.05)
        cb.record_failure()
        assert cb.state == "open"
        time.sleep(0.1)
        assert cb.state == "half-open"
        assert cb.is_available()

    def test_success_resets_to_closed(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.05)
        cb.record_failure()
        time.sleep(0.1)
        assert cb.state == "half-open"
        cb.record_success()
        assert cb.state == "closed"

    def test_failure_in_half_open_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.05)
        cb.record_failure()
        time.sleep(0.1)
        assert cb.state == "half-open"
        cb.record_failure()
        assert cb.state == "open"


class TestLLMRouterCache:
    @pytest.mark.asyncio
    async def test_cache_key_deterministic(self, router: LLMRouter):
        key1 = router._get_cache_key("test", "sys", TaskComplexity.SIMPLE)
        key2 = router._get_cache_key("test", "sys", TaskComplexity.SIMPLE)
        assert key1 == key2

    @pytest.mark.asyncio
    async def test_cache_key_differs_for_different_complexity(self, router: LLMRouter):
        key1 = router._get_cache_key("test", "sys", TaskComplexity.SIMPLE)
        key2 = router._get_cache_key("test", "sys", TaskComplexity.COMPLEX)
        assert key1 != key2

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self, router: LLMRouter):
        result = router._get_from_cache("nonexistent-key")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_save_and_retrieve(self, router: LLMRouter):
        router._save_to_cache("test-key", "test-value")
        result = router._get_from_cache("test-key")
        assert result == "test-value"


class TestLLMRouterClose:
    def test_close_without_http_client(self, router: LLMRouter):
        router._http_client = None
        router.close()

    def test_close_with_closed_http_client(self, router: LLMRouter):
        from unittest.mock import MagicMock
        mock_client = MagicMock()
        mock_client.is_closed = True
        router._http_client = mock_client
        router.close()


class TestLLMRouterClassify:
    def test_classify_simple_null(self, router: LLMRouter):
        assert router.classify_complexity("replace with null") == TaskComplexity.SIMPLE

    def test_classify_simple_empty(self, router: LLMRouter):
        assert router.classify_complexity("replace with empty") == TaskComplexity.SIMPLE

    def test_classify_complex_design(self, router: LLMRouter):
        assert router.classify_complexity("design a new test") == TaskComplexity.COMPLEX

    def test_classify_complex_analyze(self, router: LLMRouter):
        assert router.classify_complexity("analyze the results") == TaskComplexity.COMPLEX

    def test_classify_complex_reason(self, router: LLMRouter):
        assert router.classify_complexity("reason about the failure") == TaskComplexity.COMPLEX

    def test_classify_medium_default(self, router: LLMRouter):
        assert router.classify_complexity("generate a test for latency") == TaskComplexity.MEDIUM


class TestLLMRouterBatchRoute:
    @pytest.mark.asyncio
    async def test_batch_route_mixed_complexity(self, router: LLMRouter):
        prompts = [
            ("change field type of 'name'", TaskComplexity.SIMPLE),
            ("generate a latency test", TaskComplexity.MEDIUM),
        ]
        results = await router.batch_route(prompts)
        assert len(results) == 2
