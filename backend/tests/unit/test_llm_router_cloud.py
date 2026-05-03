"""Extended tests for LLMRouter — HTTP client and cloud model paths."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestGetHttpClient:
    @pytest.mark.asyncio
    async def test_creates_client_when_none(self, router: LLMRouter):
        router._http_client = None
        from api_chaos_agent.core.config import AppConfig, LLMConfig
        config = AppConfig(llm=LLMConfig(ollama_timeout=30))
        with patch("api_chaos_agent.services.llm_router.settings", config):
            client = await router._get_http_client()
            assert client is not None

    @pytest.mark.asyncio
    async def test_creates_client_when_closed(self, router: LLMRouter):
        mock_client = MagicMock()
        mock_client.is_closed = True
        router._http_client = mock_client
        from api_chaos_agent.core.config import AppConfig, LLMConfig
        config = AppConfig(llm=LLMConfig(ollama_timeout=30))
        with patch("api_chaos_agent.services.llm_router.settings", config):
            client = await router._get_http_client()
            assert client is not None


class TestCallLocalModel:
    @pytest.mark.asyncio
    async def test_call_local_model_success(self, router: LLMRouter):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "test result"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(router, "_get_http_client", return_value=mock_client):
            result = await router._call_local_model("test prompt")
        assert result == "test result"

    @pytest.mark.asyncio
    async def test_call_local_model_with_system_prompt(self, router: LLMRouter):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "result"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(router, "_get_http_client", return_value=mock_client):
            result = await router._call_local_model("test prompt", "system prompt")
        assert result == "result"
        call_kwargs = mock_client.post.call_args
        assert call_kwargs[1]["json"]["system"] == "system prompt"

    @pytest.mark.asyncio
    async def test_call_local_model_http_error(self, router: LLMRouter):
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=mock_response
            )
        )

        with patch.object(router, "_get_http_client", return_value=mock_client):
            with pytest.raises(httpx.HTTPStatusError):
                await router._call_local_model("test prompt")

    @pytest.mark.asyncio
    async def test_call_local_model_connect_error(self, router: LLMRouter):
        import httpx

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with patch.object(router, "_get_http_client", return_value=mock_client):
            with pytest.raises(httpx.ConnectError):
                await router._call_local_model("test prompt")


class TestCallCloudModel:
    @pytest.mark.asyncio
    async def test_circuit_breaker_open_falls_back(self, router: LLMRouter):
        router._circuit_breaker = CircuitBreaker(failure_threshold=1, reset_timeout=100)
        router._circuit_breaker.record_failure()

        result = await router._call_cloud_model("null check", "")
        parsed = json.loads(result)
        assert parsed["mutation"] == "null"

    @pytest.mark.asyncio
    async def test_no_cloud_client_raises(self, router: LLMRouter):
        router._openai_client = None
        router._anthropic_client = None

        with pytest.raises(RuntimeError, match="No cloud LLM"):
            await router._call_cloud_model("test prompt", "")

    @pytest.mark.asyncio
    async def test_cloud_failure_records_circuit_breaker(self, router: LLMRouter):
        router._openai_client = MagicMock()
        router._openai_client.chat.completions.create = MagicMock(
            side_effect=Exception("API error")
        )

        with pytest.raises(Exception, match="API error"):
            await router._call_cloud_model("test prompt", "")
        assert router._circuit_breaker._failure_count == 1


class TestCallOpenAI:
    @pytest.mark.asyncio
    async def test_call_openai_success(self, router: LLMRouter):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "OpenAI response"

        router._openai_client = MagicMock()
        router._openai_client.chat.completions.create = MagicMock(return_value=mock_response)

        from api_chaos_agent.core.config import AppConfig, LLMConfig
        config = AppConfig(llm=LLMConfig(cloud_timeout=30))
        with patch("api_chaos_agent.services.llm_router.settings", config):
            result = await router._call_openai("test prompt", "system prompt")
        assert result == "OpenAI response"

    @pytest.mark.asyncio
    async def test_call_openai_without_system_prompt(self, router: LLMRouter):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response"

        router._openai_client = MagicMock()
        router._openai_client.chat.completions.create = MagicMock(return_value=mock_response)

        from api_chaos_agent.core.config import AppConfig, LLMConfig
        config = AppConfig(llm=LLMConfig(cloud_timeout=30))
        with patch("api_chaos_agent.services.llm_router.settings", config):
            result = await router._call_openai("test prompt")
        assert result == "response"


class TestCallAnthropic:
    @pytest.mark.asyncio
    async def test_call_anthropic_success(self, router: LLMRouter):
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "Anthropic response"

        router._anthropic_client = MagicMock()
        router._anthropic_client.messages.create = MagicMock(return_value=mock_response)

        from api_chaos_agent.core.config import AppConfig, LLMConfig
        config = AppConfig(llm=LLMConfig(cloud_timeout=30))
        with patch("api_chaos_agent.services.llm_router.settings", config):
            result = await router._call_anthropic("test prompt", "system prompt")
        assert result == "Anthropic response"

    @pytest.mark.asyncio
    async def test_call_anthropic_without_system_prompt(self, router: LLMRouter):
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "response"

        router._anthropic_client = MagicMock()
        router._anthropic_client.messages.create = MagicMock(return_value=mock_response)

        from api_chaos_agent.core.config import AppConfig, LLMConfig
        config = AppConfig(llm=LLMConfig(cloud_timeout=30))
        with patch("api_chaos_agent.services.llm_router.settings", config):
            result = await router._call_anthropic("test prompt")
        assert result == "response"


class TestRouterCloseExtended:
    def test_close_with_open_http_client(self, router: LLMRouter):
        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()
        router._http_client = mock_client
        router.close()

    def test_del_method(self, router: LLMRouter):
        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.sync_close = MagicMock()
        router._http_client = mock_client
        router.__del__()

    def test_del_with_closed_client(self, router: LLMRouter):
        mock_client = MagicMock()
        mock_client.is_closed = True
        router._http_client = mock_client
        router.__del__()


class TestRouteMediumComplexity:
    @pytest.mark.asyncio
    async def test_medium_calls_local_model(self, router: LLMRouter):
        router._cache.clear()
        with patch.object(router, "_call_local_model", new_callable=AsyncMock, return_value="local model result"):
            result = await router.route("generate a test for latency", complexity=TaskComplexity.MEDIUM)
        assert result == "local model result"
