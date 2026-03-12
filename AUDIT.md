# Production Audit Report

**Date**: 2026-03-12
**Scope**: Full codebase scan — backend, frontend, worker, models, schemas, migrations
**Exclusions**: Issues already documented in CODEBASE.md "Known Limitations" (in-memory sessions, sequential worker processing, Temporal payload tokens, no CI/CD, unused google_auth.py, unused Sidebar.tsx)

---

## 1. Error Handling Gaps

| # | File | Line | Issue | Severity | Fix |
|---|------|------|-------|----------|-----|
| 1 | `backend/app/services/agent.py` | 192 | Bare `except Exception` catches all LLM errors indiscriminately — no differentiation between rate limits, auth failures, or transient network errors | Critical | Catch specific exceptions (`RateLimitError`, `APIError`, `httpx.ConnectError`) with different recovery strategies |
| 2 | `backend/app/services/tool_executor.py` | 88-90 | Bare `except Exception` in tool dispatch swallows root cause; returns generic error string to agent | Critical | Log full traceback with tool name/args; catch specific exception types |
| 3 | `backend/app/routers/chat.py` | 278-287 | Generic `except Exception` handler returns 500 for all agent errors — Drive 401/403/404 not differentiated | Critical | Map Drive API status codes to specific HTTP responses (401->re-auth, 403->permission denied, 404->file deleted) |
| 4 | `backend/app/routers/chat.py` | 491-508 | Same catch-all pattern in streaming endpoint | Critical | Same fix as #3 |
| 5 | `backend/app/routers/sync.py` | 114-123 | All sync errors collapsed into generic "FAILED" state — 403 Forbidden indistinguishable from timeout | Critical | Set distinct `sync_error` messages per exception type |
| 6 | `worker/activities/extract_content.py` | 120 | Bare `except Exception:` returns placeholder text — silently hides extraction bugs | Critical | Catch `(OSError, ValueError)` specifically; log traceback; re-raise unrecoverable errors |
| 7 | `backend/app/routers/projects.py` | 246-249 | Azure Search cleanup failure silently swallowed — orphans search index data | Critical | Log error and either fail deletion or queue async retry |
| 8 | `backend/app/services/google_drive.py` | 91-93 | Drive API errors not differentiated — 401 (expired token), 403 (permission), 5xx (outage) all treated identically | Medium | Check `response.status_code` and branch: 401->refresh, 403->permission error, 5xx->retry |
| 9 | `backend/app/services/azure_search.py` | 153-156 | Index creation/retrieval bare `except Exception` — permission errors masked as "index not found" | Medium | Differentiate `IndexNotFoundError` from auth/connection failures |
| 10 | `backend/app/services/embeddings.py` | 61-79 | Rate limit errors (429) not differentiated from auth errors (401) — both get same retry logic | Medium | Fail fast on `AuthenticationError`; exponential backoff only on `RateLimitError` |
| 11 | `backend/app/routers/auth.py` | 121 | `token_response.json()` called without catching `JSONDecodeError` | Medium | Wrap in try-except; return 502 with "Google auth service unavailable" |
| 12 | `frontend/src/services/api.ts` | 216-218 | `catch { }` silently swallows SSE JSON parse errors — zero visibility into malformed events | Critical | Log parse errors: `console.error('SSE parse error:', eventData, err)` |
| 13 | `frontend/src/services/api.ts` | 175-228 | Stream reader never explicitly closed on error — resource leak | Critical | Add `reader.cancel()` in finally block |
| 14 | `frontend/src/hooks/useUnifiedChat.ts` | 165-182 | All chat errors collapsed into generic message — no distinction between network/timeout/permissions | Medium | Check error type and provide specific user-facing messages |
| 15 | `frontend/src/components/knowledge/ProjectCard.tsx` | 75 | `deleteProject.mutate()` has no `onError` callback — silent failure | Medium | Add `onError` showing inline error or toast |

---

## 2. Input Validation & Security

| # | File | Line | Issue | Severity | Fix |
|---|------|------|-------|----------|-----|
| 16 | `backend/app/schemas/chat.py` | 53 | `message: str` has NO max length — unbounded input enables DoS via LLM/embedding cost amplification | Critical | Add `Field(..., max_length=10000, min_length=1)` |
| 17 | `backend/app/services/tool_executor.py` | 148-197 | **Prompt injection**: File names and content from Drive/Azure Search interpolated directly into agent output without sanitization — malicious filenames like `IGNORE PREVIOUS INSTRUCTIONS` or content with `<SYSTEM>` tags can manipulate agent behavior | Critical | Sanitize/escape all user-controlled fields before composing tool output strings |
| 18 | `backend/app/services/google_drive.py` | 176 | Drive API query built with basic string escaping (`replace("'", "\\'")`) — Unicode bypass possible | Medium | Whitelist allowed characters; use parameterized queries if available |
| 19 | `backend/app/services/google_drive.py` | 192-196 | MIME type filters from tool args interpolated directly into Drive query without validation | Medium | Whitelist allowed file type prefixes; reject unknown values |
| 20 | `backend/app/schemas/project.py` | 11,16,22 | `gdrive_folder_url` has no max_length — DB column is String(500) but schema accepts arbitrary length | Medium | Add `Field(..., max_length=500)` |
| 21 | `backend/app/schemas/project.py` | 10 | Project `name` field has no length constraint — DB column is 255 but schema is unbounded | Medium | Add `Field(..., max_length=255)` |
| 22 | `backend/app/schemas/user.py` | 9 | `email: str` instead of `EmailStr` — no email validation at API layer | Medium | Use `EmailStr` type |
| 23 | `frontend/src/components/chat/MessageBubble.tsx` | 171-177 | `ReactMarkdown` with `rehypeRaw` enables raw HTML rendering — potential XSS if backend passes unsanitized content | Medium | Disable `rehypeRaw` or add DOMPurify sanitization |
| 24 | `worker/activities/crawl_folder.py` | 79 | File names from Drive concatenated into hierarchy paths without sanitization — names like `../../etc/passwd` flow through unsanitized | Medium | Sanitize with `pathlib.Path(name).name` to strip directory traversal |
| 25 | `backend/app/main.py` | 93-96 | CORS `allow_headers=["*"]` and `allow_methods=["*"]` with credentials — overly permissive | Medium | Enumerate: `allow_headers=["Content-Type"]`, `allow_methods=["GET","POST","DELETE","OPTIONS"]` |

---

## 3. Resource Limits & Abuse Prevention

| # | File | Line | Issue | Severity | Fix |
|---|------|------|-------|----------|-----|
| 26 | `backend/app/routers/chat.py` | 114, 304 | **No rate limiting** on chat endpoints — each request triggers LLM calls ($$$) | Critical | Add `slowapi` rate limiter: 10 req/min per user on POST endpoints |
| 27 | `backend/app/services/tool_executor.py` | 325-327 | **No file size limit** on Drive downloads — 1GB file loaded entirely into memory | Critical | Check file size metadata before download; reject files > 100MB |
| 28 | `backend/app/services/tool_executor.py` | 448-483 | **Unbounded spreadsheet loading** — `openpyxl.load_workbook` loads entire XLSX into memory regardless of size | Critical | Pre-check file size; cap at 50MB; stream-parse for large files |
| 29 | `worker/workflows/sync_folder.py` | 115-194 | **No limits** on file count, file size, or folder depth during sync — 100k-file folder causes OOM and Temporal history explosion | Critical | Add max file count (10k), max file size (100MB), max recursion depth (10) |
| 30 | `backend/app/services/google_drive.py` | 277-282 | `delete_by_project` only deletes first 10,000 chunks — projects with more silently leave orphaned data | Critical | Implement pagination loop to delete all chunks |
| 31 | `backend/app/routers/chat.py` | 239 | Message history loaded unbounded — sessions with 10k+ messages all loaded into memory | Medium | Add `LIMIT` clause or paginate history sent to agent |
| 32 | `backend/app/routers/projects.py` | 119-130 | GET `/api/projects` returns all projects with no pagination | Medium | Add `limit`/`offset` query params with defaults |
| 33 | `backend/app/services/tool_executor.py` | 621-630 | `search_spreadsheet` iterates all rows (up to 1M) until 50 matches found | Medium | Add hard iteration cap (10k rows) with warning |

---

## 4. Race Conditions & Concurrency

| # | File | Line | Issue | Severity | Fix |
|---|------|------|-------|----------|-----|
| 34 | `backend/app/routers/chat.py` | 185-276 | Two concurrent POST `/api/chat` for same session can interleave — duplicate/misordered messages | Critical | Add `SELECT ... FOR UPDATE` row lock on ChatSession before writing messages |
| 35 | `backend/app/routers/sync.py` | 80-125 | Sync status check-then-update is not atomic — two rapid triggers race past the `SYNCING` guard | Critical | Use atomic UPDATE: `WHERE id=? AND sync_status != 'SYNCING'` |
| 36 | `backend/app/routers/projects.py` | 158-199 | Duplicate project check then insert is not atomic — concurrent requests create duplicate projects for same folder | Critical | Add unique constraint on `(user_id, gdrive_folder_id)` in DB |
| 37 | `frontend/src/hooks/useUnifiedChat.ts` | 66-69 | No debounce on `sendMessage` — rapid clicks send duplicate messages before `isLoading` guard activates | Critical | Add mutex guard or disable button synchronously before async call |
| 38 | `backend/app/routers/chat.py` | 226-228 | Token refresh in chat flow not synchronized — concurrent chats from same user can trigger parallel refreshes | Medium | Add user-level lock around token refresh |
| 39 | `frontend/src/hooks/useUnifiedChat.ts` | 91-94 | Switching projects doesn't clear `sessionId` — messages can go to wrong project's session | Medium | Call `startNewChat()` in `useEffect` when `projectId`/`folderId` changes |

---

## 5. Memory & Performance

| # | File | Line | Issue | Severity | Fix |
|---|------|------|-------|----------|-----|
| 40 | `worker/activities/extract_content.py` | 199-277 | Downloaded files (`io.BytesIO`) never explicitly closed — large PDFs/DOCXs held in memory until GC | Critical | Use context managers for all `BytesIO`/reader operations |
| 41 | `backend/app/services/google_drive.py` | 38-40 | N+1 pattern: `list_folder` recursively fetches each subfolder individually — deep hierarchies make 100+ sequential API calls | Medium | Batch subfolder fetches or use Drive API's `corpora=allDrives` with `q` filter |
| 42 | `backend/app/services/google_drive.py` | 164-170 | `_folder_tree_cache` per-instance with no TTL or size limit — grows unbounded | Medium | Add LRU eviction (max 100 entries) or TTL-based cache |
| 43 | `backend/app/services/agent.py` | 136 | `tool_cache: dict` has no size limit — grows unbounded across questions | Low | Add LRU cache with max 50 entries |
| 44 | `frontend/src/components/chat/CitationTooltip.tsx` | 31-33 | `mousedown` event listener cleanup only runs when `isVisible` changes — can leak if component unmounts while visible | Medium | Move cleanup `return` statement outside the `if (isVisible)` block |

---

## 6. Hardcoded Values & Configuration

| # | File | Line | Issue | Severity | Fix |
|---|------|------|-------|----------|-----|
| 45 | `backend/app/services/agent.py` | 123 | Model name `"gpt-5.2"` hardcoded as default | Medium | Move to `config.py` as `DEFAULT_LLM_MODEL` env var |
| 46 | `worker/activities/generate_questions.py` | 101 | Model `"gpt-4o-mini"` hardcoded | Medium | Use env var `QUESTION_GEN_MODEL` |
| 47 | `worker/activities/generate_embeddings.py` | 14 | `EMBEDDING_MODEL = "text-embedding-ada-002"` hardcoded | Medium | Use env var `EMBEDDING_MODEL` |
| 48 | `backend/app/utils/security.py` | 18 | `SESSION_MAX_AGE = 86400` hardcoded | Low | Move to `config.py` as `SESSION_TTL_SECONDS` |
| 49 | `backend/app/services/google_drive.py` | 39,120,141 | Three different httpx timeouts (30s, 60s, 60s) hardcoded and inconsistent | Medium | Centralize in config: `DRIVE_API_TIMEOUT`, `DRIVE_DOWNLOAD_TIMEOUT` |
| 50 | `worker/activities/generate_questions.py` | 38-44 | Commented-out Anthropic support left as TODO dead code | Low | Remove or move to GitHub issue |
| 51 | `backend/app/services/google_drive.py` | 216, 291 | `httpx.AsyncClient()` created without timeout — can hang indefinitely | Medium | Add explicit `timeout=30.0` |
| 52 | Worker activities (multiple) | — | Batch sizes (20, 5, 100, 512) all hardcoded across 4 files | Low | Extract to env vars for production tuning |

---

## 7. Type Safety & Code Quality

| # | File | Line | Issue | Severity | Fix |
|---|------|------|-------|----------|-----|
| 53 | `backend/app/schemas/chat.py` | 41 | `role: str` should be `MessageRole` enum — type mismatch with DB model | Medium | Change to `role: MessageRole` |
| 54 | `backend/app/schemas/chat.py` | 17 | `agent_type: str = "RAG"` should be `AgentType` enum | Medium | Change to `agent_type: AgentType = AgentType.RAG` |
| 55 | `backend/app/services/llm.py` | 70-71 | `self._anthropic_client: Any` and `self._openai_client: Any` — too broad | Low | Type as `Optional[AsyncAnthropic]` / `Optional[AsyncOpenAI]` |
| 56 | `backend/app/services/tool_executor.py` | 272 | `# type: ignore[assignment]` masking float/int mismatch | Low | Use `size_bytes = size_bytes / 1024` (explicit float) |
| 57 | `backend/app/services/tool_executor.py` | 167,254,547 | Tool handler args extracted from dict without type validation — LLM passing wrong type causes silent failure | Medium | Add type assertions or Pydantic validation for tool args |
| 58 | `frontend/src/hooks/useAuth.ts` | 42 | `window.location.href = "/"` for logout navigation — violates CLAUDE.md rule against `window.location.href` | Medium | Use `useNavigate()` from react-router-dom |
| 59 | Worker activities (multiple) | — | Inconsistent logger usage — some use `activity.logger`, others use module-level `logger` | Low | Standardize on `activity.logger` in all Temporal activities |

---

## 8. Frontend Robustness

| # | File | Line | Issue | Severity | Fix |
|---|------|------|-------|----------|-----|
| 60 | `frontend/src/components/chat/UnifiedChatContainer.tsx` | 281 | No Error Boundary wrapping MessageList — malformed citation/message crashes entire chat | Medium | Wrap MessageList in an `<ErrorBoundary>` with fallback UI |
| 61 | `frontend/src/components/chat/UnifiedChatContainer.tsx` | 30 | No error handling for `useProjects()` query failure — shows "No folders connected" instead of error state | Medium | Check `error` state and show retry UI |
| 62 | `frontend/src/components/chat/UnifiedChatContainer.tsx` | — | No listener for `auth:session-expired` event — if token expires mid-stream, user sees infinite "thinking" spinner | Medium | Listen for session-expired and call `startNewChat()` with error message |
| 63 | `frontend/src/components/chat/ChatInput.tsx` | 49-58 | Textarea and send button missing `aria-label` — screen readers can't announce purpose | Medium | Add `aria-label="Message input"` and `aria-label="Send message"` |
| 64 | `frontend/src/components/chat/ProjectSelector.tsx` | 28-56 | `<select>` not linked to label via `htmlFor`/`id` — accessibility gap | Medium | Add `id="project-select"` to select and `htmlFor="project-select"` to label |
| 65 | `frontend/src/components/knowledge/AddFolderModal.tsx` | 61 | Focus not returned to trigger button on modal close — keyboard users get lost | Low | Store trigger ref and call `triggerRef.current?.focus()` in `onClose` |
| 66 | `frontend/src/components/knowledge/AddFolderModal.tsx` | 204-209 | Input not disabled during validation — user can modify URL mid-validation causing race | Medium | Add `disabled={state === "validating"}` to input |

---

## 9. Data Integrity

| # | File | Line | Issue | Severity | Fix |
|---|------|------|-------|----------|-----|
| 67 | `backend/app/routers/chat.py` | 278-287 | Exception handler doesn't rollback transaction — partial writes (user message committed, assistant message lost) | Critical | Add `await db.rollback()` in except block before raising |
| 68 | `backend/app/models/chat.py` | 28-33 | No CHECK constraint preventing `project_id IS NULL AND user_id IS NULL` — allows orphaned sessions | Medium | Add DB constraint: `(project_id IS NOT NULL) OR (user_id IS NOT NULL)` |
| 69 | `backend/app/models/chat.py` | 49 | User relationship missing `back_populates` — user deletion may not cascade to chat sessions | Medium | Add `back_populates="chat_sessions"` and corresponding relationship on User model |
| 70 | `backend/alembic/versions/7333ef8eb49b_initial_tables.py` | — | Missing indexes on `messages.created_at`, `chat_sessions.created_at`, `projects.sync_status` | Medium | Add indexes in new migration |
| 71 | `backend/app/dependencies.py` | 25-38 | Global `_engine` never disposed on shutdown — connection pool may leak | Medium | Add app lifespan handler: `await _engine.dispose()` |

---

## Summary

| Severity | Count |
|----------|-------|
| **Critical** | 20 |
| **Medium** | 40 |
| **Low** | 11 |
| **Total** | **71** |

### Top 5 Priorities

1. **Rate limiting on chat endpoints** (#26) — unbounded LLM cost exposure
2. **Input validation on message length** (#16) — DoS vector
3. **Prompt injection via filenames/content** (#17) — agent manipulation
4. **Race condition on concurrent chat writes** (#34) — message corruption
5. **File size limits on downloads** (#27, #28) — OOM crashes
