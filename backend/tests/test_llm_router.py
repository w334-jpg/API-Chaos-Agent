"""
Comprehensive unit tests for LLMRouter service.
All external LLM calls are mocked — no real API calls are made.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from api_chaos_agent.services.llm_router import LLMRouter, TaskComplexity

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def router() -> LLMRouter:
    """Return a fresh LLMRouter with default config and a temp cache dir."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = {
            "cache_dir": tmpdir,
            "cache_ttl": 2,  # short TTL for expiration tests
            "openai_api_key": "test-openai-key",
            "anthropic_api_key": "test-anthropic-key",
            "ollama_base_url": "http://localhost:11434",
            "ollama_model": "llama3",
            "openai_model": "gpt-4o",
            "anthropic_model": "claude-sonnet-4-20250514",
        }
        r = LLMRouter(config=cfg)
        yield r


# ===================================================================
# 1. Task complexity classification
# ===================================================================


class TestClassifyComplexity:
    """Test classify_complexity maps prompts to the right TaskComplexity."""

    def test_simple_field_mutation(self, router: LLMRouter) -> None:
        prompt = "Change the field type of 'age' from integer to string"
        assert router.classify_complexity(prompt) == TaskComplexity.SIMPLE

    def test_simple_boundary_value(self, router: LLMRouter) -> None:
        prompt = "Generate boundary values for an integer field"
        assert router.classify_complexity(prompt) == TaskComplexity.SIMPLE

    def test_simple_null_or_empty(self, router: LLMRouter) -> None:
        prompt = "Replace the value with null or empty string"
        assert router.classify_complexity(prompt) == TaskComplexity.SIMPLE

    def test_medium_request(self, router: LLMRouter) -> None:
        prompt = "Generate a realistic but invalid JSON payload for the /users endpoint"
        assert router.classify_complexity(prompt) == TaskComplexity.MEDIUM

    def test_medium_fuzz_data(self, router: LLMRouter) -> None:
        prompt = "Create fuzz test data for the login API with various edge cases"
        assert router.classify_complexity(prompt) == TaskComplexity.MEDIUM

    def test_complex_chained_scenarios(self, router: LLMRouter) -> None:
        prompt = "Design a multi-step chaos testing scenario that chains authentication bypass with privilege escalation"
        assert router.classify_complexity(prompt) == TaskComplexity.COMPLEX

    def test_complex_reasoning(self, router: LLMRouter) -> None:
        prompt = "Analyze the API behavior and generate adversarial test cases that exploit business logic vulnerabilities"
        assert router.classify_complexity(prompt) == TaskComplexity.COMPLEX

    def test_default_medium_for_unknown(self, router: LLMRouter) -> None:
        prompt = "Do something with the API"
        assert router.classify_complexity(prompt) == TaskComplexity.MEDIUM


# ===================================================================
# 2. route() returns correct model type based on complexity
# ===================================================================


class TestRouteDispatch:
    """Test that route() dispatches to the correct backend."""

    @pytest.mark.asyncio
    async def test_route_simple_uses_rule_engine(self, router: LLMRouter) -> None:
        with (
            patch.object(
                router, "_call_rule_engine", new_callable=AsyncMock, return_value="rule-result"
            ) as mock_re,
            patch.object(router, "_call_local_model", new_callable=AsyncMock) as mock_local,
            patch.object(router, "_call_cloud_model", new_callable=AsyncMock) as mock_cloud,
        ):
            result = await router.route(
                "Change field type to string",
                complexity=TaskComplexity.SIMPLE,
            )
            assert result == "rule-result"
            mock_re.assert_awaited_once()
            mock_local.assert_not_awaited()
            mock_cloud.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_route_medium_uses_local_model(self, router: LLMRouter) -> None:
        with (
            patch.object(router, "_call_rule_engine", new_callable=AsyncMock) as mock_re,
            patch.object(
                router, "_call_local_model", new_callable=AsyncMock, return_value="local-result"
            ) as mock_local,
            patch.object(router, "_call_cloud_model", new_callable=AsyncMock) as mock_cloud,
        ):
            result = await router.route(
                "Generate fuzz data for login",
                system_prompt="You are a tester",
                complexity=TaskComplexity.MEDIUM,
            )
            assert result == "local-result"
            mock_re.assert_not_awaited()
            mock_local.assert_awaited_once()
            mock_cloud.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_route_complex_uses_cloud_model(self, router: LLMRouter) -> None:
        with (
            patch.object(router, "_call_rule_engine", new_callable=AsyncMock) as mock_re,
            patch.object(router, "_call_local_model", new_callable=AsyncMock) as mock_local,
            patch.object(
                router, "_call_cloud_model", new_callable=AsyncMock, return_value="cloud-result"
            ) as mock_cloud,
        ):
            result = await router.route(
                "Design multi-step chaos scenario",
                system_prompt="You are a security expert",
                complexity=TaskComplexity.COMPLEX,
            )
            assert result == "cloud-result"
            mock_re.assert_not_awaited()
            mock_local.assert_not_awaited()
            mock_cloud.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_route_auto_classifies_when_complexity_is_none(self, router: LLMRouter) -> None:
        """When complexity=None, route() should auto-classify and dispatch accordingly."""
        with patch.object(
            router, "_call_rule_engine", new_callable=AsyncMock, return_value="auto-result"
        ) as mock_re:
            result = await router.route("Change field type to string", complexity=None)
            assert result == "auto-result"
            mock_re.assert_awaited_once()


# ===================================================================
# 3. Caching: same input returns cached result
# ===================================================================


class TestCaching:
    """Test that cache hit avoids re-calling LLM."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_result(self, router: LLMRouter) -> None:
        call_count = 0

        async def fake_cloud(prompt: str, system_prompt: str = "") -> str:
            nonlocal call_count
            call_count += 1
            return f"cloud-{call_count}"

        with patch.object(router, "_call_cloud_model", side_effect=fake_cloud):
            result1 = await router.route("test prompt", complexity=TaskComplexity.COMPLEX)
            result2 = await router.route("test prompt", complexity=TaskComplexity.COMPLEX)
            # Second call should return the cached result, not call LLM again
            assert result1 == result2
            assert call_count == 1  # only called once

    # ===================================================================
    # 4. Cache miss triggers actual LLM call
    # ===================================================================

    @pytest.mark.asyncio
    async def test_cache_miss_triggers_llm_call(self, router: LLMRouter) -> None:
        call_count = 0

        async def fake_cloud(prompt: str, system_prompt: str = "") -> str:
            nonlocal call_count
            call_count += 1
            return f"cloud-{call_count}"

        with patch.object(router, "_call_cloud_model", side_effect=fake_cloud):
            result1 = await router.route("prompt A", complexity=TaskComplexity.COMPLEX)
            result2 = await router.route("prompt B", complexity=TaskComplexity.COMPLEX)
            assert result1 != result2
            assert call_count == 2


# ===================================================================
# 5. Cloud model client initialization
# ===================================================================


class TestCloudModelInit:
    """Test that OpenAI and Anthropic clients are initialized correctly."""

    def test_openai_client_initialized(self, router: LLMRouter) -> None:
        assert router._openai_client is not None
        # The client should have been created with the test key
        assert router._openai_client.api_key == "test-openai-key"

    def test_anthropic_client_initialized(self, router: LLMRouter) -> None:
        assert router._anthropic_client is not None
        assert router._anthropic_client.api_key == "test-anthropic-key"


# ===================================================================
# 6. Local model (Ollama) client initialization
# ===================================================================


class TestLocalModelInit:
    """Test Ollama client configuration."""

    def test_ollama_config(self, router: LLMRouter) -> None:
        assert router._ollama_base_url == "http://localhost:11434"
        assert router._ollama_model == "llama3"


# ===================================================================
# 7. Rule engine handles simple tasks
# ===================================================================


class TestRuleEngine:
    """Test the rule-based engine for simple tasks."""

    @pytest.mark.asyncio
    async def test_type_mutation(self, router: LLMRouter) -> None:
        result = await router._call_rule_engine(
            "Change the field type of 'age' from integer to string"
        )
        assert isinstance(result, str)
        assert len(result) > 0
        # Should contain a mutated value hint
        assert "string" in result.lower() or "str" in result.lower()

    @pytest.mark.asyncio
    async def test_boundary_value_generation(self, router: LLMRouter) -> None:
        result = await router._call_rule_engine("Generate boundary values for an integer field")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_null_replacement(self, router: LLMRouter) -> None:
        result = await router._call_rule_engine("Replace the value with null")
        assert isinstance(result, str)
        assert "null" in result.lower()

    @pytest.mark.asyncio
    async def test_empty_string_replacement(self, router: LLMRouter) -> None:
        result = await router._call_rule_engine("Replace the value with empty string")
        assert isinstance(result, str)
        assert len(result) > 0


# ===================================================================
# 8. Error handling when LLM API fails
# ===================================================================


class TestErrorHandling:
    """Test graceful error handling when LLM calls fail."""

    @pytest.mark.asyncio
    async def test_cloud_model_failure_returns_fallback(self, router: LLMRouter) -> None:
        with patch.object(
            router, "_call_cloud_model", new_callable=AsyncMock, side_effect=Exception("API error")
        ):
            result = await router.route(
                "Design complex scenario",
                complexity=TaskComplexity.COMPLEX,
            )
            # Should return a fallback, not raise
            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_local_model_failure_returns_fallback(self, router: LLMRouter) -> None:
        with patch.object(
            router,
            "_call_local_model",
            new_callable=AsyncMock,
            side_effect=Exception("Ollama down"),
        ):
            result = await router.route(
                "Generate fuzz data",
                complexity=TaskComplexity.MEDIUM,
            )
            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_rule_engine_never_raises(self, router: LLMRouter) -> None:
        # Rule engine should be deterministic and never raise
        result = await router._call_rule_engine("Change field type to string")
        assert isinstance(result, str)


# ===================================================================
# 9. Cache expiration / TTL behavior
# ===================================================================


class TestCacheTTL:
    """Test that cached entries expire after TTL."""

    @pytest.mark.asyncio
    async def test_cache_entry_expires_after_ttl(self, router: LLMRouter) -> None:
        call_count = 0

        async def fake_cloud(prompt: str, system_prompt: str = "") -> str:
            nonlocal call_count
            call_count += 1
            return f"cloud-{call_count}"

        with patch.object(router, "_call_cloud_model", side_effect=fake_cloud):
            # First call populates cache
            result1 = await router.route("ttl-test", complexity=TaskComplexity.COMPLEX)
            assert call_count == 1

            # Wait for cache to expire (TTL=2 seconds)
            time.sleep(2.5)

            # Should re-call LLM because cache expired
            result2 = await router.route("ttl-test", complexity=TaskComplexity.COMPLEX)
            assert call_count == 2
            assert result1 != result2


# ===================================================================
# 10. Batch request optimization
# ===================================================================


class TestBatchOptimization:
    """Test batch request handling."""

    @pytest.mark.asyncio
    async def test_batch_route_processes_multiple_prompts(self, router: LLMRouter) -> None:
        prompts = [
            ("Change field type to string", TaskComplexity.SIMPLE),
            ("Generate fuzz data", TaskComplexity.MEDIUM),
            ("Design complex scenario", TaskComplexity.COMPLEX),
        ]

        with (
            patch.object(
                router, "_call_rule_engine", new_callable=AsyncMock, return_value="rule-result"
            ),
            patch.object(
                router, "_call_local_model", new_callable=AsyncMock, return_value="local-result"
            ),
            patch.object(
                router, "_call_cloud_model", new_callable=AsyncMock, return_value="cloud-result"
            ),
        ):
            results = await router.batch_route(prompts)
            assert len(results) == 3
            assert results[0] == "rule-result"
            assert results[1] == "local-result"
            assert results[2] == "cloud-result"

    @pytest.mark.asyncio
    async def test_batch_route_deduplicates_identical_prompts(self, router: LLMRouter) -> None:
        """Identical prompts in a batch should only trigger one LLM call each."""
        call_count = 0

        async def fake_rule(prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"rule-{call_count}"

        prompts = [
            ("Change field type to string", TaskComplexity.SIMPLE),
            ("Change field type to string", TaskComplexity.SIMPLE),
        ]

        with patch.object(router, "_call_rule_engine", side_effect=fake_rule):
            results = await router.batch_route(prompts)
            assert len(results) == 2
            # Both should return the same result (deduplicated via cache)
            assert results[0] == results[1]
            # Only one actual call should have been made
            assert call_count == 1
