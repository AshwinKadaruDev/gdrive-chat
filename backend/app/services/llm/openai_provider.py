"""OpenAI (Responses API) provider — encapsulates all OpenAI-specific logic."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from app.services.llm.base import LLMProvider
from app.services.llm.errors import (
    LLMAPIError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.services.llm.registry import register_provider
from app.services.llm.types import (
    Choice,
    FunctionCall,
    LLMResponse,
    LLMStreamEvent,
    MessageContent,
    ToolCall,
)

logger = logging.getLogger(__name__)


@register_provider
class OpenAIProvider(LLMProvider):
    """LLM provider backed by the OpenAI Responses API."""

    def __init__(self, api_key: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        logger.info("[LLM] OpenAI client initialized (openai SDK)")

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #

    async def call_with_tools(
        self,
        messages: list,
        tools: list,
        model: str,
        tool_choice: str = "auto",
        temperature: float = 0.1,
    ) -> LLMResponse:
        instructions, input_items = self.convert_messages(messages)
        responses_tools = self.convert_tools(tools)

        kwargs: dict[str, Any] = {
            "model": model,
            "input": input_items,
            "tools": responses_tools,
            "reasoning": {"effort": "xhigh"},
        }
        if instructions:
            kwargs["instructions"] = instructions
        if tool_choice != "auto":
            kwargs["tool_choice"] = tool_choice

        logger.info(
            "[LLM] OpenAI Responses API call: model=%s, input_items=%d, tools=%d",
            model, len(input_items), len(responses_tools),
        )
        try:
            response = await self._client.responses.create(**kwargs)
        except Exception as exc:
            logger.exception("[LLM] OpenAI Responses API call failed")
            raise self._wrap_error(exc) from exc

        result = self.normalize_response(response)
        logger.info(
            "[LLM] OpenAI response: content_length=%s, tool_calls=%d",
            len(result.choices[0].message.content) if result.choices[0].message.content else 0,
            len(result.choices[0].message.tool_calls),
        )
        return result

    async def stream_call_with_tools(
        self,
        messages: list,
        tools: list,
        model: str,
        tool_choice: str = "auto",
        temperature: float = 0.1,
    ) -> AsyncGenerator[LLMStreamEvent, None]:
        instructions, input_items = self.convert_messages(messages)
        responses_tools = self.convert_tools(tools)

        kwargs: dict[str, Any] = {
            "model": model,
            "input": input_items,
            "tools": responses_tools,
            "reasoning": {"effort": "xhigh"},
            "stream": True,
        }
        if instructions:
            kwargs["instructions"] = instructions
        if tool_choice != "auto":
            kwargs["tool_choice"] = tool_choice

        logger.info(
            "[LLM] OpenAI Responses API streaming call: model=%s, input_items=%d, tools=%d",
            model, len(input_items), len(responses_tools),
        )

        has_function_calls = False

        try:
            async with await self._client.responses.create(**kwargs) as stream:
                async for event in stream:
                    event_type = event.type

                    if event_type == "response.output_item.added":
                        if hasattr(event, "item") and getattr(event.item, "type", None) == "function_call":
                            has_function_calls = True

                    elif event_type == "response.output_text.delta":
                        if not has_function_calls:
                            yield LLMStreamEvent(type="text_delta", text=event.delta)

                    elif event_type == "response.completed":
                        result = self.normalize_response(event.response)
                        logger.info(
                            "[LLM] Streaming response complete: content_length=%s, tool_calls=%d",
                            len(result.choices[0].message.content) if result.choices[0].message.content else 0,
                            len(result.choices[0].message.tool_calls),
                        )
                        yield LLMStreamEvent(type="response_complete", response=result)
        except Exception as exc:
            logger.exception("[LLM] OpenAI Responses API streaming call failed")
            raise self._wrap_error(exc) from exc

    async def complete(self, prompt: str, max_tokens: int = 500) -> str:
        response = await self._client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""

    @staticmethod
    def can_handle(model: str) -> bool:
        # Default / catch-all provider: handles anything that isn't Claude.
        return not model.lower().startswith("claude")

    # ------------------------------------------------------------------ #
    # Conversion helpers (static, testable in isolation)
    # ------------------------------------------------------------------ #

    @staticmethod
    def convert_tools(tools: list[dict]) -> list[dict]:
        """Convert OpenAI Chat Completions nested tool format to Responses API flat format.

        FROM: {"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}
          TO: {"type": "function", "name": ..., "description": ..., "parameters": {...}}
        """
        result: list[dict] = []
        for tool in tools:
            func = tool.get("function", tool)
            result.append({
                "type": "function",
                "name": func["name"],
                "description": func.get("description", ""),
                "parameters": func.get("parameters", {}),
            })
        return result

    @staticmethod
    def convert_messages(
        messages: list[dict],
    ) -> tuple[str | None, list[dict]]:
        """Convert OpenAI-style messages to Responses API input format.

        Returns (instructions, input_items).
        """
        instructions: str | None = None
        input_items: list[dict] = []

        for msg in messages:
            role = msg.get("role")

            if role == "system":
                instructions = msg.get("content")

            elif role == "user":
                input_items.append({"role": "user", "content": msg.get("content", "")})

            elif role == "assistant":
                raw_items = msg.get("_raw_output_items")
                if raw_items:
                    input_items.extend(raw_items)
                else:
                    tool_calls = msg.get("tool_calls")
                    if msg.get("content"):
                        input_items.append({
                            "type": "message",
                            "role": "assistant",
                            "content": msg["content"],
                        })
                    if tool_calls:
                        for tc in tool_calls:
                            func = tc.get("function", {})
                            input_items.append({
                                "type": "function_call",
                                "call_id": tc["id"],
                                "name": func.get("name", ""),
                                "arguments": func.get("arguments", "{}"),
                            })

            elif role == "tool":
                input_items.append({
                    "type": "function_call_output",
                    "call_id": msg.get("tool_call_id", ""),
                    "output": msg.get("content", ""),
                })

        return instructions, input_items

    @staticmethod
    def normalize_response(response: Any) -> LLMResponse:
        """Convert an OpenAI Responses API response into the normalized LLMResponse."""
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for item in response.output:
            if item.type == "message":
                for part in item.content:
                    if hasattr(part, "text"):
                        text_parts.append(part.text)
            elif item.type == "function_call":
                tool_calls.append(
                    ToolCall(
                        id=item.call_id,
                        function=FunctionCall(
                            name=item.name,
                            arguments=item.arguments,
                        ),
                    )
                )

        content = "\n".join(text_parts) if text_parts else None

        _OUTPUT_ONLY_FIELDS = {"status"}
        raw_items: list[dict] = []
        for item in response.output:
            try:
                d = json.loads(item.model_dump_json())
                for key in _OUTPUT_ONLY_FIELDS:
                    d.pop(key, None)
                raw_items.append(d)
            except Exception:
                raw_items.append({"type": item.type})

        return LLMResponse(
            choices=[
                Choice(
                    message=MessageContent(
                        content=content,
                        tool_calls=tool_calls,
                        _raw_output_items=raw_items,
                    )
                )
            ]
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _wrap_error(exc: Exception) -> Exception:
        """Wrap OpenAI SDK exceptions into the unified error hierarchy."""
        try:
            import httpx
            import openai
        except ImportError:
            return exc

        if isinstance(exc, openai.RateLimitError):
            return LLMRateLimitError(str(exc))
        if isinstance(exc, openai.APIConnectionError):
            return LLMConnectionError(str(exc))
        if isinstance(exc, openai.APITimeoutError):
            return LLMTimeoutError(str(exc))
        if isinstance(exc, openai.APIStatusError):
            return LLMAPIError(str(exc))
        if isinstance(exc, httpx.HTTPError):
            return LLMConnectionError(str(exc))
        return exc
