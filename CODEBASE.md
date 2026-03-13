# Codebase Map

> Read this before non-trivial work. Update it when you add/remove/move files or change architecture.

---

## Business Context

### What This Is

**Talk-to-a-Folder** is a web application that lets users have AI-powered conversations with the contents of any Google Drive folder. Authenticate with Google, paste a Drive link, and immediately start asking questions about the files inside — with citations linking back to source documents.

### Problem

Knowledge workers store critical documents across Google Drive — reports, spreadsheets, presentations, PDFs. Finding specific information means manually opening files, searching, and synthesizing across documents. This doesn't scale.

### Solution

A conversational interface that:

1. **Connects** to any Google Drive folder via its URL
2. **Answers** natural language questions via a ReAct agent that searches, reads, and reasons across the files in real time via the Google Drive API
3. **Cites** every claim back to the source file with clickable links to Google Drive

### Core User Flow

```
Sign in with Google → Paste a Drive folder URL →
Select folder in Chat → Ask questions → Get answers with citations
```

### Quality Bar

- **UI/UX**: Dark-mode, minimal, responsive. No rough edges — loading states, error handling, empty states all covered.
- **Reliability**: Graceful degradation when services are unavailable.
- **Security**: Encrypted token storage, server-side credential injection, no secrets exposed to frontend or LLM.
- **Accuracy**: Agent uses folder-first strategy (browse structure, then read specific files), cites sources, and reports when it can't find information.

---

## File Tree

```
tenex/
├── CLAUDE.md                         # Project instructions for Claude Code
├── CODEBASE.md                       # ← this file
├── Dockerfile                        # API image (multi-stage: frontend build + backend)
├── deploy.ps1 / deploy.sh           # Build + push Docker image to ACR
├── run.ps1 / run.sh                 # Start backend + frontend dev servers
├── setup.ps1 / setup.sh             # One-time environment setup (7 steps)
├── test.ps1 / test.sh               # Run all backend + frontend tests
├── production-db.ps1 / production-db.sh  # Production database migration manager
├── .env / .env.example               # Environment variables
│
├── backend/
│   ├── alembic/                      # Database migrations
│   │   ├── env.py                    # Async Alembic config (converts postgresql:// to asyncpg://)
│   │   └── versions/
│   │       ├── 7333ef8eb49b_initial_tables.py
│   │       ├── a1b2c3d4e5f6_add_drive_chat_support.py
│   │       ├── b2c3d4e5f6a7_add_constraints_and_indexes.py
│   │       └── c3d4e5f6a7b8_remove_agent_type_column.py
│   ├── app/
│   │   ├── main.py                   # FastAPI app, AuthGuardMiddleware, CORS, rate limiting, router mounts, SPA static
│   │   ├── config.py                 # Pydantic Settings (all env vars)
│   │   ├── dependencies.py           # DI: get_db, get_current_user, get_settings
│   │   ├── models/
│   │   │   ├── __init__.py           # Base + re-exports
│   │   │   ├── user.py              # User (Google OAuth tokens, encrypted)
│   │   │   ├── project.py           # Project + ProjectStatus enum
│   │   │   ├── chat.py              # ChatSession
│   │   │   └── message.py           # Message + MessageRole enum
│   │   ├── schemas/
│   │   │   ├── user.py              # UserResponse
│   │   │   ├── project.py           # ProjectCreate, ProjectResponse
│   │   │   ├── chat.py              # ChatRequest, ChatResponse, MessageResponse, CitationSchema
│   │   │   └── error.py             # ErrorResponse
│   │   ├── routers/
│   │   │   ├── auth.py              # Google OAuth login/callback/logout/me
│   │   │   ├── projects.py          # CRUD: list, create, get, delete
│   │   │   ├── chat.py              # Send message, list sessions/messages, streaming
│   │   │   └── sync.py              # Trigger sync, get status
│   │   ├── services/
│   │   │   ├── __init__.py          # Re-exports: FolderAgent, DRIVE_SYSTEM_PROMPT, DRIVE_AGENT_TOOLS, GoogleDriveService, LLMClient
│   │   │   ├── agent.py             # FolderAgent — ReAct loop (max 15 iters), DRIVE_SYSTEM_PROMPT
│   │   │   ├── agent_tools.py       # Tool definitions: DRIVE_ONLY (3), SHARED (9). Composed: DRIVE_AGENT_TOOLS (12)
│   │   │   ├── tool_executor.py     # Tool dispatch + Citation dataclass + 12 handler functions
│   │   │   ├── llm/                 # LLM provider package (strategy pattern)
│   │   │   │   ├── __init__.py      # Backward-compat re-exports (LLMClient, types, errors)
│   │   │   │   ├── types.py         # Normalized response dataclasses (ToolCall, LLMResponse, LLMStreamEvent, etc.)
│   │   │   │   ├── errors.py        # Unified error hierarchy (LLMError, LLMRateLimitError, etc.)
│   │   │   │   ├── base.py          # Abstract LLMProvider base class
│   │   │   │   ├── registry.py      # Model→provider routing via @register_provider decorator
│   │   │   │   ├── anthropic_provider.py  # Anthropic Messages API (Claude models)
│   │   │   │   ├── openai_provider.py     # OpenAI Responses API (GPT models, catch-all)
│   │   │   │   └── client.py        # Thin LLMClient router (delegates to providers)
│   │   │   └── google_drive.py      # Drive API v3 (list, download, export, metadata, search_files)
│   │   └── utils/
│   │       ├── security.py          # Fernet encryption, stateless sessions, token refresh
│   │       └── file_parsers.py      # PDF/DOCX/XLSX text extraction + token counting
│   ├── tests/
│   │   ├── conftest.py              # Fixtures: test_client, unauthed_client, mock_user
│   │   ├── test_agent.py            # FolderAgent ReAct loop tests
│   │   ├── test_drive_agent_tools.py # Agent tool definition tests
│   │   ├── test_drive_tool_handlers.py # Drive tool handler tests
│   │   ├── test_spreadsheet_tools.py # Spreadsheet tool handler tests
│   │   ├── test_llm_responses_api.py # OpenAI provider tests (conversion, normalization, call)
│   │   ├── test_llm_anthropic.py    # Anthropic provider tests (conversion, normalization, call, streaming)
│   │   ├── test_llm_streaming.py    # OpenAI streaming tests
│   │   ├── test_llm_client.py       # LLMClient routing and provider selection tests
│   │   ├── test_llm_registry.py     # Provider registry can_handle and routing tests
│   │   ├── test_schemas.py          # Pydantic schema validation tests
│   │   ├── test_tool_arg_validation.py # Tool argument validation tests
│   │   ├── test_access_token_refresh.py # OAuth token refresh tests
│   │   ├── test_auth_guard.py       # AuthGuardMiddleware + CSRF tests
│   │   ├── routers/
│   │   │   ├── test_auth.py         # Auth endpoint tests
│   │   │   ├── test_auth_config.py  # Auth configuration tests
│   │   │   ├── test_chat.py         # Chat endpoint tests
│   │   │   ├── test_projects.py     # Project CRUD tests
│   │   │   ├── test_projects_validate.py # Folder validation tests
│   │   │   └── test_sync.py         # Sync endpoint tests
│   │   ├── services/
│   │   │   ├── test_google_drive.py # Drive service tests
│   │   │   └── test_google_drive_search.py # Drive search tests
│   │   └── __init__.py
│   ├── pytest.ini                    # asyncio_mode=auto, testpaths=tests
│   └── requirements.txt
│
├── frontend/
│   ├── index.html
│   ├── package.json                  # Scripts: dev, build, test, test:watch
│   ├── vite.config.ts                # React plugin, @/ alias, /auth + /api proxy to :8000
│   ├── vitest.config.ts              # jsdom env, @/ alias
│   ├── tsconfig.json                 # Strict, @/ paths, ES2020 target
│   ├── tailwind.config.js            # brand-* and surface-* custom colors
│   ├── postcss.config.js
│   └── src/
│       ├── App.tsx                   # Auth gate → Knowledge/Chat tab routing
│       ├── main.tsx                  # QueryClientProvider → BrowserRouter → App
│       ├── index.css                 # Tailwind + custom btn/card/input classes
│       ├── types/index.ts            # User, Project, ChatSession, Message, Citation
│       ├── services/
│       │   ├── api.ts               # Axios instance + all endpoint functions + SSE streaming + 401 interceptor
│       │   └── __tests__/api.test.ts # API service tests
│       ├── hooks/
│       │   ├── useAuth.ts           # Zustand store (user, fetchUser, login, logout)
│       │   ├── useProjects.ts       # React Query: useProjects, useProjectSyncStatus, useCreateProject, useDeleteProject, useSyncProject
│       │   ├── useUnifiedChat.ts    # useUnifiedChat, useUnifiedChatSessions, useDeleteChatSession
│       │   └── useTheme.ts          # Zustand dark/light theme toggle
│       └── components/
│           ├── TenexLogo.tsx        # Shared logo: pixelated X icon + wordmark SVGs
│           ├── auth/
│           │   ├── LandingPage.tsx   # Minimal login: logo + tagline + Google sign-in
│           │   └── GoogleLoginButton.tsx
│           ├── knowledge/
│           │   ├── ProjectList.tsx   # Project grid + add button + empty/loading/error states
│           │   ├── ProjectCard.tsx   # Status badge, sync progress, 2-step delete, live polling
│           │   ├── AddFolderModal.tsx # Drive URL input form with validation
│           │   └── SyncProgress.tsx  # Animated progress bar + status text
│           ├── chat/
│           │   ├── UnifiedChatContainer.tsx # Two-pane: session sidebar + folder picker + messages
│           │   ├── ChatInput.tsx     # Auto-resize textarea, Enter to send, Shift+Enter newline
│           │   ├── MessageList.tsx   # Auto-scroll message feed + typing indicator
│           │   ├── MessageBubble.tsx # Citation parsing via regex, whitespace-pre-wrap
│           │   ├── CitationTooltip.tsx # Click/hover tooltip with snippet + Drive link
│           │   └── ProjectSelector.tsx # Dropdown for connected folders
│           └── layout/
│               └── TopBar.tsx       # Top bar: Knowledge/Chat tabs + user avatar + theme toggle + logout
│
├── benchmark/
│   ├── run_benchmark.ps1 / run_benchmark.sh  # Launcher script (activates venv, sets PYTHONPATH, forwards args)
│   ├── run.py                       # CLI entry point — loads questions, resolves auth, runs benchmark
│   ├── config.py                    # BenchmarkConfig dataclass + CLI argument parsing
│   ├── runner.py                    # TracingFolderAgent + orchestration (concurrency, retries, incremental save)
│   ├── evaluator.py                 # LLM-as-judge evaluator (OpenAI function calling)
│   ├── models.py                    # Dataclasses: ToolCallTrace, IterationTrace, AgentTrace, Evaluation, QuestionResult, BenchmarkResults
│   ├── auth.py                      # DB-based Google OAuth token retrieval for benchmark runs
│   ├── qa_test.json                 # Test questions: 17 Q&A pairs (5 easy, 5 medium, 7 hard) for a demo company
│   ├── build_viewer.py              # Scans results/*.json → generates results_manifest.js for viewer
│   ├── viewer.html                  # Self-contained dark-mode dashboard for viewing benchmark results
│   ├── results_manifest.js          # Auto-generated JS file embedding all result runs (consumed by viewer.html)
│   ├── results/                     # Timestamped JSON result files (one per run)
│   └── PRD.md                       # Benchmark product requirements document
│
└── claude_docs/
    ├── 001_agentic_gdrive_chat.md   # Product requirements document
    └── 002_styling_guide.md         # Color palette, typography, component styles
```

---

## Architecture

### Data Flow

```
User → React SPA (Vite :5173) → FastAPI API (:8000) ──→ PostgreSQL (users, projects, sessions, messages)
                                     │
                                     ├──→ Google OAuth 2.0 (login, token refresh)
                                     ├──→ FolderAgent (ReAct loop) ──→ Google Drive (file search/read)
                                     │                               ──→ LLMClient (provider pattern)
                                     │                                     ├── AnthropicProvider (Claude)
                                     │                                     └── OpenAIProvider (GPT, catch-all)
                                     │
                                     └──→ Sync endpoint (file count discovery via Drive API)
```

### CORS

`main.py` derives allowed origins from `FRONTEND_URL` and `GOOGLE_REDIRECT_URI` (backend origin), with `allow_credentials=True`, all methods and headers.

### Router Mounts

| Prefix | Router | Tags |
|--------|--------|------|
| `/auth` | `auth.router` | auth |
| `/api/projects` | `projects.router` | projects |
| `/api/chat` | `chat.router` | chat |
| `/api/sync` | `sync.router` | sync |

Production SPA: if `backend/static/` exists (copied from Vite build in Docker), FastAPI mounts it as a catch-all static file server.

---

## API Endpoints

### Auth (`/auth`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/google/login` | No | Redirect to Google OAuth consent screen |
| `GET` | `/google/callback?code=` | No | Exchange auth code → upsert user → set session cookie → redirect to frontend |
| `POST` | `/logout` | No | Delete session + clear cookie → 204 |
| `GET` | `/me` | Yes | Return current user profile → `UserResponse` |

### Projects (`/api/projects`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/` | Yes | List all projects for user (newest first) → `ProjectResponse[]` |
| `POST` | `/` | Yes | Create project from Drive URL → `ProjectResponse` (201) |
| `POST` | `/validate-folder` | Yes | Validate a Drive folder URL → folder_id, name, url |
| `GET` | `/{project_id}` | Yes | Get single project → `ProjectResponse` |
| `DELETE` | `/{project_id}` | Yes | Delete project → 204 |

Project creation extracts folder ID from URL via regex: `drive.google.com/drive/(u/\d+/)?folders/([A-Za-z0-9_-]+)`. Falls back to accepting bare folder IDs.

### Chat (`/api/chat`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/` | Yes | Send message → `ChatResponse` (contains `message` + `session_id`) |
| `POST` | `/stream` | Yes | Send message → SSE stream (events: session, status, delta, citations, done) |
| `GET` | `/sessions/drive` | Yes | List chat sessions for current user (newest first) → `ChatSessionResponse[]` |
| `GET` | `/sessions/{session_id}/messages` | Yes | List messages in session (chronological) → `MessageResponse[]` |
| `DELETE` | `/sessions/{session_id}` | Yes | Delete a chat session → 204 |

`POST /` and `POST /stream` behavior: If `session_id` provided, appends to existing session. For new sessions: requires `gdrive_folder_id`. Session title is first 120 chars of first message. Agent uses `DRIVE_AGENT_TOOLS` + `DRIVE_SYSTEM_PROMPT`.

### Sync (`/api/sync`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/{project_id}` | Yes | Trigger sync (file count discovery) → `ProjectResponse`. 409 if already syncing. |
| `GET` | `/{project_id}/status` | Yes | Get current sync status → `ProjectResponse` |

---

## Auth & Security

### OAuth Flow

1. Frontend calls `window.location.href = "/auth/google/login"`
2. Backend redirects to Google with scopes: `openid email profile https://www.googleapis.com/auth/drive.readonly`
3. Google redirects back to `/auth/google/callback?code=...`
4. Backend exchanges code for tokens, fetches user profile, upserts User row
5. Tokens encrypted with Fernet before DB storage (both access + refresh)
6. Backend creates a stateless session token (Fernet-encrypted `user_id`)
7. Sets HTTPOnly cookie: `session_id`, `samesite=lax`, `secure` derived from `FRONTEND_URL` scheme, `max_age=24h`, `path=/`
8. Redirects to `FRONTEND_URL` (default: `http://localhost:5173`)

OAuth params: `access_type=offline` (requests refresh token), `prompt=consent` (forces consent every time).

### Session Management (`utils/security.py`)

- **Stateless Fernet tokens**: `create_session(user_id, settings)` encrypts the user_id into a Fernet token. The Fernet timestamp enables TTL enforcement without server-side state.
- `validate_session(session_id, settings)` → decrypts token with `ttl=SESSION_MAX_AGE` (24h), returns user_id or None
- `delete_session(session_id)` → adds token to `_revoked` dict (pruned on each revocation to prevent unbounded growth)
- **Stateless by default**: No session store needed. The only server-side state is the small `_revoked` dict for explicit logouts.

### AuthGuard Middleware (`main.py`)

Defense-in-depth layer on all `/api/*` routes, running before handlers:
- Validates session cookie via `validate_session()` → 401 if missing/invalid
- **CSRF protection**: State-changing methods (POST, PUT, DELETE, PATCH) must include `X-Requested-With` header → 403 if missing (Axios sets this automatically)
- Complements per-handler `Depends(get_current_user)` for proper user injection

### Rate Limiting (`main.py` + `routers/chat.py`)

- Uses `slowapi` with `@limiter.limit("10/minute")` on chat endpoints (`POST /` and `POST /stream`)
- Rate key: session ID or remote IP address
- `RateLimitExceeded` exception handler registered on app

### Token Encryption

- Uses `cryptography.fernet.Fernet` with `ENCRYPTION_KEY` env var
- `encrypt_token(token, settings)` / `decrypt_token(encrypted, settings)`
- Tokens decrypted only server-side immediately before Google Drive API calls
- Never sent to frontend or exposed in any API response

### Credential Injection

In the agent system, `project_id` and `access_token` are always injected server-side by `tool_executor.py`. The LLM provides tool arguments (query, file_id, etc.) but never receives or controls credentials.

---

## Database Schema

4 tables, all UUID primary keys, cascading deletes:

```
users
  id (UUID, PK)
  email (VARCHAR 255, unique index)
  name (VARCHAR 255)
  picture_url (VARCHAR 500, nullable)
  google_access_token (TEXT, encrypted at rest, nullable)
  google_refresh_token (TEXT, encrypted at rest, nullable)
  token_expires_at (TIMESTAMP TZ, nullable)
  created_at (TIMESTAMP TZ, server_default=now())
  updated_at (TIMESTAMP TZ, onupdate=now(), nullable)

projects (FK → users.id, CASCADE)
  id (UUID, PK)
  user_id (UUID, FK, indexed)
  name (VARCHAR 255)
  gdrive_folder_id (VARCHAR 255, nullable)
  gdrive_folder_url (VARCHAR 500, nullable)
  sync_status (ENUM: PENDING|SYNCING|COMPLETED|FAILED, default=PENDING)
  files_total (INT, default=0)
  files_processed (INT, default=0)
  last_synced_at (TIMESTAMP TZ, nullable)
  sync_error (TEXT, nullable)
  created_at, updated_at

chat_sessions (FK → projects.id, CASCADE; FK → users.id, CASCADE)
  id (UUID, PK)
  project_id (UUID, FK, indexed, nullable)
  user_id (UUID, FK, indexed, NOT NULL)
  gdrive_folder_id (VARCHAR 255, nullable)
  title (VARCHAR 500, nullable)
  created_at, updated_at

messages (FK → chat_sessions.id, CASCADE)
  id (UUID, PK)
  chat_session_id (UUID, FK, indexed)
  role (ENUM: USER|ASSISTANT)
  content (TEXT)
  citations (JSON, nullable)
  created_at (TIMESTAMP TZ, server_default=now())
```

**Indexes**: `users.email` (unique), `projects.user_id`, `chat_sessions.project_id`, `chat_sessions.created_at`, `messages.chat_session_id`, `messages.created_at`, `projects.sync_status`.

**Unique constraints**: `uq_projects_user_folder` (`user_id`, `gdrive_folder_id`) — prevents duplicate folder per user.

**ORM**: SQLAlchemy 2.0 async with `Mapped[Type]` annotations, `DeclarativeBase`, `mapped_column`, `relationship(back_populates=..., cascade="all, delete-orphan")`.

---

## Agent System

### FolderAgent (`services/agent.py`)

ReAct loop that answers questions by iteratively calling tools and reasoning.

**Constructor args**: `llm_client`, `drive_service`, `model` (default: `gpt-5.2`), `max_iterations` (default: 15), `tools` (optional, defaults to `DRIVE_AGENT_TOOLS`), `system_prompt` (optional, defaults to `DRIVE_SYSTEM_PROMPT`).

**`answer()` method**:
1. Builds messages: `[system_prompt, ...chat_history, user_question]`
2. Calls `llm_client.call_with_tools()` with `self.tools`
3. If no tool calls → return final answer + accumulated citations
4. If tool calls → execute each via `tool_executor.execute_tool()`, append results, continue loop
5. If max iterations hit → return partial answer with warning text, `hit_limit=True`

**System prompt** (`DRIVE_SYSTEM_PROMPT`): Instructs agent to use `get_folder_structure` first (file names are usually descriptive enough), then go directly to the needed file. `search_drive` is a secondary fallback for content-based search when folder browsing isn't enough.

**AgentResponse dataclass**: `content: str`, `citations: list[Citation]`, `iterations: int`, `hit_limit: bool`

### Citation Dataclass (`services/tool_executor.py`)

```python
@dataclass
class Citation:
    chunk_id: str
    file_id: str
    file_name: str
    source_url: str | None = None
    location: str | None = None     # e.g. "Section X, Page Y"
    snippet: str = ""
```

Citations are accumulated across all tool calls in a single agent run and returned with the final response. The chat router serializes them as JSON dicts into `messages.citations`.

### Agent Tools (`services/agent_tools.py`)

All defined in OpenAI function calling schema format (converted to Responses API flat format by `LLMClient`). Tools are split into groups: `DRIVE_ONLY_TOOLS` (3), `SHARED_TOOLS` (9). Composed: `DRIVE_AGENT_TOOLS = DRIVE_ONLY + SHARED` (12).

**Drive-only tools (use Google Drive API directly):**

| # | Tool | Required Args | Optional Args | Description |
|---|------|--------------|---------------|-------------|
| 1 | `search_drive` | `query` | `file_types[]` | File search via Drive `fullText contains` keyword search (no citations — discovery only) |
| 2 | `get_file_content` | `file_id` | `max_chars` (default 50000) | Download + parse full file text (PDF/DOCX/Docs/text) |
| 3 | `search_within_file_text` | `file_id`, `query` | `context_chars` (default 200) | Case-insensitive text search within a downloaded file |

**Shared tools:**

| # | Tool | Required Args | Optional Args | Description |
|---|------|--------------|---------------|-------------|
| 1 | `get_folder_structure` | — | — | CALL THIS FIRST. ASCII tree of all files/folders with sizes and IDs. Caches result on `drive_service._folder_tree_cache` |
| 2 | `get_file_metadata` | `file_id` | — | File details: name, type, size, modified, Drive link |
| 3 | `read_document_pages` | `file_id`, `start_page`, `end_page` | — | Read specific pages (Google Docs/PDF/DOCX, ~3000 chars/page) |
| 4 | `get_spreadsheet_overview` | `file_id` | — | Sheet names, row/col counts, headers, sample rows |
| 5 | `read_spreadsheet_rows` | `file_id`, `sheet_name`, `start_row`, `end_row` | — | Read specific row range from a sheet (returns 1 citation) |
| 6 | `search_spreadsheet` | `file_id`, `query` | `sheet_name` | Find values in cells (max 50 matches, returns 1 citation) |
| 7 | `get_column_stats` | `file_id`, `sheet_name`, `column_name` | — | Count, sum, mean, median, min, max, stddev (returns 1 citation) |
| 8 | `report_inability` | `reason` | — | Report that the question can't be answered |
| 9 | `request_clarification` | `question` | — | Ask user for more details |

**Tool execution** (`tool_executor.py`): Dispatches to `_handle_*` async functions (12 total). Drive tools call `drive_service` directly for file search/download/parsing. Spreadsheet tools download files via `_download_spreadsheet_bytes` (returns `bytes, file_name, mime_type, web_view_link`; caches in `tool_cache`) and parse with openpyxl. **Citation policy**: content-reading tools (`get_file_content`, `read_spreadsheet_rows`, `search_spreadsheet`, `get_column_stats`, etc.) produce citations; discovery-only tools (`search_drive`, `get_folder_structure`, `get_file_metadata`) do not.

### LLM Client (`services/llm/`)

Provider-per-class architecture (strategy pattern). Each provider is self-contained; adding a new one requires no changes to existing code.

**Package structure**:
- `client.py` — Thin `LLMClient` router that delegates to providers via the registry
- `base.py` — Abstract `LLMProvider` base class (call_with_tools, stream_call_with_tools, complete, can_handle)
- `registry.py` — `@register_provider` decorator + `get_provider_for_model()` routing
- `anthropic_provider.py` — Anthropic Messages API (Claude models, thinking, beta headers)
- `openai_provider.py` — OpenAI Responses API (GPT models, catch-all for non-Claude)
- `types.py` — Normalized response dataclasses (ToolCall, LLMResponse, LLMStreamEvent, etc.)
- `errors.py` — Unified error hierarchy (LLMError → LLMRateLimitError, LLMAPIError, etc.)
- `__init__.py` — Re-exports everything for backward compatibility (`from app.services.llm import LLMClient` still works)

**Provider selection**: `LLMClient._get_provider(model)` uses `can_handle()` to route Claude models to `AnthropicProvider` and everything else to `OpenAIProvider`. Falls back to any available provider if the preferred one isn't configured.

**Error handling**: Each provider wraps SDK-specific exceptions (e.g., `openai.RateLimitError`) into the unified hierarchy (`LLMRateLimitError`). Consumers catch `LLMError` instead of importing SDK types.

**Adding a new provider**: Implement `LLMProvider`, decorate with `@register_provider`, add instantiation in `LLMClient.__init__`.

**Normalized response structure** (dataclasses in `types.py`):
```
LLMResponse → choices: [Choice → message: MessageContent → content: str | None, tool_calls: [ToolCall → id, function: FunctionCall → name, arguments]]
```

---

## Backend Patterns

### Dependency Injection

```
get_settings()     → @lru_cache singleton, Pydantic BaseSettings from .env
get_db()           → yields AsyncSession per request, auto-commit/rollback
                     Lazy-initializes engine + session factory on first call
                     Uses pool_pre_ping=True, expire_on_commit=False
get_current_user() → validates session cookie → queries DB → returns User ORM object
                     Raises 401 if cookie missing, session invalid, or user not found
```

### Service Instantiation

Services are created per-request inside route handlers (not singletons). Credentials come from injected `settings`. Imported lazily inside handlers to avoid import errors when services aren't configured:

```python
# In routers/chat.py — inside try/except
from app.services import FolderAgent, LLMClient, GoogleDriveService

llm_client = LLMClient(anthropic_api_key=..., openai_api_key=...)
drive_service = GoogleDriveService()
agent = FolderAgent(llm_client=llm_client, drive_service=drive_service)
```

### Error Handling

- **Routers**: `HTTPException` with explicit status codes (401, 404, 409, 422)
- **Chat endpoint**: Entire agent call wrapped in try/except — returns placeholder message on failure (agent unavailable, service not configured, etc.)
- **Sync trigger**: Handles Drive API errors (401/403/timeout) by setting sync_status=FAILED with descriptive error
- **Ownership checks**: Every endpoint with `{project_id}` or `{session_id}` verifies the resource belongs to the authenticated user (joins through Project.user_id)

### Schema Style

Pydantic v2 with `ConfigDict(from_attributes=True)` for ORM serialization. Request schemas are minimal; response schemas mirror the model. Route handlers return ORM objects directly (FastAPI serializes via response_model).

---

## Frontend Patterns

### State Management

| Concern | Tool | Location |
|---------|------|----------|
| Auth (user session) | Zustand | `hooks/useAuth.ts` |
| Theme (light/dark) | Zustand | `hooks/useTheme.ts` |
| Server data (projects, sessions, messages) | React Query | `hooks/useProjects.ts`, `hooks/useUnifiedChat.ts` |
| Local UI (modals, inputs, temp messages) | useState | Component-level |

**React Query config** (in `main.tsx`): `staleTime: 30s`, `retry: 1`, `refetchOnWindowFocus: false`.

**React Query keys**:
- `["projects"]` — all user projects
- `["project-sync", projectId]` — sync status polling
- `["drive-chat-sessions"]` — all chat sessions
- `["chat-messages", sessionId]` — messages in a session

### Zustand Auth Store (`hooks/useAuth.ts`)

```typescript
interface AuthState {
  user: User | null;
  isLoading: boolean;
  hasChecked: boolean;        // distinguishes "loading" from "not checked yet"
  fetchUser: () => Promise<void>;  // GET /auth/me, catches silently if not authed
  login: () => void;               // window.location.href = "/auth/google/login"
  logout: () => Promise<void>;     // POST /auth/logout, sets user=null, redirect to /
}
```

### Chat Hook (`hooks/useUnifiedChat.ts`)

Hybrid approach: local `useState` for new conversations (no session yet), React Query for existing sessions.

- `sendMessage()`: Creates temp user message (optimistic update) → streams SSE response → accumulates deltas → commits session ID on completion
- `selectSession(id)`: Switches to existing session (clears local buffer, React Query fetches messages)
- `startNewChat()`: Clears session ID + local messages (starts fresh)
- `allMessages`: returns `existingMessages` from React Query if session exists, else local `messages` state

### Sync Polling (`hooks/useProjects.ts`)

`useProjectSyncStatus` uses React Query's `refetchInterval` as a function:
- If `sync_status === "SYNCING"` → refetch every 3000ms
- Otherwise → `false` (stop polling)

### API Layer (`services/api.ts`)

Axios instance with `baseURL: ""` (Vite proxy handles routing), `withCredentials: true` (sends HTTPOnly session cookies). Response interceptor catches 401 → dispatches `auth:session-expired` event.

SSE streaming via `streamChat()`: Uses `fetch()` API for SSE parsing. Events: `session` (new session ID), `status` (tool status text), `delta` (content chunk), `citations` (array), `done`.

### Component Conventions

- Functional components with hooks. Props down, events up (`onSend`, `onDelete`, `onClose`).
- Early return for loading/error/empty states.
- `useMemo` for expensive parsing (citation regex in `MessageBubble`).
- **Two-step deletion** (`ProjectCard`): Click delete → shows confirm button → auto-cancels after 3 seconds via `setTimeout`.
- **Auto-resize textarea** (`ChatInput`): Measures `scrollHeight`, sets height dynamically (max 160px), resets after send. Enter sends, Shift+Enter adds newline.
- **Auto-scroll** (`MessageList`): `useRef` on container + `useEffect` scrolls to bottom on new messages.
- **Citation parsing** (`MessageBubble`): Regex `sourcePattern = /\[source:\s*([^\]]+)\]|\[(\d+)\]/g` finds `[source: filename]` and `[1]` patterns in message content → replaces with `<CitationTooltip>` components. Wrapped in `useMemo`.
- **Modal behavior** (`AddFolderModal`): Auto-focus name input on mount. Escape key closes. Backdrop blur with `bg-black/60`. Drive URL validation regex.

### Routing

Two-tab layout behind auth gate:
- `/knowledge` → `ProjectList` (manage Drive folders)
- `/chat` → `UnifiedChatContainer` (chat with Drive folders)
- `/quick-search`, `/deep-search`, `/drive-chat` → redirect to `/chat` (backward compat)
- `/*` → redirect to `/knowledge`
- Unauthenticated → `LandingPage`

### Styling

Dark/light theme via CSS variables + `darkMode: "class"`. Tailwind 3.4 with custom `@layer components` classes:
- `btn-primary`, `btn-secondary`, `btn-danger`, `btn-ghost`
- `card` (rounded-xl, border, shadow, `bg-surface-850`)
- `input-field` (focus ring brand-500, border transition)
- Custom colors: `brand-*` (blue, 50→900, 600 is main), `surface-*` (dark grays, 50/100/700/800/850/900/950; 950 is background)
- Custom scrollbar (thin, rounded, gray), Inter font
- See `claude_docs/002_styling_guide.md` for full palette and typography

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL async connection string |
| `GOOGLE_CLIENT_ID` | Yes | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | Yes | OAuth callback URL (default: `http://localhost:8000/auth/google/callback`) |
| `OPENAI_API_KEY` | Yes | OpenAI key (LLM reasoning) |
| `ANTHROPIC_API_KEY` | No | Anthropic key (enables Claude model selection) |
| `ANTHROPIC_THINKING_BUDGET` | No | Extended thinking token budget (default: `10000`) |
| `ANTHROPIC_EFFORT` | No | Anthropic effort level: `low`, `medium`, `high` (default: `high`) |
| `ENCRYPTION_KEY` | Yes | Fernet key for token encryption at rest |
| `FRONTEND_URL` | No | Frontend origin for OAuth redirect + cookie security (default: `http://localhost:5173`) |
| `AZURE_STORAGE_CONNECTION_STRING` | No | Azure Blob Storage (optional, unused currently) |
| `AGENT_MODEL` | No | LLM model for the agent (default: `gpt-5.2`) |
| `MAX_SYNC_FILES` | No | Max files per folder sync (default: `5000`) |
| `MAX_FOLDER_DEPTH` | No | Max folder recursion depth (default: `10`) |
| `MAX_MESSAGE_LENGTH` | No | Max chat message length (default: `32000`) |
| `MAX_CHAT_HISTORY_MESSAGES` | No | Max prior messages sent to agent (default: `100`) |

---

## Docker

### API Image (`Dockerfile`)

Multi-stage build:
1. **Stage 1** (Node 20 Alpine): Build frontend → `/dist`
2. **Stage 2** (Python 3.12 slim): Install backend deps, copy frontend build to `/static`, run Alembic migrations on startup, start Uvicorn on port 8000

Entrypoint: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000`

---

## Testing

- **Backend**: `pytest` with `asyncio_mode=auto`. Tests in `backend/tests/` mirroring `backend/app/` structure. `conftest.py` provides `test_client` (authenticated, overrides `get_current_user`) and `unauthed_client` fixtures using ASGITransport (no network). Mock user has fixed UUID `00000000-0000-0000-0000-000000000001`.
- **Frontend**: Vitest 2.1 with jsdom. `@testing-library/react` + `@testing-library/jest-dom`. Config in `vitest.config.ts` (globals: true). Tests co-located in `__tests__/` next to source.
- **Rule**: Every feature change must include corresponding test changes (enforced by stop hook).

---

## Benchmark System

End-to-end evaluation harness that tests the FolderAgent against a curated Q&A set and scores answers with an LLM judge. Lives entirely in `benchmark/`.

### How to Run

```bash
# From project root (PowerShell)
.\benchmark\run_benchmark.ps1 --folder-url "<Drive URL>"

# Or directly (with venv active and PYTHONPATH=backend)
python benchmark/run.py --folder-url "<Drive URL>"
```

**Key CLI flags**: `--questions E1 M3 H2` (run specific IDs), `--difficulty easy|medium|hard`, `--concurrency 3`, `--model gpt-5.2`, `--evaluator-model gpt-5.2`, `--max-iterations 15`, `--access-token <raw token>`, `--user-email <email>`, `--resume <results.json>`, `--fresh`.

### Architecture

```
run.py (CLI entry point)
  ├── auth.py          → resolve Google access token (raw CLI arg or DB lookup + refresh)
  ├── config.py        → BenchmarkConfig dataclass + argparse
  └── runner.py        → orchestration
        ├── TracingFolderAgent  → subclass of FolderAgent that captures per-iteration traces
        ├── run_agent_traced()  → creates fresh agent, runs question with timeout
        ├── run_single()        → agent + evaluator for one question, with retry (exponential backoff)
        ├── run_benchmark()     → concurrent execution via asyncio.Semaphore, incremental JSON save
        ├── run_all_models()    → multi-model benchmark with shared run_group UUID
        └── evaluator.py        → LLM-as-judge via OpenAI or Anthropic (auto-routed by model name)
```

### TracingFolderAgent (`runner.py`)

Subclass of `FolderAgent` that re-implements `answer()` to capture timing and tool call details at each iteration. Produces an `AgentTrace` containing `IterationTrace` records (each with `ToolCallTrace` entries). On max-iteration hit, forces a synthesis LLM call (no tools) to get a best-effort final answer.

### Evaluator (`evaluator.py`)

LLM-as-judge supporting both OpenAI and Anthropic as evaluation providers. Routes automatically based on the evaluator model name (Claude → Anthropic Messages API with `tool_use`, everything else → OpenAI Responses API with function calling). The evaluator:
1. Pre-matches expected vs actual sources via fuzzy basename matching
2. Sends a structured prompt with question, expected answer, agent answer, and source analysis
3. Forces a `submit_evaluation` tool call and returns an `Evaluation`: verdict, answer_score (0-100), source_score (0-100), justification, missing/hallucinated facts, source coverage details
4. Skips evaluation for error cases (hit_limit, report_inability, request_clarification) — these are marked as errors directly in the runner

Scoring thresholds: 80+ = pass, 50-79 = partial, <50 = fail. Scoring philosophy is generous — correct answers with different formatting, extra detail, or minor rounding differences score high.

### Data Models (`models.py`)

| Dataclass | Purpose |
|-----------|---------|
| `ToolCallTrace` | Single tool invocation: name, args, result preview (2000 chars), duration, citations produced |
| `IterationTrace` | One agent iteration: LLM response + tool calls + timing |
| `AgentTrace` | Full agent run: all iterations, total duration, LLM/tool call counts, hit_limit flag |
| `Evaluation` | LLM judge output: verdict, scores, reasoning, fact analysis, source coverage |
| `QuestionResult` | Complete result for one question: agent output + trace + evaluation + error |
| `BenchmarkResults` | Full run container: config, summary stats, list of QuestionResults. Supports resume via `completed_ids` |

All dataclasses have `to_dict()` / `from_dict()` for JSON serialization.

### QA Test Set (`qa_test.json`)

17 questions for a fictional company (Meridian Capital Advisors) across 3 difficulty levels:
- **Easy (5)**: Single-file lookups — 401(k) policy, expense thresholds, CEO info, brand colors, VPN setup
- **Medium (5)**: Multi-fact retrieval — P&L vs budget, deal pipeline status, restructuring scenarios, comp bands, compliance deadlines
- **Hard (7)**: Cross-document synthesis — month-over-month P&L comparison, full engagement status, weighted pipeline analysis, debt breakdown, marketing content audit, vendor spend, engagement financials

Each question has: `id`, `difficulty`, `persona`, `department`, `question`, `expected_answer`, `sources` (expected file paths).

### Multi-Model Runs

When `--models gpt-5.2,claude-opus-4-5-20251101` is passed, `run_all_models()` runs the full question set once per model sequentially. All runs in the batch share a `run_group` UUID. Each model's evaluator defaults to matching its own provider (OpenAI evaluates OpenAI agent runs, Anthropic evaluates Anthropic agent runs) unless `--evaluator-model` is explicitly set.

### Results Viewer

- `viewer.html`: Self-contained dark-mode dashboard (no build step). Shows run list, summary stats, per-question details with expandable agent traces, evaluation breakdowns, and justification boxes.
- **Multi-model comparison**: Runs sharing a `run_group` are grouped visually in the run list with model chips and per-model progress bars. Opening a group shows model tabs + a side-by-side comparison table (pass rate, avg score, avg iterations, duration) with the best model highlighted.
- `build_viewer.py`: Scans `results/*.json` → generates `results_manifest.js` (embeds all runs as `window.__BENCHMARK_RUNS__`). Viewer loads this on page open, or accepts manual JSON upload.
- Results are saved incrementally during a run (atomic writes via `tempfile` + `os.replace`).

### Auth (`auth.py`)

Two modes for obtaining a Google access token:
1. **CLI flag**: `--access-token <raw token>` bypasses DB entirely
2. **DB lookup** (default): Connects to PostgreSQL, finds user by `--user-email` (or first user), calls the app's `get_valid_access_token()` to refresh if expired, commits the refreshed token back to DB

---

## Known Limitations

- **In-memory revocation list**: `utils/security.py` sessions are stateless (Fernet tokens), but the `_revoked` dict for explicit logouts lives in-process memory. Multi-worker deploys would need a shared store (Redis) for logout propagation. Sessions still expire naturally via Fernet TTL even without revocation.
- **Token refresh is proactive, not background**: `get_valid_access_token()` in `utils/security.py` checks `token_expires_at` and refreshes via Google's token endpoint before making Drive calls. However, there is no background cron/task that refreshes tokens ahead of time — refresh only happens when a Drive call is about to be made.
- **No CI/CD pipeline**: No GitHub Actions, GitLab CI, or similar configured.
