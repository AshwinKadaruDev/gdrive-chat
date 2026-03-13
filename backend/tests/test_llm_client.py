"""Tests for LLMClient routing logic and provider selection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm import LLMClient
from app.services.llm.anthropic_provider import AnthropicProvider
from app.services.llm.errors import LLMProviderUnavailableError
from app.services.llm.openai_provider import OpenAIProvider


def _make_client_with_both() -> LLMClient:
    """Create an LLMClient with mock providers for both Anthropic and OpenAI."""
    client = LLMClient.__new__(LLMClient)
    client._providers = {}

    anthropic_provider = AnthropicProvider.__new__(AnthropicProvider)
    anthropic_provider._client = MagicMock()
    client._providers[AnthropicProvider] = anthropic_provider

    openai_provider = OpenAIProvider.__new__(OpenAIProvider)
    openai_provider._client = MagicMock()
    client._providers[OpenAIProvider] = openai_provider

    return client


class TestProviderRouting:
    def test_claude_model_routes_to_anthropic(self):
        client = _make_client_with_both()
        provider = client._get_provider("claude-opus-4-5-20251101")
        assert isinstance(provider, AnthropicProvider)

    def test_gpt_model_routes_to_openai(self):
        client = _make_client_with_both()
        provider = client._get_provider("gpt-5.2")
        assert isinstance(provider, OpenAIProvider)

    def test_unknown_model_routes_to_openai_as_default(self):
        client = _make_client_with_both()
        provider = client._get_provider("some-future-model")
        assert isinstance(provider, OpenAIProvider)

    def test_claude_model_falls_back_to_openai_when_no_anthropic(self):
        client = LLMClient.__new__(LLMClient)
        client._providers = {}
        openai_provider = OpenAIProvider.__new__(OpenAIProvider)
        openai_provider._client = MagicMock()
        client._providers[OpenAIProvider] = openai_provider

        provider = client._get_provider("claude-opus-4-5-20251101")
        assert isinstance(provider, OpenAIProvider)

    def test_no_providers_raises(self):
        client = LLMClient.__new__(LLMClient)
        client._providers = {}

        with pytest.raises(LLMProviderUnavailableError):
            client._get_provider("gpt-5.2")


class TestComplete:
    @pytest.mark.asyncio
    async def test_prefers_anthropic(self):
        client = _make_client_with_both()

        anthropic_provider = client._providers[AnthropicProvider]
        anthropic_provider.complete = AsyncMock(return_value="Anthropic answer")

        openai_provider = client._providers[OpenAIProvider]
        openai_provider.complete = AsyncMock(return_value="OpenAI answer")

        result = await client.complete("Hello")
        assert result == "Anthropic answer"
        anthropic_provider.complete.assert_awaited_once()
        openai_provider.complete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_falls_back_to_openai(self):
        client = LLMClient.__new__(LLMClient)
        client._providers = {}
        openai_provider = OpenAIProvider.__new__(OpenAIProvider)
        openai_provider._client = MagicMock()
        openai_provider.complete = AsyncMock(return_value="OpenAI answer")
        client._providers[OpenAIProvider] = openai_provider

        result = await client.complete("Hello")
        assert result == "OpenAI answer"
