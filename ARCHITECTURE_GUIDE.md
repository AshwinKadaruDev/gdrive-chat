# Talk-to-a-Folder: Architecture & Concepts Guide

A deep walkthrough of how this codebase works — the concepts, the patterns, and the "why" behind every layer. Written so you can teach a smart developer how the whole system fits together.

---

## Table of Contents

1. [What This App Does (30-Second Version)](#1-what-this-app-does)
2. [The Tech Stack and Why Each Piece Exists](#2-the-tech-stack)
3. [Project Structure — How Files Are Organized](#3-project-structure)
4. [Core Concepts You Need to Know](#4-core-concepts)
   - [FastAPI & Dependency Injection](#fastapi--dependency-injection)
   - [Pydantic — Validation & Serialization](#pydantic--validation--serialization)
   - [SQLAlchemy — ORM & Database](#sqlalchemy--orm--database)
   - [Alembic — Database Migrations](#alembic--database-migrations)
   - [Zustand & React Query (Frontend State)](#zustand--react-query)
5. [The Backend Layer by Layer](#5-the-backend-layer-by-layer)
   - [Entry Point: main.py](#entry-point-mainpy)
   - [Configuration: config.py](#configuration-configpy)
   - [Dependency Injection: dependencies.py](#dependency-injection-dependenciespy)
   - [Database Models: models/](#database-models)
   - [Pydantic Schemas: schemas/](#pydantic-schemas)
   - [Routers: Where API Endpoints Live](#routers)
   - [Services: Where Business Logic Lives](#services)
   - [Utils: Security & File Parsing](#utils)
6. [Core Flow #1: Authentication (Google OAuth)](#6-authentication-flow)
7. [Core Flow #2: Adding a Google Drive Folder](#7-adding-a-folder)
8. [Core Flow #3: Chatting with Your Documents](#8-chatting-with-documents)
   - [The Agent: How It Thinks](#the-agent-how-it-thinks)
   - [Tools: What the Agent Can Do](#tools-what-the-agent-can-do)
   - [The Tool Executor: Dispatch & Security](#the-tool-executor)
   - [Citations: How Sources Are Tracked](#citations)
   - [SSE Streaming: Real-Time Responses](#sse-streaming)
9. [The Frontend Layer by Layer](#9-the-frontend-layer-by-layer)
   - [Entry Point & Routing: main.tsx → App.tsx](#frontend-entry-point)
   - [The API Layer: services/api.ts](#the-api-layer)
   - [Hooks: Where State Logic Lives](#hooks)
   - [Components: The UI Tree](#components)
10. [Security Architecture](#10-security)
11. [DRY Patterns & Separation of Concerns](#11-dry-patterns)
12. [How Everything Connects (End-to-End)](#12-end-to-end)

---

## 1. What This App Does

A user signs in with Google, pastes a Google Drive folder URL, and then chats with an AI that can search, read, and reason over every file in that folder — PDFs, Docs, Spreadsheets, text files. The AI cites every claim back to the source document with clickable links.

```
User signs in → Pastes Drive folder URL → Asks questions → Gets answers with [1] [2] citations
```

---

## 2. The Tech Stack

| Layer | Technology | Why It's Here |
|-------|-----------|---------------|
| **Backend framework** | FastAPI (Python) | Async-native, automatic OpenAPI docs, built-in dependency injection, Pydantic integration |
| **Database** | PostgreSQL | Reliable relational DB for users, projects, sessions, messages |
| **ORM** | SQLAlchemy 2.0 (async) | Maps Python classes to DB tables — no raw SQL needed |
| **Migrations** | Alembic | Tracks and applies database schema changes over time |
| **Auth** | Google OAuth 2.0 | Users already have Google accounts for Drive access |
| **Encryption** | Fernet (symmetric) | Encrypts Google tokens at rest in the database |
| **LLM** | GPT-5.2 (OpenAI) | Powers the AI agent that reasons over documents |
| **Frontend framework** | React 18 + TypeScript | Component-based UI with type safety |
| **Build tool** | Vite | Fast dev server with hot reload, proxies API calls to backend |
| **Styling** | Tailwind CSS | Utility-first CSS — dark/light theme via CSS variables |
| **Client state** | Zustand | Lightweight global state (auth, theme) — simpler than Redux |
| **Server state** | React Query | Caches API responses, handles loading/error states, auto-refetching |
| **HTTP client** | Axios | Request/response interceptors, automatic cookie handling |
| **Deployment** | Docker → Azure App Service | Multi-stage build (frontend + backend in one image) |

---

## 3. Project Structure

The codebase follows a **separation by concern** pattern. Backend code is organized by *what it does* (models, routers, services, schemas), not by feature. Frontend code is organized by *type* (hooks, components, services) with components further grouped by *feature area* (auth, chat, knowledge, layout).

```
tenex/
├── backend/app/
│   ├── main.py              ← The FastAPI app (entry point, middleware, routing)
│   ├── config.py            ← All environment variables in one place
│   ├── dependencies.py      ← Shared injectable functions (DB, auth, config)
│   ├── models/              ← Database table definitions (SQLAlchemy ORM)
│   ├── schemas/             ← Request/response validation (Pydantic)
│   ├── routers/             ← API endpoint handlers (thin — delegates to services)
│   ├── services/            ← Business logic (agent, LLM, Drive API, tools)
│   └── utils/               ← Cross-cutting utilities (encryption, file parsing)
│
├── frontend/src/
│   ├── App.tsx              ← Root component (routing, auth gate)
│   ├── main.tsx             ← React entry point (providers)
│   ├── types/index.ts       ← All TypeScript interfaces
│   ├── services/api.ts      ← All API calls in one file
│   ├── hooks/               ← State management (Zustand stores, React Query hooks)
│   └── components/          ← UI organized by feature area
│       ├── auth/            ← Login page
│       ├── knowledge/       ← Folder management (add, view, sync, delete)
│       ├── chat/            ← Chat interface (messages, input, citations)
│       └── layout/          ← Shell (top bar, navigation)
│
├── backend/alembic/         ← Database migration scripts
├── Dockerfile               ← Production build (frontend + backend in one image)
├── run.ps1                  ← Dev startup script
└── .env                     ← Environment variables (never committed)
```

**Why this structure matters**: A developer looking for "where does the chat API live?" goes to `routers/chat.py`. "Where does the agent logic live?" → `services/agent.py`. "Where are the DB tables defined?" → `models/`. There's one obvious place for everything.

---

## 4. Core Concepts You Need to Know

### FastAPI & Dependency Injection

**FastAPI** is a Python web framework built on top of Starlette (ASGI) and Pydantic. Think of it as Flask but async-native, with automatic request validation and API documentation.

**Dependency Injection (DI)** is the key pattern. Instead of every endpoint function manually creating database connections or checking authentication, FastAPI lets you declare *what you need* as function parameters, and the framework provides them automatically:

```python
# Without DI — every endpoint does this manually
@router.get("/projects")
async def list_projects(request: Request):
    db = await create_session()        # manual
    user = await check_auth(request)   # manual
    ...

# With DI — FastAPI injects what you declare
@router.get("/projects")
async def list_projects(
    db: AsyncSession = Depends(get_db),           # FastAPI calls get_db() for you
    current_user: User = Depends(get_current_user) # FastAPI calls get_current_user() for you
):
    ...  # db and current_user are ready to use
```

The `Depends()` function tells FastAPI: "before calling this endpoint, run this function and pass its result as this parameter." This is how every protected endpoint gets its database session and authenticated user — without repeating that logic.

**Where DI is defined**: `backend/app/dependencies.py` — three functions:
- `get_settings()` → loads config once (cached)
- `get_db()` → yields a database session per request, auto-commits or rolls back
- `get_current_user()` → validates the session cookie, queries the DB, returns the User object (or 401)

---

### Pydantic — Validation & Serialization

**Pydantic** is a data validation library. You define a class with typed fields, and Pydantic automatically validates incoming data and rejects anything that doesn't match.

In this project, Pydantic serves two jobs:

**Job 1: Validate incoming requests** (schemas as "gatekeepers")

```python
# backend/app/schemas/chat.py
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=32000)
    session_id: Optional[uuid.UUID] = None
    gdrive_folder_id: Optional[str] = None
```

When someone POSTs to `/api/chat`, FastAPI automatically parses the JSON body into a `ChatRequest`. If `message` is empty or over 32,000 chars, FastAPI returns a 422 error *before your code even runs*. You never write `if len(message) > 32000: return error` — Pydantic handles it.

**Job 2: Serialize outgoing responses** (schemas as "filters")

```python
# backend/app/schemas/user.py
class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    name: str
    picture_url: Optional[str] = None
```

The `UserResponse` schema defines *exactly* what fields the frontend gets. The `User` database model has `google_access_token` and `google_refresh_token` — but since they're not in `UserResponse`, they're never sent to the client. `from_attributes=True` lets Pydantic read directly from SQLAlchemy objects (attribute access, not dict keys).

**Where schemas live**: `backend/app/schemas/` — one file per domain (user.py, project.py, chat.py, error.py).

---

### SQLAlchemy — ORM & Database

**SQLAlchemy** is an Object-Relational Mapper (ORM). Instead of writing raw SQL, you define Python classes that map to database tables, and SQLAlchemy translates your Python operations into SQL.

```python
# backend/app/models/user.py — defines the "users" table
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    google_access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # ... more fields

    projects: Mapped[list["Project"]] = relationship(back_populates="user", cascade="all, delete-orphan")
```

What this gives you:
- `User(email="john@example.com", name="John")` creates a row
- `session.get(User, some_uuid)` fetches by primary key → `SELECT * FROM users WHERE id = ?`
- `user.projects` automatically queries the projects table (lazy loading via the relationship)
- `cascade="all, delete-orphan"` → deleting a user automatically deletes all their projects, sessions, and messages

**This project uses SQLAlchemy 2.0 async** — all database operations are `await`ed, which means the server can handle other requests while waiting for database responses. The async engine uses `asyncpg` as the PostgreSQL driver.

**Where models live**: `backend/app/models/` — one file per table (user.py, project.py, chat.py, message.py).

**The 4 tables and their relationships:**
```
users ──1:N──→ projects ──1:N──→ chat_sessions ──1:N──→ messages
  │                                    ↑
  └──────────────1:N──────────────────┘
```

Every delete cascades down: delete a user → their projects, sessions, and messages all go away.

---

### Alembic — Database Migrations

**Problem**: Your Python models define what the database *should* look like. But what happens when you add a column, create a new table, or change a constraint? You can't just drop and recreate the database — that would destroy all data.

**Alembic** solves this. It's a migration tool that:
1. **Detects changes** between your SQLAlchemy models and the actual database schema
2. **Generates migration scripts** that describe the change (e.g., "add column `sync_error` to `projects`")
3. **Applies migrations** in order, upgrading the database schema without losing data

```bash
# Step 1: You add a field to a model
# class Project(Base):
#     sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # NEW

# Step 2: Generate a migration script
alembic revision --autogenerate -m "add sync_error to projects"
# → Creates backend/alembic/versions/abc123_add_sync_error.py

# Step 3: Apply the migration
alembic upgrade head
# → Runs ALTER TABLE projects ADD COLUMN sync_error TEXT;
```

**Where Alembic is configured**: `backend/alembic/env.py` — this file tells Alembic where the database is (reads `DATABASE_URL` from `.env`) and which models to compare against (`Base.metadata` from the SQLAlchemy models). It converts `postgresql://` to `postgresql+asyncpg://` for async compatibility.

**Migration files**: `backend/alembic/versions/` — each file is a snapshot of a schema change, with `upgrade()` and `downgrade()` functions.

In production, the Docker entrypoint runs `alembic upgrade head` before starting the server — so the database is always up to date.

---

### Zustand & React Query

The frontend has two kinds of state, and each gets its own tool:

**Zustand** = client-only state (things the server doesn't know about)
- **Auth state** (`useAuth`): Is the user logged in? Who are they?
- **Theme state** (`useTheme`): Light mode or dark mode?

Zustand is like a tiny Redux — a global store with actions, but without the boilerplate:

```typescript
// hooks/useAuth.ts — the entire auth store
const useAuth = create<AuthState>((set) => ({
  user: null,
  isLoading: false,
  hasChecked: false,
  fetchUser: async () => {
    set({ isLoading: true });
    try {
      const user = await getCurrentUser();
      set({ user, isLoading: false, hasChecked: true });
    } catch {
      set({ user: null, isLoading: false, hasChecked: true });
    }
  },
  logout: async () => { ... },
}));
```

Any component can call `useAuth()` to get the user or trigger login/logout.

**React Query** = server state (data from API calls)
- **Projects**: `useProjects()` → fetches and caches the folder list
- **Chat sessions**: `useUnifiedChatSessions()` → fetches and caches session history
- **Messages**: loaded per-session inside `useUnifiedChat`

React Query handles: loading states, error states, caching, refetching when data goes stale, and cache invalidation when mutations happen:

```typescript
// hooks/useProjects.ts
export function useProjects() {
  return useQuery({
    queryKey: ["projects"],          // cache key
    queryFn: () => getProjects(),    // API call
  });
}

export function useDeleteProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] }); // refetch after delete
    },
  });
}
```

**Why two tools?** Zustand is for state the client owns (auth, UI preferences). React Query is for state the server owns (projects, messages) — it knows when to refetch, when to serve from cache, and how to handle loading/error. Mixing these concerns (e.g., putting API data in Zustand) leads to stale caches and manual refetch logic.

---

## 5. The Backend Layer by Layer

### Entry Point: main.py

`backend/app/main.py` is where the FastAPI application object is created. Everything connects here:

1. **Creates the FastAPI app** with a lifespan handler (startup/shutdown hooks)
2. **Registers middleware** in order:
   - `AuthGuardMiddleware` — validates session on all `/api/*` routes + CSRF protection
   - `CORSMiddleware` — allows cross-origin requests from the frontend
3. **Mounts routers**:
   - `/auth` → auth.py (login, logout, profile)
   - `/api/projects` → projects.py (CRUD)
   - `/api/chat` → chat.py (messages, streaming)
   - `/api/sync` → sync.py (folder sync)
4. **Rate limiting** via SlowAPI (10 requests/minute on chat endpoints)
5. **SPA serving** — in production, serves the built React app as static files

When a request arrives: Middleware runs first (auth check, CORS) → Router matches the URL → Endpoint function runs with injected dependencies → Response returned.

---

### Configuration: config.py

`backend/app/config.py` is a single Pydantic `Settings` class that reads every environment variable:

```python
class Settings(BaseSettings):
    DATABASE_URL: str
    GOOGLE_CLIENT_ID: str
    OPENAI_API_KEY: str
    ENCRYPTION_KEY: str
    AGENT_MODEL: str = "gpt-5.2"        # defaults if not set
    MAX_CHAT_HISTORY_MESSAGES: int = 100
    # ... every env var lives here

    model_config = SettingsConfigDict(env_file=".env")
```

**Why this matters**: There's exactly one place to look for any config value. If someone asks "what model does the agent use?", the answer is in `config.py`. Pydantic validates types on startup — if `DATABASE_URL` is missing, the app fails immediately with a clear error, not 30 seconds later when the first DB query runs.

---

### Dependency Injection: dependencies.py

Three injectable functions that almost every endpoint uses:

```python
@lru_cache()
def get_settings() -> Settings:
    return Settings()  # created once, cached forever

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session     # endpoint uses the session
            await session.commit()   # auto-commit if no error
        except:
            await session.rollback() # auto-rollback on error
            raise

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401)
    user_id = validate_session(session_id, settings)
    if not user_id:
        raise HTTPException(status_code=401)
    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=401)
    return user
```

Notice how `get_current_user` itself depends on `get_db` and `get_settings` — FastAPI resolves the whole dependency chain automatically. This is **DI composability** — dependencies can depend on other dependencies.

---

### Database Models

`backend/app/models/` — four files, one per table:

| File | Table | Key Fields | Relationships |
|------|-------|-----------|---------------|
| `user.py` | users | email, name, encrypted Google tokens | → projects |
| `project.py` | projects | name, gdrive_folder_id, sync_status, file counts | → user, → chat_sessions |
| `chat.py` | chat_sessions | title, gdrive_folder_id, project_id (optional) | → user, → project, → messages |
| `message.py` | messages | role (USER/ASSISTANT), content, citations (JSON) | → chat_session |

**Key design choices:**
- **UUIDs as primary keys** — no sequential IDs that leak information about total records
- **Cascade deletes** — deleting a user cascades through projects → sessions → messages
- **Encrypted tokens** — Google access/refresh tokens stored as Fernet-encrypted text, never plaintext
- **Citations as JSON** — stored directly on the message row, not in a separate table (they're always loaded with the message)

---

### Pydantic Schemas

`backend/app/schemas/` — separate from models. This is an important distinction:

- **Models** = what the *database* looks like (internal)
- **Schemas** = what the *API* looks like (external)

Example: The `User` model has `google_access_token` and `google_refresh_token`. The `UserResponse` schema does NOT — those fields are never exposed to the frontend. Schemas act as a security boundary.

```python
# The model (internal) — has sensitive fields
class User(Base):
    email, name, google_access_token, google_refresh_token, ...

# The schema (external) — only safe fields
class UserResponse(BaseModel):
    id, email, name, picture_url, created_at
    # No tokens here — they never leave the server
```

Schemas also handle **input validation**: `ChatRequest` enforces `min_length=1, max_length=32000` on the message field. FastAPI returns 422 automatically if validation fails.

---

### Routers

`backend/app/routers/` — four files, one per API area. Routers are **thin** — they handle HTTP concerns (request parsing, response formatting, status codes) and delegate business logic to services.

| Router | Prefix | What It Does |
|--------|--------|-------------|
| `auth.py` | `/auth` | Google OAuth login/callback, logout, user profile |
| `projects.py` | `/api/projects` | CRUD for Drive folders, URL validation |
| `chat.py` | `/api/chat` | Send messages, stream responses, session management |
| `sync.py` | `/api/sync` | Trigger file count sync, check status |

**Pattern**: Every endpoint in `projects.py`, `chat.py`, and `sync.py` uses `Depends(get_current_user)` — if you're not authenticated, you never reach the handler code.

---

### Services

`backend/app/services/` — where the real logic lives. This is the most important directory:

| File | Responsibility |
|------|---------------|
| `agent.py` | The ReAct loop — orchestrates the LLM + tools to answer questions |
| `agent_tools.py` | Tool definitions (what tools exist, their parameters) — pure data, no logic |
| `tool_executor.py` | Runs tools when the agent requests them — dispatches to handler functions |
| `llm.py` | Talks to OpenAI's API — sends prompts, receives responses, handles streaming |
| `google_drive.py` | Talks to Google Drive API — list files, download, search, export |

These are completely **decoupled from HTTP**. The agent doesn't know it's being called from a web server. The LLM client doesn't know it's being used by an agent. You could use any of these services from a CLI tool or a background job.

---

### Utils

`backend/app/utils/` — cross-cutting concerns:

| File | What It Does |
|------|-------------|
| `security.py` | Fernet encryption/decryption, session token creation/validation, Google token refresh |
| `file_parsers.py` | Extracts text from PDFs (pypdf), DOCX (python-docx), XLSX (openpyxl), token counting (tiktoken) |

---

## 6. Authentication Flow

Here's exactly what happens when a user logs in, file by file:

```
Step 1: User clicks "Sign in with Google"
├── Frontend: GoogleLoginButton.tsx calls useAuth().login()
├── useAuth.ts: login() sets window.location.href = "/auth/google/login"
└── Browser navigates to backend

Step 2: Backend redirects to Google
├── routers/auth.py → google_login()
├── Generates CSRF state token (random bytes, stored in secure cookie)
├── Builds Google OAuth URL with scopes: openid, email, profile, drive.readonly
└── Returns RedirectResponse to Google's consent screen

Step 3: User approves, Google redirects back
├── routers/auth.py → google_callback(code=..., state=...)
├── Validates CSRF state token matches cookie
├── Exchanges auth code for tokens via Google Token URL (httpx POST)
├── Fetches user profile from Google userinfo endpoint
├── Upserts User row in database:
│   ├── Encrypts access_token and refresh_token with Fernet (utils/security.py)
│   └── Stores encrypted tokens in users table
├── Creates session: utils/security.py → create_session(user_id)
│   └── Fernet-encrypts the user_id — the token IS the session (stateless)
├── Sets HTTPOnly cookie: "session_id" = encrypted_token
│   ├── httponly=True (JavaScript can't read it)
│   ├── samesite="lax" (CSRF protection)
│   ├── secure=True if FRONTEND_URL uses https
│   └── max_age=24h
└── Redirects to FRONTEND_URL (e.g., http://localhost:5173)

Step 4: Frontend loads, checks auth
├── App.tsx → useEffect calls fetchUser()
├── useAuth.ts → fetchUser() calls getCurrentUser()
├── services/api.ts → GET /auth/me (Axios sends cookie automatically)
├── routers/auth.py → me() with Depends(get_current_user)
├── dependencies.py → get_current_user():
│   ├── Reads "session_id" cookie
│   ├── utils/security.py → validate_session() decrypts Fernet token
│   ├── Checks TTL (24h) and revocation list
│   ├── Extracts user_id, queries database
│   └── Returns User object
├── Schema: UserResponse filters out tokens
└── Frontend: useAuth sets user state → renders AuthenticatedLayout
```

**Why stateless sessions?** The session token is a Fernet-encrypted user_id. No session table, no Redis, no server-side state needed. Fernet's built-in timestamp enables TTL checking. The only server-side state is a small `_revoked` dict for explicit logouts (pruned automatically).

---

## 7. Adding a Folder

When a user pastes a Google Drive folder URL and clicks "Add":

```
Step 1: User opens the modal
├── ProjectList.tsx: renders "Add Folder" button
└── Click → sets showModal=true → renders AddFolderModal

Step 2: User pastes URL, frontend validates format
├── AddFolderModal.tsx: onChange handler runs regex check
│   └── Pattern: drive.google.com/drive/(u/\d+/)?folders/[A-Za-z0-9_-]+
├── If format valid → debounce 600ms → call validateFolder()
├── services/api.ts → POST /api/projects/validate-folder { gdrive_folder_url }

Step 3: Backend validates the folder exists and is accessible
├── routers/projects.py → validate_folder()
├── Extracts folder_id from URL via regex
├── Decrypts user's Google access token (utils/security.py)
├── Refreshes token if expired (utils/security.py → get_valid_access_token())
├── services/google_drive.py → validate_folder(folder_id, access_token)
│   └── GET https://www.googleapis.com/drive/v3/files/{folder_id}
│       ├── 401 → DriveAuthError (token expired)
│       ├── 403 → DrivePermissionError (no access)
│       ├── 404 → DriveValidationError (not found)
│       └── 200 but not a folder → DriveValidationError
└── Returns { folder_id, folder_name, url } to frontend

Step 4: Frontend shows "✓ folder_name" — user clicks "Add Folder"
├── AddFolderModal.tsx: onSubmit → useCreateProject().mutate()
├── services/api.ts → POST /api/projects { gdrive_folder_url, name }

Step 5: Backend creates the project
├── routers/projects.py → create_project()
├── Extracts folder_id from URL
├── Checks unique constraint (user_id, folder_id) → 409 if duplicate
├── If no name provided → fetches folder name from Drive API
├── Counts files via google_drive.py → count_files()
├── Creates Project row: sync_status=PENDING, files_total=count
├── database auto-commits (dependencies.py get_db pattern)
└── Returns ProjectResponse (201)

Step 6: Frontend updates
├── useCreateProject: onSuccess → queryClient.invalidateQueries(["projects"])
├── React Query refetches project list automatically
├── ProjectList re-renders with new ProjectCard
└── Modal closes
```

**The key pattern**: The router is thin — it validates input, extracts the folder ID, and delegates to `GoogleDriveService` for the actual Drive API call. The service knows nothing about HTTP.

---

## 8. Chatting with Documents

This is the most complex flow in the app. Here's how a user question becomes an answer with citations.

### The Agent: How It Thinks

The `FolderAgent` (`services/agent.py`) implements a **ReAct loop** — a pattern where an LLM alternates between **reasoning** (thinking about what to do) and **acting** (calling tools to get information).

```
User asks: "What was our Q3 revenue?"

Iteration 1:
  LLM thinks: "I should look at the folder structure first to find financial files"
  LLM calls: get_folder_structure()
  Result: Shows files like "Q3_Financial_Report.xlsx", "Revenue_Summary.pdf"

Iteration 2:
  LLM thinks: "The spreadsheet likely has the number. Let me check it."
  LLM calls: get_spreadsheet_overview(file_id="abc123")
  Result: Sheets: ["Revenue", "Expenses"], headers: ["Quarter", "Revenue", "Growth"]

Iteration 3:
  LLM thinks: "I need the Q3 row from the Revenue sheet"
  LLM calls: read_spreadsheet_rows(file_id="abc123", sheet_name="Revenue", start_row=1, end_row=10)
  Result: "Q3 | $4.2M | +12%" + [Citation: Q3_Financial_Report.xlsx]

Iteration 4:
  LLM thinks: "I have the answer now."
  LLM returns: "Your Q3 revenue was $4.2M, representing 12% growth. [1]"
  → No tool calls = final answer → loop ends
```

The loop runs up to **15 iterations** max. If it hits the limit, it returns whatever partial answer it has with a warning.

**The system prompt** (`DRIVE_SYSTEM_PROMPT` in `agent.py`) instructs the agent to use a **folder-first strategy**: always call `get_folder_structure` first (file names are usually descriptive enough to find what you need), then read specific files. `search_drive` is a fallback for content-based search.

### The Full Chat Flow (File by File)

```
Step 1: User types message and hits Enter
├── ChatInput.tsx: onSend(content)
├── UnifiedChatContainer.tsx: passes to useUnifiedChat's sendMessage()
├── useUnifiedChat.ts → sendMessage(content):
│   ├── Creates optimistic user message (appears immediately)
│   ├── Creates placeholder assistant message (shows loading)
│   └── Calls streamChat() from services/api.ts

Step 2: Frontend opens SSE stream
├── services/api.ts → streamChat():
│   ├── POST /api/chat/stream (using fetch(), not Axios — needed for streaming)
│   ├── Body: { message, session_id (if existing), gdrive_folder_id }
│   └── Reads response.body as ReadableStream

Step 3: Backend receives the request
├── routers/chat.py → stream_chat()
├── dependencies.py → get_current_user() validates session
├── If new session: creates ChatSession row, persists user message
├── If existing session: loads chat history from database
├── Decrypts user's Google tokens (utils/security.py)
├── Refreshes token if expired (security.py → get_valid_access_token())
├── Creates service instances:
│   ├── LLMClient(openai_api_key=...)
│   ├── GoogleDriveService()
│   └── FolderAgent(llm_client, drive_service, tools=DRIVE_AGENT_TOOLS)

Step 4: Agent runs the ReAct loop
├── services/agent.py → answer_streaming()
├── Builds messages: [DRIVE_SYSTEM_PROMPT, ...chat_history, user_question]
│
├── LOOP (max 15 iterations):
│   ├── services/llm.py → stream_call_with_tools()
│   │   ├── Converts messages to OpenAI Responses API format
│   │   ├── Converts tool definitions to flat format
│   │   ├── POST to OpenAI API with reasoning=xhigh
│   │   └── Streams response tokens back
│   │
│   ├── If response has tool_calls:
│   │   ├── Yields ("status", "Searching files...") → sent as SSE event
│   │   ├── For each tool call:
│   │   │   ├── services/tool_executor.py → execute_tool()
│   │   │   │   ├── Injects project_id + access_token (NEVER from LLM)
│   │   │   │   ├── Dispatches to _handle_{tool_name}() function
│   │   │   │   ├── Handler calls google_drive.py or parses files
│   │   │   │   └── Returns (result_text, citations[])
│   │   │   └── Appends tool result to messages for next iteration
│   │   └── Continue loop
│   │
│   └── If response has NO tool_calls (final answer):
│       ├── Yields ("delta", "text chunk") → SSE events
│       ├── Yields ("citations", [...all accumulated citations])
│       ├── Yields ("done", null)
│       └── Loop ends

Step 5: Router persists the response
├── routers/chat.py: collects streamed content + citations
├── Creates Message row: role=ASSISTANT, content=full_text, citations=JSON
└── Commits to database

Step 6: Frontend receives SSE events
├── services/api.ts: streamChat() parses SSE events:
│   ├── "session" → onSession(session_id) — stores new session ID
│   ├── "status" → onStatus(text) — "Reading Q3_Report.xlsx..."
│   ├── "delta" → onDelta(text) — appends to assistant message content
│   ├── "citations" → onCitations([...]) — attaches to message
│   └── "done" → onDone() — finalizes
├── useUnifiedChat.ts: callbacks update local state
│   ├── Assistant message accumulates text in real-time
│   ├── Status text shows what the agent is doing
│   └── On done: commits session ID, invalidates React Query cache
└── MessageBubble.tsx re-renders with streamed text + citations
```

### Tools: What the Agent Can Do

12 tools, defined as pure data in `agent_tools.py`:

**Drive-only (direct Google Drive API calls):**
| Tool | Purpose |
|------|---------|
| `search_drive` | Keyword search across file contents in the folder |
| `get_file_content` | Download and read a full file (PDF, DOCX, Docs, text) |
| `search_within_file_text` | Find specific text within a downloaded file |

**Shared tools:**
| Tool | Purpose |
|------|---------|
| `get_folder_structure` | **CALL FIRST** — ASCII tree of all files with IDs and sizes |
| `get_file_metadata` | File info: name, type, size, modified date, Drive link |
| `read_document_pages` | Read specific pages of a document (~3000 chars/page) |
| `get_spreadsheet_overview` | Sheet names, dimensions, headers, sample rows |
| `read_spreadsheet_rows` | Read a specific row range from a spreadsheet |
| `search_spreadsheet` | Search for values across cells in a spreadsheet |
| `get_column_stats` | Numeric column statistics (count, sum, mean, median, etc.) |
| `report_inability` | Tell the user the question can't be answered |
| `request_clarification` | Ask the user for more details |

Tool definitions use the **OpenAI function calling schema** — the LLM sees the tool name, description, and parameter definitions, and decides which to call based on the question.

### The Tool Executor

`tool_executor.py` is the **security boundary** between the LLM and the real world.

When the LLM says "call `get_file_content` with `file_id=abc123`", the executor:
1. **Injects credentials server-side** — adds `project_id` (folder ID) and `access_token` (user's Google token) that the LLM never sees
2. **Dispatches** to the right `_handle_*` function based on tool name
3. **Catches errors** — if a Drive API call fails, returns an error message to the LLM (doesn't crash the loop)
4. **Returns results + citations** — the handler produces text results and citation objects

This is critical security: **the LLM only controls tool arguments like `file_id` and `query` — never credentials**.

### Citations

Citations are `@dataclass` objects accumulated across all tool calls in a single agent run:

```python
@dataclass
class Citation:
    chunk_id: str        # unique ID for this citation
    file_id: str         # Google Drive file ID
    file_name: str       # human-readable name
    source_url: str      # link to file in Google Drive
    location: str        # e.g., "Sheet: Revenue, Rows 1-10"
    snippet: str         # preview text from the source
```

**Citation policy**: Only content-reading tools produce citations (`get_file_content`, `read_spreadsheet_rows`, etc.). Discovery tools don't (`search_drive`, `get_folder_structure`). This prevents inflated citation counts — finding a file isn't citing it.

On the frontend, `MessageBubble.tsx` uses regex to find `[1]`, `[2]` patterns in the response text and replaces them with interactive `CitationTooltip` components that show the snippet and link to Google Drive.

### SSE Streaming

Instead of waiting for the full response, the backend streams events to the frontend using **Server-Sent Events (SSE)**:

```
event: session
data: {"session_id": "abc-123"}

event: status
data: {"text": "Reading Q3_Financial_Report.xlsx..."}

event: delta
data: {"content": "Your Q3 revenue was "}

event: delta
data: {"content": "$4.2M, representing "}

event: delta
data: {"content": "12% growth. [1]"}

event: citations
data: [{"file_name": "Q3_Financial_Report.xlsx", ...}]

event: done
data: {}
```

The frontend manually parses these events (not using EventSource — using `fetch()` with `ReadableStream` for more control over the connection). Text deltas are accumulated into the assistant message in real-time, so the user sees the response being "typed out."

---

## 9. The Frontend Layer by Layer

### Frontend Entry Point

```
main.tsx (boots the app)
  ├── Sets up theme from localStorage (prevents flash)
  ├── Creates React Query client (staleTime: 30s, retry: 1)
  ├── Wraps everything in QueryClientProvider + BrowserRouter
  └── Renders <App />

App.tsx (routing + auth gate)
  ├── On mount: calls fetchUser() to check if session is valid
  ├── Listens for "auth:session-expired" event (from api.ts 401 interceptor)
  ├── If not authenticated → renders LandingPage
  ├── If authenticated → renders AuthenticatedLayout:
  │   ├── TopBar (navigation tabs, user profile, theme toggle, logout)
  │   └── Routes:
  │       ├── /knowledge → ProjectList
  │       ├── /chat → UnifiedChatContainer
  │       └── /* → redirect to /knowledge
  └── Shows loading spinner while checking auth
```

### The API Layer

`services/api.ts` is the **single file** that handles all communication with the backend:

- Creates an Axios instance with `withCredentials: true` (sends cookies)
- **401 interceptor**: If any API call returns 401, dispatches `auth:session-expired` event → App.tsx catches it → forces logout
- **All endpoint functions** in one place: `getCurrentUser()`, `getProjects()`, `createProject()`, `streamChat()`, etc.
- **SSE streaming** uses `fetch()` (not Axios) because Axios doesn't support streaming. The `streamChat()` function manually parses SSE event format with buffer management for incomplete lines.

**Why one file?** Any developer can open `api.ts` and see every backend call the frontend makes. No hunting through components.

### Hooks

The hooks directory is where **all state logic** lives, separated from UI:

| Hook | Type | Purpose |
|------|------|---------|
| `useAuth` | Zustand store | Global auth state: user object, login/logout actions, loading state |
| `useTheme` | Zustand store | Light/dark theme toggle, persists to localStorage |
| `useProjects` | React Query | `useProjects()` — fetches project list. `useCreateProject()` — create + invalidate cache. `useDeleteProject()` — delete + invalidate. `useSyncProject()` — trigger sync. `useProjectSyncStatus(id)` — polls every 3s while syncing. `useValidateFolder()` — validate Drive URL |
| `useUnifiedChat` | React Query + useState | The most complex hook. Manages session state, message streaming, optimistic updates. `sendMessage()` opens SSE stream, accumulates deltas, commits session on completion. `selectSession()` switches to existing session. `startNewChat()` clears state. |

**Why hooks, not logic in components?** Components become pure UI — they receive data and render it. All the "when do I fetch?", "how do I cache?", "what happens on error?" logic lives in hooks. This means:
- You can change the UI without touching business logic
- You can change data fetching without touching the UI
- Hooks are testable in isolation

### Components

Components are organized by **feature area** and follow a consistent pattern:

```
components/
├── auth/                        ← Pre-login
│   ├── LandingPage.tsx          Logo + tagline + Google login button
│   └── GoogleLoginButton.tsx    Reusable Google sign-in button
│
├── knowledge/                   ← Folder management
│   ├── ProjectList.tsx          Grid of folders + add button + empty/loading/error states
│   ├── ProjectCard.tsx          Individual folder card: status, sync, 2-step delete
│   ├── AddFolderModal.tsx       URL input → validate → create (debounced validation)
│   └── SyncProgress.tsx         Animated progress bar during sync
│
├── chat/                        ← Chat interface
│   ├── UnifiedChatContainer.tsx Two-pane layout: session sidebar + messages area
│   ├── ChatInput.tsx            Auto-resize textarea, Enter to send
│   ├── MessageList.tsx          Scrollable message feed + auto-scroll + loading state
│   ├── MessageBubble.tsx        Renders markdown + citation [1] markers + sources
│   ├── CitationTooltip.tsx      Hover/click popup with snippet + Drive link
│   └── ProjectSelector.tsx      Folder dropdown in chat header
│
├── layout/
│   └── TopBar.tsx               Navigation tabs + user avatar + theme toggle + logout
│
└── TenexLogo.tsx                Shared SVG logo component
```

**Component conventions:**
- **Props down, events up**: Parent passes data via props, child communicates via callback props (`onSend`, `onDelete`, `onClose`)
- **Early returns** for loading/error/empty states (no nested ternaries)
- **Two-step deletion** (ProjectCard): Click delete → shows "Confirm?" button → auto-cancels after 3s. Prevents accidental deletes.
- **Auto-resize textarea** (ChatInput): Measures `scrollHeight`, sets height dynamically, caps at 5 lines. Enter sends, Shift+Enter adds newline.
- **Optimistic updates** (useUnifiedChat): User message appears immediately, assistant message placeholder shows loading, then text streams in.

---

## 10. Security

### Layered Defense

```
Layer 1: AuthGuard Middleware (main.py)
├── Runs on ALL /api/* routes before any handler
├── Validates session cookie → 401 if missing/invalid
└── CSRF: State-changing requests (POST/PUT/DELETE) must include X-Requested-With header → 403 if missing

Layer 2: Dependency Injection (dependencies.py)
├── get_current_user() validates session AND loads user from DB
└── Every protected endpoint declares Depends(get_current_user)

Layer 3: Ownership Checks (routers)
├── Every endpoint verifies the resource belongs to the requesting user
└── e.g., "is this project owned by this user?" — 404 if not
```

### Token Security

```
Google tokens at rest → Fernet-encrypted in PostgreSQL
Google tokens in transit → decrypted only server-side, immediately before Drive API calls
Google tokens to frontend → NEVER (not in any API response, not in UserResponse schema)
Google tokens to LLM → NEVER (tool_executor injects them, LLM only sees tool arguments)
```

### Session Security

```
Session token = Fernet-encrypted user_id
Cookie flags: httponly, samesite=lax, secure (if HTTPS), max_age=24h
Stateless: no session table — Fernet's timestamp enforces TTL
Revocation: in-memory dict for explicit logouts, pruned automatically
```

### CSRF Protection

Dual protection:
1. `SameSite=Lax` cookie — browser won't send cookie on cross-origin POST
2. `X-Requested-With` header required on state-changing requests — Axios adds this automatically, but a malicious form submission from another site won't include it

### Credential Injection (The Big One)

The LLM never sees or controls credentials. When the agent calls a tool:

```python
# tool_executor.py — execute_tool()
result, citations = await handler(
    args=tool_args,              # from the LLM (file_id, query, etc.)
    drive_service=drive_service,
    access_token=access_token,   # INJECTED SERVER-SIDE
    project_id=project_id,       # INJECTED SERVER-SIDE
)
```

The LLM provides `file_id` and `query`. The server adds `access_token` and `project_id`. This prevents prompt injection attacks from tricking the LLM into using someone else's credentials.

### Input Sanitization

`tool_executor.py` includes `_sanitize_for_agent()` — strips XML-like tags from tool results to prevent prompt injection via malicious document content:

```python
def _sanitize_for_agent(text: str) -> str:
    # Strips tags like <system>, </system>, <tool_result>, etc.
    # Prevents documents from injecting instructions into the agent
```

---

## 11. DRY Patterns & Separation of Concerns

### Backend Separation

```
config.py          → "what are our settings?"        (data)
dependencies.py    → "what do endpoints need?"        (injection)
models/            → "what does the database store?"  (persistence)
schemas/           → "what do API consumers see?"     (validation + serialization)
routers/           → "what HTTP endpoints exist?"     (HTTP layer — thin)
services/          → "what does the app actually do?" (business logic)
utils/             → "what's shared across layers?"   (encryption, parsing)
```

**No logic leaks between layers:**
- Routers don't contain business logic — they delegate to services
- Services don't know about HTTP — they don't import FastAPI or return HTTPExceptions
- Models don't know about the API — they define tables, not responses
- Schemas don't know about the database — they define shapes, not queries

### DRY Patterns

**1. Dependency Injection (not repeated auth/DB code)**
```python
# Instead of every endpoint doing this:
session = await get_session()
user = await authenticate(request)

# DI does it once:
async def endpoint(db = Depends(get_db), user = Depends(get_current_user)):
```

**2. Single API file (frontend)**

All API calls live in `services/api.ts`. Components never call `fetch()` or `axios` directly. If the backend URL changes, you fix it in one place.

**3. React Query cache invalidation**

Mutations (`useCreateProject`, `useDeleteProject`) automatically invalidate the `["projects"]` query key. Every component showing the project list updates automatically — no manual refetch calls scattered around.

**4. Shared ownership check pattern (backend)**

Both `projects.py` and `sync.py` use `_get_user_project()` — a helper that queries a project AND verifies it belongs to the current user. Chat router has `_verify_session_access()` for the same pattern on sessions.

**5. Tool definitions separate from execution**

`agent_tools.py` is pure data (JSON-like tool definitions). `tool_executor.py` has the logic. You can add a new tool by: (1) adding its definition to `agent_tools.py`, (2) adding its handler to `tool_executor.py`. No other files need to change.

**6. Citation accumulation pattern**

Every tool handler returns `(result_text, citations_list)`. The agent loop accumulates citations across iterations. The chat router serializes them once at the end. No citation logic in multiple places.

### Frontend Separation

```
types/           → "what shapes does data have?"     (TypeScript interfaces)
services/api.ts  → "how do we talk to the backend?"  (HTTP layer)
hooks/           → "how do we manage state?"          (business logic)
components/      → "what does the user see?"          (UI only)
```

**Components don't fetch data** — they receive it from hooks. **Hooks don't render UI** — they return data for components. **api.ts doesn't manage state** — it makes HTTP calls and returns promises.

---

## 12. How Everything Connects (End-to-End)

Here's the full picture — every layer, from browser to database and back:

```
┌──────────────── FRONTEND ─────────────────┐     ┌──────────────── BACKEND ────────────────────┐
│                                            │     │                                              │
│  Component (e.g., UnifiedChatContainer)    │     │   main.py                                    │
│       │                                    │     │     ├── AuthGuardMiddleware                   │
│       ▼                                    │     │     │   └── security.py (validate_session)    │
│  Hook (e.g., useUnifiedChat)               │     │     ├── CORSMiddleware                       │
│       │                                    │     │     └── Router mount                          │
│       ▼                                    │     │           │                                   │
│  services/api.ts                           │     │           ▼                                   │
│       │                                    │     │   routers/chat.py                             │
│       │  POST /api/chat/stream             │     │     ├── Depends(get_db)        ← deps.py     │
│       │  Cookie: session_id=xxx            │ ──► │     ├── Depends(get_current_user) ← deps.py  │
│       │  X-Requested-With: XMLHttpRequest  │     │     ├── Validates input        ← schemas/    │
│       │                                    │     │     ├── Loads chat history      ← models/     │
│       │                                    │     │     ├── Refreshes token         ← security.py │
│       │                                    │     │     └── Calls FolderAgent                     │
│       │                                    │     │           │                                   │
│       │                                    │     │           ▼                                   │
│       │                                    │     │   services/agent.py (ReAct loop)              │
│       │                                    │     │     ├── Calls LLMClient        ← llm.py      │
│       │                                    │     │     │     └── OpenAI API                      │
│       │                                    │     │     ├── Calls execute_tool      ← tool_exec.  │
│       │                                    │     │     │     ├── Injects credentials              │
│       │                                    │     │     │     ├── google_drive.py  ← Drive API    │
│       │                                    │     │     │     └── file_parsers.py  ← PDF/DOCX     │
│       │                                    │     │     └── Accumulates citations                  │
│       │                                    │     │           │                                   │
│       │  ◄── SSE: delta, citations, done   │ ◄── │     Yields streaming events                   │
│       │                                    │     │     Persists message + citations ← models/     │
│       ▼                                    │     │                                              │
│  Hook updates state                        │     │   PostgreSQL                                  │
│       │                                    │     │     users ─→ projects ─→ sessions ─→ messages │
│       ▼                                    │     │                                              │
│  Component re-renders                      │     │                                              │
│  (MessageBubble with citations)            │     │                                              │
│                                            │     │                                              │
└────────────────────────────────────────────┘     └──────────────────────────────────────────────┘
```

**Every request follows this path:**
1. **Component** triggers action (user types, clicks)
2. **Hook** calls the right function (sendMessage, createProject)
3. **api.ts** makes the HTTP request with cookies
4. **Middleware** validates auth + CSRF
5. **Router** parses request, injects dependencies, delegates to services
6. **Services** do the actual work (agent reasoning, Drive API, file parsing)
7. **Response** flows back: services → router → HTTP → api.ts → hook → component → screen

The beauty is that each layer only knows about its immediate neighbors. Components don't know about the database. The agent doesn't know about HTTP. The LLM doesn't know about credentials. This separation makes the system secure, testable, and easy to modify.
