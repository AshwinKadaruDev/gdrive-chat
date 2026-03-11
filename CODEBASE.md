# Codebase Map

> Read this before non-trivial work. Update it when you add/remove/move files or change architecture.

---

## Business Context

### What This Is

**Talk-to-a-Folder** is a take-home interview project — a production-grade web application that lets users have AI-powered conversations with the contents of any Google Drive folder. The goal is a polished, professional product that does the core functionality perfectly: authenticate with Google, paste a Drive link, and immediately start asking questions about the files inside — with citations linking back to source documents.

### Problem

Knowledge workers store critical documents across Google Drive — reports, spreadsheets, presentations, PDFs. Finding specific information means manually opening files, searching, and synthesizing across documents. This doesn't scale.

### Solution

A conversational interface that:

1. **Ingests** all files within a Google Drive folder (recursively) — PDFs, DOCX, XLSX, Sheets, Slides, text, images
2. **Indexes** content using hybrid search (vector embeddings + keyword) for high-recall retrieval
3. **Answers** natural language questions via a ReAct agent that searches, reads, and reasons across the entire corpus
4. **Cites** every claim back to the source file with clickable links to Google Drive

### Core User Flow

```
Sign in with Google → Paste a Drive folder URL → Folder syncs in background →
Select folder in Chat → Ask questions → Get answers with citations
```

### Quality Bar

- **UI/UX**: Dark-mode, minimal, responsive. No rough edges — loading states, error handling, empty states all covered.
- **Reliability**: Durable ingestion via Temporal (retries, fault tolerance). Graceful degradation when services are unavailable.
- **Security**: Encrypted token storage, server-side credential injection, no secrets exposed to frontend or LLM.
- **Accuracy**: Hybrid search (semantic + keyword) with generated questions per chunk for better retrieval. Agent always searches before answering, cites sources, and reports when it can't find information.

---

## File Tree

```
tenex/
├── CLAUDE.md                         # Project instructions for Claude Code
├── CODEBASE.md                       # ← this file
├── Dockerfile                        # API image (multi-stage: frontend build + backend)
├── Dockerfile.worker                 # Worker image (Python + Tesseract/Poppler)
├── docker-compose.yml                # Local dev: Postgres, Temporal, API, Worker
├── run.ps1                           # Start all 4 dev services
├── setup.ps1                         # One-time environment setup (8 steps)
├── .env / .env.example               # Environment variables
│
├── backend/
│   ├── alembic/                      # Database migrations
│   │   ├── env.py                    # Async Alembic config (converts postgresql:// to asyncpg://)
│   │   └── versions/
│   │       ├── 7333ef8eb49b_initial_tables.py
│   │       └── a1b2c3d4e5f6_add_drive_chat_support.py
│   ├── app/
│   │   ├── main.py                   # FastAPI app, CORS, router mounts, SPA static
│   │   ├── config.py                 # Pydantic Settings (all env vars)
│   │   ├── dependencies.py           # DI: get_db, get_current_user, get_settings
│   │   ├── models/
│   │   │   ├── __init__.py           # Base + re-exports
│   │   │   ├── user.py              # User (Google OAuth tokens, encrypted)
│   │   │   ├── project.py           # Project + ProjectStatus enum
│   │   │   ├── chat.py              # ChatSession + AgentType enum (RAG|DRIVE)
│   │   │   └── message.py           # Message + MessageRole enum
│   │   ├── schemas/
│   │   │   ├── user.py              # UserResponse
│   │   │   ├── project.py           # ProjectCreate, ProjectResponse
│   │   │   ├── chat.py              # ChatRequest, ChatResponse, MessageResponse, CitationSchema
│   │   │   └── error.py             # ErrorResponse
│   │   ├── routers/
│   │   │   ├── auth.py              # Google OAuth login/callback/logout/me
│   │   │   ├── projects.py          # CRUD: list, create, get, delete
│   │   │   ├── chat.py              # Send message, list sessions/messages
│   │   │   └── sync.py              # Trigger sync, get status
│   │   ├── services/
│   │   │   ├── __init__.py          # Re-exports: FolderAgent, DRIVE_SYSTEM_PROMPT, DRIVE_AGENT_TOOLS, RAG_AGENT_TOOLS, AzureSearchService, EmbeddingsService, GoogleDriveService, LLMClient
│   │   │   ├── agent.py             # FolderAgent — ReAct loop (max 15 iters), SYSTEM_PROMPT + DRIVE_SYSTEM_PROMPT
│   │   │   ├── agent_tools.py       # Tool definitions grouped: RAG_ONLY (4), DRIVE_ONLY (3), SHARED (9). Composed: RAG_AGENT_TOOLS (13), DRIVE_AGENT_TOOLS (12)
│   │   │   ├── tool_executor.py     # Tool dispatch + Citation dataclass + 16 handler functions (13 RAG/shared + 3 Drive)
│   │   │   ├── llm.py              # LLMClient (Anthropic + OpenAI, normalized response format)
│   │   │   ├── azure_search.py      # Azure AI Search (hybrid vector + keyword)
│   │   │   ├── embeddings.py        # OpenAI text-embedding-ada-002
│   │   │   ├── google_drive.py      # Drive API v3 (list, download, export, metadata, search_files)
│   │   │   └── google_auth.py       # OAuth token exchange utility (unused — logic lives in auth router)
│   │   └── utils/
│   │       ├── security.py          # Fernet encryption, in-memory session store
│   │       └── file_parsers.py      # PDF/DOCX/XLSX text extraction + token counting
│   ├── tests/
│   │   ├── conftest.py              # Fixtures: test_client, unauthed_client, mock_user
│   │   ├── test_drive_agent_tools.py # Drive agent tool definition tests
│   │   ├── test_drive_tool_handlers.py # Drive tool handler tests
│   │   └── __init__.py
│   ├── pytest.ini                    # asyncio_mode=auto, testpaths=tests
│   └── requirements.txt
│
├── worker/
│   ├── main.py                       # Temporal worker entrypoint (retry connect, 15 attempts)
│   ├── activities/
│   │   ├── crawl_folder.py          # Recursive Drive listing via httpx
│   │   ├── extract_content.py       # MIME-dispatch: PDF/DOCX/XLSX/Sheets/OCR
│   │   ├── chunk_content.py         # Heading → paragraph → fixed-window splitting
│   │   ├── generate_embeddings.py   # OpenAI ada-002, batch 20, rate-limit retry
│   │   ├── generate_questions.py    # LLM-generated RAG questions + embedding
│   │   └── index_chunks.py         # Azure Search batch upsert (100/batch)
│   ├── workflows/
│   │   └── sync_folder.py          # SyncFolderWorkflow orchestrator
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
│       ├── types/index.ts            # User, Project, ChatSession, Message, Citation, SendMessageResponse
│       ├── services/api.ts           # Axios instance + all endpoint functions + 401 interceptor
│       ├── hooks/
│       │   ├── useAuth.ts           # Zustand store (user, fetchUser, login, logout)
│       │   ├── useProjects.ts       # React Query: useProjects, useProjectSyncStatus, useCreateProject, useDeleteProject, useSyncProject
│       │   ├── useChat.ts           # useChatSessions, useChatMessages, useChat (local + React Query hybrid)
│       │   └── useDriveChat.ts      # useDriveChatSessions, useDriveChat (same pattern as useChat)
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
│           │   ├── ChatContainer.tsx # Two-pane: session sidebar + messages (RAG Chat)
│           │   ├── ChatInput.tsx     # Auto-resize textarea, Enter to send, Shift+Enter newline
│           │   ├── MessageList.tsx   # Auto-scroll message feed + typing indicator
│           │   ├── MessageBubble.tsx # Citation parsing via regex, whitespace-pre-wrap
│           │   ├── CitationTooltip.tsx # Click/hover tooltip with snippet + Drive link
│           │   └── ProjectSelector.tsx # Dropdown for completed projects only
│           ├── drive-chat/
│           │   ├── DriveChatContainer.tsx # Two-pane: session sidebar + messages (Drive Chat)
│           │   └── FolderUrlInput.tsx     # Google Drive folder URL input with validation
│           └── layout/
│               ├── Header.tsx       # Top bar: branding + user avatar/initials + logout
│               ├── TabNav.tsx       # Knowledge | RAG Chat | Drive Chat tabs (3 NavLinks)
│               └── Sidebar.tsx      # Wrapper (not actively used — Header + TabNav composed in App.tsx)
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
                                     ├──→ FolderAgent (ReAct loop) ──→ Azure AI Search (hybrid query)
                                     │                               ──→ Google Drive (file read)
                                     │                               ──→ Claude / GPT-4o (reasoning)
                                     │
                                     └──→ Temporal (start sync workflow)
                                              │
                                              └──→ Worker Pipeline:
                                                   crawl_folder → extract_content → chunk_content
                                                   → generate_embeddings → generate_questions → index_chunks
                                                   → Azure AI Search (upsert)
```

### CORS

`main.py` allows origins `http://localhost:5173` (frontend dev) and `http://localhost:8000`, with `allow_credentials=True`, all methods and headers.

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
| `GET` | `/{project_id}` | Yes | Get single project → `ProjectResponse` |
| `DELETE` | `/{project_id}` | Yes | Delete project + cleanup Azure index → 204 |

Project creation extracts folder ID from URL via regex: `drive.google.com/drive/(u/\d+/)?folders/([A-Za-z0-9_-]+)`. Falls back to accepting bare folder IDs.

### Chat (`/api/chat`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/` | Yes | Send message → `ChatResponse` (contains `message` + `session_id`). Supports `agent_type: "rag"` (default) or `"drive"`. |
| `GET` | `/sessions/drive` | Yes | List Drive Chat sessions for current user (newest first) → `ChatSessionResponse[]` |
| `GET` | `/sessions/{project_id}` | Yes | List RAG sessions for project (newest first) → `ChatSessionResponse[]` |
| `GET` | `/sessions/{session_id}/messages` | Yes | List messages in session (chronological) → `MessageResponse[]` |

`POST /` behavior: If `session_id` provided, appends to existing session. For new sessions: RAG (`agent_type=rag`) requires `project_id`, Drive (`agent_type=drive`) requires `gdrive_folder_id`. Session title is first 120 chars of first message. Drive agent uses `DRIVE_AGENT_TOOLS` + `DRIVE_SYSTEM_PROMPT` with no search/embeddings services.

### Sync (`/api/sync`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/{project_id}` | Yes | Trigger sync → `ProjectResponse`. 409 if already syncing. Falls back to COMPLETED if Temporal unavailable. |
| `GET` | `/{project_id}/status` | Yes | Get current sync status → `ProjectResponse` |

---

## Auth & Security

### OAuth Flow

1. Frontend calls `window.location.href = "/auth/google/login"`
2. Backend redirects to Google with scopes: `openid email profile https://www.googleapis.com/auth/drive.readonly`
3. Google redirects back to `/auth/google/callback?code=...`
4. Backend exchanges code for tokens, fetches user profile, upserts User row
5. Tokens encrypted with Fernet before DB storage (both access + refresh)
6. Backend creates in-memory session mapping (`session_id → user_id`)
7. Sets HTTPOnly cookie: `session_id`, `samesite=lax`, `secure=False`, `max_age=7 days`, `path=/`
8. Redirects to `http://localhost:5173`

OAuth params: `access_type=offline` (requests refresh token), `prompt=consent` (forces consent every time).

### Session Management (`utils/security.py`)

- **In-memory dict**: `_sessions: dict[str, str]` maps `session_id → user_id`
- `create_session(user_id)` → generates `secrets.token_urlsafe()` session ID
- `validate_session(session_id)` → returns user_id or None
- `delete_session(session_id)` → removes from dict
- **Limitation**: Single-process only. Needs Redis for multi-worker production deployments.

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
  sync_status (ENUM: PENDING|SYNCING|PROCESSING|COMPLETED|FAILED, default=PENDING)
  files_total (INT, default=0)
  files_processed (INT, default=0)
  last_synced_at (TIMESTAMP TZ, nullable)
  sync_error (TEXT, nullable)
  created_at, updated_at

chat_sessions (FK → projects.id, CASCADE; FK → users.id, CASCADE)
  id (UUID, PK)
  project_id (UUID, FK, indexed, nullable — null for Drive Chat)
  user_id (UUID, FK, indexed, nullable — set for all sessions)
  agent_type (ENUM: RAG|DRIVE, default=RAG)
  gdrive_folder_id (VARCHAR 255, nullable — set for Drive Chat sessions)
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

**Indexes**: `users.email` (unique), `projects.user_id`, `chat_sessions.project_id`, `messages.chat_session_id`.

**ORM**: SQLAlchemy 2.0 async with `Mapped[Type]` annotations, `DeclarativeBase`, `mapped_column`, `relationship(back_populates=..., cascade="all, delete-orphan")`.

---

## Azure Search Index

Index: `talk-to-folder-chunks` (configurable via `AZURE_SEARCH_INDEX_NAME`)

| Field | Type | Attributes | Purpose |
|-------|------|------------|---------|
| `chunk_id` | String | **key**, filterable | Primary key |
| `project_id` | String | filterable | Scope queries to project (multi-tenant isolation) |
| `file_id` | String | filterable | Source file reference |
| `file_name` | String | searchable, filterable | Source file name |
| `file_type` | String | filterable | MIME-based file type |
| `hierarchy` | String | searchable | File path within folder structure |
| `source_url` | String | — | Google Drive web link |
| `content` | String | searchable (`en.microsoft` analyzer) | Chunk text for keyword search |
| `content_vector` | Collection(Single) | searchable, 1536-dim | Semantic embedding (ada-002) |
| `questions` | Collection(String) | searchable | Generated hypothetical questions per chunk |
| `questions_vector` | Collection(Single) | searchable, 1536-dim | Question embedding for query matching |
| `keywords` | Collection(String) | searchable, filterable | Extracted keywords |
| `section_heading` | String | searchable | Heading/section within document |
| `page_number` | Int32 | filterable | Page number in source document |
| `sheet_name` | String | filterable | Spreadsheet sheet name |
| `created_at` | DateTimeOffset | — | Indexing timestamp |

**Vector search**: HNSW algorithm (`default-hnsw`) with vector profile `default-vector-profile`.

**Hybrid search**: Combines `search_text` (keyword) + `VectorizedQuery` on `content_vector` with `k_nearest_neighbors`. Filter on `project_id` (always) + optional `file_type`. Both `hybrid_search` and `search_within_file` use this pattern.

**Neighbor lookup** (`get_chunk_with_neighbors`): Fetches all chunks for a file, finds target by `chunk_id`, returns previous + current + next chunks ordered by `chunk_id asc`.

---

## Agent System

### FolderAgent (`services/agent.py`)

ReAct loop that answers questions by iteratively calling tools and reasoning.

**Constructor args**: `llm_client`, `drive_service`, `search_service` (optional), `embeddings_service` (optional), `model` (default: `claude-sonnet-4-5-20250929`), `max_iterations` (default: 15), `tools` (optional, defaults to `ALL_TOOL_DEFINITIONS`), `system_prompt` (optional, defaults to `SYSTEM_PROMPT`).

**`answer()` method**:
1. Builds messages: `[self.system_prompt, ...chat_history, user_question]`
2. Calls `llm_client.call_with_tools()` with `self.tools`
3. If no tool calls → return final answer + accumulated citations
4. If tool calls → execute each via `tool_executor.execute_tool()`, append results, continue loop
5. If max iterations hit → return partial answer with warning text, `hit_limit=True`

**Two system prompts**:
- `SYSTEM_PROMPT` (RAG): Instructs agent to use `hybrid_search` as primary search, cite sources, handle spreadsheets/documents.
- `DRIVE_SYSTEM_PROMPT` (Drive): Instructs agent to use `search_drive` as primary search (keyword-based, not semantic), fall back to `get_folder_structure`, read files via `get_file_content`.

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

All defined in OpenAI function calling schema format (converted to Anthropic format by `LLMClient` when using Claude). Tools are split into groups: `RAG_ONLY_TOOLS` (4), `DRIVE_ONLY_TOOLS` (3), `SHARED_TOOLS` (9). Composed: `RAG_AGENT_TOOLS = RAG_ONLY + SHARED` (13), `DRIVE_AGENT_TOOLS = DRIVE_ONLY + SHARED` (12).

**RAG-only (require Azure AI Search index):**

| # | Tool | Required Args | Optional Args | Description |
|---|------|--------------|---------------|-------------|
| # | Tool | Required Args | Optional Args | Description |
|---|------|--------------|---------------|-------------|
| 1 | `hybrid_search` | `query` | `file_types[]`, `top_k` (default 8, max 20) | Primary search across ALL files — hybrid text + vector |
| 2 | `search_within_file` | `query`, `file_id` | `top_k` (default 5) | Search within a specific file |
| 3 | `read_chunk_context` | `chunk_id` | — | Read a chunk + its previous/next neighbors |
| 4 | `get_document_outline` | `file_id` | — | Table of contents from section headings |

**Drive-only (use Google Drive API directly):**

| # | Tool | Required Args | Optional Args | Description |
|---|------|--------------|---------------|-------------|
| 1 | `search_drive` | `query` | `file_types[]` | Search files via Drive `fullText contains` keyword search |
| 2 | `get_file_content` | `file_id` | `max_chars` (default 50000) | Download + parse full file text (PDF/DOCX/Docs/text) |
| 3 | `search_within_file_text` | `file_id`, `query` | `context_chars` (default 200) | Case-insensitive text search within a downloaded file |

**Shared tools (both agents):**

| # | Tool | Required Args | Optional Args | Description |
|---|------|--------------|---------------|-------------|
| 1 | `get_folder_structure` | — | — | ASCII tree of all files/folders with sizes and IDs |
| 2 | `get_file_metadata` | `file_id` | — | File details: name, type, size, modified, Drive link |
| 3 | `read_document_pages` | `file_id`, `start_page`, `end_page` | — | Read specific pages (Google Docs/PDF/DOCX, ~3000 chars/page) |
| 4 | `get_spreadsheet_overview` | `file_id` | — | Sheet names, row/col counts, headers, sample rows |
| 5 | `read_spreadsheet_rows` | `file_id`, `sheet_name`, `start_row`, `end_row` | — | Read specific row range from a sheet |
| 6 | `search_spreadsheet` | `file_id`, `query` | `sheet_name` | Find values in cells (max 50 matches) |
| 7 | `get_column_stats` | `file_id`, `sheet_name`, `column_name` | — | Count, sum, mean, median, min, max, stddev |
| 8 | `report_inability` | `reason` | — | Report that the question can't be answered |
| 9 | `request_clarification` | `question` | — | Ask user for more details |

**Tool execution** (`tool_executor.py`): Dispatches to `_handle_*` async functions (16 total). RAG search tools embed the query via `embeddings_service.get_embedding()` before calling Azure Search. Drive tools call `drive_service` directly for file search/download/parsing. Spreadsheet tools download files via Drive API and parse with openpyxl.

### LLM Multi-Provider (`services/llm.py`)

`LLMClient` normalizes Anthropic and OpenAI to a common response format.

**Provider selection**:
- If model string contains `"claude"` and `ANTHROPIC_API_KEY` is set → use Anthropic
- Otherwise → use OpenAI (falls back to `gpt-4o` if model was a Claude model)
- `complete()` method (no tools): prefers Anthropic (`claude-sonnet-4-5-20250929`), falls back to `gpt-4o-mini`

**Normalized response structure** (dataclasses):
```
LLMResponse → choices: [Choice → message: MessageContent → content: str | None, tool_calls: [ToolCall → id, function: FunctionCall → name, arguments]]
```

**Anthropic conversion**:
- System messages extracted and passed as `system=` parameter (not in messages array)
- Assistant messages with tool_calls → `tool_use` content blocks
- `role: "tool"` messages → `role: "user"` with `tool_result` content blocks; consecutive tool results merged into a single user message
- Tool definitions: OpenAI `function.parameters` → Anthropic `input_schema`
- `tool_choice` mapping: `"auto"` → `{"type": "auto"}`, `"required"` → `{"type": "any"}`
- `max_tokens`: 4096, `temperature`: 0.1

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
from app.services import FolderAgent, LLMClient, AzureSearchService, EmbeddingsService, GoogleDriveService

llm_client = LLMClient(anthropic_api_key=..., openai_api_key=...)
search_service = AzureSearchService(endpoint=..., api_key=..., index_name=...)
agent = FolderAgent(llm_client=llm_client, search_service=..., ...)
```

### Error Handling

- **Routers**: `HTTPException` with explicit status codes (401, 404, 409, 422)
- **Chat endpoint**: Entire agent call wrapped in try/except — returns placeholder message on failure (agent unavailable, service not configured, etc.)
- **Project delete**: Azure index cleanup failure is non-fatal — project still deleted from DB
- **Sync trigger**: Temporal connection failure → falls back to marking project COMPLETED (dev mode)
- **Ownership checks**: Every endpoint with `{project_id}` or `{session_id}` verifies the resource belongs to the authenticated user (joins through Project.user_id)

### Schema Style

Pydantic v2 with `ConfigDict(from_attributes=True)` for ORM serialization. Request schemas are minimal; response schemas mirror the model. Route handlers return ORM objects directly (FastAPI serializes via response_model).

---

## Worker Patterns

### Temporal Connection

`worker/main.py` connects to Temporal with retries: up to 15 attempts, 3-second intervals. Registers all 6 activities and 1 workflow on task queue `talk-to-folder-sync`. Supports TLS via `TEMPORAL_API_KEY` env var (for Temporal Cloud).

### Activity Structure

All activities are `@activity.defn` async functions. No dependency injection — they read env vars directly via `os.environ.get()` and create their own httpx/SDK clients per invocation.

### Workflow Orchestration

`SyncFolderWorkflow` receives `SyncInput(project_id, folder_id, user_access_token, user_refresh_token)`.

**Pipeline** (sequential per-file):

| Step | Activity | Timeout | Retries | Notes |
|------|----------|---------|---------|-------|
| 1 | `crawl_folder` | 10 min | 3 | Recursive Drive listing, pagination (pageSize: 1000) |
| 2a | `extract_content` | 5 min | 2 | Per file. MIME dispatch: Google Docs/Sheets/Slides export, PDF/DOCX/XLSX binary extraction, text/CSV/MD direct download, images → placeholder |
| 2b | `chunk_content` | 2 min | 2 | Per file. See chunking strategy below |
| 2c | `generate_embeddings` | 10 min | 3 | Per file. OpenAI ada-002, batch 20, 0.5s inter-batch delay |
| 2d | `generate_questions` | 10 min | 2 | Per file. 3-5 questions via Claude Sonnet or GPT-4o-mini fallback, then embed |
| 3 | `index_chunks` | 5 min | 3 | All files batched. 500 chunks per Temporal payload, 100 per Azure Search upload |

Failed files are logged and skipped — processing continues with remaining files.

**Return value**: `{project_id, folder_id, total_files, processed_files, failed_files, indexed_chunks}`

### Chunking Strategy (`activities/chunk_content.py`)

- **Documents**: Split by markdown headings (`^#{1,6}\s+`) → sections. Each section: if ≤512 tokens → single chunk. If >512 tokens → split by paragraphs (double newline). If paragraph >512 tokens → fixed-window split (512 tokens, 50-token overlap using last 50 tokens of previous chunk prepended to next).
- **Spreadsheets**: One chunk per sheet. If sheet >1024 tokens → fixed-window split.
- **Tokenizer**: `tiktoken` cl100k_base encoding.
- **Chunk metadata**: `chunk_id` (UUID), `text`, `file_id`, `file_name`, `file_type`, `hierarchy`, `source_url`, `section_heading`, `page_number`, `sheet_name`.

### Embedding & Questions

- **Embeddings** (`generate_embeddings.py`): OpenAI ada-002. Batch size 20. Text truncated to 32k chars. 0.5s inter-batch delay. Rate-limit retry: waits 10s, max 5 retries. Adds `content_vector` (1536-dim) to each chunk.
- **Questions** (`generate_questions.py`): Prefers Claude Sonnet (`claude-sonnet-4-20250514`) if `ANTHROPIC_API_KEY` set, falls back to GPT-4o-mini. Generates 3-5 hypothetical questions per chunk (text truncated to 6000 chars, temp 0.7, max 500 tokens). Strips numbering, validates question marks. Concatenated questions embedded with ada-002 (32k char truncation). Batch size 5, 1.0s delay. Empty questions/vectors on error. Adds `questions` (list[str]) + `questions_vector` (1536-dim).

---

## Frontend Patterns

### State Management

| Concern | Tool | Location |
|---------|------|----------|
| Auth (user session) | Zustand | `hooks/useAuth.ts` |
| Server data (projects, sessions, messages) | React Query | `hooks/useProjects.ts`, `hooks/useChat.ts` |
| Local UI (modals, inputs, temp messages) | useState | Component-level |

**React Query config** (in `main.tsx`): `staleTime: 30s`, `retry: 1`, `refetchOnWindowFocus: false`.

**React Query keys**:
- `["projects"]` — all user projects
- `["project-sync", projectId]` — sync status polling
- `["chat-sessions", projectId]` — sessions for a project
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

### Chat Hook (`hooks/useChat.ts`)

Hybrid approach: local `useState` for new conversations (no session yet), React Query for existing sessions.

- `sendMessage()`: Creates temp user message (optimistic update with `id: "temp-..."`) → calls API → on success: removes temp, sets session ID if new, adds real messages → on error: adds error assistant message
- `selectSession(id)`: Switches to existing session (clears local buffer, React Query fetches messages)
- `startNewChat()`: Clears session ID + local messages (starts fresh)
- `allMessages`: returns `existingMessages` from React Query if session exists, else local `messages` state

### Sync Polling (`hooks/useProjects.ts`)

`useProjectSyncStatus` uses React Query's `refetchInterval` as a function:
- If `sync_status === "SYNCING" || "PROCESSING"` → refetch every 3000ms
- Otherwise → `false` (stop polling)

### API Layer (`services/api.ts`)

Axios instance with `baseURL: ""` (Vite proxy handles routing), `withCredentials: true` (sends HTTPOnly session cookies). Response interceptor catches 401 → redirects to `/` if not already there.

Functions follow `verb + noun`: `getProjects`, `createProject`, `deleteProject`, `triggerSync`, `getSyncStatus`, `getChatSessions`, `getMessages`, `sendMessage`, `getCurrentUser`, `login`, `logout`.

### Component Conventions

- Functional components with hooks. Props down, events up (`onSend`, `onDelete`, `onClose`).
- Early return for loading/error/empty states.
- `useMemo` for expensive parsing (citation regex in `MessageBubble`).
- **Two-step deletion** (`ProjectCard`): Click delete → shows confirm button → auto-cancels after 3 seconds via `setTimeout`.
- **Auto-resize textarea** (`ChatInput`): Measures `scrollHeight`, sets height dynamically (max 160px ≈ 4 lines), resets after send. Enter sends, Shift+Enter adds newline.
- **Auto-scroll** (`MessageList`): `useRef` on container + `useEffect` scrolls to bottom on new messages.
- **Citation parsing** (`MessageBubble`): Regex `sourcePattern = /\[source:\s*([^\]]+)\]|\[(\d+)\]/g` finds `[source: filename]` and `[1]` patterns in message content → replaces with `<CitationTooltip>` components. Wrapped in `useMemo`.
- **Modal behavior** (`AddFolderModal`): Auto-focus name input on mount. Escape key closes. Backdrop blur with `bg-black/60`. Drive URL validation regex: `/^https:\/\/drive\.google\.com\/(drive\/)?folders\/[a-zA-Z0-9_-]+/`.
- **Project filtering**: `ChatContainer` only shows projects where `sync_status === "COMPLETED"` in the project selector dropdown.

### Routing

Three-tab layout behind auth gate:
- `/knowledge` → `ProjectList` (manage Drive folders)
- `/chat` → `ChatContainer` (RAG Chat — chat with indexed documents)
- `/drive-chat` → `DriveChatContainer` (Drive Chat — live Drive API search, no pre-indexing)
- `/*` → redirect to `/knowledge`
- Unauthenticated → `LandingPage`

### Styling

Dark-mode only. Tailwind 3.4 with custom `@layer components` classes:
- `btn-primary`, `btn-secondary`, `btn-danger`, `btn-ghost`
- `card` (rounded-xl, border, shadow, `bg-surface-850`)
- `input-field` (focus ring brand-500, border transition)
- Custom colors: `brand-*` (blue, 50→900, 600 is main), `surface-*` (dark grays, 50/100/700/800/850/900/950; 950 is background)
- Custom scrollbar (thin, rounded, gray), Inter font
- See `claude_docs/002_styling_guide.md` for full palette and typography

---

## Environment Variables

| Variable | Required | Used By | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | API | PostgreSQL async connection string |
| `GOOGLE_CLIENT_ID` | Yes | API | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | API | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | Yes | API | OAuth callback URL (default: `http://localhost:8000/auth/google/callback`) |
| `AZURE_SEARCH_ENDPOINT` | Yes | API, Worker | Azure AI Search endpoint URL |
| `AZURE_SEARCH_API_KEY` | Yes | API, Worker | Azure AI Search admin key |
| `AZURE_SEARCH_INDEX_NAME` | Yes | API, Worker | Index name (default: `talk-to-folder-chunks`) |
| `OPENAI_API_KEY` | Yes | API, Worker | OpenAI key (embeddings + fallback LLM) |
| `ANTHROPIC_API_KEY` | No | API, Worker | Anthropic key (primary LLM if set) |
| `TEMPORAL_HOST` | No | API, Worker | Temporal gRPC address (default: `localhost:7233`) |
| `TEMPORAL_NAMESPACE` | No | API, Worker | Temporal namespace (default: `default`) |
| `TEMPORAL_API_KEY` | No | Worker | Temporal Cloud API key (enables TLS) |
| `ENCRYPTION_KEY` | Yes | API | Fernet key for token encryption at rest |
| `SESSION_SECRET` | Yes | API | Secret for session management |
| `AZURE_STORAGE_CONNECTION_STRING` | No | API | Azure Blob Storage (optional, unused currently) |

---

## Docker

### API Image (`Dockerfile`)

Multi-stage build:
1. **Stage 1** (Node 20 Alpine): Build frontend → `/dist`
2. **Stage 2** (Python 3.12 slim): Install backend deps, copy frontend build to `/static`, run Alembic migrations on startup, start Uvicorn on port 8000

Entrypoint: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000`

### Worker Image (`Dockerfile.worker`)

Single-stage Python 3.12 slim with system deps: `poppler-utils` (PDF), `tesseract-ocr` (OCR), `libpq-dev`. Runs `python -m worker.main`.

### docker-compose.yml

4 services: `db` (Postgres 15 Alpine on :5432), `temporal` (auto-setup v1.22 on :7233/:8233), `app` (API on :8000), `worker`. Volume: `pgdata`.

Health check: `db` uses `pg_isready`. `app` and `worker` depend on `db` (healthy) + `temporal` (started).

---

## Testing

- **Backend**: `pytest` with `asyncio_mode=auto`. Tests in `backend/tests/` mirroring `backend/app/` structure. `conftest.py` provides `test_client` (authenticated, overrides `get_current_user`) and `unauthed_client` fixtures using ASGITransport (no network). Mock user has fixed UUID `00000000-0000-0000-0000-000000000001`.
- **Frontend**: Vitest 2.1 with jsdom. `@testing-library/react` + `@testing-library/jest-dom`. Config in `vitest.config.ts` (globals: true). Tests co-located in `__tests__/` next to source.
- **Rule**: Every feature change must include corresponding test changes (enforced by stop hook).

---

## Known Limitations

- **In-memory sessions**: `utils/security.py` stores sessions in a Python dict. Restarts lose all sessions. Multi-worker deploys need Redis or similar.
- **No automatic token refresh**: Google access tokens expire (~1 hour) but there's no background refresh logic. Users need to re-login when tokens expire.
- **Cookie `secure=False`**: Set in `routers/auth.py` line 168. Must change to `True` for production HTTPS.
- **Hardcoded redirect URLs**: OAuth callback redirects to `http://localhost:5173`. Needs to be configurable for production.
- **`google_auth.py` service unused**: The OAuth helper service exists but all auth logic lives directly in `routers/auth.py`.
- **No CI/CD pipeline**: No GitHub Actions, GitLab CI, or similar configured.
- **Sequential file processing**: Worker processes files one at a time (not parallel). Large folders will be slow.
- **Sync tokens in Temporal payload**: `routers/sync.py` passes decrypted Google tokens as plain text in the Temporal workflow input. These are visible in the Temporal UI. Consider encrypting the payload or using a token-exchange service.
- **`Sidebar.tsx` unused**: Layout component exists but Header + TabNav are composed directly in `App.tsx`.
