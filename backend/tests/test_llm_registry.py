"""Tests for LLM provider registry — can_handle and get_provider_for_model."""

from unittest.mock import MagicMock

from app.services.llm.anthropic_provider import AnthropicProvider
from app.services.llm.openai_provider import OpenAIProvider
from app.services.llm.registry import get_provider_for_model


class TestCanHandle:
    def test_anthropic_handles_claude(self):
        assert AnthropicProvider.can_handle("claude-opus-4-5-20251101") is True
        assert AnthropicProvider.can_handle("claude-sonnet-4-5-20250929") is True
        assert AnthropicProvider.can_handle("Claude-3-Haiku") is True

    def test_anthropic_rejects_non_claude(self):
        assert AnthropicProvider.can_handle("gpt-5.2") is False
        assert AnthropicProvider.can_handle("gemini-pro") is False

    def test_openai_handles_non_claude(self):
        assert OpenAIProvider.can_handle("gpt-5.2") is True
        assert OpenAIProvider.can_handle("o3-mini") is True
        assert OpenAIProvider.can_handle("gemini-pro") is True

    def test_openai_rejects_claude(self):
        assert OpenAIProvider.can_handle("claude-opus-4-5-20251101") is False


class TestGetProviderForModel:
    def _make_providers(self, anthropic=True, openai=True):
        providers = {}
        if anthropic:
            p = AnthropicProvider.__new__(AnthropicProvider)
            p._client = MagicMock()
            providers[AnthropicProvider] = p
        if openai:
            p = OpenAIProvider.__new__(OpenAIProvider)
            p._client = MagicMock()
            providers[OpenAIProvider] = p
        return providers

    def test_claude_routes_to_anthropic(self):
        providers = self._make_providers()
        result = get_provider_for_model("claude-opus-4-5-20251101", providers)
        assert isinstance(result, AnthropicProvider)

    def test_gpt_routes_to_openai(self):
        providers = self._make_providers()
        result = get_provider_for_model("gpt-5.2", providers)
        assert isinstance(result, OpenAIProvider)

    def test_fallback_when_preferred_unavailable(self):
        providers = self._make_providers(anthropic=False, openai=True)
        result = get_provider_for_model("claude-opus-4-5-20251101", providers)
        assert isinstance(result, OpenAIProvider)

    def test_returns_none_when_no_providers(self):
        result = get_provider_for_model("gpt-5.2", {})
        assert result is None
