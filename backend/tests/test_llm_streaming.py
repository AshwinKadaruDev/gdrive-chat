"""Tests for LLM streaming — text deltas, tool-call suppression, response_complete, errors."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm import LLMClient, LLMStreamEvent


def _make_event(event_type: str, **kwargs):
    """Build a SimpleNamespace mimicking an OpenAI streaming event."""
    return SimpleNamespace(type=event_type, **kwargs)


def _make_output_text_delta(delta: str):
    return _make_event("response.output_text.delta", delta=delta)


def _make_output_item_added(item_type: str = "message"):
    item = SimpleNamespace(type=item_type)
    return _make_event("response.output_item.added", item=item)


def _make_response_completed(output_items):
    """Build a response.completed event with given output items."""
    output = []
    for item in output_items:
        if item["type"] == "message":
            content_parts = [SimpleNamespace(text=item["text"])]
            output.append(SimpleNamespace(
                type="message",
                content=content_parts,
                model_dump_json=lambda: '{"type": "message"}',
            ))
        elif item["type"] == "function_call":
            fc = SimpleNamespace(
                type="function_call",
                call_id=item["call_id"],
                name=item["name"],
                arguments=item["arguments"],
                content=[],
                model_dump_json=lambda: '{"type": "function_call"}',
            )
            output.append(fc)

    response = SimpleNamespace(output=output)
    return _make_event("response.completed", response=response)


class TestStreamOpenAI:
    async def test_yields_text_delta_events(self):
        """Text deltas should be yielded when there are no function calls."""
        mock_openai = AsyncMock()

        async def fake_stream():
            yield _make_output_item_added("message")
            yield _make_output_text_delta("Hello ")
            yield _make_output_text_delta("world!")
            yield _make_response_completed([
                {"type": "message", "text": "Hello world!"}
            ])

        # Create an async context manager mock
        stream_cm = AsyncMock()
        stream_cm.__aenter__ = AsyncMock(return_value=fake_stream())
        stream_cm.__aexit__ = AsyncMock(return_value=False)
        mock_openai.responses.create = AsyncMock(return_value=stream_cm)

        client = LLMClient.__new__(LLMClient)
        client._openai_client = mock_openai

        events = []
        async for event in client._stream_openai(
            messages=[{"role": "user", "content": "Hi"}],
            tools=[],
            model="gpt-5.2",
            tool_choice="auto",
            temperature=0.1,
        ):
            events.append(event)

        text_deltas = [e for e in events if e.type == "text_delta"]
        assert len(text_deltas) == 2
        assert text_deltas[0].text == "Hello "
        assert text_deltas[1].text == "world!"

    async def test_suppresses_deltas_during_tool_calling(self):
        """Text deltas should be suppressed when function calls are present."""
        mock_openai = AsyncMock()

        async def fake_stream():
            yield _make_output_item_added("function_call")
            yield _make_output_text_delta("reasoning text")
            yield _make_response_completed([
                {"type": "function_call", "call_id": "c1",
                 "name": "search", "arguments": "{}"}
            ])

        stream_cm = AsyncMock()
        stream_cm.__aenter__ = AsyncMock(return_value=fake_stream())
        stream_cm.__aexit__ = AsyncMock(return_value=False)
        mock_openai.responses.create = AsyncMock(return_value=stream_cm)

        client = LLMClient.__new__(LLMClient)
        client._openai_client = mock_openai

        events = []
        async for event in client._stream_openai(
            messages=[{"role": "user", "content": "Hi"}],
            tools=[{"function": {"name": "search", "parameters": {}}}],
            model="gpt-5.2",
            tool_choice="auto",
            temperature=0.1,
        ):
            events.append(event)

        text_deltas = [e for e in events if e.type == "text_delta"]
        assert len(text_deltas) == 0

    async def test_yields_response_complete(self):
        """A response_complete event should be yielded at the end."""
        mock_openai = AsyncMock()

        async def fake_stream():
            yield _make_output_item_added("message")
            yield _make_response_completed([
                {"type": "message", "text": "Done."}
            ])

        stream_cm = AsyncMock()
        stream_cm.__aenter__ = AsyncMock(return_value=fake_stream())
        stream_cm.__aexit__ = AsyncMock(return_value=False)
        mock_openai.responses.create = AsyncMock(return_value=stream_cm)

        client = LLMClient.__new__(LLMClient)
        client._openai_client = mock_openai

        events = []
        async for event in client._stream_openai(
            messages=[{"role": "user", "content": "Hi"}],
            tools=[],
            model="gpt-5.2",
            tool_choice="auto",
            temperature=0.1,
        ):
            events.append(event)

        complete_events = [e for e in events if e.type == "response_complete"]
        assert len(complete_events) == 1
        assert complete_events[0].response is not None

    async def test_error_propagation(self):
        """Errors from the OpenAI API should propagate."""
        mock_openai = AsyncMock()

        async def failing_stream():
            raise RuntimeError("API error")
            yield  # pragma: no cover

        stream_cm = AsyncMock()
        stream_cm.__aenter__ = AsyncMock(return_value=failing_stream())
        stream_cm.__aexit__ = AsyncMock(return_value=False)
        mock_openai.responses.create = AsyncMock(return_value=stream_cm)

        client = LLMClient.__new__(LLMClient)
        client._openai_client = mock_openai

        with pytest.raises(RuntimeError, match="API error"):
            async for _ in client._stream_openai(
                messages=[{"role": "user", "content": "Hi"}],
                tools=[],
                model="gpt-5.2",
                tool_choice="auto",
                temperature=0.1,
            ):
                pass
