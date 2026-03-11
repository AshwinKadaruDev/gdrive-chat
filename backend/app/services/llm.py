import json
import logging
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

        if anthropic_api_key:
            import anthropic

            self._anthropic_client = anthropic.AsyncAnthropic(
                api_key=anthropic_api_key
            )

        if openai_api_key:
            from openai import AsyncOpenAI

            self._openai_client = AsyncOpenAI(api_key=openai_api_key)

    def _is_anthropic_model(self, model: str) -> bool:
        """Determine if the model string refers to an Anthropic model."""
        return "claude" in model.lower()

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
        if self._is_anthropic_model(model) and self._anthropic_client:
            return await self._call_anthropic(
                messages, tools, model, tool_choice, temperature
            )
        elif self._openai_client:
            return await self._call_openai(
                messages, tools, model, tool_choice, temperature
            )
        else:
            raise ValueError(
                "No LLM client available. Provide at least one API key."
            )

    async def complete(self, prompt: str, max_tokens: int = 500) -> str:
        """Simple text completion without tool use."""
        if self._anthropic_client:
            response = await self._anthropic_client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        elif self._openai_client:
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
    # Anthropic
    # ------------------------------------------------------------------ #

    async def _call_anthropic(
        self,
        messages: list,
        tools: list,
        model: str,
        tool_choice: str,
        temperature: float,
    ) -> LLMResponse:
        """Call Anthropic's Messages API with tool use."""
        # Convert OpenAI-style tool defs to Anthropic format
        anthropic_tools = self._convert_tools_to_anthropic(tools)

        # Separate system message and convert conversation messages
        system_prompt: str | None = None
        conversation = self._convert_messages_to_anthropic(messages)

        # Extract system prompt from converted messages
        filtered: list[dict] = []
        for msg in conversation:
            if msg.get("role") == "system":
                system_prompt = msg["content"]
            else:
                filtered.append(msg)
        conversation = filtered

        # Build the Anthropic tool_choice parameter
        if tool_choice == "auto":
            anthropic_tool_choice: dict[str, str] = {"type": "auto"}
        elif tool_choice == "none":
            anthropic_tool_choice = {"type": "none"}  # not officially supported, but safe
        elif tool_choice == "required":
            anthropic_tool_choice = {"type": "any"}
        else:
            anthropic_tool_choice = {"type": "tool", "name": tool_choice}

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": conversation,
            "tools": anthropic_tools,
            "tool_choice": anthropic_tool_choice,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = await self._anthropic_client.messages.create(**kwargs)
        return self._normalize_anthropic_response(response)

    @staticmethod
    def _convert_messages_to_anthropic(messages: list[dict]) -> list[dict]:
        """
        Convert OpenAI-style messages to Anthropic format.

        Key differences:
        - System messages are kept as-is (extracted later).
        - Assistant messages with ``tool_calls`` become content blocks with
          ``tool_use`` entries.
        - ``role: "tool"`` messages become ``role: "user"`` with
          ``tool_result`` content blocks.  Consecutive tool results are
          merged into a single user message.
        """
        result: list[dict] = []

        for msg in messages:
            role = msg.get("role")

            if role == "system":
                result.append(msg)

            elif role == "assistant":
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    content_blocks: list[dict] = []
                    # Include text if present
                    if msg.get("content"):
                        content_blocks.append(
                            {"type": "text", "text": msg["content"]}
                        )
                    # Convert each tool_call to a tool_use block
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        arguments = func.get("arguments", "{}")
                        try:
                            input_data = json.loads(arguments)
                        except (json.JSONDecodeError, TypeError):
                            input_data = {}
                        content_blocks.append(
                            {
                                "type": "tool_use",
                                "id": tc["id"],
                                "name": func.get("name", ""),
                                "input": input_data,
                            }
                        )
                    result.append({"role": "assistant", "content": content_blocks})
                else:
                    # Plain text assistant message
                    result.append({"role": "assistant", "content": msg.get("content", "")})

            elif role == "tool":
                # Convert to user message with tool_result content block
                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": msg.get("content", ""),
                }
                # Merge with previous user message if it also contains tool_results
                if (
                    result
                    and result[-1].get("role") == "user"
                    and isinstance(result[-1].get("content"), list)
                    and result[-1]["content"]
                    and result[-1]["content"][0].get("type") == "tool_result"
                ):
                    result[-1]["content"].append(tool_result_block)
                else:
                    result.append({"role": "user", "content": [tool_result_block]})

            elif role == "user":
                result.append({"role": "user", "content": msg.get("content", "")})

            else:
                # Unknown role -- pass through
                result.append(msg)

        return result

    @staticmethod
    def _convert_tools_to_anthropic(tools: list[dict]) -> list[dict]:
        """Convert OpenAI-style function definitions to Anthropic tool format."""
        anthropic_tools: list[dict] = []
        for tool in tools:
            func = tool.get("function", tool)
            anthropic_tools.append(
                {
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {}),
                }
            )
        return anthropic_tools

    @staticmethod
    def _normalize_anthropic_response(response: Any) -> LLMResponse:
        """Convert an Anthropic response into the normalized LLMResponse."""
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

        return LLMResponse(
            choices=[
                Choice(
                    message=MessageContent(
                        content=content,
                        tool_calls=tool_calls,
                    )
                )
            ]
        )

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
        # If model was a Claude model but no Anthropic key, fall back to GPT-5.2
        if self._is_anthropic_model(model):
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

        response = await self._openai_client.responses.create(**kwargs)
        return self._normalize_openai_response(response)

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

        return LLMResponse(
            choices=[
                Choice(
                    message=MessageContent(
                        content=content,
                        tool_calls=tool_calls,
                        _raw_output_items=list(response.output),
                    )
                )
            ]
        )
