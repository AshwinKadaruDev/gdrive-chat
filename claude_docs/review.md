# Codebase Audit

Audit this codebase for real code quality issues. **Do NOT fix anything** — only identify and document problems.

## Context

This is **Talk-to-a-Folder** — a Google Drive document chatbot built as a take-home interview project. Users sign in via Google OAuth, paste a Drive folder URL, the system indexes all documents (chunked + embedded into Azure AI Search), and they chat with a ReAct agent that searches and reasons over the corpus with citations.

The stack is: **FastAPI + SQLAlchemy async** (backend), **React 18 + TypeScript + Vite + Tailwind** (frontend), **Temporal** (durable sync pipeline), **Azure AI Search** (hybrid vector + keyword retrieval), **Claude / GPT-4o** (LLM), **OpenAI ada-002** (embeddings).

Every issue you surface should be evaluated through this lens: **is this production-ready? Would this cause bugs, security gaps, data loss, or a poor user experience in a real deployment?**

## Philosophy

The goal is code that is **simple, clean, and robust** — not clever, not over-engineered, not hacky.

- If something can be done in 5 lines, it shouldn't be 20. Prefer the straightforward, readable solution.
- But simplicity never comes at the cost of correctness, security, or extensibility.
- Follow established patterns: DRY, separation of concerns, single responsibility. But don't be dogmatic — a small amount of duplication is fine if the alternative is a premature abstraction.
- Industry-standard practices for auth, database access, error handling, and security. No homegrown solutions where battle-tested patterns exist.

## What to Review

### 1. Core Service Layer (highest priority)
Everything in `backend/app/services/` — agent, tool_executor, llm, azure_search, embeddings, google_drive — is the backbone of the application. Audit for:
- **Service instantiation**: Services are created per-request inside route handlers (not singletons). Is this appropriate, or does it cause unnecessary overhead (e.g., re-creating Azure Search clients on every chat message)?
- **Router/service separation**: Are route handlers (`routers/`) doing too much business logic, or is logic properly delegated to services?
- **RAG vs Drive consistency**: Two parallel code paths exist — RAG agent (Azure Search + indexed docs) and Drive agent (live Google Drive API). Are they cleanly separated? Do they share code that assumes one mode? Is there unjustified duplication?
- **Frontend hook duplication**: `useChat` and `useDriveChat` follow the same pattern. Same for `ChatContainer` and `DriveChatContainer`. Is this justified separation or copy-paste that should be unified?

### 2. Temporal Sync Pipeline
The worker runs a single workflow (`SyncFolderWorkflow`) with 6 sequential activities: crawl → extract → chunk → embed → generate questions → index. Audit for:

**Pipeline Design:**
- Is `SyncFolderWorkflow` pure orchestration with business logic in activities (Temporal best practice)?
- Files are processed sequentially (not in parallel). Is the sequential design correct and robust, even if slow for large folders?
- Failed files are logged and skipped — does the user know which files failed and why? Does the failure info surface through the polling endpoint?
- Retry policies, timeouts, and heartbeat configuration — are they appropriate for each activity's workload (e.g., 10 min for crawl, 5 min for extract)?

**Activity Quality:**
- **Idempotency**: Are activities safe to retry? Especially `index_chunks` (batch upsert to Azure Search) — could retries create duplicate chunks?
- **Credential handling**: `routers/sync.py` decrypts Google tokens and passes them as plain text in the Temporal workflow input (`SyncInput`). These are visible in the Temporal UI. This is a known issue — flag severity.
- **Dependency management**: Activities read `os.environ` directly (no DI). Is this consistent and acceptable, or are there activities that do it differently?
- **Rate limiting**: `generate_embeddings` has 0.5s inter-batch delay and retry logic. `generate_questions` has 1.0s delay. Are these sufficient? Any activity missing rate-limit handling?

**Worker Resilience:**
- Can `Dockerfile.worker` scale horizontally (multiple replicas) without conflicts?
- Is there anything in the worker setup that assumes single-instance (e.g., in-memory state, local file paths)?
- Worker connection retry (15 attempts, 3s intervals) — is this robust enough?

### 3. FolderAgent & Tool System
The `FolderAgent` (`services/agent.py`) runs a ReAct loop (max 15 iterations) with 16 tool handler functions dispatched by `tool_executor.py`. Two modes: RAG (13 tools, Azure Search) and Drive (12 tools, live API). Audit for:

**ReAct Loop Robustness:**
- What happens when the LLM returns malformed output (bad JSON, unexpected tool names, missing arguments)?
- What happens when a tool call fails mid-loop? Does the loop recover, surface the error to the LLM for reasoning, or silently break?
- What happens when the LLM API call itself fails (timeout, rate limit, 500)? Is there any retry or graceful degradation?
- Max 15 iterations with `hit_limit=True` fallback — does the partial answer mechanism work correctly? Does the user get useful feedback?

**Credential Injection Security:**
- `tool_executor.py` injects `project_id` and `access_token` server-side. The LLM provides tool arguments (query, file_id, etc.) but never receives credentials. Verify this is airtight — is there any code path where the LLM could influence which credentials are used, or where credentials could leak into LLM context?

**LLMClient Multi-Provider (`services/llm.py`):**
- Anthropic ↔ OpenAI message format conversion is complex: system message extraction, `tool_use` → `tool_result` block conversion, consecutive tool results merged into single user messages. Are there edge cases that silently corrupt the message history?
- Tool definition conversion (OpenAI function schema → Anthropic `input_schema`): any schema types that don't map cleanly?
- Provider fallback logic: if model contains `"claude"` but `ANTHROPIC_API_KEY` is missing, it falls back to OpenAI with `gpt-4o`. Is this fallback silent or logged? Could it surprise the user?

**Tool Handlers:**
- 16 handler functions in `tool_executor.py`. Are error boundaries consistent across all handlers? Does one failing handler crash the whole loop?
- Spreadsheet tools download files via Drive API and parse with openpyxl on every call. Any caching? Could repeated calls to the same spreadsheet be expensive?
- Citation accumulation across tool calls — any deduplication issues? Could failed searches leave stale/incorrect citations?

### 4. Architecture & Abstraction
- Code that's **over-engineered**: unnecessary indirection, abstractions without multiple consumers, wrapper functions that add no value
- Code that's **under-engineered**: copy-pasted logic, inline business rules that should be extracted, hardcoded values that should be configurable
- **Unused code**: `google_auth.py` is noted as unused in CODEBASE.md (auth logic lives in `routers/auth.py`). `Sidebar.tsx` is noted as unused. Are there other dead files or exports?
- **Frontend duplication**: `ChatContainer` vs `DriveChatContainer`, `useChat` vs `useDriveChat` — are these near-identical implementations that should be a single parameterized component/hook?
- **Import patterns**: Services are imported lazily inside route handlers (inside try/except) to avoid import errors when services aren't configured. Is this the right approach, or does it hide configuration problems?

### 5. Authentication & Security
- **Full auth flow audit**: Google OAuth → in-memory session dict → HTTPOnly cookie → `get_current_user` dependency. Trace the entire flow for gaps.
- **In-memory sessions** (`utils/security.py`): `_sessions: dict[str, str]` maps session_id → user_id. Server restarts lose all sessions. Is this acceptable for the project scope, or a real risk?
- **Cookie security**: `secure=False`, `samesite=lax`, `max_age=7 days`. Flag the `secure=False` for production. Are there other cookie flag issues?
- **No token refresh**: Google access tokens expire in ~1 hour. There's no background refresh logic. What's the actual user experience when a token expires mid-session? Does the agent fail gracefully?
- **Hardcoded redirect URLs**: OAuth callback redirects to `http://localhost:5173`. How painful is this to change for production?
- **Fernet encryption**: Tokens encrypted at rest with `ENCRYPTION_KEY`. Is key management sound? Any risks around key rotation or key exposure?
- **Credential injection**: Server-side injection in tool_executor — verify no leaks to LLM context or API responses.
- **CORS**: `allow_credentials=True` with specific origins (`localhost:5173`, `localhost:8000`). Correct for dev — any issues for production?
- **Ownership checks**: Every endpoint with `{project_id}` or `{session_id}` should verify the resource belongs to the authenticated user. Are there any endpoints that skip this check?
- **CSRF**: With cookie-based auth and `allow_credentials=True`, is there CSRF protection?

### 6. Database & Data Access
- **No repository pattern**: DB queries live inline in route handlers. Is this clean enough for 4 tables, or is business logic leaking into routers?
- **Async session management**: `get_db()` yields `AsyncSession` per request with auto-commit/rollback. Any leak risks? Any places where sessions aren't properly closed (especially in error paths)?
- **Temporal activities**: Worker activities create their own DB-adjacent clients (httpx, Azure SDK). Are there any activities that need database access? If so, how do they get sessions?
- **Query patterns**: N+1 risks (e.g., loading projects with their sessions), missing indexes beyond the documented ones (`users.email`, `projects.user_id`, `chat_sessions.project_id`, `messages.chat_session_id`).
- **Transaction boundaries**: Are multi-step operations (e.g., creating a project + triggering sync) wrapped in transactions correctly?
- **Edge cases**: Race conditions on concurrent writes (e.g., two sync triggers for the same project), upsert correctness in auth callback (user already exists), cascade delete behavior (deleting a project cascades to sessions and messages — is Azure Search index cleanup also handled?).
- **Schema**: `messages.citations` is a JSON column. Is this appropriate, or should citations be a separate table? Any missing constraints or FK integrity issues?

### 7. Error Handling & Resilience
- Missing or inconsistent try/catch — especially around external calls:
  - **Google Drive API**: rate limits, auth failures (expired token), file access denied, folder not found
  - **Azure AI Search**: connection failures, index not found, malformed queries
  - **OpenAI API**: embedding failures, rate limits (worker has retry logic — is it sufficient?)
  - **Anthropic / OpenAI LLM**: agent loop failures, malformed responses, context window exceeded
- **Silent failures**: errors caught but swallowed without logging or user feedback. Particularly: the chat endpoint wraps the entire agent call in try/except and returns a placeholder message on failure — does the user get any useful feedback about what went wrong?
- **Temporal fallback**: When Temporal is unavailable, `routers/sync.py` falls back to marking the project as COMPLETED without actually syncing. Is this safe? Could a user think their folder is indexed when it isn't?
- **Retry safety**: Are Temporal activities designed to be safely retried? Any non-idempotent operations that could cause duplicates or corruption on retry (especially `index_chunks` batch upserts)?
- **Frontend error states**: Do all API calls handle failure gracefully? Are loading/error/empty states covered for every data-fetching component?
- **Sync failure surfacing**: If a workflow fails or files are skipped, does the user see this via the polling endpoint (`/api/sync/{project_id}/status`)? Or do failures silently disappear?

### 8. Code Quality
- DRY violations that actually matter (not trivial ones)
- Mixed concerns: business logic in UI components, data fetching mixed with presentation, route handlers doing too much
- Functions or files that are doing too many things (particularly `tool_executor.py` with 16 handler functions)
- Dead code, unused imports, stale patterns from earlier iterations
- Consistency: are similar operations handled the same way across the codebase? (e.g., error handling in different routers, API response shapes, frontend component patterns)

### 9. Tests
The test suite is small — backend has a few test files in `backend/tests/`, frontend has co-located `__tests__/` directories. Audit for:
- **Stale tests**: Tests that pass but validate behavior that no longer exists or has changed. These are worse than no tests because they give false confidence.
- **Weak assertions**: Tests that assert something was called or returned *anything* rather than asserting the correct behavior. A test that just checks `response.status_code == 200` without validating the response body is often useless.
- **Missing coverage on critical paths**: The following are high-value areas that should have tests:
  - OAuth flow (login, callback, session creation, logout)
  - Agent ReAct loop (iteration, tool dispatch, error handling, max iterations)
  - Tool executor (credential injection, individual handler correctness)
  - LLMClient provider switching and message format conversion
  - Sync pipeline activities (especially chunking logic, embedding batching)
  - Citation parsing in `MessageBubble` (regex edge cases)
  - Frontend hooks (useChat send/receive flow, useAuth state transitions)
- **Brittle tests**: Tests tightly coupled to implementation details (mocking internals, asserting exact call counts on private methods) that break on any refactor even if behavior is unchanged.
- **Duplicate tests**: Multiple tests that exercise the exact same code path with no meaningful variation.
- **Missing edge case tests**: Especially around expired tokens, malformed Drive URLs, empty folders, LLM returning unexpected formats, concurrent sync triggers, and large file handling.

## What NOT to Do

- **Do not invent issues.** If a file is clean and well-structured, skip it. A short report with 5 real issues is infinitely more useful than a long report with 30 nitpicks.
- **Do not flag style preferences.** If code works, is readable, and follows the existing patterns, it's fine.
- **Do not suggest adding comments, docstrings, or documentation** unless the code is genuinely confusing without them.
- **Do not recommend adding types/interfaces purely for ceremony.** But do flag missing types on shared boundaries (API responses, hook return values, service contracts) where the lack of typing could cause real bugs.
- **Do not recommend refactors that are pure preference** (e.g., "could use a reduce instead of forEach"). Only flag things that cause real problems.

## Output Format

Create a markdown report at `AUDIT.md` organized by severity:

### Severity Levels
- **Critical**: Security vulnerabilities, data integrity risks, bugs that would hit production
- **High**: Architectural issues that would cause real pain in production, significant security gaps, data loss risks
- **Medium**: Code quality issues that make the codebase harder to maintain but aren't urgent
- **Low**: Minor improvements that would be nice but aren't causing problems today

Also make sure you number the issues found so we can reference them easily.

### Per Issue
```
**[SEVERITY] Issue title**
- **Where**: File path(s) and line numbers
- **What**: 1-2 sentence description of the actual problem
- **Why it matters**: What breaks, degrades, or becomes painful if left unfixed
- **Suggested approach**: 1-2 sentences, no implementation
```

## Process

1. Start by reading `CODEBASE.md` for full architecture context
2. Explore the project structure to orient yourself
3. Review the services layer first (`backend/app/services/`), then Temporal worker pipeline (`worker/`), then routers (`backend/app/routers/`), then frontend (`frontend/src/`)
4. Be honest. If the codebase is in good shape, say so. The best audit result is a short list or an empty one.
