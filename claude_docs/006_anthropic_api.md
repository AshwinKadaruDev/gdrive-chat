# Anthropic Claude Opus 4.5 — Integration Reference for Talk-to-a-Folder

> Exhaustive reference for adding Anthropic as an LLM provider.
> Maps every concept directly to the existing OpenAI Responses API integration.
>
> **Model:** `claude-opus-4-5-20251101` · **API:** Messages API (`/v1/messages`) · **Thinking:** Extended (`budget_tokens`) · **Effort:** `output_config.effort`

---

## Table of Contents

1. [Model & Pricing](#1-model--pricing)
2. [API Surface — OpenAI vs Anthropic](#2-api-surface--openai-vs-anthropic)
3. [Authentication & Headers](#3-authentication--headers)
4. [Basic Request / Response](#4-basic-request--response)
5. [Extended Thinking (≈ OpenAI `reasoning`)](#5-extended-thinking--openai-reasoning)
6. [Effort Parameter](#6-effort-parameter)
7. [Tool Use (Function Calling)](#7-tool-use-function-calling)
8. [Controlling Tool Behavior](#8-controlling-tool-behavior)
9. [The Agentic Loop — Mapping to FolderAgent](#9-the-agentic-loop--mapping-to-folderagent)
10. [Multi-Turn Message Construction](#10-multi-turn-message-construction)
11. [Streaming](#11-streaming)
12. [Prompt Caching](#12-prompt-caching)
13. [Compaction & Context Editing](#13-compaction--context-editing)
14. [Handling Stop Reasons](#14-handling-stop-reasons)
15. [Error Handling](#15-error-handling)
16. [Python SDK vs Raw HTTP](#16-python-sdk-vs-raw-http)
17. [Tool Runner (Beta)](#17-tool-runner-beta)
18. [Environment Variables](#18-environment-variables)
19. [Implementation Plan](#19-implementation-plan)
20. [Key Gotchas](#20-key-gotchas)
21. [Quick Reference Cheat Sheet](#21-quick-reference-cheat-sheet)
22. [Upgrade Path — Opus 4.6](#22-upgrade-path--opus-46)
23. [Documentation Links](#23-documentation-links)

---

## 1. Model & Pricing

```
Model ID (full):     claude-opus-4-5-20251101
Alias:               claude-opus-4-5
Context window:      200,000 tokens
Max output:          64,000 tokens
Knowledge cutoff:    May 2025
Pricing:             $5 / $25 per million tokens (input / output)
Cache write:         $6.25 / MTok (1.25× input)
Cache read:          $0.50 / MTok (0.1× input)
Batch API:           50% discount on standard pricing
Release date:        November 24, 2025
```

Opus 4.5 is Anthropic's frontier model — state-of-the-art for coding (80.9% SWE-bench), agents, tool use, and computer use. It supports extended thinking, the effort parameter, interleaved thinking (beta), and full tool use with up to 12+ tools.

---

## 2. API Surface — OpenAI vs Anthropic

| Concept | OpenAI Responses API (current `llm.py`) | Anthropic Messages API (target) |
|---|---|---|
| Endpoint | `POST /v1/responses` | `POST /v1/messages` |
| Auth | `Authorization: Bearer <key>` | `x-api-key: <key>` + `anthropic-version: 2023-06-01` |
| State management | `previous_response_id` (server-side) | Stateless — send full `messages` array every call |
| System prompt | `instructions=` parameter | `system=` top-level parameter (string or content blocks) |
| Messages | `input=` (list of items) | `messages=` (alternating `user`/`assistant` roles) |
| Tool definitions | Flat format: `{type: "function", name, parameters}` | `tools=` array: `{name, description, input_schema}` |
| Tool call in response | `type: "function_call"` in output items | `type: "tool_use"` content blocks in `response.content` |
| Tool call ID | `call_id` on `function_call_output` | `tool_use_id` on `tool_result` (must match `id` from `tool_use` block) |
| Tool results | `type: "function_call_output"` items in `input` | `tool_result` blocks inside a `user` message |
| Tool result placement | Flat in `input_items` | Inside a `user` message, tool_result blocks first |
| Reasoning config | `reasoning: {"effort": "xhigh"}` | `thinking: {type: "enabled", budget_tokens: N}` + `output_config: {effort: "high"}` |
| Loop signal | No tool calls in output = done | `stop_reason: "end_turn"` = done; `"tool_use"` = execute tools |
| Streaming text event | `response.output_text.delta` | `content_block_delta` with `delta.type: "text_delta"` |
| Raw output preservation | `_raw_output_items` on `MessageContent` | Thinking blocks (`type: "thinking"`) with `signature` field |

---

## 3. Authentication & Headers

Every request requires these headers:

```
x-api-key: $ANTHROPIC_API_KEY
anthropic-version: 2023-06-01
content-type: application/json
```

**Beta features** require an additional header (combine with commas):

```
anthropic-beta: interleaved-thinking-2025-05-14,effort-2025-11-24
```

| Beta header | Feature |
|---|---|
| `interleaved-thinking-2025-05-14` | Thinking between tool calls (recommended for agents) |
| `effort-2025-11-24` | Effort parameter on Opus 4.5 |
| `advanced-tool-use-2025-11-20` | Tool search, programmatic tool calling, input_examples |

---

## 4. Basic Request / Response

### 4a. Simple completion (no tools)

```python
import anthropic

client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

response = await client.messages.create(
    model="claude-opus-4-5-20251101",
    max_tokens=16384,
    system="You are a helpful assistant.",
    messages=[
        {"role": "user", "content": "Hello, Claude"}
    ],
)
```

### 4b. Response structure

```json
{
  "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
  "type": "message",
  "role": "assistant",
  "content": [
    {"type": "text", "text": "Hello! Here is my answer..."}
  ],
  "model": "claude-opus-4-5-20251101",
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {
    "input_tokens": 2095,
    "output_tokens": 503
  }
}
```

**Key difference from OpenAI**: `content` is a flat array of content blocks. Each block has a `type` — `"text"`, `"tool_use"`, or `"thinking"`.

To extract the text reply:

```python
# SDK objects
text = "".join(b.text for b in response.content if b.type == "text")

# Raw dict
text = "".join(b["text"] for b in data["content"] if b["type"] == "text")
```

---

## 5. Extended Thinking (≈ OpenAI `reasoning`)

This is the equivalent of `reasoning: {"effort": "xhigh"}` in the OpenAI Responses API. When enabled, Claude performs internal chain-of-thought reasoning before responding.

### 5a. Enabling extended thinking

```python
response = await client.messages.create(
    model="claude-opus-4-5-20251101",
    max_tokens=16384,
    thinking={
        "type": "enabled",
        "budget_tokens": 10000,   # min 1024, target not strict limit
    },
    system="You are a helpful assistant.",
    messages=[{"role": "user", "content": "Analyze this data..."}],
    tools=[...],
)
```

### 5b. Key rules

- `budget_tokens` must be **less than** `max_tokens`.
- Minimum budget is **1,024 tokens**.
- Thinking tokens are billed as output tokens.
- Claude 4 models return **summarized** thinking — you're charged for full thinking, not the summary.
- The `signature` field contains encrypted full thinking; pass it back unmodified for multi-turn continuity.
- Start at 1024 and increase incrementally — diminishing returns above ~32K.
- You **cannot** prefill assistant messages (final assistant message with content) when thinking is enabled.
- You **cannot** set `temperature` to anything other than `1` when thinking is enabled.

### 5c. Response with thinking blocks

```json
{
  "content": [
    {
      "type": "thinking",
      "thinking": "Let me analyze this step by step...\n1. First...",
      "signature": "EqQBCgIYAhIM1gbcDa9GJwZA2b3h..."
    },
    {
      "type": "text",
      "text": "Based on my analysis, the answer is..."
    }
  ]
}
```

### 5d. Interleaved thinking (recommended for agents)

For the FolderAgent, enable interleaved thinking so Claude can reason between tool calls:

```python
response = await client.messages.create(
    model="claude-opus-4-5-20251101",
    max_tokens=16384,
    thinking={"type": "enabled", "budget_tokens": 10000},
    extra_headers={"anthropic-beta": "interleaved-thinking-2025-05-14,effort-2025-11-24"},
    system=DRIVE_SYSTEM_PROMPT,
    messages=messages,
    tools=anthropic_tools,
)
```

With interleaved thinking, a response might contain:

```
[thinking] → "I need to find the 401k policy..."
[tool_use] → get_folder_structure()
--- tool result returned ---
[thinking] → "I see HR_Policies.pdf, let me read that..."
[tool_use] → get_file_content(file_id="abc")
--- tool result returned ---
[thinking] → "The document says the match is 6%..."
[text]     → "According to HR Policies, the 401(k) match is 6%..."
```

With interleaved thinking, `budget_tokens` is the TOTAL across all thinking blocks in one assistant turn (can exceed `max_tokens`).

### 5e. Mapping to your codebase

In `services/llm.py`, you currently store `_raw_output_items` on `MessageContent` to preserve OpenAI reasoning blocks across turns. For Anthropic:

```python
# After receiving a response, store the full content blocks
message_content._raw_content_blocks = response.content  # includes thinking + text + tool_use

# On subsequent turns, reconstruct the assistant message from raw blocks
assistant_message = {
    "role": "assistant",
    "content": raw_content_blocks  # pass thinking blocks back as-is
}
```

**Opus 4.5 preserves thinking blocks from previous turns by default** — unlike earlier models that stripped them. The API automatically ignores thinking blocks from previous turns when calculating context usage, but needs them for reasoning continuity.

---

## 6. Effort Parameter

The effort parameter controls how many tokens Claude spends across the **entire** response — text, tool calls, and thinking. This is the closest analog to OpenAI's `reasoning.effort`.

### 6a. Configuration

For Opus 4.5, requires the beta header:

```python
response = await client.messages.create(
    model="claude-opus-4-5-20251101",
    max_tokens=16384,
    thinking={"type": "enabled", "budget_tokens": 10000},
    output_config={"effort": "high"},
    extra_headers={"anthropic-beta": "interleaved-thinking-2025-05-14,effort-2025-11-24"},
    system=DRIVE_SYSTEM_PROMPT,
    messages=messages,
    tools=anthropic_tools,
)
```

### 6b. Effort levels

| Level | Behavior | Use case |
|---|---|---|
| `high` | **Default.** Maximum thoroughness — deep reasoning, more tool calls. | Complex analysis, agent tasks (**recommended for FolderAgent**) |
| `medium` | Balanced. Matches Sonnet 4.5 quality at **76% fewer tokens**. | Production workloads where cost/speed matter |
| `low` | Most token-efficient. May skip thinking for simple problems. | High-volume classification, routing, data extraction |

**Notes:**
- `high` is the default — specifying it is identical to omitting effort entirely.
- Effort works **with or without** extended thinking enabled.
- Lower effort means Claude makes **fewer tool calls** — important for agent behavior.
- The effort parameter affects all tokens: text responses, tool call arguments, and thinking.

### 6c. Mapping to your OpenAI reasoning config

| Your current OpenAI config | Anthropic equivalent |
|---|---|
| `reasoning: {"effort": "xhigh"}` | `thinking: {type: "enabled", budget_tokens: 10000}` + `output_config: {effort: "high"}` |
| Reasoning blocks in output | Thinking blocks (`type: "thinking"`) in content array |
| Auto-included in `_raw_output_items` | Auto-preserved in Opus 4.5 multi-turn (pass content blocks back as-is) |

---

## 7. Tool Use (Function Calling)

### 7a. Tool definition format

**Your current OpenAI format** (in `agent_tools.py`, converted to Responses API flat format by `LLMClient`):

```python
{
    "type": "function",
    "function": {
        "name": "search_drive",
        "description": "Search files in Google Drive by keyword. Returns file names and IDs.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "file_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional file type filter"
                }
            },
            "required": ["query"]
        }
    }
}
```

**Anthropic equivalent:**

```python
{
    "name": "search_drive",
    "description": "Search files in Google Drive by keyword. Returns file names and IDs. Use when folder browsing isn't enough to find the right file.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "file_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional file type filter"
            }
        },
        "required": ["query"]
    }
}
```

### 7b. Conversion function (put in `llm.py`)

```python
def _convert_tool_openai_to_anthropic(tool: dict) -> dict:
    """Convert OpenAI function-calling tool format to Anthropic tool format."""
    if "function" in tool:
        # Nested Chat Completions format
        func = tool["function"]
        return {
            "name": func["name"],
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
        }
    # Already flat (Responses API format or Anthropic format)
    return {
        "name": tool["name"],
        "description": tool.get("description", ""),
        "input_schema": tool.get("parameters") or tool.get("input_schema", {"type": "object", "properties": {}}),
    }


def _convert_all_tools(tools: list[dict]) -> list[dict]:
    """Convert all DRIVE_AGENT_TOOLS to Anthropic format."""
    return [_convert_tool_openai_to_anthropic(t) for t in tools]
```

### 7c. Response with tool calls

When Claude wants to call a tool, `stop_reason` is `"tool_use"`:

```json
{
  "id": "msg_abc123",
  "role": "assistant",
  "stop_reason": "tool_use",
  "content": [
    {
      "type": "thinking",
      "thinking": "I should first look at the folder structure...",
      "signature": "..."
    },
    {
      "type": "text",
      "text": "Let me look at the folder structure first."
    },
    {
      "type": "tool_use",
      "id": "toolu_01A09q90qw90lq917835lq9",
      "name": "get_folder_structure",
      "input": {}
    }
  ]
}
```

**Key differences from OpenAI:**
- `stop_reason` is `"tool_use"` (OpenAI: check for `function_call` items in output)
- Tool calls are content blocks with `type: "tool_use"`, each with a unique `id` (prefix `toolu_`)
- The `id` maps to `tool_use_id` in results — equivalent to OpenAI's `call_id`
- `input` is a **parsed dict**, not a JSON string — your `tool_executor` may need `json.loads()` guarding
- Text, thinking, and tool_use blocks can be **interleaved** in the same response
- Claude can call **multiple tools** in a single response (parallel tool use is on by default)

### 7d. Returning tool results

After executing the tool, send results back as `tool_result` blocks inside a `user` message:

```python
# Append the full assistant response first
messages.append({"role": "assistant", "content": response.content})

# Build tool results
tool_results = []
for block in response.content:
    if block.type == "tool_use":
        result_text, citations = await tool_executor.execute_tool(
            block.name, json.loads(json.dumps(block.input)),  # ensure it's a plain dict
            project_id=project_id,
            access_token=access_token,
        )
        tool_results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": result_text,
        })

# Append tool results as a user message
messages.append({"role": "user", "content": tool_results})
```

**For errors**, add `is_error: True`:

```python
{
    "type": "tool_result",
    "tool_use_id": "toolu_01abc123",
    "content": "Error: File not found or access denied",
    "is_error": True,
}
```

### 7e. Best practices for tool definitions

- **Write 3–4+ sentence descriptions.** This is the single biggest factor in tool-use quality.
- **Return only high-signal data** in tool results. Strip UUIDs, metadata, and noise.
- Your existing `DRIVE_SYSTEM_PROMPT` strategy (folder-first, then targeted reads) translates perfectly.

---

## 8. Controlling Tool Behavior

### 8a. tool_choice

```python
# Let Claude decide (default)
tool_choice={"type": "auto"}

# Force Claude to use at least one tool
tool_choice={"type": "any"}

# Force a specific tool
tool_choice={"type": "tool", "name": "get_folder_structure"}

# Prevent tool use entirely
tool_choice={"type": "none"}
```

**With extended thinking enabled:** Only `auto` and `none` are supported. `any` and `tool` will error.

### 8b. Parallel tool use

Claude can call multiple tools in a single response by default. Disable with:

```python
tool_choice={"type": "auto", "disable_parallel_tool_use": True}
```

### 8c. Structured outputs (strict mode)

Force tool inputs to match your schema exactly (zero invalid args):

```python
{
    "name": "get_file_content",
    "description": "...",
    "input_schema": { ... },
    "strict": True,  # Guarantees schema-valid output
}
```

---

## 9. The Agentic Loop — Mapping to FolderAgent

### 9a. Current flow (`agent.py`)

```
1. Build messages: [system, ...history, user_question]
2. llm_client.call_with_tools(messages, tools)
3. If no tool calls → return content + citations
4. If tool calls → execute each via tool_executor, append results, goto 2
5. Max iterations (15) → return partial with warning
```

### 9b. New Anthropic flow

```
1. Build messages: alternating user/assistant
   System prompt → top-level "system" param
2. POST /v1/messages with tools + thinking + effort
3. Append full assistant response (content blocks including thinking)
4. If stop_reason == "end_turn" → extract text, return + citations
5. If stop_reason == "tool_use":
   a. Extract tool_use blocks → execute each via tool_executor (SAME CODE)
   b. Build tool_result content blocks with tool_use_id
   c. Append user message with tool_results
   d. Goto 2
6. Max iterations → force one more call with tools=[] to get final answer
```

### 9c. Full implementation

```python
import anthropic
import json
from app.services.tool_executor import execute_tool, Citation

client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def run_anthropic_agent(
    user_question: str,
    chat_history: list,
    drive_service,
    project_id: str,
    access_token: str,
    system_prompt: str,
    tools: list,
    max_iterations: int = 15,
    model: str = "claude-opus-4-5-20251101",
    thinking_budget: int = 10000,
    effort: str = "high",
):
    # Convert tools to Anthropic format
    anthropic_tools = _convert_all_tools(tools)

    # Build initial messages
    messages = _build_anthropic_messages(chat_history, user_question)
    all_citations: list[Citation] = []

    for i in range(max_iterations):
        response = await client.messages.create(
            model=model,
            max_tokens=max(thinking_budget + 8192, 16384),
            system=system_prompt,
            thinking={"type": "enabled", "budget_tokens": thinking_budget},
            output_config={"effort": effort},
            extra_headers={
                "anthropic-beta": "interleaved-thinking-2025-05-14,effort-2025-11-24"
            },
            messages=messages,
            tools=anthropic_tools,
        )

        # Append the full assistant response (preserves thinking blocks)
        messages.append({"role": "assistant", "content": response.content})

        # Done — extract final text
        if response.stop_reason == "end_turn":
            text = "".join(b.text for b in response.content if b.type == "text")
            return AgentResponse(
                content=text,
                citations=all_citations,
                iterations=i + 1,
                hit_limit=False,
            )

        # Tool use — execute and continue
        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result_text, citations = await execute_tool(
                        tool_name=block.name,
                        tool_args=block.input,  # Already a dict (not JSON string!)
                        drive_service=drive_service,
                        project_id=project_id,
                        access_token=access_token,
                    )
                    all_citations.extend(citations)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    })

            messages.append({"role": "user", "content": tool_results})

        # Truncated — could retry with higher max_tokens
        if response.stop_reason == "max_tokens":
            break

    # Hit iteration limit — force a final synthesis call with no tools
    response = await client.messages.create(
        model=model,
        max_tokens=8192,
        system=system_prompt + "\n\nProvide your best answer based on what you've found so far.",
        messages=messages,
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    return AgentResponse(
        content=text + "\n\n⚠️ Maximum iterations reached.",
        citations=all_citations,
        iterations=max_iterations,
        hit_limit=True,
    )
```

### 9d. Critical differences from OpenAI agent loop

1. **`tool_executor.py` dispatch stays identical** — only `llm.py` changes.
2. Tool args arrive as a **dict** (`block.input`), not a JSON string (`function.arguments`).
3. `stop_reason` is checked explicitly instead of checking for empty tool_calls list.
4. Full `response.content` (including thinking blocks) must be appended as-is for multi-turn context.
5. Tool results go in a `user` message, not a separate role.

---

## 10. Multi-Turn Message Construction

Anthropic requires strictly alternating `user` → `assistant` → `user` → `assistant` messages.

### 10a. Message flow

```
Turn 1:
  messages = [
    {role: "user", content: "What's in my Drive?"}
  ]

Turn 2 (after tool use):
  messages = [
    {role: "user", content: "What's in my Drive?"},
    {role: "assistant", content: [<thinking>, <text>, <tool_use>]},   ← full response.content
    {role: "user", content: [{type: "tool_result", ...}]},            ← your tool results
  ]

Turn 3 (final answer):
  messages = [
    ...all of the above...,
    {role: "assistant", content: [<thinking>, <text>]},                ← Claude's answer
    {role: "user", content: "Now summarize that."},                    ← next user message
  ]
```

### 10b. Conversion function (put in `llm.py`)

```python
def _build_anthropic_messages(chat_history: list, user_question: str) -> list:
    """
    Convert internal message format to Anthropic messages.

    Key rules:
    - System prompt is extracted separately (top-level 'system' param)
    - Messages must alternate: user, assistant, user, assistant...
    - Tool results go in user messages as tool_result content blocks
    - Thinking blocks from previous assistant turns are passed back as-is
    """
    messages = []

    for msg in chat_history:
        role = msg.get("role")

        if role == "system":
            continue  # Handled separately via system= parameter

        elif role == "user":
            messages.append({"role": "user", "content": msg["content"]})

        elif role == "assistant":
            if "_raw_content_blocks" in msg:
                # Preserved raw Anthropic content blocks
                messages.append({"role": "assistant", "content": msg["_raw_content_blocks"]})
            else:
                messages.append({"role": "assistant", "content": msg["content"]})

        elif role == "tool":
            # Tool results must be in a user message
            tool_result = {
                "type": "tool_result",
                "tool_use_id": msg["tool_call_id"],
                "content": msg["content"],
            }
            # Append to existing user message with tool_results, or create new one
            if messages and messages[-1]["role"] == "user" and isinstance(messages[-1]["content"], list):
                messages[-1]["content"].append(tool_result)
            else:
                messages.append({"role": "user", "content": [tool_result]})

    # Add the new user question
    messages.append({"role": "user", "content": user_question})

    return messages
```

### 10c. Critical rules

- `tool_result` blocks must immediately follow the `assistant` message containing the matching `tool_use`.
- `tool_use_id` must match the `id` from the `tool_use` block **exactly**.
- Pass thinking blocks back as-is — the API ignores them for context calculation but needs them for continuity.
- No `system` role in messages — system prompts go in the top-level `system` parameter.
- Consecutive same-role messages are merged by the API, but best to structure correctly.

---

## 11. Streaming

### 11a. Event sequence

```
message_start          → message metadata (id, model, initial usage)
content_block_start    → new block beginning (text, tool_use, or thinking)
content_block_delta    → incremental data:
                           - text_delta       → {"text": "chunk"}
                           - input_json_delta → {"partial_json": "..."}  (tool args)
                           - thinking_delta   → {"thinking": "..."}
                           - signature_delta  → {"signature": "..."}
content_block_stop     → block complete
message_delta          → stop_reason + cumulative usage
message_stop           → response complete
ping                   → keepalive
error                  → error during stream (e.g. overloaded_error)
```

### 11b. Streaming with the SDK (recommended)

```python
async with client.messages.stream(
    model="claude-opus-4-5-20251101",
    max_tokens=16384,
    system=DRIVE_SYSTEM_PROMPT,
    thinking={"type": "enabled", "budget_tokens": 10000},
    output_config={"effort": "high"},
    extra_headers={"anthropic-beta": "interleaved-thinking-2025-05-14,effort-2025-11-24"},
    tools=anthropic_tools,
    messages=messages,
) as stream:
    async for event in stream:
        if event.type == "content_block_start":
            if event.content_block.type == "tool_use":
                # Tool call starting — could yield a "status" SSE event
                pass
        elif event.type == "content_block_delta":
            if event.delta.type == "text_delta":
                yield {"type": "delta", "text": event.delta.text}
            elif event.delta.type == "thinking_delta":
                yield {"type": "status", "text": "Thinking..."}  # optional
            elif event.delta.type == "input_json_delta":
                pass  # Accumulate tool argument JSON
        elif event.type == "message_delta":
            if event.delta.stop_reason == "tool_use":
                pass  # Execute tools and continue loop

    final_message = await stream.get_final_message()
```

### 11c. Mapping to your frontend SSE events

Your frontend expects: `session`, `status`, `delta`, `citations`, `done`.

| Anthropic event | Your SSE event | Notes |
|---|---|---|
| `content_block_delta` with `text_delta` (on final answer) | `delta` | Stream text to user |
| `thinking_delta` | `status` (optional) | "Analyzing..." indicator |
| Tool execution starting | `status` | "Reading file X..." (same as current) |
| `message_stop` with `end_turn` | `done` + `citations` | Send accumulated citations |

### 11d. Strategy for the agentic loop

**Recommended approach** — non-streaming tool calls, stream only the final response:

During tool-use iterations, use non-streaming `client.messages.create()` for speed and simplicity. When `stop_reason` is `"end_turn"` (final answer), use `client.messages.stream()` to yield text deltas to the frontend in real-time. This matches your current OpenAI approach exactly.

---

## 12. Prompt Caching

Your system prompt + 12 tool definitions are identical on every request — a perfect caching target. Prompt caching can reduce input costs by **up to 90%** on cache hits.

### 12a. Automatic caching (simplest)

```python
response = await client.messages.create(
    model="claude-opus-4-5-20251101",
    max_tokens=16384,
    cache_control={"type": "ephemeral"},  # Top-level: cache everything cacheable
    system=DRIVE_SYSTEM_PROMPT,
    messages=messages,
    tools=anthropic_tools,
)
```

### 12b. Explicit cache breakpoints (fine-grained)

```python
response = await client.messages.create(
    model="claude-opus-4-5-20251101",
    max_tokens=16384,
    system=[
        {
            "type": "text",
            "text": DRIVE_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},  # Cache the system prompt
        }
    ],
    messages=messages,
    tools=anthropic_tools,
)
```

### 12c. Caching rules

- Cache prefix must be at least **1,024 tokens** (Opus) or 4,096 (Haiku).
- Up to **4 cache breakpoints** per request.
- Default TTL: **5 minutes** (refreshed on each hit). 1-hour TTL available at 2× write cost.
- Cache order: `tools` → `system` → `messages`. Changes to earlier elements invalidate later caches.
- Cache write: **1.25×** base input price ($6.25/MTok for Opus 4.5).
- Cache read: **0.1×** base input price ($0.50/MTok for Opus 4.5).
- Changes to `tool_choice` or presence/absence of images invalidate the cache.

### 12d. Impact on your app

Your DRIVE_SYSTEM_PROMPT + 12 tools are likely ~2,000–4,000 tokens. On a busy session with 15 agent iterations, caching saves ~90% of repeated input costs on those tokens.

---

## 13. Compaction & Context Editing

For long-running agent sessions, these features prevent context window overflow.

### 13a. Context editing — clear old tool results (recommended for agents)

Strips old tool_use/tool_result pairs to save context space:

```python
response = await client.messages.create(
    model="claude-opus-4-5-20251101",
    max_tokens=16384,
    betas=["context-management-2025-06-27"],
    system=DRIVE_SYSTEM_PROMPT,
    messages=messages,
    tools=anthropic_tools,
    context_management={
        "edits": [
            {
                "type": "clear_tool_uses_20250919",
                "trigger": {"type": "input_tokens", "value": 150000},
            }
        ]
    },
)
```

### 13b. Server-side compaction (auto-summarize old turns)

```python
response = await client.messages.create(
    model="claude-opus-4-5-20251101",
    max_tokens=16384,
    betas=["compact-2026-01-12"],
    messages=messages,
    context_management={
        "edits": [
            {
                "type": "compact_20260112",
                "trigger": {"type": "input_tokens", "value": 100000},
            }
        ]
    },
)
```

When triggered:
1. API detects input tokens exceeding your threshold.
2. Generates a summary of the conversation.
3. Returns a `compaction` block in the response.
4. On next call, auto-drops all messages before the compaction block.

### 13c. Relevance to your app

Your FolderAgent has `max_iterations=15`, and each iteration adds assistant + tool_result messages. With large file contents (50K chars from `get_file_content`), context can grow fast. Context editing is the safest addition — it strips stale tool results while preserving reasoning.

---

## 14. Handling Stop Reasons

| `stop_reason` | Meaning | Action |
|---|---|---|
| `end_turn` | Claude finished naturally | Extract text, return final answer + citations |
| `tool_use` | Claude wants to call tool(s) | Execute tools, send `tool_result`, call API again |
| `max_tokens` | Output was truncated | Retry with higher `max_tokens` or return partial |
| `stop_sequence` | Hit a custom stop sequence | Handle as needed |
| `pause_turn` | Server paused a long turn (server tools like web_search) | Append response, call API again to continue |
| `compaction` | Context was compacted (beta) | Append response, continue — API handles the rest |

---

## 15. Error Handling

### 15a. Error response format

```json
{
  "type": "error",
  "error": {
    "type": "rate_limit_error",
    "message": "Rate limit exceeded. Please retry after 30 seconds."
  }
}
```

### 15b. Error types

| Error type | HTTP status | Retry? | Description |
|---|---|---|---|
| `invalid_request_error` | 400 | No | Malformed request, bad params |
| `authentication_error` | 401 | No | Invalid API key |
| `permission_error` | 403 | No | Key lacks access to model |
| `not_found_error` | 404 | No | Model not found |
| `request_too_large` | 413 | No | Request exceeds size limit |
| `rate_limit_error` | 429 | **Yes** | Rate limit — retry with exponential backoff |
| `api_error` | 500 | **Yes** | Server error — retry |
| `overloaded_error` | 529 | **Yes** | API overloaded — retry with backoff |

### 15c. Retry strategy

```python
RETRYABLE_STATUS = {429, 500, 529}

async def call_with_retry(fn, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await fn()
        except anthropic.RateLimitError:
            wait = 2 ** attempt
            await asyncio.sleep(wait)
        except anthropic.InternalServerError:
            wait = 2 ** attempt
            await asyncio.sleep(wait)
        except anthropic.APIStatusError as e:
            if e.status_code in RETRYABLE_STATUS:
                await asyncio.sleep(2 ** attempt)
                continue
            raise
    raise Exception("Max retries exceeded")
```

Note: The `anthropic` SDK has built-in retry logic with exponential backoff. You can configure it:

```python
client = anthropic.AsyncAnthropic(
    api_key=settings.ANTHROPIC_API_KEY,
    max_retries=3,  # default is 2
)
```

---

## 16. Python SDK vs Raw HTTP

### Option A: `anthropic` Python SDK (recommended)

```bash
pip install anthropic
```

```python
import anthropic

client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

response = await client.messages.create(
    model="claude-opus-4-5-20251101",
    max_tokens=16384,
    system=system_prompt,
    thinking={"type": "enabled", "budget_tokens": 10000},
    output_config={"effort": "high"},
    extra_headers={"anthropic-beta": "interleaved-thinking-2025-05-14,effort-2025-11-24"},
    tools=anthropic_tools,
    messages=messages,
)

# Access response
stop_reason = response.stop_reason          # "end_turn" or "tool_use"
content_blocks = response.content           # list of ContentBlock objects
text = "".join(b.text for b in content_blocks if b.type == "text")
tool_calls = [b for b in content_blocks if b.type == "tool_use"]
```

**Pros**: Type safety, built-in retries, streaming helpers, handles SSE parsing, async-native.

### Option B: Raw `httpx`

Use `httpx.AsyncClient` directly. All headers and JSON construction manual.

**Pros**: No new dependency, full control.
**Cons**: Manual SSE parsing, manual retry logic, no type checking.

### Recommendation

Use the `anthropic` SDK. It's async-native, handles streaming properly, and is well-maintained. Normalize its response types in `llm.py` the same way you currently normalize OpenAI Responses API output into your `LLMResponse` / `MessageContent` dataclasses.

Add to `requirements.txt`:

```
anthropic>=0.40.0
```

---

## 17. Tool Runner (Beta)

The SDK provides a tool runner that automates the agentic loop. Useful if you want a simpler integration and don't need custom per-iteration control.

### 17a. Define tools with decorators

```python
from anthropic import beta_tool

@beta_tool
def get_folder_structure() -> str:
    """Get the folder tree of all files with sizes and IDs. CALL THIS FIRST."""
    # your implementation
    return json.dumps(tree_data)

@beta_tool
def search_drive(query: str, file_types: list[str] | None = None) -> str:
    """Search files in Google Drive by keyword."""
    # your implementation
    return json.dumps(results)
```

### 17b. Run with the tool runner

```python
runner = client.beta.messages.tool_runner(
    model="claude-opus-4-5-20251101",
    max_tokens=16384,
    system=DRIVE_SYSTEM_PROMPT,
    tools=[get_folder_structure, search_drive],
    messages=[{"role": "user", "content": "What is the 401(k) policy?"}],
)

for message in runner:
    # Each iteration yields a BetaMessage
    print(f"Stop reason: {message.stop_reason}")

final = runner.final_message
text = "".join(b.text for b in final.content if b.type == "text")
```

### 17c. When to use it

The tool runner is great for simple cases but **not recommended** for your FolderAgent because:
- You need per-iteration citation tracking.
- You need credential injection (`project_id`, `access_token`) per tool call.
- You need status events during tool execution for SSE streaming.
- You need the custom max-iterations + forced-synthesis logic.

Use the manual loop from Section 9 instead.

---

## 18. Environment Variables

Add to `backend/app/config.py`:

```python
class Settings(BaseSettings):
    # Existing
    OPENAI_API_KEY: str
    AGENT_MODEL: str = "gpt-5.2"

    # New
    ANTHROPIC_API_KEY: str | None = None       # Optional — enables Anthropic provider
    AGENT_PROVIDER: str = "openai"             # "openai" or "anthropic"
    ANTHROPIC_THINKING_BUDGET: int = 10000     # Thinking token budget (1024-64000)
    ANTHROPIC_EFFORT: str = "high"             # "low", "medium", "high"
```

Add to `.env.example`:

```env
# LLM Provider: "openai" or "anthropic"
AGENT_PROVIDER=openai
AGENT_MODEL=gpt-5.2

# Anthropic (required if AGENT_PROVIDER=anthropic)
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_THINKING_BUDGET=10000
ANTHROPIC_EFFORT=high
```

---

## 19. Implementation Plan

### Phase 1: Provider abstraction in `llm.py`

1. Add `_call_anthropic()` method to `LLMClient` alongside `_call_openai()`.
2. Create `_convert_tools_to_anthropic()` for tool schema conversion.
3. Create `_convert_messages_to_anthropic()` for message format conversion.
4. Normalize Anthropic response → your existing `LLMResponse` / `MessageContent` dataclasses.
5. Route based on model name prefix: `claude-*` → Anthropic, else → OpenAI.
6. Store raw content blocks on `MessageContent._raw_content_blocks` (parallel to `_raw_output_items`).

### Phase 2: Streaming support

1. Add `_stream_anthropic()` alongside existing OpenAI streaming.
2. Handle SSE event types: filter `thinking_delta` (optional status event), yield `text_delta`.
3. Detect `stop_reason: "tool_use"` → trigger tool execution in agent loop.
4. Yield `status` events during tool execution (same as current).

### Phase 3: Agent loop updates (`agent.py`)

1. Store raw content blocks on assistant messages for thinking preservation.
2. Handle `stop_reason` field instead of checking for empty tool_calls.
3. Build `tool_result` messages in Anthropic format.
4. Handle `input` as dict (not JSON string) from tool_use blocks.
5. Test with all 12 `DRIVE_AGENT_TOOLS`.

### Phase 4: Config & testing

1. Add `ANTHROPIC_API_KEY`, `AGENT_PROVIDER`, `ANTHROPIC_EFFORT` to config.
2. Update `routers/chat.py` to pass provider info to `LLMClient`.
3. Add tests for Anthropic message conversion.
4. Add tests for tool schema conversion.
5. Add tests for thinking block preservation across turns.
6. Run benchmark suite against Anthropic.

### Phase 5: Optimization

1. Enable prompt caching on system prompt + tools.
2. Add context editing for long sessions (`clear_tool_uses`).
3. Tune `budget_tokens` and `effort` for your specific Q&A workload.

---

## 20. Key Gotchas

1. **`max_tokens` is required** — Anthropic has no default. Always pass it.

2. **No `temperature` with thinking** — When extended thinking is enabled, `temperature` must be unset or `1`. Cannot lower it.

3. **Thinking tokens count toward output** — Budget for `budget_tokens + expected_text_output` when setting `max_tokens`. If `budget_tokens >= max_tokens`, the API errors.

4. **Alternating roles are enforced** — Consecutive same-role messages are merged by the API, but structure them correctly to avoid surprises.

5. **Tool args are dicts, not strings** — Anthropic returns `input` as a parsed dict, not a JSON string like OpenAI's `function.arguments`. Your `tool_executor` may need `json.loads()` guarding: `args = json.loads(args) if isinstance(args, str) else args`.

6. **`tool_use_id` must match exactly** — The `tool_use_id` in your `tool_result` must be the exact string from the `tool_use` block's `id` field.

7. **Thinking is summarized** — You're billed for full thinking tokens but only see a summary. The `signature` field contains encrypted full thinking; pass it back unmodified.

8. **Effort beta header required for Opus 4.5** — Use `anthropic-beta: effort-2025-11-24`. Not needed on newer 4.6 models where effort is GA.

9. **No `system` role in messages** — System prompts go in the top-level `system` parameter. Including a `{"role": "system"}` message will error.

10. **Streaming tool args** — Tool argument deltas come as `input_json_delta` with `partial_json` strings. Accumulate them and parse once you get `content_block_stop`. The SDK handles this automatically.

11. **Cache invalidation** — Any change to tools, system prompt, or early messages invalidates the cache for everything after. Keep stable content first.

12. **No conversations API** — Anthropic is fully stateless. There's no `previous_response_id` or server-side session. You manage the full `messages` array.

---

## 21. Quick Reference Cheat Sheet

```
POST https://api.anthropic.com/v1/messages

Headers:
  x-api-key: sk-ant-...
  anthropic-version: 2023-06-01
  anthropic-beta: interleaved-thinking-2025-05-14,effort-2025-11-24
  content-type: application/json

Body:
{
  "model": "claude-opus-4-5-20251101",
  "max_tokens": 16384,
  "system": "You are a helpful assistant...",
  "thinking": {"type": "enabled", "budget_tokens": 10000},
  "output_config": {"effort": "high"},
  "stream": false,
  "tools": [
    {"name": "search_drive", "description": "...", "input_schema": {...}},
    ...
  ],
  "messages": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": [<thinking>, <text>, <tool_use>]},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "...", "content": "..."}]},
    {"role": "user", "content": "Follow-up question"}
  ]
}

Response (stop_reason: "end_turn"):
{
  "content": [
    {"type": "thinking", "thinking": "...", "signature": "..."},
    {"type": "text", "text": "Final answer..."}
  ],
  "stop_reason": "end_turn",
  "usage": {"input_tokens": N, "output_tokens": N}
}

Response (stop_reason: "tool_use"):
{
  "content": [
    {"type": "thinking", "thinking": "...", "signature": "..."},
    {"type": "tool_use", "id": "toolu_...", "name": "search_drive", "input": {"query": "..."}}
  ],
  "stop_reason": "tool_use"
}
```

**Settings summary:**

| Setting | Value |
|---|---|
| Model | `claude-opus-4-5-20251101` |
| Thinking | `thinking: {type: "enabled", budget_tokens: N}` |
| Effort | `output_config: {effort: "high"}` |
| API endpoint | `POST /v1/messages` |
| Auth header | `x-api-key: $ANTHROPIC_API_KEY` |
| Version header | `anthropic-version: 2023-06-01` |
| Stream param | `stream: true` |
| Text delta event | `content_block_delta` with `text_delta` |
| Tool call block type | `tool_use` (in response content) |
| Tool output type | `tool_result` with `tool_use_id` |
| Stop reason for tools | `stop_reason: "tool_use"` |
| Stop reason for done | `stop_reason: "end_turn"` |
| Pricing (Opus 4.5) | $5 / $25 per MTok (input / output) |
| Cache read pricing | $0.50 / MTok (0.1× input) |
| Cache write pricing | $6.25 / MTok (1.25× input) |

---

## 22. Upgrade Path — Opus 4.6

Claude Opus 4.6 (`claude-opus-4-6`) is now available at the **same $5/$25 pricing** with significant upgrades:

| Feature | Opus 4.5 | Opus 4.6 |
|---|---|---|
| Context window | 200K | **1M (beta)** |
| Max output | 64K | **128K** |
| Thinking | Manual: `{type: "enabled", budget_tokens: N}` | **Adaptive: `{type: "adaptive"}`** |
| Effort | Beta header required | **GA — no header needed** |
| Interleaved thinking | Beta header required | **Automatic** |
| `budget_tokens` | Required for thinking | **Deprecated — use effort instead** |

To upgrade, change the model ID and simplify thinking config:

```python
response = await client.messages.create(
    model="claude-opus-4-6",              # New model
    max_tokens=16384,
    thinking={"type": "adaptive"},         # Replaces {type: "enabled", budget_tokens: N}
    output_config={"effort": "high"},      # No beta header needed
    # No anthropic-beta header needed for thinking or effort
    system=DRIVE_SYSTEM_PROMPT,
    messages=messages,
    tools=anthropic_tools,
)
```

Opus 4.6 also supports a `"max"` effort level (only on Opus 4.6) for absolute highest capability.

---

## 23. Documentation Links

**Core API:**
- Messages API Reference: https://platform.claude.com/docs/en/api/messages
- Streaming Messages: https://platform.claude.com/docs/en/build-with-claude/streaming
- Models Overview: https://platform.claude.com/docs/en/about-claude/models/overview
- Pricing: https://platform.claude.com/docs/en/about-claude/pricing

**Thinking & Effort:**
- Extended Thinking: https://platform.claude.com/docs/en/build-with-claude/extended-thinking
- Adaptive Thinking (4.6): https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking
- Effort Parameter: https://platform.claude.com/docs/en/build-with-claude/effort

**Tool Use:**
- Tool Use Overview: https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
- How to Implement Tool Use: https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use
- Structured Outputs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs

**Context Management:**
- Prompt Caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Compaction: https://platform.claude.com/docs/en/build-with-claude/compaction
- Context Editing: https://platform.claude.com/docs/en/build-with-claude/context-editing

**Agent Building:**
- Writing Tools for Agents (Blog): https://www.anthropic.com/engineering/writing-tools-for-agents
- Agent SDK: https://platform.claude.com/docs/en/agent-sdk/overview
- Agent Loop Explained: https://platform.claude.com/docs/en/agent-sdk/agent-loop

**SDKs:**
- Python SDK: https://github.com/anthropics/anthropic-sdk-python
- TypeScript SDK: https://github.com/anthropics/anthropic-sdk-typescript