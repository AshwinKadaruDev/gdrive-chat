"""Tests for the Anthropic provider — tool/message conversion, normalization, call, streaming."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm import (
    FunctionCall,
    LLMClient,
    LLMResponse,
    MessageContent,
    ToolCall,
)
from app.services.llm.anthropic_provider import AnthropicProvider


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


def _make_anthropic_client() -> LLMClient:
    """Create an LLMClient with a mock Anthropic client (no real SDK needed)."""
    with patch("openai.AsyncOpenAI"):
        client = LLMClient(openai_api_key="test-key")
    # Manually inject a mock Anthropic provider
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider._client = MagicMock()
    client._providers[AnthropicProvider] = provider
    return client


SAMPLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_drive",
            "description": "Search documents.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_content",
            "description": "Read file content.",
            "parameters": {
                "type": "object",
                "properties": {"file_id": {"type": "string"}},
            },
        },
    },
]


# ------------------------------------------------------------------ #
# Tool conversion
# ------------------------------------------------------------------ #


class TestConvertToolsToAnthropic:
    def test_nested_format_to_anthropic(self):
        result = AnthropicProvider.convert_tools(SAMPLE_TOOLS)

        assert len(result) == 2
        assert result[0] == {
            "name": "search_drive",
            "description": "Search documents.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }
        assert result[1]["name"] == "get_file_content"
        # No nested "function" key or "type" key
        assert "function" not in result[1]
        assert "type" not in result[1]

    def test_flat_format_passthrough(self):
        flat_tools = [
            {
                "name": "search_drive",
                "description": "Search.",
                "parameters": {
                    "type": "object",
                    "properties": {"q": {"type": "string"}},
                },
            }
        ]
        result = AnthropicProvider.convert_tools(flat_tools)

        assert result[0]["name"] == "search_drive"
        assert result[0]["input_schema"]["properties"]["q"]["type"] == "string"

    def test_empty_tools(self):
        assert AnthropicProvider.convert_tools([]) == []


# ------------------------------------------------------------------ #
# Message conversion
# ------------------------------------------------------------------ #


class TestConvertMessagesToAnthropic:
    def test_system_extraction(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        system, msgs = AnthropicProvider.convert_messages(messages)

        assert system == "You are helpful."
        assert len(msgs) == 1
        assert msgs[0] == {"role": "user", "content": "Hello"}

    def test_user_passthrough(self):
        messages = [{"role": "user", "content": "What is revenue?"}]
        system, msgs = AnthropicProvider.convert_messages(messages)

        assert system is None
        assert msgs == [{"role": "user", "content": "What is revenue?"}]

    def test_tool_results_as_user_message(self):
        messages = [
            {"role": "tool", "tool_call_id": "toolu_abc", "content": "Found 3 results."},
        ]
        _, msgs = AnthropicProvider.convert_messages(messages)

        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert isinstance(msgs[0]["content"], list)
        assert msgs[0]["content"][0] == {
            "type": "tool_result",
            "tool_use_id": "toolu_abc",
            "content": "Found 3 results.",
        }

    def test_consecutive_tool_results_merged(self):
        messages = [
            {"role": "tool", "tool_call_id": "toolu_1", "content": "Result 1"},
            {"role": "tool", "tool_call_id": "toolu_2", "content": "Result 2"},
        ]
        _, msgs = AnthropicProvider.convert_messages(messages)

        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert len(msgs[0]["content"]) == 2
        assert msgs[0]["content"][0]["tool_use_id"] == "toolu_1"
        assert msgs[0]["content"][1]["tool_use_id"] == "toolu_2"

    def test_assistant_with_anthropic_raw_blocks(self):
        raw_blocks = [
            {"type": "thinking", "thinking": "Let me think...", "signature": "abc"},
            {"type": "text", "text": "Here is my answer."},
        ]
        messages = [
            {
                "role": "assistant",
                "content": "Here is my answer.",
                "_raw_output_items": raw_blocks,
            }
        ]
        _, msgs = AnthropicProvider.convert_messages(messages)

        assert len(msgs) == 1
        assert msgs[0]["role"] == "assistant"
        assert msgs[0]["content"] == raw_blocks

    def test_assistant_with_openai_raw_blocks_falls_back_to_content(self):
        raw_blocks = [
            {"type": "reasoning", "content": "thinking..."},
            {"type": "function_call", "call_id": "fc_1", "name": "search", "arguments": "{}"},
        ]
        messages = [
            {
                "role": "assistant",
                "content": "Let me search.",
                "_raw_output_items": raw_blocks,
            }
        ]
        _, msgs = AnthropicProvider.convert_messages(messages)

        # OpenAI-style blocks should NOT be treated as Anthropic blocks
        assert len(msgs) == 1
        assert msgs[0]["role"] == "assistant"
        assert msgs[0]["content"] == "Let me search."


# ------------------------------------------------------------------ #
# looks_like_own_blocks
# ------------------------------------------------------------------ #


class TestLooksLikeAnthropicBlocks:
    def test_thinking_blocks(self):
        items = [{"type": "thinking", "thinking": "...", "signature": "abc"}]
        assert AnthropicProvider.looks_like_own_blocks(items) is True

    def test_text_blocks(self):
        items = [{"type": "text", "text": "Hello"}]
        assert AnthropicProvider.looks_like_own_blocks(items) is True

    def test_tool_use_blocks(self):
        items = [{"type": "tool_use", "id": "toolu_1", "name": "search", "input": {}}]
        assert AnthropicProvider.looks_like_own_blocks(items) is True

    def test_openai_blocks_not_anthropic(self):
        items = [{"type": "reasoning", "content": "thinking..."}]
        assert AnthropicProvider.looks_like_own_blocks(items) is False

    def test_function_call_blocks_not_anthropic(self):
        items = [{"type": "function_call", "call_id": "fc_1"}]
        assert AnthropicProvider.looks_like_own_blocks(items) is False

    def test_empty_list(self):
        assert AnthropicProvider.looks_like_own_blocks([]) is False


# ------------------------------------------------------------------ #
# Response normalization
# ------------------------------------------------------------------ #


def _make_anthropic_text_block(text: str) -> SimpleNamespace:
    ns = SimpleNamespace(type="text", text=text)
    ns.model_dump_json = lambda: json.dumps({"type": "text", "text": text})
    return ns


def _make_anthropic_tool_use_block(
    block_id: str, name: str, input_dict: dict
) -> SimpleNamespace:
    ns = SimpleNamespace(type="tool_use", id=block_id, name=name, input=input_dict)
    ns.model_dump_json = lambda: json.dumps(
        {"type": "tool_use", "id": block_id, "name": name, "input": input_dict}
    )
    return ns


def _make_anthropic_thinking_block(thinking: str) -> SimpleNamespace:
    ns = SimpleNamespace(type="thinking", thinking=thinking, signature="sig_abc")
    ns.model_dump_json = lambda: json.dumps(
        {"type": "thinking", "thinking": thinking, "signature": "sig_abc"}
    )
    return ns


class TestNormalizeAnthropicResponse:
    def test_text_only(self):
        response = SimpleNamespace(
            content=[_make_anthropic_text_block("The answer is 42.")]
        )
        result = AnthropicProvider.normalize_response(response)

        msg = result.choices[0].message
        assert msg.content == "The answer is 42."
        assert msg.tool_calls == []

    def test_tool_use(self):
        response = SimpleNamespace(
            content=[
                _make_anthropic_tool_use_block(
                    "toolu_abc", "search_drive", {"query": "revenue"}
                ),
            ]
        )
        result = AnthropicProvider.normalize_response(response)

        msg = result.choices[0].message
        assert msg.content is None
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].id == "toolu_abc"
        assert msg.tool_calls[0].function.name == "search_drive"
        # Arguments must be a JSON string (agent.py calls json.loads)
        assert msg.tool_calls[0].function.arguments == '{"query": "revenue"}'
        assert json.loads(msg.tool_calls[0].function.arguments) == {"query": "revenue"}

    def test_mixed_content(self):
        response = SimpleNamespace(
            content=[
                _make_anthropic_thinking_block("Let me think..."),
                _make_anthropic_text_block("I'll search for that."),
                _make_anthropic_tool_use_block("toolu_1", "search_drive", {"query": "q"}),
            ]
        )
        result = AnthropicProvider.normalize_response(response)

        msg = result.choices[0].message
        assert msg.content == "I'll search for that."
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].id == "toolu_1"
        # All 3 blocks preserved in raw items
        assert len(msg._raw_output_items) == 3
        assert msg._raw_output_items[0]["type"] == "thinking"
        assert msg._raw_output_items[1]["type"] == "text"
        assert msg._raw_output_items[2]["type"] == "tool_use"

    def test_parsed_output_stripped_from_raw_items(self):
        """parsed_output on text blocks must be stripped — the API rejects it as input."""

        def _make_text_block_with_parsed_output(text: str) -> SimpleNamespace:
            ns = SimpleNamespace(type="text", text=text)
            ns.model_dump_json = lambda: json.dumps(
                {"type": "text", "text": text, "parsed_output": None}
            )
            return ns

        response = SimpleNamespace(
            content=[
                _make_anthropic_thinking_block("thinking..."),
                _make_text_block_with_parsed_output("I'll search."),
                _make_anthropic_tool_use_block("toolu_1", "search_drive", {"query": "q"}),
            ]
        )
        result = AnthropicProvider.normalize_response(response)

        raw = result.choices[0].message._raw_output_items
        assert len(raw) == 3
        # Text block must NOT contain parsed_output
        text_block = raw[1]
        assert text_block["type"] == "text"
        assert text_block["text"] == "I'll search."
        assert "parsed_output" not in text_block

    def test_arguments_always_json_string(self):
        """Verify tool_use input (dict) is converted to JSON string for agent.py compat."""
        response = SimpleNamespace(
            content=[
                _make_anthropic_tool_use_block(
                    "toolu_x", "get_file_content", {"file_id": "abc123", "pages": [1, 2]}
                ),
            ]
        )
        result = AnthropicProvider.normalize_response(response)

        args_str = result.choices[0].message.tool_calls[0].function.arguments
        assert isinstance(args_str, str)
        parsed = json.loads(args_str)
        assert parsed == {"file_id": "abc123", "pages": [1, 2]}


# ------------------------------------------------------------------ #
# _call_anthropic integration (via provider)
# ------------------------------------------------------------------ #


class TestCallAnthropic:
    @pytest.mark.asyncio
    async def test_passes_correct_kwargs(self):
        client = _make_anthropic_client()
        provider = client._providers[AnthropicProvider]

        mock_response = SimpleNamespace(
            content=[_make_anthropic_text_block("Hello")],
            stop_reason="end_turn",
        )
        provider._client.messages = MagicMock()
        provider._client.messages.create = AsyncMock(return_value=mock_response)

        mock_settings = MagicMock()
        mock_settings.ANTHROPIC_THINKING_BUDGET = 10000
        mock_settings.ANTHROPIC_EFFORT = "high"

        with patch("app.dependencies.get_settings", return_value=mock_settings):
            result = await provider.call_with_tools(
                messages=[
                    {"role": "system", "content": "Be helpful."},
                    {"role": "user", "content": "Hi"},
                ],
                tools=SAMPLE_TOOLS,
                model="claude-opus-4-5-20251101",
                tool_choice="auto",
                temperature=0.1,
            )

        provider._client.messages.create.assert_awaited_once()
        call_kwargs = provider._client.messages.create.call_args[1]

        assert call_kwargs["model"] == "claude-opus-4-5-20251101"
        assert call_kwargs["system"] == "Be helpful."
        assert call_kwargs["thinking"] == {"type": "enabled", "budget_tokens": 10000}
        assert call_kwargs["max_tokens"] == 18192  # max(10000 + 8192, 16384)
        assert len(call_kwargs["tools"]) == 2
        assert call_kwargs["tools"][0]["name"] == "search_drive"
        assert "input_schema" in call_kwargs["tools"][0]
        # effort == "high" is default, so output_config should NOT be set
        assert "output_config" not in call_kwargs
        # tool_choice == "auto" should NOT be set
        assert "tool_choice" not in call_kwargs

        assert result.choices[0].message.content == "Hello"


# ------------------------------------------------------------------ #
# _stream_anthropic integration (via provider)
# ------------------------------------------------------------------ #


class TestStreamAnthropic:
    @pytest.mark.asyncio
    async def test_text_delta_suppression_during_tool_use(self):
        """When tool_use is detected, text deltas should not be yielded."""
        client = _make_anthropic_client()
        provider = client._providers[AnthropicProvider]

        # Build mock events
        tool_block_start = SimpleNamespace(
            type="content_block_start",
            content_block=SimpleNamespace(type="tool_use"),
        )
        text_delta = SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="text_delta", text="suppressed"),
        )
        final_msg = SimpleNamespace(
            content=[
                _make_anthropic_tool_use_block("toolu_1", "search_drive", {"query": "q"}),
            ],
            stop_reason="tool_use",
        )

        # Mock the stream context manager
        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        async def mock_aiter(self):
            yield tool_block_start
            yield text_delta

        mock_stream.__aiter__ = mock_aiter
        mock_stream.get_final_message = AsyncMock(return_value=final_msg)

        provider._client.messages = MagicMock()
        provider._client.messages.stream = MagicMock(return_value=mock_stream)

        mock_settings = MagicMock()
        mock_settings.ANTHROPIC_THINKING_BUDGET = 10000
        mock_settings.ANTHROPIC_EFFORT = "high"

        events = []
        with patch("app.dependencies.get_settings", return_value=mock_settings):
            async for event in provider.stream_call_with_tools(
                messages=[{"role": "user", "content": "test"}],
                tools=SAMPLE_TOOLS,
                model="claude-opus-4-5-20251101",
                tool_choice="auto",
                temperature=0.1,
            ):
                events.append(event)

        # Text deltas should be suppressed (tool use detected), only response_complete
        assert len(events) == 1
        assert events[0].type == "response_complete"
        assert events[0].response is not None
        assert len(events[0].response.choices[0].message.tool_calls) == 1

    @pytest.mark.asyncio
    async def test_text_deltas_yielded_without_tool_use(self):
        """When no tool_use, text deltas should be yielded normally."""
        client = _make_anthropic_client()
        provider = client._providers[AnthropicProvider]

        text_delta_1 = SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="text_delta", text="Hello "),
        )
        text_delta_2 = SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="text_delta", text="world"),
        )
        final_msg = SimpleNamespace(
            content=[_make_anthropic_text_block("Hello world")],
            stop_reason="end_turn",
        )

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        async def mock_aiter(self):
            yield text_delta_1
            yield text_delta_2

        mock_stream.__aiter__ = mock_aiter
        mock_stream.get_final_message = AsyncMock(return_value=final_msg)

        provider._client.messages = MagicMock()
        provider._client.messages.stream = MagicMock(return_value=mock_stream)

        mock_settings = MagicMock()
        mock_settings.ANTHROPIC_THINKING_BUDGET = 10000
        mock_settings.ANTHROPIC_EFFORT = "high"

        events = []
        with patch("app.dependencies.get_settings", return_value=mock_settings):
            async for event in provider.stream_call_with_tools(
                messages=[{"role": "user", "content": "test"}],
                tools=[],
                model="claude-opus-4-5-20251101",
                tool_choice="auto",
                temperature=0.1,
            ):
                events.append(event)

        # 2 text deltas + 1 response_complete
        assert len(events) == 3
        assert events[0].type == "text_delta"
        assert events[0].text == "Hello "
        assert events[1].type == "text_delta"
        assert events[1].text == "world"
        assert events[2].type == "response_complete"
