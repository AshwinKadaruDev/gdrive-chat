# Claude Agentic Chat — Developer Reference

> Model: **`claude-opus-4-5-20250929`** · API: **Messages API (`/v1/messages`)** · Thinking: **Extended (`budget_tokens`)**

---

## 1. Why the Messages API

Anthropic's Messages API is the single endpoint for all Claude work — chat, tool use, agentic loops, streaming, and extended thinking. There is no separate "agentic" endpoint; agentic behavior emerges from the tool-use loop you build on top of Messages.

- **Stateless by design** — you send the full conversation history (system + messages) each call, giving you complete control over context.
- **Tool use is native** — define tools in the `tools` parameter; Claude returns `tool_use` content blocks when it wants to call one.
- **Extended thinking** — enable chain-of-thought reasoning with the `thinking` parameter for higher intelligence on complex decisions.
- **Prompt caching** — mark stable content with `cache_control` for up to 90% cost reduction on repeated prefixes.

**Endpoint:** `POST https://api.anthropic.com/v1/messages`

**Required Headers:**
```
x-api-key: $ANTHROPIC_API_KEY
anthropic-version: 2023-06-01
content-type: application/json
```

---

## 2. Model & Thinking Configuration

```
Model ID:            claude-opus-4-5-20250929
Alias:               claude-opus-4-5
Context window:      200,000 tokens (1M beta on Opus 4.6)
Max output:          64,000 tokens (128K on Opus 4.6)
Knowledge cutoff:    Early 2025
Pricing:             $5 / $25 per million tokens (input / output)
```

> **Note:** Claude Opus 4.6 (`claude-opus-4-6`) is now available at the same $5/$25 pricing with a 1M context window (beta), 128K max output, and adaptive thinking. Consider upgrading — it's a strict improvement at no extra cost.

### Extended Thinking

Opus 4.5 uses `type: "enabled"` with an explicit `budget_tokens`:

```python
response = client.messages.create(
    model="claude-opus-4-5-20250929",
    max_tokens=16000,
    thinking={
        "type": "enabled",
        "budget_tokens": 10000,
    },
    messages=[{"role": "user", "content": "..."}],
    tools=[...],
)
```

**Key rules:**
- `budget_tokens` must be less than `max_tokens`.
- Minimum budget is **1,024 tokens**.
- Thinking tokens are billed as output tokens. Claude 4 models return **summarized** thinking (you're charged for full thinking, not the summary).
- Start at the minimum and increase incrementally — diminishing returns above 32K.
- You **cannot** prefill assistant messages when thinking is enabled.
- For interleaved thinking with tools (thinking between tool calls), add the beta header: `anthropic-beta: interleaved-thinking-2025-05-14`.

> **Opus 4.6 upgrade path:** On Opus 4.6, use adaptive thinking instead — `thinking: {"type": "adaptive"}` with an optional `effort` parameter (`low`, `medium`, `high`, `max`). Claude decides when and how much to think. Interleaved thinking is automatic. `budget_tokens` is deprecated on 4.6.

---

## 3. The Agentic Loop — How It Works

The core pattern: call the Messages API → check if `stop_reason` is `"tool_use"` → execute the tools → send results back as `tool_result` blocks → repeat until `stop_reason` is `"end_turn"`.

### 3a. Non-Streaming Agent Loop (Python)

```python
import anthropic
import json

client = anthropic.Anthropic()

# Define your tools
tools = [
    {
        "name": "get_weather",
        "description": "Get current weather for a city. Returns temperature and conditions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name, e.g. 'San Francisco, CA'",
                }
            },
            "required": ["city"],
        },
    }
]

# Your tool implementations
def execute_tool(name: str, input_data: dict) -> str:
    if name == "get_weather":
        return json.dumps({"temp": "72F", "condition": "sunny"})
    return json.dumps({"error": "Unknown tool"})


def run_agent(user_message: str, max_iterations: int = 10):
    messages = [{"role": "user", "content": user_message}]

    for i in range(max_iterations):
        response = client.messages.create(
            model="claude-opus-4-5-20250929",
            max_tokens=4096,
            system="You are a helpful assistant.",
            thinking={"type": "enabled", "budget_tokens": 5000},
            messages=messages,
            tools=tools,
        )

        # Append the full assistant response to messages
        messages.append({"role": "assistant", "content": response.content})

        # Check stop reason
        if response.stop_reason == "end_turn":
            # Extract final text
            text_blocks = [b.text for b in response.content if b.type == "text"]
            return "\n".join(text_blocks)

        if response.stop_reason == "tool_use":
            # Collect all tool_use blocks
            tool_uses = [b for b in response.content if b.type == "tool_use"]

            # Build tool results
            tool_results = []
            for tool_use in tool_uses:
                result = execute_tool(tool_use.name, tool_use.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result,
                })

            # Append tool results as a user message
            messages.append({"role": "user", "content": tool_results})

    return "Max iterations reached."
```

**Key differences from OpenAI's Responses API:**
- **No `previous_response_id`** — Anthropic's API is stateless. You always send the full `messages` array.
- **Tool results go in a `user` message** — not a separate role. The `tool_result` blocks must come **first** in the content array, before any text.
- **`stop_reason` tells you what to do** — `"tool_use"` means execute tools; `"end_turn"` means done; `"max_tokens"` means the response was truncated.
- **Thinking blocks appear in `response.content`** — you must pass them back in the conversation. The API automatically ignores thinking blocks from previous turns when calculating context usage.

### 3b. Using the Tool Runner (Beta — Recommended)

The Python, TypeScript, and Ruby SDKs provide a tool runner that automates the loop:

```python
import anthropic

client = anthropic.Anthropic()

@anthropic.beta_tool
def get_weather(city: str) -> str:
    """Get current weather for a city. Returns temperature and conditions."""
    return json.dumps({"temp": "72F", "condition": "sunny"})

# The tool runner handles the loop automatically
result = client.messages.create_with_tools(
    model="claude-opus-4-5-20250929",
    max_tokens=4096,
    system="You are a helpful assistant.",
    messages=[{"role": "user", "content": "What's the weather in Paris?"}],
    tools=[get_weather],
)
```

The runner automatically:
- Executes tools when Claude calls them
- Sends results back to the API
- Manages the message history
- Loops until Claude returns a final text response

You can also iterate over the runner for intermediate messages:

```python
runner = client.messages.create_with_tools(
    model="claude-opus-4-5-20250929",
    max_tokens=4096,
    messages=[{"role": "user", "content": "What's the weather in Paris?"}],
    tools=[get_weather],
)

for message in runner:
    # Inspect intermediate messages, log tool calls, etc.
    print(f"Stop reason: {message.stop_reason}")

final_message = runner.final_message
```

---

## 4. Streaming

Set `stream=True` (raw HTTP) or use the SDK's `.stream()` helper for server-sent events.

### 4a. Basic Streaming (SDK Helper)

```python
with client.messages.stream(
    model="claude-opus-4-5-20250929",
    max_tokens=4096,
    messages=[{"role": "user", "content": "Explain quantum computing."}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

### 4b. Streaming in the Agentic Loop

**Approach 1 — Non-streaming tool calls, stream only the final response:**

```python
def run_agent_stream_final(user_message: str, max_iterations: int = 10):
    messages = [{"role": "user", "content": user_message}]

    for i in range(max_iterations):
        response = client.messages.create(
            model="claude-opus-4-5-20250929",
            max_tokens=4096,
            system="You are a helpful assistant.",
            messages=messages,
            tools=tools,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            return response.content[0].text

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})

    return "Max iterations reached."
```

**Approach 2 — Stream every call, yield text deltas on the final one:**

```python
def run_agent_fully_streamed(user_message: str, max_iterations: int = 10):
    messages = [{"role": "user", "content": user_message}]

    for i in range(max_iterations):
        with client.messages.stream(
            model="claude-opus-4-5-20250929",
            max_tokens=4096,
            system="You are a helpful assistant.",
            messages=messages,
            tools=tools,
        ) as stream:
            response = stream.get_final_message()

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # On the final iteration, you can also iterate stream.text_stream
            # for real-time text deltas instead of waiting for final_message
            return response.content[0].text

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})

    return "Max iterations reached."
```

### 4c. Key Streaming Events (Raw SSE)

| Event | Purpose |
|---|---|
| `message_start` | Message object created (includes model, usage) |
| `content_block_start` | New content block (text, tool_use, or thinking) |
| `content_block_delta` | Incremental content — `text_delta`, `input_json_delta`, or `thinking_delta` |
| `content_block_stop` | Content block finalized |
| `message_delta` | Top-level changes — `stop_reason`, cumulative `usage` |
| `message_stop` | Entire response complete |
| `ping` | Keepalive |
| `error` | Error during stream (e.g. `overloaded_error`) |

**Raw SSE example output:**
```
event: message_start
data: {"type":"message_start","message":{"id":"msg_...","model":"claude-opus-4-5-20250929",...}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":15}}

event: message_stop
data: {"type":"message_stop"}
```

---

## 5. Tool (Function) Definition Format

Tools use `name`, `description`, and `input_schema` (JSON Schema):

```python
{
    "name": "search_database",
    "description": "Search the product database by query string. Returns top 5 matches with name, price, and category. Use when the user asks about products or inventory.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (default 5)",
            },
        },
        "required": ["query"],
    },
}
```

**Tool result format** (what you send back after executing):

```python
{
    "type": "tool_result",
    "tool_use_id": "<id from the tool_use block>",
    "content": "<string result — typically JSON-serialized>",
}
```

For errors, add `"is_error": True`:

```python
{
    "type": "tool_result",
    "tool_use_id": "toolu_01abc123",
    "content": "Error: City not found",
    "is_error": True,
}
```

**Tool use examples** (optional, helps with complex tools):

```python
{
    "name": "search_database",
    "description": "...",
    "input_schema": { ... },
    "input_examples": [
        {"query": "wireless headphones", "limit": 3},
        {"query": "laptop stand"},
    ],
}
```

### Best practices for tool definitions

- **Write 3–4+ sentence descriptions.** This is the single biggest factor in tool-use quality. Explain what, when, how, and limitations.
- **Consolidate related operations** into fewer tools with an `action` parameter instead of many small tools.
- **Use meaningful namespacing** — `gdrive_search`, `gdrive_read`, `gdrive_list` — especially when using many tools.
- **Return only high-signal data** in tool results. Strip UUIDs, metadata, and noise.

---

## 6. Conversation State Management

Anthropic's API is **stateless**. You send the full `messages` array every call. There is no `previous_response_id` equivalent.

### Message Structure

```
Turn 1:
  messages = [
    {role: "user", content: "What's in my Drive?"}
  ]

Turn 2 (after tool use):
  messages = [
    {role: "user", content: "What's in my Drive?"},
    {role: "assistant", content: [<text>, <tool_use>]},       ← full response.content
    {role: "user", content: [{type: "tool_result", ...}]},    ← your tool results
  ]

Turn 3 (final answer):
  messages = [
    ...all of the above...,
    {role: "assistant", content: [<text>]},                    ← Claude's answer
    {role: "user", content: "Now summarize that."},            ← next user message
  ]
```

**Critical rules:**
- Messages must alternate `user` → `assistant` → `user` → `assistant`.
- `tool_result` blocks go inside a `user` message, and must come **before** any text in that message.
- `tool_result` must immediately follow the `assistant` message containing the matching `tool_use`.
- Pass thinking blocks back as-is — the API ignores them for context calculation but needs them for continuity.

---

## 7. Controlling Claude's Output

### tool_choice

```python
# Let Claude decide (default)
tool_choice={"type": "auto"}

# Force Claude to use at least one tool
tool_choice={"type": "any"}

# Force a specific tool
tool_choice={"type": "tool", "name": "get_weather"}

# Prevent tool use entirely
tool_choice={"type": "none"}
```

> **With extended thinking:** Only `auto` and `none` are supported. `any` and `tool` will error.

### Parallel Tool Use

Claude can call multiple tools in a single response by default. Disable with:

```python
tool_choice={"type": "auto", "disable_parallel_tool_use": True}
```

### Structured Outputs (Strict Mode)

Force tool inputs to match your schema exactly:

```python
{
    "name": "extract_info",
    "description": "...",
    "input_schema": { ... },
    "strict": True,  # Guarantees schema-valid output
}
```

---

## 8. Compaction (Long-Running Agents)

When context grows large, use server-side compaction to automatically summarize older turns.

### Server-Side Compaction (Beta — Recommended for Opus 4.6)

```python
response = client.beta.messages.create(
    betas=["compact-2026-01-12"],
    model="claude-opus-4-6",
    max_tokens=4096,
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

# Append response as-is — compaction blocks are included automatically
messages.append({"role": "assistant", "content": response.content})
```

When triggered, the API:
1. Detects input tokens exceeding your threshold
2. Generates a summary of the conversation
3. Returns a `compaction` block in the response
4. On next call, auto-drops all messages before the compaction block

### Client-Side Compaction (SDK — for Opus 4.5 or custom summarization)

The SDK monitors token usage and injects a summary prompt when a threshold is exceeded:

```python
runner = client.messages.create_with_tools(
    model="claude-opus-4-5-20250929",
    max_tokens=4096,
    messages=messages,
    tools=tools,
    compaction_control={
        "threshold": 100000,  # tokens
    },
)
```

### Context Editing (Clearing Old Tool Results)

For agentic workflows with heavy tool use, clear old tool results to save context:

```python
response = client.beta.messages.create(
    betas=["context-management-2025-06-27"],
    model="claude-opus-4-5-20250929",
    max_tokens=4096,
    messages=messages,
    tools=tools,
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

---

## 9. Prompt Caching

Cache stable content (system prompts, tool definitions, large documents) for up to 90% cost savings.

### Automatic Caching (Simplest)

```python
response = client.messages.create(
    model="claude-opus-4-5-20250929",
    max_tokens=4096,
    cache_control={"type": "ephemeral"},  # Top-level: cache everything cacheable
    system="You are an AI assistant for analyzing Google Drive files...",
    messages=[{"role": "user", "content": "What's in my Drive?"}],
    tools=tools,
)
```

### Explicit Cache Breakpoints (Fine-Grained)

```python
response = client.messages.create(
    model="claude-opus-4-5-20250929",
    max_tokens=4096,
    system=[
        {
            "type": "text",
            "text": "You are an AI assistant...",
        },
        {
            "type": "text",
            "text": "<large_context>...</large_context>",
            "cache_control": {"type": "ephemeral"},  # Cache up to here
        },
    ],
    messages=[{"role": "user", "content": "Summarize the context."}],
)
```

**Rules:**
- Cache prefix must be at least **1,024 tokens** (4,096 for Haiku 4.5).
- Up to **4 cache breakpoints** per request.
- Default TTL is **5 minutes** (refreshed on each hit). 1-hour TTL available at 2× write cost.
- Cache processes in order: `tools` → `system` → `messages`. Changes to earlier elements invalidate later caches.
- Pricing: writes are 1.25× base input; reads are 0.1× base input.
- Changes to `tool_choice` or presence/absence of images invalidate the cache.

---

## 10. Handling Stop Reasons

| `stop_reason` | Meaning | Action |
|---|---|---|
| `end_turn` | Claude finished naturally | Extract text, conversation is done for this turn |
| `tool_use` | Claude wants to call tool(s) | Execute tools, send `tool_result`, call API again |
| `max_tokens` | Output was truncated | Retry with higher `max_tokens` |
| `stop_sequence` | Hit a custom stop sequence | Handle as needed |
| `pause_turn` | Server paused a long turn (server tools) | Append response and call again to continue |
| `compaction` | Context was compacted (beta) | Append response, continue — API handles the rest |

---

## 11. TypeScript / Node.js Syntax

```typescript
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic();

// Non-streaming
const response = await client.messages.create({
  model: "claude-opus-4-5-20250929",
  max_tokens: 4096,
  thinking: { type: "enabled", budget_tokens: 5000 },
  system: "You are a helpful assistant.",
  messages: [{ role: "user", content: "Hello" }],
  tools: [
    {
      name: "get_weather",
      description: "Get weather for a city. Returns temp and conditions.",
      input_schema: {
        type: "object",
        properties: { city: { type: "string" } },
        required: ["city"],
      },
    },
  ],
});

// Streaming
const stream = client.messages.stream({
  model: "claude-opus-4-5-20250929",
  max_tokens: 4096,
  messages: [{ role: "user", content: "Explain quantum computing." }],
});

for await (const text of stream) {
  if (text.type === "content_block_delta" && text.delta.type === "text_delta") {
    process.stdout.write(text.delta.text);
  }
}

// Or use the text stream helper
const stream2 = client.messages.stream({
  model: "claude-opus-4-5-20250929",
  max_tokens: 4096,
  messages: [{ role: "user", content: "Explain quantum computing." }],
});

stream2.on("text", (text) => process.stdout.write(text));
await stream2.finalMessage();
```

---

## 12. Quick Reference

| Setting | Value |
|---|---|
| Model | `claude-opus-4-5-20250929` |
| Upgrade | `claude-opus-4-6` (same price, better) |
| Thinking | `thinking: {type: "enabled", budget_tokens: N}` |
| API endpoint | `POST /v1/messages` |
| Auth header | `x-api-key: $ANTHROPIC_API_KEY` |
| Version header | `anthropic-version: 2023-06-01` |
| Stream param | `stream: true` |
| Text delta event | `content_block_delta` with `text_delta` |
| Tool call block type | `tool_use` (in response content) |
| Tool output type | `tool_result` with `tool_use_id` |
| Stop reason for tools | `stop_reason: "tool_use"` |
| Stop reason for done | `stop_reason: "end_turn"` |
| Compaction (server) | `context_management.edits: [{type: "compact_20260112"}]` |
| Prompt caching | `cache_control: {type: "ephemeral"}` |
| Pricing (Opus 4.5) | $5 / $25 per MTok (input / output) |
| Cache read pricing | 0.1× base input |

---

## 13. Key Differences from OpenAI's Responses API

| Concept | OpenAI (Responses API) | Anthropic (Messages API) |
|---|---|---|
| Endpoint | `/v1/responses` | `/v1/messages` |
| State management | `previous_response_id` (server-side) | Stateless — send full `messages` array |
| Tool output role | `function_call_output` with `call_id` | `tool_result` with `tool_use_id` in a `user` message |
| Tool result placement | Flat in `input_items` | Inside a `user` message, before any text |
| Loop signal | No tool calls in output = done | `stop_reason: "end_turn"` = done |
| Reasoning config | `reasoning: {effort: "xhigh"}` | `thinking: {type: "enabled", budget_tokens: N}` |
| Compaction trigger | `context_management: [{type: "compaction", compact_threshold: N}]` | `context_management: {edits: [{type: "compact_20260112", trigger: {type: "input_tokens", value: N}}]}` |
| Streaming text event | `response.output_text.delta` | `content_block_delta` with `delta.type: "text_delta"` |
| Conversations API | `conversation: {id: "..."}` | No equivalent — manage state client-side |

---

## 14. Key Documentation Links

- **Messages API Reference:** https://platform.claude.com/docs/en/api/messages
- **Tool Use Overview:** https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
- **How to Implement Tool Use:** https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use
- **Extended Thinking:** https://platform.claude.com/docs/en/build-with-claude/extended-thinking
- **Adaptive Thinking (Opus 4.6):** https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking
- **Streaming Messages:** https://platform.claude.com/docs/en/build-with-claude/streaming
- **Compaction:** https://platform.claude.com/docs/en/build-with-claude/compaction
- **Context Editing:** https://platform.claude.com/docs/en/build-with-claude/context-editing
- **Prompt Caching:** https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- **Models Overview:** https://platform.claude.com/docs/en/about-claude/models/overview
- **Pricing:** https://platform.claude.com/docs/en/about-claude/pricing
- **Writing Tools for Agents (Blog):** https://www.anthropic.com/engineering/writing-tools-for-agents
- **Agent SDK:** https://platform.claude.com/docs/en/agent-sdk/overview
- **Agent Loop Explained:** https://platform.claude.com/docs/en/agent-sdk/agent-loop
- **Python SDK:** https://github.com/anthropics/anthropic-sdk-python
- **TypeScript SDK:** https://github.com/anthropics/anthropic-sdk-typescript