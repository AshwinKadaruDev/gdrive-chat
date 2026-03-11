# Building LLM Agents: A Complete Framework

A research-backed guide synthesizing best practices from OpenAI, Anthropic, and production deployments.

---

## 1. What an Agent Actually Is (and Isn't)

An agent is an LLM that operates in a loop, using tools and making decisions until a task is complete. The critical distinction both OpenAI and Anthropic make:

- **Not an agent**: A chatbot answering questions. A single LLM call. A sentiment classifier.
- **An agent**: A system where the LLM manages workflow execution, decides which tools to call, recognizes when it's done, and can self-correct.

The core characteristics (from OpenAI's practical guide):

1. It uses an LLM to manage workflow execution and make decisions
2. It recognizes when a workflow is complete and can proactively correct its actions
3. In case of failure, it can halt execution and transfer control back to the user
4. It has access to tools and dynamically selects the appropriate ones

**The simplest possible agent is a while loop:**

```python
messages = [system_prompt, user_message]

for i in range(max_iterations):
    response = llm.call(messages, tools=tool_definitions)

    if response.has_tool_calls:
        for tool_call in response.tool_calls:
            result = execute_tool(tool_call.name, tool_call.args)
            messages.append(tool_result(tool_call.id, result))
    else:
        break  # Agent is done
```

That's the entire architecture. Everything else is details about what goes into the system prompt, how tools are designed, and how to manage the growing message history.

---

## 2. When to Build an Agent (and When Not To)

Both OpenAI and Anthropic strongly emphasize starting simple:

**Anthropic's core advice**: "Find the simplest solution possible, and only increase complexity when needed. This might mean not building agentic systems at all."

**Build an agent when your workflow has:**

- Complex decision-making requiring nuanced judgment (e.g., fraud analysis, refund approval)
- Rules that are difficult to maintain as if-then-else chains
- Heavy reliance on unstructured data (documents, natural language, conversations)
- Tasks that need self-correction based on intermediate results

**Don't build an agent when:**

- A single LLM call with good prompting and retrieval solves the problem
- The workflow is fully deterministic (use conventional code)
- You need guaranteed, reproducible outputs every time
- The task doesn't involve judgment or ambiguity

**The cost tradeoff**: Agents trade latency and token cost for better task performance on complex workflows. A simple retrieval + LLM call might take 2 seconds and cost $0.01. An agent loop might take 30 seconds and cost $0.50. Make sure the complexity is worth it.

---

## 3. The Three Foundations

Both OpenAI and Anthropic converge on three core components:

### 3.1 The Model

**Start with the most capable model, then optimize down.** Prototype with the best model available to establish a performance baseline. Only swap in smaller/cheaper models once you have evals proving they maintain acceptable quality.

Different tasks within the same agent can use different models. Intent classification might use a small, fast model. Complex reasoning might need a large model. Don't prematurely optimize.

### 3.2 Tools

Tools are how the agent interacts with the world: reading data, taking actions, calling APIs. They are the most critical design decision you'll make.

### 3.3 Instructions (System Prompt)

The system prompt defines the agent's behavior, persona, and decision-making rules. It is the single most important lever for agent reliability. Clear instructions reduce ambiguity and improve decision-making.

---

## 4. Tool Design — The Heart of Agent Engineering

Tool design determines whether your agent works well or fails catastrophically. This section synthesizes the best practices from across the ecosystem.

### 4.1 The Core Principle: LLM Decides, Code Executes

This is the fundamental split of responsibilities:

| Responsibility | Who Handles It |
|---|---|
| "Which operation do I need next?" | The LLM (reasoning) |
| "What arguments should I pass?" | The LLM (reasoning) |
| "Execute the operation correctly" | Your code (deterministic) |
| "Handle edge cases and safety" | Your code (deterministic) |
| "Interpret the result and decide what's next" | The LLM (reasoning) |

The model never runs your code directly. It outputs structured JSON saying "call function X with arguments Y." Your code executes that deterministically. This division means all judgment lives in the LLM, all reliability lives in the code.

### 4.2 The Three Categories of Tools

OpenAI categorizes tools into three types. Every tool you build falls into one:

**Data tools** — Retrieve context and information. Query databases, read documents, search the web, fetch API data. The agent needs to see before it can act.

**Action tools** — Interact with systems to make changes. Send emails, update records, create tickets, write files. These are the tools that "do things."

**Orchestration tools** — Other agents invoked as tools. A "refund agent" called by a "customer service agent." This is how multi-agent systems are composed.

A complementary framework from the community adds a useful lens — assess whether your agent has balanced capabilities across data access, computation, and actions. An agent that can read data but can't act on it is useless. An agent that can act but can't compute is dangerous.

### 4.3 What Makes a Good Tool Definition

The LLM reads your tool's JSON schema like a developer reads API docs. Quality of description directly impacts whether the model uses the tool correctly.

**Naming**: Use verb phrases that describe what the tool does. `delete_rows_matching` is good. `process_rows` or `row_handler` is bad. The model uses the name to find the right tool.

**Description**: Include what the tool does, when to use it, and safety guarantees. Include example use cases so the model can discover the tool. Mention what it will NOT do.

```json
{
  "name": "delete_rows_matching",
  "description": "Delete all rows where any cell matches a regex pattern. The header row is NEVER deleted even if it matches. Use this to remove summary rows, totals, empty rows, or other non-data rows.",
  "parameters": {
    "type": "object",
    "properties": {
      "pattern": {
        "type": "string",
        "description": "Regex pattern — rows where ANY cell matches will be deleted"
      },
      "column": {
        "type": "string",
        "description": "Optional: limit matching to a specific column (by letter like 'A' or by header name)"
      }
    },
    "required": ["pattern"]
  }
}
```

What makes this good:

- The name is a verb phrase — instantly clear
- Description explains behavior AND safety guarantees ("header row is NEVER deleted")
- Includes use cases ("summary rows, totals, empty rows")
- Parameter descriptions are specific about accepted formats
- Only `pattern` is required; `column` has a sensible default

**Parameters**: Minimize required parameters. Provide sensible defaults. Accept multiple input formats where possible (column letter OR column name). The model shouldn't need to provide 5 arguments every time.

### 4.4 What Should Be a Tool vs. a Prompt Instruction

This is one of the most important design decisions:

**Make it a tool when:**

- It involves doing something to state (reading data, mutating data, calling an API)
- It requires deterministic execution (regex matching, calculations, row deletion)
- It needs to return structured data the model will reason about
- Getting it wrong would corrupt data or cause silent errors

**Leave it to the prompt when:**

- It's a judgment call ("Is this a header row?" "Does this look like a summary?")
- It's sequencing logic ("First inspect, then transform, then validate")
- It requires domain knowledge ("Financial reports usually have totals at the bottom")
- It's about when to stop ("The data looks clean enough")

**Concrete example**: Don't build a `find_header_row()` tool that guesses which row is the header. Instead, build a `view_rows()` tool that shows raw data and a `set_header_row(row_number)` tool that sets a specific row. The decision about which row is the header requires judgment (the LLM). The action of marking it requires precise state mutation (the tool).

### 4.5 Tool Design Patterns

**Pattern 1: Observation tools return formatted, bounded data.**

Don't dump 10,000 rows into the context window. Return human-readable, truncated summaries with sensible defaults (`count=20`, `max_columns=20`). Label values clearly: `A(Date)=01/15` tells the model both the column letter and header name.

**Pattern 2: Transform tools report what they did.**

Return human-readable summaries: "Deleted 4 rows before row 5. New row count: 96." Not raw JSON. Not just "OK." The model needs to verify its actions had the intended effect. If it expected to delete 4 rows and the tool says "Deleted 0," it knows to try a different approach.

**Pattern 3: Tools accept multiple input formats.**

The model might refer to a column as `"A"`, `"Date"`, or `"date"`. Your tool should handle all of these internally. Flexibility in input, strictness in execution.

**Pattern 4: Validation is an explicit tool, not a side effect.**

Let the model choose when to validate. It can batch 5 transformations then validate, or validate after each change. Don't waste tokens on validation results the model didn't ask for.

**Pattern 5: Compound operations for common multi-step tasks.**

If something is conceptually one operation but mechanically complex (find rows matching a pattern, propagate values, delete originals), make it one tool. The model thinks in terms of intent. But don't bundle unrelated operations.

**Pattern 6: Explicit failure paths.**

Give the model a way to say "I can't do this." Without a `report_failure()` tool, a stuck model loops uselessly for 40 iterations, burning money and time.

### 4.6 Tool Anti-Patterns

- **Vague descriptions**: "Process the data" — the model won't know when to use this
- **Too many required parameters**: Forces the model to provide everything every time
- **Returning raw JSON**: Wastes tokens and the model has to parse it
- **No safety rails**: The model can accidentally delete everything; bake protection into the tool
- **Overly granular tools**: `set_cell_value()` would need 400 calls for a 100-row spreadsheet. Use `delete_rows_matching(pattern)` instead — match the level of human intent

### 4.7 How Many Tools Is Too Many?

OpenAI's practical guide: "The issue isn't solely the number of tools, but their similarity or overlap. Some implementations successfully manage more than 15 well-defined, distinct tools while others struggle with fewer than 10 overlapping tools."

If the model is picking the wrong tools, first try improving tool descriptions (names, parameters, use cases). Only split into multiple agents if clarity improvements don't help.

### 4.8 Push Safety Into Tools, Not Prompts

This is a critical principle: Prompts can be forgotten or misinterpreted. Code is absolute.

If the header row should never be deleted, don't put "never delete the header row" in the prompt. Put `if row_idx == header_row: continue` in the tool implementation. The model doesn't need to remember the constraint — the tool enforces it unconditionally.

---

## 5. Instructions and System Prompt Design

### 5.1 Best Practices from OpenAI

- **Use existing documents**: Convert SOPs, policy docs, and knowledge base articles into prompt-friendly instructions. Don't reinvent from scratch.
- **Break tasks into steps**: Dense resources become clearer as smaller, explicit steps.
- **Define clear actions**: Every step should correspond to a specific action or output. Be explicit about the action and even the wording of user-facing messages.
- **Capture edge cases**: Anticipate common variations. Include conditional branches: "If the user provides incomplete information, ask for X."
- **Use prompt templates**: Rather than maintaining separate prompts for each use case, use a single flexible base prompt with variables that adapt to context.

### 5.2 System Prompt Structure

A good agent system prompt typically includes:

1. **Role definition**: Who the agent is and what it does
2. **Available tools summary**: Brief overview of what tools exist (the detailed schemas are sent separately)
3. **Workflow instructions**: Step-by-step process for how to approach the task
4. **Decision-making rules**: When to use which tool, when to ask for clarification, when to stop
5. **Output format**: What the final output should look like
6. **Edge case handling**: What to do when things go wrong
7. **Safety constraints**: What the agent must never do

### 5.3 The Key Insight: Instructions Drive Reliability

The system prompt is where most agent failures originate and where most improvements come from. Before adding more tools or switching models, improve your instructions. Ambiguous instructions lead to ambiguous behavior.

---

## 6. Orchestration Patterns

### 6.1 Start with a Single Agent

Both OpenAI and Anthropic strongly recommend: maximize a single agent's capabilities first. Multi-agent systems add complexity and overhead. A single agent with well-designed tools can handle surprisingly complex workflows.

The single-agent pattern is a simple loop:

```
Input → Agent (tools + instructions) → [loop until done] → Output
```

Exit conditions for the loop: a final output is produced, the model responds without tool calls, an error occurs, or the maximum number of iterations is reached.

### 6.2 Anthropic's Workflow Patterns (Before Full Agents)

Anthropic identifies several patterns that are simpler than full agents but more capable than single LLM calls:

**Prompt chaining**: Task broken into sequential steps, each step's output feeds the next. Good when the task decomposes into fixed subtasks. Example: Generate outline → Validate outline → Write document.

**Routing**: Classify the input, then send it to a specialized handler. Example: Classify customer query → Route to billing/technical/sales handler.

**Parallelization**: Run multiple LLM calls simultaneously and aggregate results. Example: Evaluate a document against 5 different criteria in parallel.

**Orchestrator-worker**: A central LLM breaks the task into subtasks and delegates to workers. Example: "Research this topic" → Orchestrator assigns 3 research subtasks → Workers execute → Orchestrator synthesizes.

**Evaluator-optimizer**: One LLM generates, another evaluates, loop until quality threshold is met. Example: Write code → Run tests → Fix failures → Retest.

### 6.3 When to Go Multi-Agent

Split into multiple agents only when:

- **Complex logic**: Your prompt has so many conditional branches that it's becoming unmaintainable
- **Tool overload**: You have overlapping tools and the model confuses them despite clear descriptions
- **Distinct domains**: Different parts of the workflow require fundamentally different expertise or tool sets

### 6.4 Multi-Agent Patterns

**Manager pattern**: A central agent delegates to specialized sub-agents via tool calls. The manager maintains context and synthesizes results. Best when you want one agent controlling the conversation.

**Decentralized (handoff) pattern**: Agents pass control to each other. A triage agent hands off to a sales agent or a support agent. Best when specialized agents should fully take over.

---

## 7. Memory and Context Engineering

### 7.1 The Core Problem

LLMs are stateless. Every call starts fresh. The "memory" is just the message history you send with each request. As the agent loops, the message history grows. Eventually it exceeds the context window.

This is the most critical engineering challenge for agents: providing the right information at the right time within token limits.

### 7.2 The Message History Is the Agent's Memory

In the basic agent loop, the full conversation — system prompt, user message, every assistant response, every tool call, every tool result — is sent to the LLM every iteration. This means:

- The agent can see everything it's done
- Context grows linearly with each iteration
- Eventually you hit the context window limit

### 7.3 Context Management Strategies

**Conversation trimming**: Keep only the last N turns. Simple but lossy — the agent may forget earlier important context.

**Summarization**: Use an LLM to summarize older messages, replacing them with a compact summary. Preserves meaning but adds latency and cost for the summarization call.

**Structured note-taking / scratchpads**: The agent writes important information to a separate store (file, database, state object) instead of relying on the message history. Key information persists even when conversation history is trimmed.

**Observation masking**: For tool results that are very large, truncate or mask older tool outputs while keeping recent ones intact. Research from JetBrains shows this can match LLM summarization in both cost savings and performance.

### 7.4 What Goes in Context

Think of the context window as a precious, finite resource. At each step, the agent sees:

- **System prompt**: Static instructions and role definition
- **User input**: The original request
- **Conversation history**: All prior turns (or a trimmed/summarized version)
- **Retrieved knowledge**: Documents, data, or context pulled from external sources
- **Tool results**: Output from recent tool calls

The engineering challenge is deciding what stays, what gets summarized, and what gets dropped. As one practitioner put it: "Most agent failures are not model failures — they are context failures."

### 7.5 Short-Term vs. Long-Term Memory

**Short-term memory**: The current context window. Recent turns, current tool outputs, active reasoning. Limited capacity, high fidelity.

**Long-term memory**: External storage (vector databases, key-value stores). User preferences, past interactions, learned patterns. Unlimited capacity, requires retrieval.

For agents that need to persist information across sessions, implement a memory system that stores facts/preferences externally and retrieves relevant ones into the context window at the start of each session.

---

## 8. Guardrails and Safety

### 8.1 Layered Defense

OpenAI's framework treats guardrails as layered defenses. No single guardrail is sufficient — use multiple, specialized ones:

- **Input guardrails**: Relevance classifiers, safety classifiers, PII filters, moderation
- **Tool guardrails**: Risk-rate each tool (low/medium/high), require human approval for high-risk actions
- **Output guardrails**: Validate responses align with brand values and policies
- **Rules-based protections**: Blocklists, input length limits, regex filters

### 8.2 Tool Risk Assessment

Assign a risk rating to each tool based on:

- Read-only vs. write access
- Reversibility (can you undo it?)
- Required permissions
- Financial impact

Use ratings to trigger automated controls: low-risk tools execute freely, medium-risk tools log for review, high-risk tools pause for human approval.

### 8.3 Human-in-the-Loop

Two triggers for human intervention:

1. **Exceeding failure thresholds**: The agent has retried too many times or taken too many actions without progress
2. **High-risk actions**: Sensitive, irreversible, or high-stakes operations (canceling orders, authorizing refunds, making payments)

Always give the agent a way to escalate to a human. This is like the `report_failure()` tool — a graceful exit when the agent is stuck or the stakes are too high.

### 8.4 Bake Safety into Tools

Repeat of a critical principle: Safety constraints belong in tool implementations, not just in prompts. The model might forget a prompt instruction. It can't bypass a `if row_idx == header_row: continue` check.

---

## 9. Evaluation and Testing

### 9.1 Why Agent Evals Are Different

Traditional LLM evals test a single input→output pair. Agent evals must assess an entire trajectory: Was the right sequence of tools called? Were the arguments correct? Did the agent self-correct? Was the final outcome correct?

Agent evaluation is more like a "job performance review" than a school exam. You're assessing behavior, not just answers.

### 9.2 What to Evaluate

Evaluate at two levels:

**End-to-end**: Did the agent complete the task? Was the final output correct? How many iterations did it take? What was the cost?

**Component-level**: Did the agent select the correct tools? Were arguments valid? Did it call tools in the right order? Did it handle errors appropriately? This is where you find root causes.

### 9.3 The Eval Development Loop

1. **Establish a baseline**: Use the best model, measure task completion rate
2. **Build a golden dataset**: Create test cases with known-correct outcomes. Start with 20-50 representative examples.
3. **Automate grading**: Use deterministic checks where possible (did the output file match the schema?), LLM-as-judge for subjective quality
4. **Iterate**: Change instructions, tools, or models, re-run evals, measure improvement
5. **Regression test**: When you change anything, ensure you haven't broken previously passing cases

### 9.4 Practical Eval Approaches

**For coding agents**: Run tests against the output. Deterministic, cheap, reliable.

**For data processing agents**: Compare output against expected output files. Check schema conformance, row counts, data integrity.

**For conversational agents**: Use a second LLM to simulate users, then grade the transcript with rubrics for task completion and interaction quality.

**For any agent**: Track cost per task, iterations per task, and failure rate. These operational metrics matter as much as accuracy.

### 9.5 The Cold Start Problem

If you don't have test cases yet:

1. Generate realistic tasks with an LLM
2. Have an "expert" agent (best model, generous settings) produce ideal solutions
3. Have your actual agent try the same tasks
4. Score automatically by comparing against the ideal solutions

---

## 10. Practical Checklist: Building Your First Agent

### Phase 1: Validate the Use Case

- [ ] Does this task require judgment, not just rules?
- [ ] Would a single LLM call with good prompting solve it?
- [ ] Is the latency/cost tradeoff acceptable?
- [ ] Can you define what "success" looks like?

### Phase 2: Design Tools

- [ ] List the operations the agent needs to perform
- [ ] Categorize each as Data, Action, or Orchestration
- [ ] Design tools at the right abstraction level (human intent, not machine operations)
- [ ] Write clear descriptions with use cases and safety guarantees
- [ ] Minimize required parameters, provide sensible defaults
- [ ] Bake safety rails into implementations
- [ ] Make tools return human-readable summaries

### Phase 3: Write Instructions

- [ ] Define the agent's role and capabilities
- [ ] Provide step-by-step workflow
- [ ] Handle edge cases explicitly
- [ ] Include examples of good behavior
- [ ] Specify output format

### Phase 4: Build the Loop

- [ ] Implement the basic while loop (call LLM → execute tools → repeat)
- [ ] Set a maximum iteration count
- [ ] Handle errors gracefully (tool failures, parsing errors)
- [ ] Add a failure/escalation tool
- [ ] Log all tool calls and results

### Phase 5: Evaluate

- [ ] Create 20+ test cases covering common scenarios and edge cases
- [ ] Measure task completion rate, cost, and iteration count
- [ ] Identify failure modes and fix instructions/tools
- [ ] Add regression tests as you fix issues

### Phase 6: Optimize

- [ ] Try smaller models for simpler sub-tasks
- [ ] Implement context management (trimming, summarization) if loops are long
- [ ] Monitor production performance
- [ ] Add guardrails based on real-world failures

---

## 11. Key Principles Summary

1. **Start simple.** A single agent with a good prompt and well-designed tools goes further than you think. Add complexity only when measured evals show you need it.

2. **The model handles judgment; the code handles execution.** The LLM decides what to do. Your tools do it reliably, safely, and deterministically.

3. **Push safety into tools, not prompts.** Prompts can be forgotten. Code is absolute.

4. **Tools should match human intent.** Not `set_cell_value()` — that's machine-level. Use `rename_column()` — that's how humans think about the task.

5. **The system prompt is your biggest lever.** Before changing models, adding tools, or building multi-agent systems, improve your instructions.

6. **Context is everything.** Most agent failures are context failures, not model failures. Manage what the model sees at each step.

7. **Evals are non-negotiable.** You cannot improve what you cannot measure. Build evals before you optimize.

8. **Plan for failure.** Give the agent explicit ways to fail gracefully, escalate to humans, and report what went wrong.

---

## Sources

- OpenAI, "A Practical Guide to Building Agents" (2025)
- Anthropic, "Building Effective Agents" (2024)
- Anthropic, "Demystifying Evals for AI Agents" (2025)
- OpenAI Cookbook, "Context Engineering — Short-Term Memory Management" (2025)
- OpenAI Cookbook, "Context Engineering for Personalization" (2025)
- LangChain, "Context Engineering in Agents" documentation
- Amazon AWS, "Evaluating AI Agents: Real-World Lessons" (2025)
- Google Cloud, "Agent Factory: Agent Evaluation and Multi-Agent Systems" (2025)