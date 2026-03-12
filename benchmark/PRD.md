# Benchmark Suite — Product Requirements Document

## 1. Goal

Build an automated benchmark suite that runs every question from `qa_test.json` against the **existing FolderAgent** (imported directly from `backend/app/services/`), evaluates correctness via an LLM-as-judge, captures full agent reasoning traces, and presents results in a single-file HTML viewer.

The suite must be:
- **Separate** from the main app (lives in `benchmark/`, no coupling to routers or HTTP layer)
- **Non-invasive** to the existing agent code (one small, backward-compatible change)
- **Durable** — saves results incrementally, can resume interrupted runs
- **Concurrent** — runs multiple questions in parallel with rate-limit awareness

---

## 2. Architecture Overview

```
qa_test.json (golden questions + expected answers)
        │
        ▼
┌─────────────────┐    import    ┌──────────────────────────┐
│  run.py (CLI)   │ ──────────► │  FolderAgent.answer()    │
│  runner.py      │             │  LLMClient               │
│  (orchestrator) │             │  GoogleDriveService       │
└────────┬────────┘             │  execute_tool()           │
         │                      └──────────────────────────┘
         │                          │          │
         │                   Google Drive   OpenAI API
         │                    (live files)   (gpt-5.2)
         │
         ▼
┌─────────────────┐
│  evaluator.py   │ ──► OpenAI API (gpt-5.2, function calling)
│  (LLM judge)    │
└────────┬────────┘
         │
         ▼
   results/{timestamp}.json
         │
         ▼
   viewer.html (load JSON, filter, explore traces)
```

---

## 3. Auth & Token Strategy

The benchmark bypasses the HTTP layer entirely — it imports Python modules directly. But it still needs a valid **Google OAuth access token** for Drive API calls.

### Approach: Reuse tokens from the database

The user is already authenticated in the app. The runner will:

1. Connect to the same PostgreSQL database (using `DATABASE_URL` from `.env`)
2. Look up the user by email (configurable, defaults to the first user in the DB)
3. Call `get_valid_access_token(user, settings, db)` from `utils/security.py` — this handles token refresh automatically if expired
4. Pass the token to the agent for all Drive API calls

**Why this approach:**
- No manual token copying (short-lived tokens are annoying)
- Refresh logic is already built and tested
- Same auth path as production — the benchmark tests the real flow
- Requires only `DATABASE_URL`, `ENCRYPTION_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (all already in `.env`)

**Fallback**: If the user prefers not to hit the DB, they can pass `--access-token <token>` directly (e.g., grabbed from browser dev tools). But this expires in ~1 hour.

---

## 4. Agent Trace Capture

### The Problem

`FolderAgent.answer()` returns `AgentResponse(content, citations, iterations, hit_limit)` — just the final answer. For debugging, we need to see every iteration: what the LLM decided, which tools it called, what results came back, and how long each step took.

### Solution: Instrument `execute_tool` via wrapper

We do **not** modify the FolderAgent class. Instead, the benchmark wraps `execute_tool` at call time to intercept every tool invocation:

```python
# Conceptual — actual implementation in tracer.py
class TracingToolExecutor:
    """Wraps execute_tool to capture a full trace of the agent run."""

    def __init__(self):
        self.steps: list[TraceStep] = []

    async def execute_tool_traced(self, tool_name, tool_args, ...):
        start = time.monotonic()
        result_str, citations = await original_execute_tool(...)
        elapsed = time.monotonic() - start

        self.steps[-1].tool_calls.append(ToolCallRecord(
            name=tool_name,
            arguments=tool_args,
            result=result_str[:2000],  # truncate for storage
            citations_produced=len(citations),
            duration_sec=elapsed,
        ))
        return result_str, citations
```

To also capture LLM reasoning (the assistant's thinking before tool calls), we use `unittest.mock.patch` on `execute_tool` at the module level inside agent.py during the benchmark run. The trace also records each iteration boundary and the assistant's intermediate content.

**Implementation**: A `TracingFolderAgent` subclass that overrides `answer()` — duplicating the loop logic but adding trace collection at each step. This is ~80 lines of code, keeps the original agent untouched, and gives us full control over what we capture.

### Trace Data Structure

```python
@dataclass
class ToolCallTrace:
    name: str                  # e.g. "get_folder_structure"
    arguments: dict            # tool args the LLM provided
    result_preview: str        # first 2000 chars of result
    result_length: int         # full result length
    citations_produced: int
    duration_sec: float
    error: str | None = None

@dataclass
class IterationTrace:
    iteration: int
    assistant_content: str | None     # LLM's reasoning text (if any)
    tool_calls: list[ToolCallTrace]   # tools called this iteration
    is_final: bool                    # True if this was the final answer
    duration_sec: float               # wall time for this iteration

@dataclass
class AgentTrace:
    iterations: list[IterationTrace]
    total_duration_sec: float
    total_llm_calls: int
    total_tool_calls: int
    hit_limit: bool
```

---

## 5. Evaluator (LLM-as-Judge)

### Design

After the agent answers a question, we send the question + agent answer + golden answer to a **separate** LLM call (GPT-5.2, `reasoning: xhigh`) that returns a structured evaluation via **function calling**.

### Why function calling (not raw text)

- Guarantees consistent JSON structure across all 17 evaluations
- Easy to aggregate, filter, and query programmatically
- No regex parsing of free-form text
- The evaluator is forced to fill every field

### Evaluator Prompt

```
You are an expert evaluator for a document Q&A system. You are given:
1. The QUESTION that was asked
2. The EXPECTED ANSWER (ground truth from the test suite)
3. The AGENT'S ANSWER (what the system produced)
4. The EXPECTED SOURCES (files the answer should come from)
5. The AGENT'S SOURCES (files the agent actually cited)

Your job is to judge whether the agent's answer is correct, complete, and
properly sourced. Be strict but fair:
- Minor formatting differences are OK
- Rounding differences in numbers are OK (e.g., $2.14M vs $2,140,500)
- The agent may provide EXTRA correct information — that's fine
- But MISSING key facts or WRONG numbers are failures
- Source coverage matters: the agent should cite the right files
```

### Function Call Schema

```json
{
  "name": "submit_evaluation",
  "description": "Submit structured evaluation of the agent's answer",
  "parameters": {
    "type": "object",
    "required": ["verdict", "answer_score", "answer_reasoning",
                  "source_score", "source_reasoning",
                  "missing_facts", "hallucinated_facts",
                  "expected_sources", "found_sources",
                  "missed_sources", "extra_sources"],
    "properties": {
      "verdict": {
        "type": "string",
        "enum": ["pass", "partial", "fail"],
        "description": "pass = correct & complete, partial = mostly correct but missing details or minor errors, fail = wrong or significantly incomplete"
      },
      "answer_score": {
        "type": "integer",
        "minimum": 0, "maximum": 100,
        "description": "0-100 score for answer quality. 90+ = pass, 60-89 = partial, <60 = fail"
      },
      "answer_reasoning": {
        "type": "string",
        "description": "Explanation of why the answer received this score"
      },
      "source_score": {
        "type": "integer",
        "minimum": 0, "maximum": 100,
        "description": "0-100 score for source coverage"
      },
      "source_reasoning": {
        "type": "string",
        "description": "Explanation of source coverage assessment"
      },
      "missing_facts": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Key facts from the expected answer that the agent omitted"
      },
      "hallucinated_facts": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Claims the agent made that contradict the expected answer or aren't supported by sources"
      },
      "expected_sources": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Source files listed in the test suite"
      },
      "found_sources": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Expected sources that the agent DID cite (matched by file name)"
      },
      "missed_sources": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Expected sources that the agent did NOT cite"
      },
      "extra_sources": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Sources the agent cited that were not in the expected list"
      }
    }
  }
}
```

### Source Matching Logic

Source matching is fuzzy by design. The golden answer has paths like `"2. Finance/Monthly P&L - January 2026.xlsx"` but the agent's citations have `file_name` fields like `"Monthly P&L - January 2026.xlsx"`. The evaluator gets both and judges coverage — but we also do a **programmatic pre-match** before sending to the evaluator:

1. Extract file names from citation objects (`citation.file_name`)
2. For each expected source path, extract the basename (last segment)
3. Match if the agent's `file_name` contains the expected basename (case-insensitive)
4. Pass the pre-matched results to the evaluator as context so it can focus on judgment rather than string matching

---

## 6. Concurrency & Durability

### Concurrency Model

```
asyncio.Semaphore(concurrency)  # default: 3
    │
    ├── Question E1 ──► agent.answer() (3-8 LLM calls) ──► evaluator (1 LLM call)
    ├── Question E2 ──► agent.answer() ...
    ├── Question E3 ──► agent.answer() ...
    │   (E4 waits for semaphore)
    ├── Question E4 ──► ...
    └── ...
```

**Why concurrency=3 default**: Each agent run makes 3-15 LLM API calls (ReAct iterations). With 3 concurrent questions, that's 9-45 in-flight requests. OpenAI's rate limits for GPT-5.2 are generous but not unlimited. 3 is conservative enough to avoid 429s while providing ~3x speedup over sequential.

**Configurable**: `--concurrency N` flag. Set to 1 for debugging, up to 5 for aggressive parallelism.

### Rate Limit Handling

- **Per-question retry**: If the agent or evaluator gets a 429 (rate limit) or 5xx, retry that question up to 3 times with exponential backoff (5s, 15s, 45s)
- **No global retry queue**: Each question handles its own retries independently
- **Timeout**: Each question has a 5-minute wall-clock timeout. If exceeded, mark as `error` and move on

### Durability (Incremental Save + Resume)

Results are saved **after each question completes** (not at the end):

```python
async def run_question(q, results_path):
    result = await execute_and_evaluate(q)
    # Append to results file atomically
    append_result(results_path, result)
```

**File format**: The results file is written as a complete JSON after each question (read-modify-write with a temp file + rename for atomicity). This means if the process crashes mid-run, all completed questions are saved.

**Resume**: On startup, if a results file already exists for this run:
1. Load it and check which question IDs are already completed
2. Skip those questions
3. Continue with remaining questions
4. `--resume <results_file>` flag, or `--fresh` to force a new run

This is critical for the hard questions (H2 uses 6 files, could take 2+ minutes) — you don't want to lose 15 completed results because question 16 crashed.

---

## 7. Results JSON Schema

```jsonc
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "started_at": "2026-03-12T14:30:00Z",
  "completed_at": "2026-03-12T14:42:00Z",
  "config": {
    "model": "gpt-5.2",
    "evaluator_model": "gpt-5.2",
    "folder_id": "1ABC123...",
    "folder_url": "https://drive.google.com/drive/folders/1ABC123...",
    "max_iterations": 15,
    "concurrency": 3,
    "qa_file": "qa_test.json",
    "question_filter": null  // or ["E1", "M3", "H2"] if filtered
  },
  "summary": {
    "total": 17,
    "completed": 17,
    "pass": 12,
    "partial": 3,
    "fail": 2,
    "error": 0,
    "pass_rate_pct": 70.6,
    "pass_partial_rate_pct": 88.2,
    "avg_answer_score": 82.3,
    "avg_source_score": 78.1,
    "avg_iterations": 4.2,
    "avg_duration_sec": 45.3,
    "total_duration_sec": 720.0,
    "by_difficulty": {
      "easy":   { "total": 5, "pass": 5, "partial": 0, "fail": 0, "avg_score": 95.0 },
      "medium": { "total": 5, "pass": 4, "partial": 1, "fail": 0, "avg_score": 85.0 },
      "hard":   { "total": 7, "pass": 3, "partial": 2, "fail": 2, "avg_score": 68.0 }
    }
  },
  "results": [
    {
      "id": "E1",
      "difficulty": "easy",
      "persona": "New Employee",
      "department": "HR / Onboarding",
      "question": "What is the company's 401(k) match policy?",
      "expected_answer": "Meridian matches 100% of employee contributions up to 4%...",
      "expected_sources": [
        "3. Human Resources/3a. Policies/Benefits Guide 2026.pdf"
      ],

      // --- Agent output ---
      "agent_answer": "Based on the Benefits Guide...",
      "agent_citations": [
        {
          "file_id": "abc123",
          "file_name": "Benefits Guide 2026.pdf",
          "source_url": "https://drive.google.com/...",
          "location": null,
          "snippet": "401(k): 100% match up to 4%..."
        }
      ],
      "agent_iterations": 3,
      "agent_hit_limit": false,
      "duration_sec": 28.5,

      // --- Full trace ---
      "trace": [
        {
          "iteration": 1,
          "assistant_content": null,
          "tool_calls": [
            {
              "name": "get_folder_structure",
              "arguments": {},
              "result_preview": "[folder] 1. Leadership & Strategy...",
              "result_length": 2450,
              "citations_produced": 0,
              "duration_sec": 1.8,
              "error": null
            }
          ],
          "is_final": false,
          "duration_sec": 4.2
        },
        {
          "iteration": 2,
          "assistant_content": "I can see the Benefits Guide in the HR folder. Let me read it.",
          "tool_calls": [
            {
              "name": "get_file_content",
              "arguments": { "file_id": "xyz789" },
              "result_preview": "Content of Benefits Guide 2026.pdf:\n\n...",
              "result_length": 12000,
              "citations_produced": 1,
              "duration_sec": 3.1,
              "error": null
            }
          ],
          "is_final": false,
          "duration_sec": 8.5
        },
        {
          "iteration": 3,
          "assistant_content": "Based on the Benefits Guide, Meridian matches 100%...",
          "tool_calls": [],
          "is_final": true,
          "duration_sec": 15.8
        }
      ],

      // --- Evaluation ---
      "evaluation": {
        "verdict": "pass",
        "answer_score": 95,
        "answer_reasoning": "Agent correctly identified 100% match up to 4% with 3-year vesting.",
        "source_score": 100,
        "source_reasoning": "Agent cited the Benefits Guide, which is the expected source.",
        "missing_facts": [],
        "hallucinated_facts": [],
        "expected_sources": ["3. Human Resources/3a. Policies/Benefits Guide 2026.pdf"],
        "found_sources": ["Benefits Guide 2026.pdf"],
        "missed_sources": [],
        "extra_sources": []
      },

      // --- Error (null if successful) ---
      "error": null
    }
    // ... 16 more results
  ]
}
```

---

## 8. CLI Interface

```bash
# Run all questions
python benchmark/run.py --folder-url "https://drive.google.com/drive/folders/1ABC..."

# Run specific questions
python benchmark/run.py --folder-url "..." --questions E1 M3 H2

# Run only hard questions
python benchmark/run.py --folder-url "..." --difficulty hard

# Custom concurrency
python benchmark/run.py --folder-url "..." --concurrency 5

# Use a raw access token instead of DB
python benchmark/run.py --folder-url "..." --access-token "ya29.a0..."

# Specify user email for DB token lookup
python benchmark/run.py --folder-url "..." --user-email "user@example.com"

# Resume a previous run
python benchmark/run.py --resume benchmark/results/2026-03-12T143000.json

# Override model
python benchmark/run.py --folder-url "..." --model gpt-5.2
```

### PowerShell Launcher (`run_benchmark.ps1`)

```powershell
# Activates venv, sets PYTHONPATH, forwards all args to run.py
param([Parameter(ValueFromRemainingArguments)]$args)

$venv = "backend\.venv\Scripts\Activate.ps1"
if (Test-Path $venv) { & $venv }
$env:PYTHONPATH = "backend"
python benchmark/run.py @args
```

---

## 9. HTML Viewer

A **single file** (`viewer.html`) — no build step, no dependencies. Opens in any browser.

### Features

1. **File loader**: Drag-and-drop or file picker to load a results JSON
2. **Summary dashboard**:
   - Pass / Partial / Fail counts with color bars
   - Breakdown by difficulty (easy / medium / hard)
   - Average scores (answer + source)
   - Total run time, average iterations
3. **Results table**:
   - Columns: ID, Difficulty, Question (truncated), Verdict, Answer Score, Source Score, Iterations, Duration
   - Color-coded rows: green (pass), yellow (partial), red (fail), gray (error)
   - Click column headers to sort
   - Filter dropdowns: difficulty, verdict, department
   - Free-text search across questions and answers
4. **Detail panel** (click a row to expand):
   - Full question and expected answer
   - Agent's answer (side-by-side with expected)
   - Evaluation reasoning
   - Missing facts / hallucinated facts (highlighted)
   - Source coverage table (expected vs found vs missed)
   - **Full trace timeline**: collapsible per-iteration view showing:
     - LLM thinking text
     - Each tool call: name, args, result preview (expandable to full), duration
     - Iteration timing
5. **Export**: Button to copy summary stats as Markdown (for pasting into PRs/docs)

### Tech

- Vanilla HTML + CSS + JavaScript (no frameworks)
- CSS Grid/Flexbox layout
- Dark theme (matches the app aesthetic)
- `<template>` elements for row rendering
- JSON loaded via FileReader API
- All state in memory (no persistence needed)

---

## 10. File Structure

```
benchmark/
├── PRD.md                  # ← this document
├── run.py                  # CLI entry point (argparse, orchestration)
├── runner.py               # Question runner: agent invocation + trace capture
├── evaluator.py            # LLM-as-judge with function calling
├── models.py               # Dataclasses for trace, evaluation, results
├── auth.py                 # DB-based token retrieval + refresh
├── config.py               # BenchmarkConfig dataclass + CLI arg parsing
├── viewer.html             # Single-file results viewer
├── run_benchmark.ps1       # PowerShell launcher
└── results/                # Output directory
    └── .gitkeep
```

**No new dependencies** — the benchmark uses the same packages as the backend (openai, httpx, sqlalchemy, cryptography, openpyxl). No `requirements.txt` needed.

---

## 11. Detailed Module Specs

### `run.py` — Entry Point

- Parse CLI args via `argparse`
- Load `qa_test.json` and filter questions based on `--questions` / `--difficulty`
- Resolve auth (DB lookup or `--access-token`)
- Extract `folder_id` from `--folder-url` (regex: same as `routers/projects.py`)
- Create or resume results file
- Call `runner.run_benchmark(questions, config)`
- Print summary table to terminal on completion
- Exit code: 0 if all pass, 1 if any fail/error

### `runner.py` — Orchestrator

```python
async def run_benchmark(questions, config) -> BenchmarkResults:
    semaphore = asyncio.Semaphore(config.concurrency)
    results = load_existing_results(config.results_path)  # resume support

    pending = [q for q in questions if q["id"] not in results.completed_ids]

    tasks = [run_single(q, semaphore, config) for q in pending]
    for coro in asyncio.as_completed(tasks):
        result = await coro
        results.add(result)
        save_results(config.results_path, results)  # incremental save
        print_progress(result, results)              # live terminal output

    results.finalize()  # compute summary stats
    save_results(config.results_path, results)
    return results
```

```python
async def run_single(question, semaphore, config) -> QuestionResult:
    async with semaphore:
        for attempt in range(config.max_retries):
            try:
                # 1. Run agent with tracing
                agent_result, trace = await run_agent_traced(
                    question=question["question"],
                    folder_id=config.folder_id,
                    access_token=config.access_token,
                    config=config,
                )

                # 2. Evaluate
                evaluation = await evaluate_answer(
                    question=question,
                    agent_answer=agent_result.content,
                    agent_citations=agent_result.citations,
                    config=config,
                )

                return QuestionResult(
                    question=question,
                    agent_result=agent_result,
                    trace=trace,
                    evaluation=evaluation,
                )

            except (RateLimitError, APIConnectionError) as e:
                if attempt < config.max_retries - 1:
                    wait = config.retry_base_sec * (3 ** attempt)  # 5, 15, 45
                    log(f"Retrying {question['id']} in {wait}s: {e}")
                    await asyncio.sleep(wait)
                else:
                    return QuestionResult(
                        question=question,
                        error=f"Failed after {config.max_retries} retries: {e}",
                    )

            except asyncio.TimeoutError:
                return QuestionResult(
                    question=question,
                    error="Timed out after 5 minutes",
                )
```

### `runner.py` — `run_agent_traced()`

This is where trace capture happens. Creates a `TracingFolderAgent` (subclass) that records each iteration:

```python
async def run_agent_traced(question, folder_id, access_token, config):
    llm_client = LLMClient(openai_api_key=config.openai_api_key)
    drive_service = GoogleDriveService()
    agent = TracingFolderAgent(
        llm_client=llm_client,
        drive_service=drive_service,
        model=config.model,
        max_iterations=config.max_iterations,
    )

    start = time.monotonic()
    response = await asyncio.wait_for(
        agent.answer(question, folder_id, access_token),
        timeout=config.question_timeout_sec,
    )
    total_time = time.monotonic() - start

    trace = AgentTrace(
        iterations=agent.trace_iterations,
        total_duration_sec=total_time,
        total_llm_calls=len(agent.trace_iterations),
        total_tool_calls=sum(len(it.tool_calls) for it in agent.trace_iterations),
        hit_limit=response.hit_limit,
    )
    return response, trace
```

### `evaluator.py` — LLM Judge

```python
async def evaluate_answer(question, agent_answer, agent_citations, config) -> Evaluation:
    # Pre-match sources programmatically
    expected_basenames = [path.split("/")[-1] for path in question["sources"]]
    agent_filenames = [c.file_name for c in agent_citations]

    found = []
    missed = []
    for expected in expected_basenames:
        if any(expected.lower() in af.lower() for af in agent_filenames):
            found.append(expected)
        else:
            missed.append(expected)

    extra = [af for af in agent_filenames
             if not any(eb.lower() in af.lower() for eb in expected_basenames)]

    # Build evaluator prompt
    prompt = build_evaluator_prompt(
        question=question["question"],
        expected_answer=question["expected_answer"],
        agent_answer=agent_answer,
        expected_sources=question["sources"],
        agent_sources=agent_filenames,
        pre_matched={"found": found, "missed": missed, "extra": extra},
    )

    # Call OpenAI with function calling
    response = await openai_client.responses.create(
        model=config.evaluator_model,
        input=[{"role": "user", "content": prompt}],
        tools=[EVALUATION_TOOL_SCHEMA],
        tool_choice={"type": "function", "name": "submit_evaluation"},
        reasoning={"effort": "high"},
    )

    # Extract function call arguments
    evaluation_data = parse_function_call(response)
    return Evaluation(**evaluation_data)
```

### `auth.py` — Token Retrieval

```python
async def get_access_token_from_db(user_email=None) -> str:
    """Connect to DB, find user, return valid access token."""
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async with AsyncSession(engine) as db:
        if user_email:
            user = await db.execute(
                select(User).where(User.email == user_email)
            )
        else:
            user = await db.execute(
                select(User).order_by(User.created_at.asc()).limit(1)
            )
        user = user.scalar_one_or_none()
        if not user:
            raise RuntimeError("No user found in database")

        token = await get_valid_access_token(user, settings, db)
        await db.commit()  # persist refreshed token if needed
        return token
```

---

## 12. Terminal Output

During the run, print live progress:

```
Benchmark: 17 questions | concurrency: 3 | model: gpt-5.2
──────────────────────────────────────────────────────────

[1/17] E1  PASS  (score: 95, 3 iters, 28.5s)  What is the company's 401(k) match...
[2/17] E3  PASS  (score: 88, 4 iters, 35.2s)  Who is the CEO and when was...
[3/17] E2  PASS  (score: 92, 2 iters, 22.1s)  What is the expense approval...
[4/17] M1  PARTIAL (score: 72, 6 iters, 48.3s) How did our actual revenue...
[5/17] E4  PASS  (score: 97, 3 iters, 25.0s)  What are the brand colors...
...

══════════════════════════════════════════════════════════
RESULTS SUMMARY
──────────────────────────────────────────────────────────
Total:    17 | Pass: 12 | Partial: 3 | Fail: 2 | Error: 0
Pass Rate: 70.6% | Pass+Partial: 88.2%

By Difficulty:
  Easy:   5/5  (100%)  avg score: 95.0
  Medium: 4/5  ( 80%)  avg score: 85.0
  Hard:   3/7  ( 42%)  avg score: 68.0

Avg iterations: 4.2 | Avg time: 45.3s | Total: 12m 0s
Results: benchmark/results/2026-03-12T143000.json
══════════════════════════════════════════════════════════
```

---

## 13. Edge Cases & Error Handling

| Scenario | Handling |
|----------|----------|
| Agent errors on a question (LLM crash, Drive API fail) | Catch, retry up to 3x. If all retries fail, record as `error` with error message. Don't crash the run. |
| Evaluator LLM call fails | Retry 2x. If still fails, set evaluation to `null` — the agent's answer and trace are still saved. |
| Google token expires mid-run | If using DB mode, `get_valid_access_token` auto-refreshes. If using `--access-token`, fail gracefully and tell user to provide a fresh token. |
| Rate limit (429) from OpenAI | Exponential backoff per-question (5s, 15s, 45s). The semaphore already limits concurrency. |
| Question times out (>5 min) | `asyncio.wait_for` raises `TimeoutError`. Record as error, continue. |
| Results file corrupted | On resume, validate JSON. If invalid, prompt user to start fresh. |
| Agent calls `request_clarification` | Treat as a failure — the benchmark has no human to clarify. Record the clarification request in the trace. |
| Agent calls `report_inability` | Record as the agent's answer. The evaluator will likely mark it as `fail`. |
| Partial results from Ctrl+C | Incremental save means everything up to the interrupt is preserved. |

---

## 14. Future Enhancements (Out of Scope Now)

- **Regression tracking**: Compare results across runs (same questions, different models/prompts)
- **Cost tracking**: Sum up token usage per question from OpenAI response metadata
- **Custom question sets**: Support multiple JSON test files
- **Prompt A/B testing**: Run with different system prompts and compare
- **CI integration**: Run as a GitHub Action on PR, fail if pass rate drops below threshold
- **Streaming viewer**: Watch results appear in the HTML viewer in real-time (WebSocket or polling)
