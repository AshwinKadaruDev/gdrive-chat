import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Normalized tool call representation."""

    id: str
    function: "FunctionCall"


@dataclass
class FunctionCall:
    """Normalized function call with name and JSON arguments."""

    name: str
    arguments: str  # JSON string


@dataclass
class MessageContent:
    """Normalized message from an LLM response."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    _raw_output_items: list = field(default_factory=list)  # Responses API only


@dataclass
class Choice:
    """Normalized choice wrapper."""

    message: MessageContent = field(default_factory=MessageContent)


@dataclass
class LLMResponse:
    """Normalized LLM response matching OpenAI-style structure."""

    choices: list[Choice] = field(default_factory=list)


@dataclass
class LLMStreamEvent:
    """Event yielded during streaming LLM calls."""

    type: str  # "text_delta" or "response_complete"
    text: str | None = None
    response: LLMResponse | None = None


class LLMClient:
    """
    Unified LLM client supporting both Anthropic (Claude) and OpenAI models.

    Normalizes responses so callers do not need to know which provider is used.
    """

    def __init__(
        self,
        anthropic_api_key: str | None = None,
        openai_api_key: str | None = None,
    ) -> None:
        self._anthropic_client: Any = None
        self._openai_client: Any = None

        # TODO: Re-enable Anthropic support
        # if anthropic_api_key:
        #     import anthropic
        #     self._anthropic_client = anthropic.AsyncAnthropic(
        #         api_key=anthropic_api_key
        #     )

        if openai_api_key:
            from openai import AsyncOpenAI

            self._openai_client = AsyncOpenAI(api_key=openai_api_key)
            logger.info("[LLM] OpenAI client initialized (openai SDK)")
        else:
            logger.warning("[LLM] No OpenAI API key provided — client not created")

    def _is_anthropic_model(self, model: str) -> bool:
        """Determine if the model string refers to an Anthropic model."""
        return False  # TODO: Re-enable — was: "claude" in model.lower()

    async def call_with_tools(
        self,
        messages: list,
        tools: list,
        model: str,
        tool_choice: str = "auto",
        temperature: float = 0.1,
    ) -> LLMResponse:
        """
        Call an LLM with tool definitions and return a normalized response.

        Prefers Anthropic if the model is a Claude model and the key is available.
        Falls back to OpenAI otherwise.
        """
        logger.info(
            "[LLM] call_with_tools: model=%s, tools=%d, messages=%d, tool_choice=%s",
            model, len(tools), len(messages), tool_choice,
        )
        # TODO: Re-enable Anthropic routing
        # if self._is_anthropic_model(model) and self._anthropic_client:
        #     return await self._call_anthropic(
        #         messages, tools, model, tool_choice, temperature
        #     )
        if self._openai_client:
            return await self._call_openai(
                messages, tools, model, tool_choice, temperature
            )
        else:
            raise ValueError(
                "No LLM client available. Provide at least one API key."
            )

    async def stream_call_with_tools(
        self,
        messages: list,
        tools: list,
        model: str,
        tool_choice: str = "auto",
        temperature: float = 0.1,
    ) -> AsyncGenerator[LLMStreamEvent, None]:
        """Stream an LLM call, yielding text deltas and a final response_complete event."""
        logger.info(
            "[LLM] stream_call_with_tools: model=%s, tools=%d, messages=%d",
            model, len(tools), len(messages),
        )
        if self._openai_client:
            async for event in self._stream_openai(
                messages, tools, model, tool_choice, temperature
            ):
                yield event
        else:
            raise ValueError(
                "No LLM client available. Provide at least one API key."
            )

    async def _stream_openai(
        self,
        messages: list,
        tools: list,
        model: str,
        tool_choice: str,
        temperature: float,
    ) -> AsyncGenerator[LLMStreamEvent, None]:
        """Stream from OpenAI Responses API, yielding text deltas and response_complete."""
        if "claude" in model.lower():
            logger.info("[LLM] Remapping Claude model %r → gpt-5.2", model)
            model = "gpt-5.2"

        instructions, input_items = self._convert_messages_to_responses_api(messages)
        responses_tools = self._convert_tools_to_responses_api(tools)

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
            async with await self._openai_client.responses.create(**kwargs) as stream:
                async for event in stream:
                    event_type = event.type

                    # Track if this response contains function calls
                    if event_type == "response.output_item.added":
                        if hasattr(event, "item") and getattr(event.item, "type", None) == "function_call":
                            has_function_calls = True

                    # Yield text deltas only when there are no function calls
                    # (i.e., this is the final answer, not intermediate reasoning)
                    elif event_type == "response.output_text.delta":
                        if not has_function_calls:
                            yield LLMStreamEvent(type="text_delta", text=event.delta)

                    # On completion, normalize and yield the full response
                    elif event_type == "response.completed":
                        result = self._normalize_openai_response(event.response)
                        logger.info(
                            "[LLM] Streaming response complete: content_length=%s, tool_calls=%d",
                            len(result.choices[0].message.content) if result.choices[0].message.content else 0,
                            len(result.choices[0].message.tool_calls),
                        )
                        yield LLMStreamEvent(type="response_complete", response=result)
        except Exception:
            logger.exception("[LLM] OpenAI Responses API streaming call failed")
            raise

    async def complete(self, prompt: str, max_tokens: int = 500) -> str:
        """Simple text completion without tool use."""
        # TODO: Re-enable Anthropic support
        # if self._anthropic_client:
        #     response = await self._anthropic_client.messages.create(
        #         model="claude-sonnet-4-5-20250929",
        #         max_tokens=max_tokens,
        #         messages=[{"role": "user", "content": prompt}],
        #     )
        #     return response.content[0].text
        if self._openai_client:
            response = await self._openai_client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content or ""
        else:
            raise ValueError(
                "No LLM client available. Provide at least one API key."
            )

    # ------------------------------------------------------------------ #
    # TODO: Re-enable Anthropic support
    # The following methods are commented out while Anthropic is disabled:
    # _call_anthropic, _convert_messages_to_anthropic,
    # _convert_tools_to_anthropic, _normalize_anthropic_response
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # OpenAI (Responses API)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _convert_tools_to_responses_api(tools: list[dict]) -> list[dict]:
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
    def _convert_messages_to_responses_api(
        messages: list[dict],
    ) -> tuple[str | None, list[dict]]:
        """Convert OpenAI-style messages to Responses API input format.

        Returns (instructions, input_items) where instructions is extracted
        from the system message and input_items is the list of input items.
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
                    # Preserve original output items (including reasoning)
                    input_items.extend(raw_items)
                else:
                    # Reconstruct from normalized fields
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

    async def _call_openai(
        self,
        messages: list,
        tools: list,
        model: str,
        tool_choice: str,
        temperature: float,
    ) -> LLMResponse:
        """Call OpenAI's Responses API with function calling."""
        # If model was a Claude model, fall back to GPT-5.2
        if "claude" in model.lower():
            logger.info("[LLM] Remapping Claude model %r → gpt-5.2", model)
            model = "gpt-5.2"

        instructions, input_items = self._convert_messages_to_responses_api(messages)
        responses_tools = self._convert_tools_to_responses_api(tools)

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
            response = await self._openai_client.responses.create(**kwargs)
        except Exception:
            logger.exception("[LLM] OpenAI Responses API call failed")
            raise
        result = self._normalize_openai_response(response)
        logger.info(
            "[LLM] OpenAI response: content_length=%s, tool_calls=%d",
            len(result.choices[0].message.content) if result.choices[0].message.content else 0,
            len(result.choices[0].message.tool_calls),
        )
        return result

    @staticmethod
    def _normalize_openai_response(response: Any) -> LLMResponse:
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
            # "reasoning" items: preserved in _raw_output_items only

        content = "\n".join(text_parts) if text_parts else None

        # Convert raw output items to plain dicts to avoid pydantic
        # serialization issues when passing them back as input on the
        # next iteration (openai SDK model_dump vs pydantic 2.9 compat).
        # Also strip output-only fields (like "status") that the API
        # rejects when sent back as input.
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
