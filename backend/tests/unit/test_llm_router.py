"""Unit tests for LLMRouter."""

from __future__ import annotations

import json

import pytest

from api_chaos_agent.services.llm_router import LLMRouter, TaskComplexity, CircuitBreaker


@pytest.fixture
def router() -> LLMRouter:
    return LLMRouter(config={
        "openai_api_key": "",
        "anthropic_api_key": "",
        "ollama_base_url": "http://localhost:99999",
    })


def test_classify_simple(router: LLMRouter) -> None:
    assert router.classify_complexity("change field type of name to integer") == TaskComplexity.SIMPLE
    assert router.classify_complexity("boundary value test for age") == TaskComplexity.SIMPLE
    assert router.classify_complexity("replace with null") == TaskComplexity.SIMPLE


def test_classify_complex(router: LLMRouter) -> None:
    assert router.classify_complexity("design a multi-step chained attack scenario") == TaskComplexity.COMPLEX
    assert router.classify_complexity("analyze authentication bypass vulnerability") == TaskComplexity.COMPLEX


def test_classify_medium(router: LLMRouter) -> None:
    assert router.classify_complexity("generate a latency test for /api/users") == TaskComplexity.MEDIUM


@pytest.mark.asyncio
async def test_rule_engine_type_mutation(router: LLMRouter) -> None:
    result = await router.route(
        "change field type of 'name' from string to integer",
        complexity=TaskComplexity.SIMPLE,
    )
    parsed = json.loads(result)
    assert parsed["mutation"] == "type_change"
    assert parsed["field"] == "name"


@pytest.mark.asyncio
async def test_rule_engine_boundary(router: LLMRouter) -> None:
    result = await router.route(
        "boundary value test for integer field",
        complexity=TaskComplexity.SIMPLE,
    )
    parsed = json.loads(result)
    assert parsed["mutation"] == "boundary_values"
    assert "values" in parsed


@pytest.mark.asyncio
async def test_rule_engine_null(router: LLMRouter) -> None:
    result = await router.route("replace with null", complexity=TaskComplexity.SIMPLE)
    parsed = json.loads(result)
    assert parsed["mutation"] == "null"


@pytest.mark.asyncio
async def test_caching(router: LLMRouter) -> None:
    prompt = "change field type of 'email' to integer"
    result1 = await router.route(prompt, complexity=TaskComplexity.SIMPLE)
    result2 = await router.route(prompt, complexity=TaskComplexity.SIMPLE)
    assert result1 == result2


@pytest.mark.asyncio
async def test_fallback_to_rule_engine(router: LLMRouter) -> None:
    result = await router.route(
        "complex multi-step adversarial scenario",
        complexity=TaskComplexity.COMPLEX,
    )
    assert result is not None
    assert len(result) > 0


def test_circuit_breaker() -> None:
    cb = CircuitBreaker(failure_threshold=3, reset_timeout=0.1)
    assert cb.state == "closed"
    assert cb.is_available()

    cb.record_failure()
    cb.record_failure()
    assert cb.state == "closed"

    cb.record_failure()
    assert cb.state == "open"
    assert not cb.is_available()

    import time
    time.sleep(0.15)
    assert cb.state == "half-open"
    assert cb.is_available()

    cb.record_success()
    assert cb.state == "closed"


def test_circuit_breaker_reset() -> None:
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.05)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "open"

    import time
    time.sleep(0.1)
    assert cb.state == "half-open"

    cb.record_failure()
    assert cb.state == "open"


@pytest.mark.asyncio
async def test_batch_route(router: LLMRouter) -> None:
    prompts = [
        ("change field type of 'name'", TaskComplexity.SIMPLE),
        ("boundary test for integer", TaskComplexity.SIMPLE),
    ]
    results = await router.batch_route(prompts)
    assert len(results) == 2
    for r in results:
        assert r is not None
