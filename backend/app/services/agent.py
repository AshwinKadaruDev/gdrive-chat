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

from app.services.agent_tools import ALL_TOOL_DEFINITIONS
from app.services.tool_executor import Citation, execute_tool

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """The final output of the agent's reasoning loop."""

    content: str
    citations: list[Citation] = field(default_factory=list)
    iterations: int = 0
    hit_limit: bool = False


SYSTEM_PROMPT = """\
You are an expert research assistant with access to a project folder containing \
documents, spreadsheets, and other files. Your job is to answer the user's question \
accurately and thoroughly using ONLY the information available in the project files.

IMPORTANT RULES:
1. ALWAYS search before answering. Never guess or use prior knowledge.
2. If you cannot find the answer after thorough searching, use report_inability to explain what you tried.
3. If the question is ambiguous, use request_clarification to ask for more details.
4. For spreadsheet questions, first use get_spreadsheet_overview, then targeted tools.
5. For document questions, first try hybrid_search, then read specific pages if needed.
6. Be precise and quote relevant text when appropriate.
7. If you find partial information, say so explicitly rather than making up the rest.

RESPONSE FORMAT:
- Write your final answer in **Markdown** (headings, bold, bullets, tables, etc.).
- Cite sources using numbered superscripts like [1], [2], etc. in your text.
- Each number corresponds to a source you found. The system will attach the source \
details automatically — just use the numbers inline where relevant.
- Example: "Revenue grew 15% year-over-year [1], driven primarily by the APAC region [2]."
- Place citations right after the specific claim they support, not at the end of a paragraph.

You have access to the following tools to search and read the project files. \
Use them strategically to find the best answer.\
"""

DRIVE_SYSTEM_PROMPT = """\
You are an expert research assistant with access to a Google Drive folder. \
Your job is to answer the user's question accurately using ONLY the files in \
the folder. Files are accessed live via the Google Drive API — there is no \
pre-built search index.

IMPORTANT RULES:
1. ALWAYS search before answering. Never guess or use prior knowledge.
2. Use search_drive as your primary search tool to find relevant files by keyword.
3. After finding files, use get_file_content to read their full text, or \
search_within_file_text for targeted lookups within a specific file.
4. If search_drive returns no results, try get_folder_structure to see all \
available files, then read promising ones directly.
5. If you cannot find the answer after thorough searching, use report_inability.
6. If the question is ambiguous, use request_clarification.
7. Be precise and quote relevant text when appropriate.
8. For spreadsheet questions, use get_spreadsheet_overview first.

RESPONSE FORMAT:
- Write your final answer in **Markdown** (headings, bold, bullets, tables, etc.).
- Cite sources using numbered superscripts like [1], [2], etc. in your text.
- Each number corresponds to a source you found. The system will attach the source \
details automatically — just use the numbers inline where relevant.
- Example: "Revenue grew 15% year-over-year [1], driven primarily by the APAC region [2]."
- Place citations right after the specific claim they support, not at the end of a paragraph.

Note: search_drive uses Google Drive keyword search (fullText contains), \
not semantic search. Use specific, targeted keywords for best results. \
If one query doesn't work, try alternative terms.\
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
        search_service: "AzureSearchService | None" = None,
        embeddings_service: "EmbeddingsService | None" = None,
        model: str = "claude-sonnet-4-5-20250929",
        max_iterations: int = 15,
        tools: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.search_service = search_service
        self.embeddings_service = embeddings_service
        self.drive_service = drive_service
        self.model = model
        self.max_iterations = max_iterations
        self.tools = tools if tools is not None else ALL_TOOL_DEFINITIONS
        self.system_prompt = system_prompt if system_prompt is not None else SYSTEM_PROMPT

    async def answer(
        self,
        question: str,
        project_id: str,
        user_access_token: str,
        chat_history: list[dict] | None = None,
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
            logger.info("Agent iteration %d/%d", iteration, self.max_iterations)

            # Call LLM with tools
            response = await self.llm_client.call_with_tools(
                messages=messages,
                tools=self.tools,
                model=self.model,
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
                    tool_args = {}

                logger.info("Executing tool: %s(%s)", tool_name, tool_args)

                result_str, citations = await execute_tool(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    project_id=project_id,
                    access_token=user_access_token,
                    search_service=self.search_service,
                    drive_service=self.drive_service,
                    embeddings_service=self.embeddings_service,
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
    ) -> AsyncGenerator[tuple[str, Any], None]:
        """
        Run the ReAct loop, yielding SSE-style events.

        Yields tuples of ``(event_type, data)``:
        - ``("status", "Searching files...")`` — progress updates during tool use
        - ``("delta", "chunk of text")`` — streamed final answer tokens
        - ``("citations", [...])`` — citation data
        - ``("done", None)`` — signals completion
        """
        messages: list[dict] = [{"role": "system", "content": self.system_prompt}]
        if chat_history:
            for msg in chat_history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": question})

        all_citations: list[Citation] = []

        _TOOL_STATUS = {
            "search_drive": "Searching files...",
            "hybrid_search": "Searching documents...",
            "get_file_content": "Reading file...",
            "get_folder_structure": "Scanning folder...",
            "get_file_metadata": "Getting file info...",
            "read_document_pages": "Reading pages...",
            "search_within_file": "Searching in document...",
            "search_within_file_text": "Searching in file...",
            "get_spreadsheet_overview": "Reading spreadsheet...",
            "read_spreadsheet_rows": "Reading rows...",
            "search_spreadsheet": "Searching spreadsheet...",
            "get_column_stats": "Computing stats...",
            "read_chunk_context": "Reading context...",
            "get_document_outline": "Reading outline...",
        }

        for iteration in range(1, self.max_iterations + 1):
            logger.info("Agent iteration %d/%d (streaming)", iteration, self.max_iterations)

            response = await self.llm_client.call_with_tools(
                messages=messages,
                tools=self.tools,
                model=self.model,
            )

            choice = response.choices[0]
            assistant_message = choice.message

            if assistant_message.content:
                messages.append({"role": "assistant", "content": assistant_message.content})

            # Final answer — no tool calls
            if not assistant_message.tool_calls:
                final_text = assistant_message.content or ""
                # Stream the final text in word-sized chunks
                words = final_text.split(" ")
                for i, word in enumerate(words):
                    chunk = word if i == len(words) - 1 else word + " "
                    yield ("delta", chunk)

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
                    tool_args = {}

                yield ("status", _TOOL_STATUS.get(tool_name, f"Using {tool_name}..."))

                result_str, citations = await execute_tool(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    project_id=project_id,
                    access_token=user_access_token,
                    search_service=self.search_service,
                    drive_service=self.drive_service,
                    embeddings_service=self.embeddings_service,
                )
                all_citations.extend(citations)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

        # Hit max iterations
        yield ("delta", "I reached my maximum number of reasoning steps. The answer may be incomplete.")
        yield ("citations", [])
        yield ("done", None)

    # ------------------------------------------------------------------ #
    # Non-streaming answer (original method) — max iterations fallback
    # ------------------------------------------------------------------ #
