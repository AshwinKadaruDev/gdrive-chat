# OpenAI Agentic Chat — Developer Reference

> Model: **`gpt-5.2`** · API: **Responses API (`/v1/responses`)** · Reasoning: **`xhigh`**

---

## 1. Why the Responses API (Not Chat Completions)

OpenAI's Responses API is the recommended path for all new agentic work. Key advantages over Chat Completions:

- **Agentic by default** — the model can call multiple tools (built-in or custom functions) within a single API request, looping internally before returning.
- **Stateful by default** — use `previous_response_id` to chain turns without manually resending full history.
- **Better reasoning performance** — reasoning items (chain-of-thought) persist between tool calls within a turn, yielding higher intelligence on tool-use decisions.
- **40–80% better cache utilization** than Chat Completions in OpenAI's internal benchmarks.

**Endpoint:** `POST https://api.openai.com/v1/responses`

---

## 2. Model & Reasoning Configuration

```
Model ID:         gpt-5.2
Snapshot:         gpt-5.2-2025-12-11
Context window:   400,000 tokens
Max output:       128,000 tokens
Knowledge cutoff: Aug 31, 2025
```

### Reasoning Effort

GPT-5.2 supports: `none` (default), `low`, `medium`, `high`, `xhigh`.

**Important:** The default for GPT-5.2 is `none`. You must explicitly set it higher. For maximum reasoning quality on agentic tasks, use `xhigh`.

```python
response = client.responses.create(
    model="gpt-5.2",
    reasoning={"effort": "xhigh"},
    input=[{"role": "user", "content": "..."}],
    tools=[...],
)
```

---

## 3. The Agentic Loop — How It Works

The core pattern: call the Responses API → check if the model returned tool calls → execute them → feed results back → repeat until the model returns a final text response.

### 3a. Non-Streaming Agent Loop (Python)

```python
from openai import OpenAI
import json

client = OpenAI()

# Define your tools
tools = [
    {
        "type": "function",
        "name": "get_weather",
        "description": "Get current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name"}
            },
            "required": ["city"],
            "additionalProperties": False,
        },
    }
]

# Your tool implementations
def execute_tool(name: str, args: dict) -> str:
    if name == "get_weather":
        # Your actual implementation here
        return json.dumps({"temp": "72F", "condition": "sunny"})
    return json.dumps({"error": "Unknown tool"})


def run_agent(user_message: str, max_iterations: int = 10):
    input_items = [{"role": "user", "content": user_message}]

    for i in range(max_iterations):
        response = client.responses.create(
            model="gpt-5.2",
            reasoning={"effort": "xhigh"},
            instructions="You are a helpful assistant.",
            input=input_items,
            tools=tools,
        )

        # Collect tool calls from output
        tool_calls = [item for item in response.output if item.type == "function_call"]

        if not tool_calls:
            # No tool calls = final response
            return response.output_text

        # Append the model's output (including reasoning items) to input
        input_items += response.output

        # Execute each tool call and append results
        for tool_call in tool_calls:
            args = json.loads(tool_call.arguments)
            result = execute_tool(tool_call.name, args)
            input_items.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": result,
            })

    return "Max iterations reached."
```

**Key points:**
- `response.output` contains a list of items: reasoning items, function_call items, and/or message items.
- You must append **all** output items (including reasoning) back to `input_items` before the next call — this preserves the model's chain-of-thought and avoids re-reasoning.
- The loop exits when the model returns a text message without any tool calls.

### 3b. Using `previous_response_id` (Stateful Chaining)

Instead of manually accumulating `input_items`, you can let OpenAI store the conversation server-side:

```python
response = client.responses.create(
    model="gpt-5.2",
    reasoning={"effort": "xhigh"},
    input=[{"role": "user", "content": "What's the weather in Paris?"}],
    tools=tools,
)

# For next turn, just pass the new input + previous response ID
response2 = client.responses.create(
    model="gpt-5.2",
    reasoning={"effort": "xhigh"},
    previous_response_id=response.id,
    input=[{
        "type": "function_call_output",
        "call_id": response.output[0].call_id,
        "output": '{"temp": "18C", "condition": "cloudy"}',
    }],
    tools=tools,
)
```

This avoids sending the full conversation each turn. The server reconstructs context from the stored response chain.

---

## 4. Streaming the Final Response

For a chat agent, you want to stream the model's final text response back to the user in real-time. Set `stream=True`.

### 4a. Basic Streaming

```python
stream = client.responses.create(
    model="gpt-5.2",
    reasoning={"effort": "xhigh"},
    input=[{"role": "user", "content": "Explain quantum computing."}],
    stream=True,
)

for event in stream:
    if event.type == "response.output_text.delta":
        print(event.delta, end="", flush=True)
    elif event.type == "response.completed":
        break
```

### 4b. Streaming in the Agentic Loop

The trick: run non-streaming calls during the tool-calling loop (for speed/simplicity), then stream only the final response. Or stream every call and filter events.

**Approach 1 — Stream only the final call:**

```python
def run_agent_stream_final(user_message: str, max_iterations: int = 10):
    input_items = [{"role": "user", "content": user_message}]

    for i in range(max_iterations):
        # Non-streaming call during tool-use iterations
        response = client.responses.create(
            model="gpt-5.2",
            reasoning={"effort": "xhigh"},
            instructions="You are a helpful assistant.",
            input=input_items,
            tools=tools,
        )

        tool_calls = [item for item in response.output if item.type == "function_call"]

        if not tool_calls:
            # Final response — now re-call with stream=True
            # (pass the same input to get the same response, streamed)
            # OR just return the non-streamed text:
            return response.output_text

        input_items += response.output

        for tool_call in tool_calls:
            args = json.loads(tool_call.arguments)
            result = execute_tool(tool_call.name, args)
            input_items.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": result,
            })

    return "Max iterations reached."
```

**Approach 2 — Stream every call, yield text deltas only on the final one:**

```python
async def run_agent_fully_streamed(user_message: str, max_iterations: int = 10):
    input_items = [{"role": "user", "content": user_message}]

    for i in range(max_iterations):
        tool_calls_in_progress = {}
        has_tool_calls = False
        full_output_items = []

        stream = client.responses.create(
            model="gpt-5.2",
            reasoning={"effort": "xhigh"},
            instructions="You are a helpful assistant.",
            input=input_items,
            tools=tools,
            stream=True,
        )

        for event in stream:
            # Accumulate function call arguments from stream
            if event.type == "response.output_item.added":
                if hasattr(event.item, 'type') and event.item.type == "function_call":
                    has_tool_calls = True
                    tool_calls_in_progress[event.output_index] = event.item

            elif event.type == "response.function_call_arguments.delta":
                idx = event.output_index
                if idx in tool_calls_in_progress:
                    tool_calls_in_progress[idx].arguments += event.delta

            # Stream text deltas to user (this is the final answer)
            elif event.type == "response.output_text.delta":
                yield event.delta  # Send chunk to user

            elif event.type == "response.completed":
                full_output_items = event.response.output

        if not has_tool_calls:
            return  # Done — text was already streamed via deltas

        # Execute tool calls and continue loop
        input_items += full_output_items

        for idx, tool_call in tool_calls_in_progress.items():
            args = json.loads(tool_call.arguments)
            result = execute_tool(tool_call.name, args)
            input_items.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": result,
            })
```

### 4c. Key Streaming Events

| Event | Purpose |
|---|---|
| `response.created` | Response object created |
| `response.output_item.added` | New output item (message, function_call, etc.) |
| `response.output_text.delta` | Text chunk of the final answer |
| `response.function_call_arguments.delta` | Chunk of function call arguments |
| `response.function_call_arguments.done` | Function call arguments complete |
| `response.output_text.done` | Full text of output part finalized |
| `response.completed` | Entire response is done |
| `error` | Error occurred |

---

## 5. Tool (Function) Definition Format

In the Responses API, tools use this structure:

```python
{
    "type": "function",
    "name": "search_database",
    "description": "Search the product database by query string. Returns top 5 matches.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (default 5)"
            }
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    "strict": True,  # Enables Structured Outputs — model output matches schema exactly
}
```

**Tool call output format** (what you send back after executing):

```python
{
    "type": "function_call_output",
    "call_id": "<call_id from the function_call item>",
    "output": "<string result — typically JSON-serialized>",
}
```

---

## 6. Conversation State Management

### Option A: Manual Input Array (Stateless)

You build and send the full `input` array each call. You control exactly what the model sees.

```
Turn 1: input = [user_msg]
Turn 2: input = [user_msg, ...response.output, tool_outputs]
Turn 3: input = [user_msg, ...response.output, tool_outputs, ...response2.output, tool_outputs2]
```

### Option B: `previous_response_id` (Stateful)

Let OpenAI reconstruct context. Each call only sends new items.

```python
response = client.responses.create(
    model="gpt-5.2",
    previous_response_id="resp_abc123",
    input=[{"role": "user", "content": "Now summarize the results."}],
    tools=tools,
)
```

### Option C: Conversations API

For persistent, cross-session state:

```python
response = client.responses.create(
    model="gpt-5.2",
    input=[{"role": "user", "content": "Hello"}],
    conversation={"id": "conv_xyz"},
)
```

---

## 7. Compaction (Long-Running Agents)

When context grows large, use compaction to shrink it while preserving key state.

### Server-Side (Automatic)

```python
response = client.responses.create(
    model="gpt-5.2",
    reasoning={"effort": "xhigh"},
    input=input_items,
    tools=tools,
    context_management=[{
        "type": "compaction",
        "compact_threshold": 200000,  # tokens
    }],
)
```

When token count crosses the threshold, the server auto-compacts mid-stream and emits a compaction item in the output. Pass it through to the next call as-is.

### Standalone Endpoint

```python
compacted = client.responses.compact(
    model="gpt-5.2",
    input=long_input_items,
)
# Use compacted.output as input for the next call
```

---

## 8. TypeScript / Node.js Syntax

```typescript
import OpenAI from "openai";

const client = new OpenAI();

// Non-streaming
const response = await client.responses.create({
  model: "gpt-5.2",
  reasoning: { effort: "xhigh" },
  input: [{ role: "user", content: "Hello" }],
  tools: [
    {
      type: "function",
      name: "get_weather",
      description: "Get weather for a city",
      parameters: {
        type: "object",
        properties: { city: { type: "string" } },
        required: ["city"],
        additionalProperties: false,
      },
    },
  ],
});

// Streaming
const stream = await client.responses.create({
  model: "gpt-5.2",
  reasoning: { effort: "xhigh" },
  input: [{ role: "user", content: "Explain quantum computing." }],
  stream: true,
});

for await (const event of stream) {
  if (event.type === "response.output_text.delta") {
    process.stdout.write(event.delta);
  }
}
```

---

## 9. Quick Reference

| Setting | Value |
|---|---|
| Model | `gpt-5.2` |
| Reasoning effort | `xhigh` |
| API endpoint | `POST /v1/responses` |
| Stream param | `stream: true` |
| Text delta event | `response.output_text.delta` |
| Tool call event | `response.function_call_arguments.delta` |
| Tool output type | `function_call_output` with `call_id` |
| State chaining | `previous_response_id` |
| Compaction | `context_management: [{type: "compaction", compact_threshold: N}]` |

---

## 10. Key Documentation Links

- **Responses API Migration Guide:** https://platform.openai.com/docs/guides/migrate-to-responses
- **Function Calling Guide:** https://platform.openai.com/docs/guides/function-calling
- **Streaming Guide:** https://platform.openai.com/docs/guides/streaming-responses
- **Reasoning Models:** https://platform.openai.com/docs/guides/reasoning
- **GPT-5.2 Model Guide:** https://platform.openai.com/docs/guides/latest-model
- **Conversation State:** https://developers.openai.com/api/docs/guides/conversation-state/
- **Compaction:** https://developers.openai.com/api/docs/guides/compaction/
- **Codex Agent Loop (blog):** https://openai.com/index/unrolling-the-codex-agent-loop/
- **Agents SDK (Python):** https://github.com/openai/openai-agents-python
- **WebSocket Mode (low-latency agentic):** https://developers.openai.com/api/docs/guides/websocket-mode/