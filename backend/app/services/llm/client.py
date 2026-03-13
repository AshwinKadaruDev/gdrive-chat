"""Thin LLMClient router — delegates to the correct provider."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from app.services.llm.base import LLMProvider
from app.services.llm.errors import LLMProviderUnavailableError
from app.services.llm.registry import get_provider_for_model
from app.services.llm.types import LLMResponse, LLMStreamEvent

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM client supporting multiple providers.

    Constructor signature is unchanged from the original monolithic class.
    """

    def __init__(
        self,
        anthropic_api_key: str | None = None,
        openai_api_key: str | None = None,
    ) -> None:
        self._providers: dict[type[LLMProvider], LLMProvider] = {}

        if anthropic_api_key:
            from app.services.llm.anthropic_provider import AnthropicProvider
            self._providers[AnthropicProvider] = AnthropicProvider(api_key=anthropic_api_key)

        if openai_api_key:
            from app.services.llm.openai_provider import OpenAIProvider
            self._providers[OpenAIProvider] = OpenAIProvider(api_key=openai_api_key)
        else:
            logger.warning("[LLM] No OpenAI API key provided — client not created")

    def _get_provider(self, model: str) -> LLMProvider:
        provider = get_provider_for_model(model, self._providers)
        if provider is None:
            raise LLMProviderUnavailableError(
                "No LLM client available. Provide at least one API key."
            )
        return provider

    async def call_with_tools(
        self,
        messages: list,
        tools: list,
        model: str,
        tool_choice: str = "auto",
        temperature: float = 0.1,
    ) -> LLMResponse:
        logger.info(
            "[LLM] call_with_tools: model=%s, tools=%d, messages=%d, tool_choice=%s",
            model, len(tools), len(messages), tool_choice,
        )
        provider = self._get_provider(model)
        return await provider.call_with_tools(
            messages, tools, model, tool_choice, temperature,
        )

    async def stream_call_with_tools(
        self,
        messages: list,
        tools: list,
        model: str,
        tool_choice: str = "auto",
        temperature: float = 0.1,
    ) -> AsyncGenerator[LLMStreamEvent, None]:
        logger.info(
            "[LLM] stream_call_with_tools: model=%s, tools=%d, messages=%d",
            model, len(tools), len(messages),
        )
        provider = self._get_provider(model)
        async for event in provider.stream_call_with_tools(
            messages, tools, model, tool_choice, temperature,
        ):
            yield event

    async def complete(self, prompt: str, max_tokens: int = 500) -> str:
        """Simple text completion — prefers Anthropic (current behavior)."""
        from app.services.llm.anthropic_provider import AnthropicProvider
        from app.services.llm.openai_provider import OpenAIProvider

        # Prefer Anthropic for simple completions
        for cls in (AnthropicProvider, OpenAIProvider):
            provider = self._providers.get(cls)
            if provider is not None:
                return await provider.complete(prompt, max_tokens)

        raise LLMProviderUnavailableError(
            "No LLM client available. Provide at least one API key."
        )
