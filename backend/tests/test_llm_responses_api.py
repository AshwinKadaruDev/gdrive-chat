"""Tests for the OpenAI Responses API migration in LLMClient."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm import (
    FunctionCall,
    LLMClient,
    MessageContent,
    ToolCall,
)


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


def _make_client() -> LLMClient:
    """Create an LLMClient with a mocked OpenAI client."""
    with patch("openai.AsyncOpenAI"):
        client = LLMClient(openai_api_key="test-key")
    return client


SAMPLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "hybrid_search",
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


class TestConvertToolsToResponsesAPI:
    def test_nested_to_flat(self):
        result = LLMClient._convert_tools_to_responses_api(SAMPLE_TOOLS)

        assert len(result) == 2
        assert result[0] == {
            "type": "function",
            "name": "hybrid_search",
            "description": "Search documents.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }
        assert result[1]["name"] == "get_file_content"
        assert "function" not in result[1]  # no nested function key


# ------------------------------------------------------------------ #
# Message conversion
# ------------------------------------------------------------------ #


class TestConvertMessagesToResponsesAPI:
    def test_system_extraction(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        instructions, items = LLMClient._convert_messages_to_responses_api(messages)

        assert instructions == "You are helpful."
        assert len(items) == 1
        assert items[0]["role"] == "user"

    def test_user_passthrough(self):
        messages = [{"role": "user", "content": "What is revenue?"}]
        instructions, items = LLMClient._convert_messages_to_responses_api(messages)

        assert instructions is None
        assert items == [{"role": "user", "content": "What is revenue?"}]

    def test_assistant_with_raw_items(self):
        raw = [
            {"type": "reasoning", "content": "thinking..."},
            {"type": "function_call", "call_id": "fc_1", "name": "search", "arguments": "{}"},
        ]
        messages = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "fc_1", "type": "function", "function": {"name": "search", "arguments": "{}"}}],
                "_raw_output_items": raw,
            }
        ]
        _, items = LLMClient._convert_messages_to_responses_api(messages)

        assert items == raw

    def test_assistant_without_raw_items_text_only(self):
        messages = [{"role": "assistant", "content": "Here is the answer."}]
        _, items = LLMClient._convert_messages_to_responses_api(messages)

        assert len(items) == 1
        assert items[0] == {
            "type": "message",
            "role": "assistant",
            "content": "Here is the answer.",
        }

    def test_assistant_without_raw_items_with_tool_calls(self):
        messages = [
            {
                "role": "assistant",
                "content": "Let me search.",
                "tool_calls": [
                    {
                        "id": "call_abc",
                        "type": "function",
                        "function": {"name": "hybrid_search", "arguments": '{"query": "revenue"}'},
                    }
                ],
            }
        ]
        _, items = LLMClient._convert_messages_to_responses_api(messages)

        assert len(items) == 2
        assert items[0] == {
            "type": "message",
            "role": "assistant",
            "content": "Let me search.",
        }
        assert items[1] == {
            "type": "function_call",
            "call_id": "call_abc",
            "name": "hybrid_search",
            "arguments": '{"query": "revenue"}',
        }

    def test_tool_result(self):
        messages = [
            {"role": "tool", "tool_call_id": "call_abc", "content": "Found 3 results."}
        ]
        _, items = LLMClient._convert_messages_to_responses_api(messages)

        assert items == [
            {"type": "function_call_output", "call_id": "call_abc", "output": "Found 3 results."}
        ]


# ------------------------------------------------------------------ #
# Response normalization
# ------------------------------------------------------------------ #


def _make_message_item(text: str) -> SimpleNamespace:
    """Create a mock Responses API message output item."""
    part = SimpleNamespace(type="output_text", text=text)
    return SimpleNamespace(type="message", content=[part])


def _make_function_call_item(call_id: str, name: str, arguments: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="function_call", call_id=call_id, name=name, arguments=arguments
    )


def _make_reasoning_item(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="reasoning", content=text)


class TestNormalizeOpenAIResponse:
    def test_text_only(self):
        response = SimpleNamespace(output=[_make_message_item("The answer is 42.")])
        result = LLMClient._normalize_openai_response(response)

        msg = result.choices[0].message
        assert msg.content == "The answer is 42."
        assert msg.tool_calls == []

    def test_function_calls(self):
        response = SimpleNamespace(
            output=[
                _make_function_call_item("fc_1", "hybrid_search", '{"query": "revenue"}'),
                _make_function_call_item("fc_2", "get_file_content", '{"file_id": "abc"}'),
            ]
        )
        result = LLMClient._normalize_openai_response(response)

        msg = result.choices[0].message
        assert msg.content is None
        assert len(msg.tool_calls) == 2
        assert msg.tool_calls[0].id == "fc_1"
        assert msg.tool_calls[0].function.name == "hybrid_search"
        assert msg.tool_calls[1].id == "fc_2"
        assert msg.tool_calls[1].function.arguments == '{"file_id": "abc"}'

    def test_preserves_raw_items_as_dicts(self):
        items = [
            _make_reasoning_item("Let me think..."),
            _make_message_item("Done."),
        ]
        response = SimpleNamespace(output=items)
        result = LLMClient._normalize_openai_response(response)

        # Raw items are serialized to dicts (not original Pydantic objects)
        # to avoid SDK serialization issues on multi-turn conversations.
        raw = result.choices[0].message._raw_output_items
        assert len(raw) == 2
        assert all(isinstance(r, dict) for r in raw)
        assert raw[0]["type"] == "reasoning"
        assert raw[1]["type"] == "message"

    def test_mixed_reasoning_and_calls(self):
        items = [
            _make_reasoning_item("Thinking..."),
            _make_function_call_item("fc_1", "search", '{"q": "x"}'),
            _make_message_item("I'll search for that."),
        ]
        response = SimpleNamespace(output=items)
        result = LLMClient._normalize_openai_response(response)

        msg = result.choices[0].message
        assert msg.content == "I'll search for that."
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].id == "fc_1"
        # All 3 items preserved in raw
        assert len(msg._raw_output_items) == 3


# ------------------------------------------------------------------ #
# _call_openai integration
# ------------------------------------------------------------------ #


class TestCallOpenAI:
    @pytest.mark.asyncio
    async def test_uses_responses_api(self):
        client = _make_client()

        mock_response = SimpleNamespace(
            output=[_make_message_item("Hello")]
        )
        client._openai_client.responses = MagicMock()
        client._openai_client.responses.create = AsyncMock(return_value=mock_response)

        result = await client._call_openai(
            messages=[
                {"role": "system", "content": "Be helpful."},
                {"role": "user", "content": "Hi"},
            ],
            tools=SAMPLE_TOOLS,
            model="gpt-5.2",
            tool_choice="auto",
            temperature=0.1,
        )

        # Verify responses.create was called (not chat.completions.create)
        client._openai_client.responses.create.assert_awaited_once()
        call_kwargs = client._openai_client.responses.create.call_args[1]

        assert call_kwargs["model"] == "gpt-5.2"
        assert call_kwargs["instructions"] == "Be helpful."
        assert call_kwargs["reasoning"] == {"effort": "xhigh"}
        assert len(call_kwargs["tools"]) == 2
        assert call_kwargs["tools"][0]["name"] == "hybrid_search"
        # tool_choice should NOT be passed when "auto" (default)
        assert "tool_choice" not in call_kwargs

        assert result.choices[0].message.content == "Hello"

    @pytest.mark.asyncio
    async def test_claude_fallback_model(self):
        client = _make_client()

        mock_response = SimpleNamespace(
            output=[_make_message_item("Response")]
        )
        client._openai_client.responses = MagicMock()
        client._openai_client.responses.create = AsyncMock(return_value=mock_response)

        await client._call_openai(
            messages=[{"role": "user", "content": "test"}],
            tools=[],
            model="claude-sonnet-4-5-20250929",
            tool_choice="auto",
            temperature=0.1,
        )

        call_kwargs = client._openai_client.responses.create.call_args[1]
        assert call_kwargs["model"] == "gpt-5.2"
