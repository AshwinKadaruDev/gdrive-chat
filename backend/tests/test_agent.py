"""Tests for FolderAgent ReAct loop — single iteration, multi-iteration,
max-iterations fallback, LLM error handling, and malformed JSON args."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.agent import AgentResponse, FolderAgent
from app.services.llm import (
    Choice,
    FunctionCall,
    LLMResponse,
    LLMStreamEvent,
    MessageContent,
    ToolCall,
)
from app.services.tool_executor import Citation


def _make_llm_response(
    content: str | None = None,
    tool_calls: list[ToolCall] | None = None,
) -> LLMResponse:
    """Build a minimal LLMResponse."""
    return LLMResponse(
        choices=[
            Choice(
                message=MessageContent(
                    content=content,
                    tool_calls=tool_calls or [],
                )
            )
        ]
    )


def _make_agent(llm_client=None, max_iterations=15):
    """Create a FolderAgent with a mock LLM client."""
    if llm_client is None:
        llm_client = AsyncMock()
    return FolderAgent(
        llm_client=llm_client,
        drive_service=AsyncMock(),
        max_iterations=max_iterations,
    )


class TestAnswerNonStreaming:
    async def test_single_iteration_no_tools(self):
        """Agent returns immediately when LLM gives text without tool calls."""
        llm = AsyncMock()
        llm.call_with_tools = AsyncMock(
            return_value=_make_llm_response(content="The answer is 42.")
        )
        agent = _make_agent(llm)

        result = await agent.answer("What is the answer?", "proj-1", "token-1", session_id="sess-1")

        assert isinstance(result, AgentResponse)
        assert result.content == "The answer is 42."
        assert result.iterations == 1
        assert not result.hit_limit
        assert result.citations == []

    async def test_multi_iteration_with_tools_and_citations(self):
        """Agent calls a tool, collects citations, then produces a final answer."""
        llm = AsyncMock()
        # Iteration 1: LLM calls a tool
        tool_response = _make_llm_response(
            content=None,
            tool_calls=[
                ToolCall(
                    id="tc-1",
                    function=FunctionCall(
                        name="search_drive",
                        arguments=json.dumps({"query": "revenue"}),
                    ),
                )
            ],
        )
        # Iteration 2: LLM gives final answer
        final_response = _make_llm_response(content="Revenue grew 15% [1].")
        llm.call_with_tools = AsyncMock(
            side_effect=[tool_response, final_response]
        )

        agent = _make_agent(llm)

        citation = Citation(
            chunk_id="c1", file_id="f1", file_name="report.pdf",
            source_url=None, location="Page 3", snippet="Revenue grew..."
        )

        with patch("app.services.agent.execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ("Search results...", [citation])
            result = await agent.answer("Revenue?", "proj-1", "token-1", session_id="sess-1")

        assert result.iterations == 2
        assert len(result.citations) == 1
        assert result.citations[0].file_name == "report.pdf"
        assert "Revenue grew 15%" in result.content

    async def test_max_iterations_fallback_includes_citations(self):
        """When max iterations is reached, synthesis is called and citations are preserved."""
        llm = AsyncMock()
        # Iterations 1-2: always return tool calls — never a final answer
        tool_response = _make_llm_response(
            content="Thinking...",
            tool_calls=[
                ToolCall(
                    id="tc-1",
                    function=FunctionCall(
                        name="search_drive",
                        arguments=json.dumps({"query": "test"}),
                    ),
                )
            ],
        )
        # Synthesis call: returns text, no tools
        synthesis_response = _make_llm_response(content="Here is my synthesized answer.")
        llm.call_with_tools = AsyncMock(
            side_effect=[tool_response, tool_response, synthesis_response]
        )

        agent = _make_agent(llm, max_iterations=2)

        citation = Citation(
            chunk_id="c1", file_id="f1", file_name="doc.pdf",
            snippet="some text"
        )

        with patch("app.services.agent.execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ("result", [citation])
            result = await agent.answer("Q?", "proj-1", "token-1", session_id="sess-1")

        assert result.hit_limit
        assert result.iterations == 2
        assert len(result.citations) == 2  # one per iteration
        assert "synthesized answer" in result.content

    async def test_llm_error_returns_graceful_response(self):
        """When the LLM call raises, agent returns a graceful error message."""
        llm = AsyncMock()
        llm.call_with_tools = AsyncMock(side_effect=httpx.ConnectError("API down"))

        agent = _make_agent(llm)
        result = await agent.answer("Q?", "proj-1", "token-1", session_id="sess-1")

        assert "went wrong" in result.content
        assert result.iterations == 1

    async def test_malformed_json_args_sends_error_to_llm(self):
        """When tool args are invalid JSON, agent sends error message back to LLM."""
        llm = AsyncMock()
        # Iteration 1: bad JSON args
        bad_tool_response = _make_llm_response(
            content=None,
            tool_calls=[
                ToolCall(
                    id="tc-1",
                    function=FunctionCall(
                        name="search_drive",
                        arguments="{bad json",
                    ),
                )
            ],
        )
        # Iteration 2: final answer
        final_response = _make_llm_response(content="I fixed it.")
        llm.call_with_tools = AsyncMock(
            side_effect=[bad_tool_response, final_response]
        )

        agent = _make_agent(llm)
        # execute_tool should NOT be called for the bad JSON
        with patch("app.services.agent.execute_tool", new_callable=AsyncMock) as mock_exec:
            result = await agent.answer("Q?", "proj-1", "token-1", session_id="sess-1")
            mock_exec.assert_not_called()

        assert result.content == "I fixed it."
        assert result.iterations == 2


class TestAnswerStreaming:
    async def test_streaming_event_sequence(self):
        """Streaming should yield delta, citations, and done events."""
        llm = AsyncMock()

        async def fake_stream(**kwargs):
            yield LLMStreamEvent(type="text_delta", text="Hello ")
            yield LLMStreamEvent(type="text_delta", text="world!")
            yield LLMStreamEvent(
                type="response_complete",
                response=_make_llm_response(content="Hello world!"),
            )

        llm.stream_call_with_tools = fake_stream

        agent = _make_agent(llm)
        events = []
        async for event_type, data in agent.answer_streaming("Hi", "proj-1", "token-1", session_id="sess-1"):
            events.append((event_type, data))

        event_types = [e[0] for e in events]
        assert "delta" in event_types
        assert "citations" in event_types
        assert "done" in event_types
        # Done should be last
        assert event_types[-1] == "done"

    async def test_streaming_llm_error_yields_error_and_done(self):
        """When LLM streaming fails, should yield error delta, citations, done."""
        llm = AsyncMock()

        async def failing_stream(**kwargs):
            raise httpx.ConnectError("Stream failed")
            # Make it an async generator
            yield  # pragma: no cover

        llm.stream_call_with_tools = failing_stream

        agent = _make_agent(llm)
        events = []
        async for event_type, data in agent.answer_streaming("Hi", "proj-1", "token-1", session_id="sess-1"):
            events.append((event_type, data))

        event_types = [e[0] for e in events]
        assert "delta" in event_types
        assert "citations" in event_types
        assert "done" in event_types
        # Error message in delta
        delta_texts = [d for t, d in events if t == "delta"]
        assert any("went wrong" in str(d) for d in delta_texts)

    async def test_streaming_max_iterations_includes_citations(self):
        """When streaming hits max iterations, synthesis is streamed and citations are included."""
        llm = AsyncMock()

        call_count = 0

        async def stream_dispatch(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: tool call (iteration 1)
                yield LLMStreamEvent(
                    type="response_complete",
                    response=_make_llm_response(
                        content="Thinking...",
                        tool_calls=[
                            ToolCall(
                                id="tc-1",
                                function=FunctionCall(
                                    name="search_drive",
                                    arguments=json.dumps({"query": "test"}),
                                ),
                            )
                        ],
                    ),
                )
            else:
                # Second call: synthesis (no tools)
                yield LLMStreamEvent(type="text_delta", text="Synthesized answer.")
                yield LLMStreamEvent(
                    type="response_complete",
                    response=_make_llm_response(content="Synthesized answer."),
                )

        llm.stream_call_with_tools = stream_dispatch

        citation = Citation(
            chunk_id="c1", file_id="f1", file_name="doc.pdf", snippet="text"
        )

        agent = _make_agent(llm, max_iterations=1)
        events = []
        with patch("app.services.agent.execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ("result", [citation])
            async for event_type, data in agent.answer_streaming("Q?", "proj-1", "token-1", session_id="sess-1"):
                events.append((event_type, data))

        # Find citations event
        citation_events = [d for t, d in events if t == "citations"]
        assert len(citation_events) == 1
        assert len(citation_events[0]) > 0  # Should not be empty
        # Synthesis text was streamed
        delta_texts = [d for t, d in events if t == "delta"]
        assert any("Synthesized" in str(d) for d in delta_texts)


class TestForcedSynthesis:
    async def test_max_iterations_forces_synthesis(self):
        """When all iterations produce only tool calls, the forced synthesis call
        happens with tools=[] and produces the final answer."""
        llm = AsyncMock()
        # All normal iterations: tool calls only (no assistant text content)
        tool_response = _make_llm_response(
            content=None,
            tool_calls=[
                ToolCall(
                    id="tc-1",
                    function=FunctionCall(
                        name="get_folder_structure",
                        arguments=json.dumps({}),
                    ),
                )
            ],
        )
        synthesis_response = _make_llm_response(
            content="Based on my research, the answer is X."
        )
        llm.call_with_tools = AsyncMock(
            side_effect=[tool_response, tool_response, synthesis_response]
        )

        agent = _make_agent(llm, max_iterations=2)

        with patch("app.services.agent.execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = ("folder structure...", [])
            result = await agent.answer("Q?", "proj-1", "token-1", session_id="sess-1")

        assert result.hit_limit
        assert "Based on my research" in result.content
        # Verify the synthesis call was made with tools=[]
        synthesis_call = llm.call_with_tools.call_args_list[-1]
        assert synthesis_call.kwargs.get("tools") == [] or synthesis_call[1].get("tools") == []
