"""Anthropic (Messages API) provider — encapsulates all Claude-specific logic."""

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
class AnthropicProvider(LLMProvider):
    """LLM provider backed by the Anthropic Messages API."""

    def __init__(self, api_key: str) -> None:
        import anthropic

        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            max_retries=3,
        )
        logger.info("[LLM] Anthropic client initialized")

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
        system_prompt, anthropic_messages = self.convert_messages(messages)
        anthropic_tools = self.convert_tools(tools)
        kwargs = self._build_kwargs(
            model, anthropic_messages, anthropic_tools, system_prompt, tool_choice,
        )

        logger.info(
            "[LLM] Anthropic Messages API call: model=%s, messages=%d, tools=%d",
            model, len(anthropic_messages), len(anthropic_tools),
        )
        try:
            response = await self._client.messages.create(**kwargs)
        except Exception as exc:
            logger.warning("[LLM] Anthropic API error: %s: %s", type(exc).__name__, exc)
            raise self._wrap_error(exc) from exc

        result = self.normalize_response(response)
        logger.info(
            "[LLM] Anthropic response: content_length=%s, tool_calls=%d, stop_reason=%s",
            len(result.choices[0].message.content) if result.choices[0].message.content else 0,
            len(result.choices[0].message.tool_calls),
            response.stop_reason,
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
        system_prompt, anthropic_messages = self.convert_messages(messages)
        anthropic_tools = self.convert_tools(tools)
        kwargs = self._build_kwargs(
            model, anthropic_messages, anthropic_tools, system_prompt, tool_choice,
        )

        logger.info(
            "[LLM] Anthropic Messages API streaming call: model=%s, messages=%d, tools=%d",
            model, len(anthropic_messages), len(anthropic_tools),
        )

        has_tool_use = False

        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    if event.type == "content_block_start":
                        if hasattr(event, "content_block") and getattr(event.content_block, "type", None) == "tool_use":
                            has_tool_use = True
                    elif event.type == "content_block_delta":
                        if hasattr(event, "delta") and getattr(event.delta, "type", None) == "text_delta":
                            if not has_tool_use:
                                yield LLMStreamEvent(type="text_delta", text=event.delta.text)

                final_message = await stream.get_final_message()
                result = self.normalize_response(final_message)
                logger.info(
                    "[LLM] Anthropic streaming complete: content_length=%s, tool_calls=%d",
                    len(result.choices[0].message.content) if result.choices[0].message.content else 0,
                    len(result.choices[0].message.tool_calls),
                )
                yield LLMStreamEvent(type="response_complete", response=result)
        except Exception as exc:
            logger.warning("[LLM] Anthropic streaming error: %s: %s", type(exc).__name__, exc)
            raise self._wrap_error(exc) from exc

    async def complete(self, prompt: str, max_tokens: int = 500) -> str:
        response = await self._client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    @staticmethod
    def can_handle(model: str) -> bool:
        return "claude" in model.lower()

    # ------------------------------------------------------------------ #
    # Conversion helpers (static, testable in isolation)
    # ------------------------------------------------------------------ #

    @staticmethod
    def convert_tools(tools: list[dict]) -> list[dict]:
        """Convert OpenAI function-calling tool format to Anthropic tool format.

        FROM: {"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}
          TO: {"name": ..., "description": ..., "input_schema": {...}}
        """
        result: list[dict] = []
        for tool in tools:
            if "function" in tool:
                func = tool["function"]
                result.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
                })
            else:
                result.append({
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("parameters") or tool.get("input_schema", {"type": "object", "properties": {}}),
                })
        return result

    @staticmethod
    def looks_like_own_blocks(items: list) -> bool:
        """Check if _raw_output_items contains Anthropic-style content blocks."""
        if not items:
            return False
        for item in items:
            if isinstance(item, dict):
                t = item.get("type", "")
                if t in ("thinking", "tool_use") or (t == "text" and "text" in item):
                    return True
            elif hasattr(item, "type"):
                t = getattr(item, "type", "")
                if t in ("thinking", "text", "tool_use"):
                    return True
        return False

    @staticmethod
    def convert_messages(
        messages: list[dict],
    ) -> tuple[str | None, list[dict]]:
        """Convert internal message format to Anthropic messages.

        Returns (system_prompt, anthropic_messages).
        System messages are extracted as the system param.
        Tool messages become tool_result blocks inside user messages.
        """
        system_prompt: str | None = None
        anthropic_messages: list[dict] = []

        for msg in messages:
            role = msg.get("role")

            if role == "system":
                system_prompt = msg.get("content")

            elif role == "user":
                anthropic_messages.append({"role": "user", "content": msg.get("content", "")})

            elif role == "assistant":
                raw_items = msg.get("_raw_output_items")
                if raw_items and AnthropicProvider.looks_like_own_blocks(raw_items):
                    anthropic_messages.append({"role": "assistant", "content": raw_items})
                elif msg.get("content"):
                    anthropic_messages.append({"role": "assistant", "content": msg["content"]})

            elif role == "tool":
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": msg.get("content", ""),
                }
                if (anthropic_messages
                        and anthropic_messages[-1]["role"] == "user"
                        and isinstance(anthropic_messages[-1]["content"], list)):
                    anthropic_messages[-1]["content"].append(tool_result)
                else:
                    anthropic_messages.append({"role": "user", "content": [tool_result]})

        return system_prompt, anthropic_messages

    @staticmethod
    def normalize_response(response: Any) -> LLMResponse:
        """Convert an Anthropic Messages API response into the normalized LLMResponse."""
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        function=FunctionCall(
                            name=block.name,
                            arguments=json.dumps(block.input),
                        ),
                    )
                )

        content = "\n".join(text_parts) if text_parts else None

        _ANTHROPIC_OUTPUT_ONLY_FIELDS = {"parsed_output"}
        raw_items: list[dict] = []
        for block in response.content:
            try:
                d = json.loads(block.model_dump_json())
                for key in _ANTHROPIC_OUTPUT_ONLY_FIELDS:
                    d.pop(key, None)
                raw_items.append(d)
            except Exception:
                raw_items.append({"type": block.type})

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
    def _build_kwargs(
        model: str,
        messages: list[dict],
        tools: list[dict],
        system_prompt: str | None,
        tool_choice: str,
    ) -> dict[str, Any]:
        """Build shared kwargs for both call and stream."""
        from app.dependencies import get_settings
        settings = get_settings()

        budget = settings.ANTHROPIC_THINKING_BUDGET
        effort = settings.ANTHROPIC_EFFORT

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max(budget + 8192, 16384),
            "messages": messages,
            "thinking": {"type": "enabled", "budget_tokens": budget},
            "extra_headers": {
                "anthropic-beta": "interleaved-thinking-2025-05-14,effort-2025-11-24"
            },
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = tools
        if effort != "high":
            kwargs["output_config"] = {"effort": effort}
        if tool_choice != "auto" and tool_choice != "none":
            kwargs["tool_choice"] = {"type": tool_choice}
        elif tool_choice == "none":
            kwargs["tool_choice"] = {"type": "none"}

        return kwargs

    @staticmethod
    def _wrap_error(exc: Exception) -> Exception:
        """Wrap Anthropic SDK exceptions into the unified error hierarchy."""
        try:
            import anthropic
        except ImportError:
            return exc

        if isinstance(exc, anthropic.RateLimitError):
            return LLMRateLimitError(str(exc))
        if isinstance(exc, anthropic.APIConnectionError):
            return LLMConnectionError(str(exc))
        if isinstance(exc, anthropic.APITimeoutError):
            return LLMTimeoutError(str(exc))
        if isinstance(exc, anthropic.APIStatusError):
            return LLMAPIError(str(exc))
        return exc
