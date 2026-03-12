"""
FolderAgent: ReAct-loop agent that answers questions about a Google Drive folder.

Uses an LLM with tool-calling to iteratively search, read, and reason
over the project's indexed documents.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import httpx
import openai

from app.services.agent_tools import DRIVE_AGENT_TOOLS
from app.services.tool_executor import Citation, execute_tool

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """The final output of the agent's reasoning loop."""

    content: str
    citations: list[Citation] = field(default_factory=list)
    iterations: int = 0
    hit_limit: bool = False


DRIVE_SYSTEM_PROMPT = """\
You are an expert research assistant with access to a Google Drive folder. \
Your job is to answer the user's question accurately. Files are accessed live \
via the Google Drive API — there is no pre-built search index.

WHEN TO USE TOOLS vs. ANSWER DIRECTLY:
- If the user asks about specific facts, data, or content from the Drive files → \
browse and read the files before answering.
- If the answer is already in the conversation history (e.g. a follow-up about \
something you just found) → answer directly from context without searching again.
- If the user asks a general knowledge question → answer directly. No tools needed.
- When in doubt about whether information is in the files, look first.

RULES:
1. ALWAYS start with get_folder_structure to see what files exist. File names are \
usually descriptive enough to identify what you need.
2. Go directly to the files you need: for spreadsheets → get_spreadsheet_overview → \
read_spreadsheet_rows or search_spreadsheet; for documents → get_file_content or \
read_document_pages.
3. Use search_drive only when you cannot identify the right file from the folder \
structure (e.g. you need to search inside file content, not file names).
4. If you cannot find the answer after thorough searching, use report_inability.
5. If the question is ambiguous, use request_clarification.
6. Be precise and quote relevant text when appropriate.
7. If you find partial information, say so explicitly rather than making up the rest.

RESPONSE FORMAT:
- Write in clear Markdown. Use headings, bullets, or tables only when they help \
structure a complex answer — not for short replies.
- When citing Drive files, use numbered references like [1], [2] inline right \
after the claim they support. The system attaches source details automatically.
- Example: "Revenue grew 15% year-over-year [1], driven primarily by the APAC region [2]."
- For conversational or general-knowledge answers, write naturally without citations \
or heavy formatting.\
"""


class FolderAgent:
    """
    Agent that answers questions about a project folder using a ReAct loop.

    On each iteration the agent can call tools (search, read, etc.) and
    accumulates citations.  The loop terminates when the agent produces a
    final text response without tool calls, or when max_iterations is reached.
    """

    def __init__(
        self,
        llm_client: "LLMClient",
        drive_service: "GoogleDriveService",
        model: str | None = None,
        max_iterations: int = 15,
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> None:
        from app.dependencies import get_settings
        self.llm_client = llm_client
        self.drive_service = drive_service
        self.model = model or get_settings().AGENT_MODEL
        self.max_iterations = max_iterations
        self.tools = tools if tools is not None else DRIVE_AGENT_TOOLS
        self.system_prompt = system_prompt if system_prompt is not None else DRIVE_SYSTEM_PROMPT
        self.tool_cache: dict = {}

    async def answer(
        self,
        question: str,
        project_id: str,
        user_access_token: str,
        chat_history: list[dict] | None = None,
        session_id: str | None = None,
    ) -> AgentResponse:
        """
        Run the ReAct loop to answer a user question.

        Parameters
        ----------
        question:
            The user's question.
        project_id:
            The Google Drive folder ID / project identifier used for
            scoping searches and tool calls.
        user_access_token:
            OAuth access token for Google Drive API calls.
        chat_history:
            Prior messages in the conversation, each a dict with
            ``role`` and ``content`` keys.

        Returns
        -------
        AgentResponse
            The agent's answer, citations, iteration count, and whether
            the iteration limit was reached.
        """
        # Build the message list
        messages: list[dict] = [{"role": "system", "content": self.system_prompt}]

        # Append chat history
        if chat_history:
            for msg in chat_history:
                messages.append(
                    {"role": msg["role"], "content": msg["content"]}
                )

        # Append the current question
        messages.append({"role": "user", "content": question})

        all_citations: list[Citation] = []

        for iteration in range(1, self.max_iterations + 1):
            logger.info("Agent iteration %d/%d (session=%s)", iteration, self.max_iterations, session_id)

            # Call LLM with tools
            try:
                response = await self.llm_client.call_with_tools(
                    messages=messages,
                    tools=self.tools,
                    model=self.model,
                )
            except (openai.RateLimitError, openai.APIStatusError, openai.APIConnectionError, openai.APITimeoutError, httpx.HTTPError) as exc:
                logger.error("LLM call failed on iteration %d: %s: %s", iteration, type(exc).__name__, exc, exc_info=True)
                return AgentResponse(
                    content=(
                        "I'm sorry, something went wrong while processing your request. "
                        "Please try again."
                    ),
                    citations=all_citations,
                    iterations=iteration,
                    hit_limit=False,
                )

            choice = response.choices[0]
            assistant_message = choice.message

            # If the model returned text content, add it to messages
            if assistant_message.content:
                messages.append(
                    {"role": "assistant", "content": assistant_message.content}
                )

            # If there are no tool calls, we have the final answer
            if not assistant_message.tool_calls:
                return AgentResponse(
                    content=assistant_message.content or "",
                    citations=all_citations,
                    iterations=iteration,
                    hit_limit=False,
                )

            # Process each tool call
            # If there's text + tool calls, replace the last message with
            # a combined assistant message for providers that need it
            if assistant_message.content and assistant_message.tool_calls:
                # Remove the text-only message we just appended
                messages.pop()

            # Add assistant message indicating tool calls
            tool_call_records = []
            for tc in assistant_message.tool_calls:
                tool_call_records.append(
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": tool_call_records,
                    "_raw_output_items": assistant_message._raw_output_items,
                }
            )

            # Execute each tool and collect results
            for tc in assistant_message.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    logger.warning("Malformed JSON in tool args for %s: %s", tool_name, tc.function.arguments)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": f"Invalid JSON in tool arguments: {tc.function.arguments}. Please provide valid JSON.",
                        }
                    )
                    continue

                logger.info("Executing tool: %s(%s)", tool_name, tool_args)

                result_str, citations = await execute_tool(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    project_id=project_id,
                    access_token=user_access_token,
                    drive_service=self.drive_service,
                    tool_cache=self.tool_cache,
                )

                all_citations.extend(citations)

                # Add tool result to messages
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    }
                )

        # Reached max iterations without a final answer
        logger.warning(
            "Agent hit max iterations (%d) without final answer.",
            self.max_iterations,
        )
        last_content = ""
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                last_content = msg["content"]
                break
        warning = (
            "\n\n**Note:** I reached my maximum number of reasoning steps. "
            "The answer above may be incomplete. Please try rephrasing your "
            "question or breaking it into smaller parts."
        )
        return AgentResponse(
            content=(last_content + warning) if last_content else (
                "I was unable to formulate a complete answer within the allowed "
                "number of reasoning steps. Please try rephrasing your question."
            ),
            citations=all_citations,
            iterations=self.max_iterations,
            hit_limit=True,
        )

    async def answer_streaming(
        self,
        question: str,
        project_id: str,
        user_access_token: str,
        chat_history: list[dict] | None = None,
        session_id: str | None = None,
    ) -> AsyncGenerator[tuple[str, Any], None]:
        """
        Run the ReAct loop, yielding SSE-style events.

        Yields tuples of ``(event_type, data)``:
        - ``("status", "Searching files...")`` — progress updates during tool use
        - ``("delta", "chunk of text")`` — streamed final answer tokens
        - ``("citations", [...])`` — citation data
        - ``("done", None)`` — signals completion
        """
        logger.info(
            "[AGENT-STREAM] Starting: model=%s, question=%r, folder=%s, session=%s, history=%d msgs",
            self.model, question[:80], project_id, session_id, len(chat_history) if chat_history else 0,
        )
        messages: list[dict] = [{"role": "system", "content": self.system_prompt}]
        if chat_history:
            for msg in chat_history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": question})

        all_citations: list[Citation] = []

        _TOOL_STATUS = {
            "search_drive": "Searching files...",
            "get_file_content": "Reading file...",
            "get_folder_structure": "Scanning folder...",
            "get_file_metadata": "Getting file info...",
            "read_document_pages": "Reading pages...",
            "search_within_file_text": "Searching in file...",
            "get_spreadsheet_overview": "Reading spreadsheet...",
            "read_spreadsheet_rows": "Reading rows...",
            "search_spreadsheet": "Searching spreadsheet...",
            "get_column_stats": "Computing stats...",
        }

        for iteration in range(1, self.max_iterations + 1):
            logger.info("Agent iteration %d/%d (streaming)", iteration, self.max_iterations)

            # Stream the LLM call — yields text deltas (for final answers) and a response_complete event
            llm_response = None
            try:
                async for event in self.llm_client.stream_call_with_tools(
                    messages=messages,
                    tools=self.tools,
                    model=self.model,
                ):
                    if event.type == "text_delta" and event.text:
                        yield ("delta", event.text)
                    elif event.type == "response_complete":
                        llm_response = event.response
            except (openai.RateLimitError, openai.APIStatusError, openai.APIConnectionError, openai.APITimeoutError, httpx.HTTPError) as exc:
                logger.error("[AGENT-STREAM] LLM call failed on iteration %d: %s: %s", iteration, type(exc).__name__, exc, exc_info=True)
                yield ("delta", "I'm sorry, something went wrong while processing your request. Please try again.")
                # Deduplicate and serialize citations collected so far
                seen: set[tuple[str, str | None]] = set()
                unique_citations: list[Citation] = []
                for c in all_citations:
                    key = (c.file_id, c.location)
                    if key not in seen:
                        seen.add(key)
                        unique_citations.append(c)
                yield ("citations", [
                    {
                        "chunk_id": c.chunk_id, "file_id": c.file_id,
                        "file_name": c.file_name, "source_url": c.source_url,
                        "location": c.location, "snippet": c.snippet,
                    }
                    for c in unique_citations
                ])
                yield ("done", None)
                return

            if llm_response is None:
                logger.error("[AGENT-STREAM] No response_complete event received")
                yield ("delta", "An error occurred while processing your request.")
                yield ("citations", [])
                yield ("done", None)
                return

            choice = llm_response.choices[0]
            assistant_message = choice.message

            logger.info(
                "[AGENT-STREAM] Iteration %d result: content_length=%s, tool_calls=%d",
                iteration,
                len(assistant_message.content) if assistant_message.content else 0,
                len(assistant_message.tool_calls),
            )

            if assistant_message.content:
                messages.append({"role": "assistant", "content": assistant_message.content})

            # Final answer — no tool calls (text was already streamed via deltas)
            if not assistant_message.tool_calls:
                logger.info(
                    "[AGENT-STREAM] Final answer: %d chars, %d citations",
                    len(assistant_message.content or ""), len(all_citations),
                )

                # Deduplicate citations by (file_id, location)
                seen: set[tuple[str, str | None]] = set()
                unique_citations: list[Citation] = []
                for c in all_citations:
                    key = (c.file_id, c.location)
                    if key not in seen:
                        seen.add(key)
                        unique_citations.append(c)

                yield ("citations", [
                    {
                        "chunk_id": c.chunk_id,
                        "file_id": c.file_id,
                        "file_name": c.file_name,
                        "source_url": c.source_url,
                        "location": c.location,
                        "snippet": c.snippet,
                    }
                    for c in unique_citations
                ])
                yield ("done", None)
                return

            # Tool calls — process them
            if assistant_message.content and assistant_message.tool_calls:
                messages.pop()

            tool_call_records = []
            for tc in assistant_message.tool_calls:
                tool_call_records.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })
            messages.append({
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": tool_call_records,
                "_raw_output_items": assistant_message._raw_output_items,
            })

            for tc in assistant_message.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    logger.warning("[AGENT-STREAM] Malformed JSON in tool args for %s: %s", tool_name, tc.function.arguments)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": f"Invalid JSON in tool arguments: {tc.function.arguments}. Please provide valid JSON.",
                    })
                    continue

                logger.info("[AGENT-STREAM] Calling tool: %s(%s)", tool_name, tool_args)
                yield ("status", _TOOL_STATUS.get(tool_name, f"Using {tool_name}..."))

                result_str, citations = await execute_tool(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    project_id=project_id,
                    access_token=user_access_token,
                    drive_service=self.drive_service,
                    tool_cache=self.tool_cache,
                )
                logger.info(
                    "[AGENT-STREAM] Tool %s returned: %d chars, %d citations",
                    tool_name, len(result_str), len(citations),
                )
                all_citations.extend(citations)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

        # Hit max iterations — still emit accumulated citations
        yield ("delta", "I reached my maximum number of reasoning steps. The answer may be incomplete.")
        seen_max: set[tuple[str, str | None]] = set()
        unique_max: list[Citation] = []
        for c in all_citations:
            key = (c.file_id, c.location)
            if key not in seen_max:
                seen_max.add(key)
                unique_max.append(c)
        yield ("citations", [
            {
                "chunk_id": c.chunk_id, "file_id": c.file_id,
                "file_name": c.file_name, "source_url": c.source_url,
                "location": c.location, "snippet": c.snippet,
            }
            for c in unique_max
        ])
        yield ("done", None)

    # ------------------------------------------------------------------ #
    # Non-streaming answer (original method) — max iterations fallback
    # ------------------------------------------------------------------ #
