# Talk to a Folder

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Minimal code impact.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Only touch what's necessary. Don't introduce bugs.
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: step back — "knowing everything I know now, implement the elegant solution."
- Skip the above for simple, obvious fixes — don't over-engineer.
- Challenge your own work before presenting it.

## Architecture

- **Codebase Map**: See `CODEBASE.md` for the full file tree, patterns, and env vars — read it before non-trivial work. Update it when you add/remove/move files or change architecture.
- **Product**: Google Drive document chatbot — users connect a Drive folder and chat with an AI agent that searches and reasons over their documents in real time via the Google Drive API.
- **Backend**: FastAPI + Pydantic v2 — `backend/app/`
- **Frontend**: React 18 + TypeScript + Vite + Tailwind — `frontend/src/`
- **Auth**: Google OAuth → encrypted tokens → HTTPOnly session cookie. Backend dependency `get_current_user` in `dependencies.py`. Frontend Zustand store `useAuth` + Axios 401 interceptor.
- **LLM**: Claude (preferred) or GPT-4o fallback via `backend/app/services/llm.py`. FolderAgent (`services/agent.py`) runs a ReAct loop with 12 tools for document search, reading, and spreadsheet ops.
- **Data**: PostgreSQL via SQLAlchemy async + asyncpg. Alembic for migrations. Models in `backend/app/models/`. 4 tables: users, projects, chat_sessions, messages.
- **Deployment**: Single Docker image — API (`Dockerfile`). Azure App Service + Postgres.

## Project Layout

```
backend/app/
  config.py              # Pydantic Settings (.env)
  main.py                # FastAPI app, CORS, router registration
  dependencies.py        # get_db, get_current_user, get_settings
  models/                # SQLAlchemy ORM (user, project, chat, message)
  schemas/               # Pydantic request/response models
  routers/               # auth, projects, chat, sync
  services/              # agent, agent_tools, tool_executor, llm,
                         #   google_drive, google_auth
  utils/                 # security (encryption, sessions), file_parsers

frontend/src/
  App.tsx                # Routing (Knowledge / Chat tabs)
  components/            # auth/, chat/, knowledge/, layout/
  hooks/                 # useAuth (Zustand), useProjects (React Query), useChat
  services/api.ts        # Axios client, all API calls
  types/index.ts         # User, Project, ChatSession, Message, Citation
```

## Common Commands

```bash
# Dev servers
.\run.ps1                                        # start backend + frontend

# Backend
cd backend && python -m pytest --tb=short -q     # run backend tests
cd backend && alembic revision --autogenerate -m "description"   # generate migration
cd backend && alembic upgrade head                                # apply migrations

# Frontend
cd frontend && npm test                           # run frontend tests
cd frontend && npx tsc --noEmit                   # type check
```

## Don't

- Don't add new env vars without updating `.env.example`, `Dockerfile`, and the env var table in `CODEBASE.md`.
- Don't use `window.location.href` for navigation in React — use router navigation or dispatch events.
- Don't paste large code blocks into CLAUDE.md — reference file paths instead.

## Testing

```bash
cd backend  && python -m pytest --tb=short -q    # backend only
cd frontend && npm test                          # frontend only
```

- **Backend**: Tests in `backend/tests/` mirroring `backend/app/` structure. Use `tmp_path` for file I/O, `unittest.mock.patch` for external calls.
- **Frontend**: Tests in `__tests__/` co-located next to source. Always import `{ describe, it, expect }` from `'vitest'`. Use `@/` alias.
- **Rule**: Every feature change must include corresponding test changes. A Stop hook runs after every response — it type-checks, runs both suites, and flags untested code.
- See `.claude/skills/testing/SKILL.md` for patterns, mock helpers, what needs tests, and anti-patterns.

## Compaction

When compacting, always preserve:
- The full list of files modified in this session
- Current task status and next steps
- Any failing test output or error messages
