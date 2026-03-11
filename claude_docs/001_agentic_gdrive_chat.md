# Talk-to-a-Folder: Product Requirements Document

## Executive Summary

**Talk-to-a-Folder** is a production-grade web application that enables users to have intelligent conversations with the contents of any Google Drive folder. Users authenticate with their Google account, paste a folder link, and an AI agent answers questions about the folder's contents — with citations linking back to source files.

This document outlines the full technical architecture, implementation details, and production considerations.

---

## Table of Contents

1. [Business Context](#business-context)
2. [User Experience](#user-experience)
3. [Technical Architecture](#technical-architecture)
4. [Project Structure](#project-structure)
5. [Data Models](#data-models)
6. [Authentication & Security](#authentication--security)
7. [Ingestion Pipeline](#ingestion-pipeline)
8. [Agent System](#agent-system)
9. [Deployment](#deployment)
10. [Edge Cases & Error Handling](#edge-cases--error-handling)
11. [Future Enhancements](#future-enhancements)

---

## Business Context

### Problem Statement

Knowledge workers store critical documents across Google Drive folders — reports, spreadsheets, presentations, images, and more. Finding specific information requires manually opening files, searching, and synthesizing across documents. This is:

- **Time-consuming**: Searching through nested folders and multiple file types
- **Error-prone**: Easy to miss relevant information in large document sets
- **Not scalable**: As document volumes grow, manual search becomes impractical

### Solution

A conversational AI interface that:

1. Ingests and indexes all files within a Google Drive folder (recursively)
2. Enables natural language questions across the entire corpus
3. Returns accurate answers with citations to source documents
4. Handles diverse file types: documents, spreadsheets, PDFs, images, text files

### Target Users

- Knowledge workers managing document repositories
- Teams sharing project folders
- Researchers with large document collections
- Anyone who needs to quickly extract information from Drive folders

---

## User Experience

### Core Workflows

#### 1. Onboarding

```
User lands on app → Clicks "Sign in with Google" → OAuth flow → Redirected to app (authenticated)
```

#### 2. Adding a Folder (Knowledge Tab)

```
User navigates to "Knowledge" tab → Clicks "Add Folder" → Pastes Google Drive folder URL
→ Names the project → Clicks "Sync" → Background job processes folder → Status updates in UI
```

#### 3. Chatting with a Folder (Chat Tab)

```
User navigates to "Chat" tab → Selects a synced project from dropdown
→ Types question → Agent searches, retrieves, reasons → Response with inline citations
```

#### 4. Re-syncing

```
User navigates to "Knowledge" tab → Selects project → Clicks "Re-sync" → Background job runs
```

### UI Components

| Component | Description |
|-----------|-------------|
| **Auth Header** | Google profile picture, name, sign out button |
| **Knowledge Tab** | List of folder projects with sync status, add/remove/re-sync controls |
| **Chat Tab** | Project selector dropdown, message history, input field |
| **Message Bubbles** | User messages (right-aligned), Assistant messages (left-aligned) with citation superscripts |
| **Citation Tooltip** | On hover: shows source file name, snippet. On click: opens Google Drive file in new tab |
| **Sync Progress** | Progress indicator showing files processed, current file, errors encountered |

---

## Technical Architecture

### High-Level Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Azure App Service                                │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                      Docker Container                              │  │
│  │                                                                    │  │
│  │   ┌─────────────────┐         ┌─────────────────────────────┐     │  │
│  │   │   React (TS)    │         │       FastAPI (Python)      │     │  │
│  │   │   Static Build  │◄───────►│                             │     │  │
│  │   │                 │         │  • Auth routes (/auth/*)    │     │  │
│  │   │  • Knowledge UI │         │  • Project CRUD (/projects) │     │  │
│  │   │  • Chat UI      │         │  • Chat endpoint (/chat)    │     │  │
│  │   │  • Auth flows   │         │  • Sync trigger (/sync)     │     │  │
│  │   └─────────────────┘         └─────────────────────────────┘     │  │
│  │                                                                    │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
          │              │                │               │
          ▼              ▼                ▼               ▼
   ┌──────────┐   ┌─────────────┐  ┌────────────┐  ┌─────────────┐
   │ Supabase │   │   Google    │  │  Azure AI  │  │  Temporal   │
   │ Postgres │   │    APIs     │  │   Search   │  │   Cloud     │
   │          │   │             │  │            │  │             │
   │ • Users  │   │ • OAuth     │  │ • Vectors  │  │ • Workflows │
   │ • Projects│  │ • Drive API │  │ • Keywords │  │ • Workers   │
   │ • Chats  │   │ • Export    │  │ • Metadata │  │             │
   └──────────┘   └─────────────┘  └────────────┘  └─────────────┘
                                                          │
                                          ┌───────────────┼───────────────┐
                                          ▼               ▼               ▼
                                    ┌──────────┐   ┌──────────┐   ┌──────────┐
                                    │  OpenAI  │   │  Google  │   │  Azure   │
                                    │ (Embed)  │   │  Drive   │   │   Blob   │
                                    │  Ada-002 │   │   API    │   │ (cache)  │
                                    └──────────┘   └──────────┘   └──────────┘
```

### Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Frontend** | React 18 + TypeScript | Single-page application |
| **Styling** | Tailwind CSS | Utility-first styling |
| **Backend** | FastAPI (Python 3.12) | REST API, serves static frontend |
| **Validation** | Pydantic v2 | Request/response schemas, settings management |
| **ORM** | SQLAlchemy 2.0 | Database models and queries |
| **Migrations** | Alembic | Schema versioning and migrations |
| **Database** | PostgreSQL (Supabase) | Persistent storage for users, projects, chats |
| **Search Index** | Azure AI Search | Hybrid vector + keyword search |
| **Embeddings** | OpenAI Ada-002 | Text embeddings for semantic search |
| **LLM** | Claude (Anthropic) or GPT-4 | Agent reasoning and response generation |
| **Job Queue** | Temporal Cloud | Durable workflow execution for sync jobs |
| **Blob Storage** | Azure Blob Storage | Optional: cached file contents |
| **Auth** | Google OAuth 2.0 | User authentication + Drive access |
| **Deployment** | Docker → Azure Container Registry → Azure App Service | Containerized deployment |

---

## Project Structure

```
talk-to-folder/
├── frontend/
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── components/
│   │   │   ├── auth/
│   │   │   │   └── GoogleLoginButton.tsx
│   │   │   ├── knowledge/
│   │   │   │   ├── ProjectList.tsx
│   │   │   │   ├── ProjectCard.tsx
│   │   │   │   ├── AddFolderModal.tsx
│   │   │   │   └── SyncProgress.tsx
│   │   │   ├── chat/
│   │   │   │   ├── ChatContainer.tsx
│   │   │   │   ├── MessageList.tsx
│   │   │   │   ├── MessageBubble.tsx
│   │   │   │   ├── CitationTooltip.tsx
│   │   │   │   ├── ChatInput.tsx
│   │   │   │   └── ProjectSelector.tsx
│   │   │   └── layout/
│   │   │       ├── Header.tsx
│   │   │       ├── Sidebar.tsx
│   │   │       └── TabNav.tsx
│   │   ├── hooks/
│   │   │   ├── useAuth.ts
│   │   │   ├── useProjects.ts
│   │   │   └── useChat.ts
│   │   ├── services/
│   │   │   └── api.ts
│   │   ├── types/
│   │   │   └── index.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── tailwind.config.js
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app, mounts static files
│   │   ├── config.py                  # Pydantic Settings
│   │   ├── dependencies.py            # Dependency injection
│   │   │
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                # /auth/* routes
│   │   │   ├── projects.py            # /projects/* routes
│   │   │   ├── chat.py                # /chat/* routes
│   │   │   └── sync.py                # /sync/* routes
│   │   │
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── project.py
│   │   │   ├── chat.py
│   │   │   └── message.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── project.py
│   │   │   ├── chat.py
│   │   │   └── message.py
│   │   │
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── google_auth.py         # OAuth logic
│   │   │   ├── google_drive.py        # Drive API wrapper
│   │   │   ├── azure_search.py        # Azure AI Search client
│   │   │   ├── embeddings.py          # OpenAI embeddings
│   │   │   ├── llm.py                 # LLM client (Claude/GPT)
│   │   │   ├── agent.py               # FolderAgent class + loop
│   │   │   ├── agent_tools.py         # Tool definitions (JSON schemas)
│   │   │   └── tool_executor.py       # Tool implementations (deterministic code)
│   │   │
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── security.py            # Token encryption, session handling
│   │       └── file_parsers.py        # Extraction utilities
│   │
│   ├── alembic/
│   │   ├── versions/
│   │   ├── env.py
│   │   └── script.py.mako
│   ├── alembic.ini
│   ├── requirements.txt
│   └── pytest.ini
│
├── worker/
│   ├── __init__.py
│   ├── main.py                        # Temporal worker entry point
│   ├── workflows/
│   │   ├── __init__.py
│   │   └── sync_folder.py             # Sync workflow definition
│   ├── activities/
│   │   ├── __init__.py
│   │   ├── crawl_folder.py            # List all files recursively
│   │   ├── extract_content.py         # File-type-specific extraction
│   │   ├── chunk_content.py           # Chunking logic
│   │   ├── generate_embeddings.py     # Call OpenAI Ada
│   │   ├── generate_questions.py      # LLM-generated questions
│   │   └── index_chunks.py           # Upsert to Azure AI Search
│   └── requirements.txt
│
├── docker-compose.yml                  # Local development
├── docker-compose.prod.yml             # Production (if needed)
├── Dockerfile                          # Multi-stage build
├── Dockerfile.worker                   # Worker container
├── .env.example
├── .gitignore
└── README.md
```

---

## Data Models

### PostgreSQL Schema (Alembic-managed)

#### Users Table

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    picture_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Encrypted tokens
    google_access_token: Mapped[Optional[str]] = mapped_column(Text)
    google_refresh_token: Mapped[Optional[str]] = mapped_column(Text)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    projects: Mapped[List["Project"]] = relationship(back_populates="user")
```

#### Projects Table

```python
class ProjectStatus(enum.Enum):
    PENDING = "pending"
    SYNCING = "syncing"
    COMPLETED = "completed"
    FAILED = "failed"

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    name: Mapped[str] = mapped_column(String(255))
    gdrive_folder_id: Mapped[str] = mapped_column(String(255))
    gdrive_folder_url: Mapped[str] = mapped_column(String(500))

    sync_status: Mapped[ProjectStatus] = mapped_column(default=ProjectStatus.PENDING)
    files_total: Mapped[int] = mapped_column(default=0)
    files_processed: Mapped[int] = mapped_column(default=0)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sync_error: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="projects")
    chat_sessions: Mapped[List["ChatSession"]] = relationship(back_populates="project")
```

#### Chat Sessions Table

```python
class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))

    title: Mapped[Optional[str]] = mapped_column(String(255))  # Auto-generated from first message

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="chat_sessions")
    messages: Mapped[List["Message"]] = relationship(back_populates="chat_session", order_by="Message.created_at")
```

#### Messages Table

```python
class MessageRole(enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chat_session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"))

    role: Mapped[MessageRole]
    content: Mapped[str] = mapped_column(Text)

    # Citations stored as JSON array
    # [{"chunk_id": "...", "file_name": "...", "source_url": "...", "snippet": "..."}]
    citations: Mapped[Optional[dict]] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    chat_session: Mapped["ChatSession"] = relationship(back_populates="messages")
```

### Azure AI Search Index Schema

```json
{
  "name": "talk-to-folder-chunks",
  "fields": [
    {"name": "chunk_id", "type": "Edm.String", "key": true},
    {"name": "project_id", "type": "Edm.String", "filterable": true},
    {"name": "file_id", "type": "Edm.String", "filterable": true},
    {"name": "file_name", "type": "Edm.String", "searchable": true, "filterable": true},
    {"name": "file_type", "type": "Edm.String", "filterable": true, "facetable": true},
    {"name": "hierarchy", "type": "Edm.String", "searchable": true},
    {"name": "source_url", "type": "Edm.String"},

    {"name": "content", "type": "Edm.String", "searchable": true, "analyzer": "en.microsoft"},
    {"name": "content_vector", "type": "Collection(Edm.Single)", "dimensions": 1536, "vectorSearchProfile": "default-profile"},

    {"name": "questions", "type": "Collection(Edm.String)", "searchable": true},
    {"name": "questions_vector", "type": "Collection(Edm.Single)", "dimensions": 1536, "vectorSearchProfile": "default-profile"},

    {"name": "keywords", "type": "Collection(Edm.String)", "searchable": true, "filterable": true},

    {"name": "page_number", "type": "Edm.Int32", "filterable": true},
    {"name": "sheet_name", "type": "Edm.String", "filterable": true},
    {"name": "section_heading", "type": "Edm.String", "searchable": true},

    {"name": "created_at", "type": "Edm.DateTimeOffset", "filterable": true, "sortable": true}
  ],
  "vectorSearch": {
    "profiles": [
      {"name": "default-profile", "algorithm": "default-algorithm"}
    ],
    "algorithms": [
      {"name": "default-algorithm", "kind": "hnsw"}
    ]
  }
}
```

---

## Authentication & Security

### OAuth Flow

```
1. User clicks "Sign in with Google"
2. Frontend redirects to: /auth/google/login
3. Backend generates OAuth URL with scopes:
   - openid
   - email
   - profile
   - https://www.googleapis.com/auth/drive.readonly
4. User authorizes in Google consent screen
5. Google redirects to: /auth/google/callback?code=...
6. Backend exchanges code for tokens (access_token, refresh_token)
7. Backend creates/updates user in DB (tokens encrypted at rest)
8. Backend creates session, sets HttpOnly cookie
9. Redirect to frontend app
```

### Session Management

```python
# backend/app/utils/security.py

from cryptography.fernet import Fernet
from datetime import timedelta

# Session cookie settings
SESSION_COOKIE_NAME = "session_id"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = True  # HTTPS only in production
SESSION_COOKIE_SAMESITE = "lax"
SESSION_MAX_AGE = timedelta(days=7)

# Token encryption
def encrypt_token(token: str, key: bytes) -> str:
    f = Fernet(key)
    return f.encrypt(token.encode()).decode()

def decrypt_token(encrypted: str, key: bytes) -> str:
    f = Fernet(key)
    return f.decrypt(encrypted.encode()).decode()
```

### Security Considerations

| Concern | Mitigation |
|---------|------------|
| **Token exposure** | Access/refresh tokens encrypted in DB with Fernet |
| **XSS** | HttpOnly cookies, no tokens in frontend |
| **CSRF** | SameSite=Lax cookie, consider CSRF tokens for mutations |
| **Secrets management** | Environment variables, never committed |
| **HTTPS** | Enforced in production via Azure App Service |
| **SQL injection** | SQLAlchemy parameterized queries |
| **Input validation** | Pydantic models for all request bodies |

### Environment Variables

```bash
# .env.example

# Database
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Google OAuth
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxx
GOOGLE_REDIRECT_URI=https://yourapp.com/auth/google/callback

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://xxx.search.windows.net
AZURE_SEARCH_API_KEY=xxx
AZURE_SEARCH_INDEX_NAME=talk-to-folder-chunks

# OpenAI (Embeddings)
OPENAI_API_KEY=sk-xxx

# LLM (Claude or OpenAI)
ANTHROPIC_API_KEY=sk-ant-xxx
# or
# OPENAI_API_KEY=sk-xxx (reuse above)

# Temporal
TEMPORAL_HOST=xxx.tmprl.cloud:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_API_KEY=xxx

# Security
ENCRYPTION_KEY=xxx  # Fernet key, 32 bytes base64 encoded
SESSION_SECRET=xxx  # Random secret for session signing

# Azure Blob (optional)
AZURE_STORAGE_CONNECTION_STRING=xxx
```

---

## Ingestion Pipeline

### Temporal Workflow Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SyncFolderWorkflow                              │
│                                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│  │  CrawlFolder │───►│  For Each    │───►│ IndexChunks  │              │
│  │  Activity    │    │    File:     │    │  Activity    │              │
│  │              │    │              │    │  (batch)     │              │
│  │ • List all   │    │ ┌──────────┐ │    │              │              │
│  │   files      │    │ │ Extract  │ │    │ • Upsert to  │              │
│  │ • Recursive  │    │ │ Content  │ │    │   Azure AI   │              │
│  │ • Get metadata│   │ └────┬─────┘ │    │   Search     │              │
│  └──────────────┘    │      │       │    └──────────────┘              │
│                      │ ┌────▼─────┐ │                                   │
│                      │ │  Chunk   │ │                                   │
│                      │ │  Content │ │                                   │
│                      │ └────┬─────┘ │                                   │
│                      │      │       │                                   │
│                      │ ┌────▼─────┐ │                                   │
│                      │ │ Generate │ │                                   │
│                      │ │Embeddings│ │                                   │
│                      │ └────┬─────┘ │                                   │
│                      │      │       │                                   │
│                      │ ┌────▼─────┐ │                                   │
│                      │ │ Generate │ │                                   │
│                      │ │Questions │ │                                   │
│                      │ └──────────┘ │                                   │
│                      └──────────────┘                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

### File Type Extraction

```python
# worker/activities/extract_content.py

async def extract_content(file: DriveFile, access_token: str) -> ExtractedContent:
    """Extract text content from various file types."""

    match file.mime_type:
        case "application/vnd.google-apps.document":
            # Export as plain text
            text = await export_google_doc(file.id, access_token, "text/plain")
            return ExtractedContent(text=text, extraction_type="google_doc")

        case "application/vnd.google-apps.spreadsheet":
            # Export as CSV, capture metadata
            sheets = await export_google_sheets(file.id, access_token)
            return ExtractedContent(
                sheets=sheets,  # List of {name, headers, sample_rows, row_count}
                extraction_type="google_sheet"
            )

        case "application/pdf":
            content = await download_file(file.id, access_token)
            text = extract_pdf_text(content)
            if not text.strip():
                # Scanned PDF - use vision
                images = pdf_to_images(content)
                text = await vision_extract(images)
            return ExtractedContent(text=text, extraction_type="pdf")

        case "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            content = await download_file(file.id, access_token)
            text = extract_docx_text(content)
            return ExtractedContent(text=text, extraction_type="docx")

        case "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            content = await download_file(file.id, access_token)
            sheets = extract_xlsx_metadata(content)
            return ExtractedContent(sheets=sheets, extraction_type="xlsx")

        case mime if mime.startswith("image/"):
            content = await download_file(file.id, access_token)
            description = await vision_describe(content, file.mime_type)
            return ExtractedContent(
                text=description,
                extraction_type="image_description"
            )

        case "text/plain" | "text/markdown" | "text/csv":
            text = await download_file_text(file.id, access_token)
            return ExtractedContent(text=text, extraction_type="text")

        case _:
            raise UnsupportedFileType(file.mime_type)
```

### Chunking Strategy

```python
# worker/activities/chunk_content.py

def chunk_content(content: ExtractedContent, config: ChunkConfig) -> List[Chunk]:
    """
    Recursive chunking strategy:
    1. Try to split by headings
    2. If any chunk > max_tokens, split by paragraphs
    3. If still > max_tokens, split by fixed window with overlap
    """

    if content.extraction_type in ("google_sheet", "xlsx"):
        # Sheets: one chunk per sheet with metadata
        return chunk_spreadsheet(content.sheets)

    text = content.text

    # Step 1: Try heading-based splits
    chunks = split_by_headings(text)

    # Step 2: Check sizes, split large chunks by paragraph
    final_chunks = []
    for chunk in chunks:
        if count_tokens(chunk.text) > config.max_tokens:
            # Split by paragraphs
            sub_chunks = split_by_paragraphs(chunk.text, parent_heading=chunk.heading)

            for sub in sub_chunks:
                if count_tokens(sub.text) > config.max_tokens:
                    # Step 3: Fixed window fallback
                    final_chunks.extend(
                        split_fixed_window(
                            sub.text,
                            window_size=config.max_tokens,
                            overlap=config.overlap,
                            parent_heading=sub.heading
                        )
                    )
                else:
                    final_chunks.append(sub)
        else:
            final_chunks.append(chunk)

    return final_chunks


def split_by_headings(text: str) -> List[Chunk]:
    """Split text by markdown-style headings (# Heading)."""
    pattern = r'^(#{1,6})\s+(.+)$'
    # ... implementation


def split_by_paragraphs(text: str, parent_heading: Optional[str]) -> List[Chunk]:
    """Split text by double newlines."""
    paragraphs = text.split('\n\n')
    # ... implementation


def split_fixed_window(text: str, window_size: int, overlap: int, parent_heading: Optional[str]) -> List[Chunk]:
    """Last resort: fixed token window with overlap."""
    # ... implementation
```

### Question Generation

```python
# worker/activities/generate_questions.py

QUESTION_GENERATION_PROMPT = """
Given the following text content, generate 3-5 questions that this content could answer.
These questions should be phrased the way a user might naturally ask them.

Content:
{content}

Output only the questions, one per line, no numbering or bullets.
"""

async def generate_questions(chunk: Chunk, llm_client: LLMClient) -> List[str]:
    """Generate hypothetical questions this chunk could answer."""

    response = await llm_client.complete(
        prompt=QUESTION_GENERATION_PROMPT.format(content=chunk.text),
        max_tokens=200
    )

    questions = [q.strip() for q in response.split('\n') if q.strip()]
    return questions[:5]  # Cap at 5
```

---

## Agent System

### Design Philosophy

The folder agent follows a core principle borrowed from production agent systems: **the model handles judgment, the code handles execution.** The LLM decides which files to examine, what to search for, and how to synthesize an answer. The tools execute searches, read file contents, and return bounded, formatted results. The LLM never touches Google Drive, Azure Search, or file parsing libraries directly — it outputs structured JSON saying "call function X with arguments Y," and deterministic code executes that.

The critical difference from a write-oriented agent (like a spreadsheet cleaning agent) is that this agent is **read-only** — it never mutates data. This simplifies safety concerns (no need for row-protection or reverse-iteration) but introduces a different challenge: **navigating large, heterogeneous document collections without blowing the context window.**

The agent must handle files it has never seen before — messy spreadsheets with 1,000+ rows, scanned PDFs with OCR artifacts, Google Docs with embedded images, nested folder hierarchies with ambiguous naming. The tool design assumes the worst case: every file is messy, every spreadsheet is huge, and the answer might span multiple documents.

### The Core Algorithm

The entire agent is a while loop that calls the LLM until the LLM stops requesting tool calls. This is the same ReAct (Reasoning + Acting) pattern used in production agent systems:

```
START with:
  - A system prompt (instructions, tool summaries, project context)
  - Chat history (previous turns in the conversation)
  - The user's question
  - A list of 14 tool definitions the LLM can call

REPEAT up to 15 times:
  1. Send everything to the LLM (system prompt + all messages + tool definitions)

  2. LLM responds with EITHER:
     a) Tool calls: "I want to call hybrid_search with query='Q3 revenue'"
     b) Just text: "Based on my research, here's what I found..."

  3. IF the LLM wants to call tools:
     - Execute each tool (inject project_id and access_token — model never provides these)
     - Collect any citations generated by the tool
     - Add the tool results to the message history
     - Go back to step 1

  4. IF the LLM just sent text (no tool calls):
     - The agent is done
     - Return the response with deduplicated citations

END
```

Most questions resolve in 3-6 tool calls. Complex cross-file synthesis may take 8-12. The 15-iteration cap prevents runaway loops.

### Architecture

```python
# backend/app/services/agent.py

class FolderAgent:
    """
    ReAct-style agent for answering questions about Google Drive folder contents.
    Uses tool-calling in a loop until the LLM produces a final answer.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        search_service: AzureSearchService,
        drive_service: GoogleDriveService,
        model: str = "anthropic/claude-sonnet-4-5-20250929",
        max_iterations: int = 15,
    ):
        self.llm = llm_client
        self.search = search_service
        self.drive = drive_service
        self.model = model
        self.max_iterations = max_iterations

    async def answer(
        self,
        question: str,
        project_id: str,
        user_access_token: str,
        chat_history: list[Message],
    ) -> AgentResponse:
        """
        Main entry point. Runs the agent loop until the LLM stops
        calling tools or max_iterations is reached.
        """

        system_prompt = self._build_system_prompt(project_id)
        messages = self._build_messages(chat_history, question)

        citations_collected: list[Citation] = []

        for iteration in range(self.max_iterations):
            response = await self.llm.call_with_tools(
                messages=messages,
                tools=ALL_TOOL_DEFINITIONS,
                model=self.model,
                tool_choice="auto",
                temperature=0.1,
            )

            assistant_msg = response.choices[0].message

            if assistant_msg.tool_calls:
                # Add assistant message to history
                messages.append(serialize_assistant_msg(assistant_msg))

                # Execute each tool call
                for tool_call in assistant_msg.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    # Safety: inject project_id and access_token unconditionally.
                    # The model never provides these — the code does.
                    result, new_citations = await execute_tool(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        project_id=project_id,
                        access_token=user_access_token,
                        search_service=self.search,
                        drive_service=self.drive,
                    )

                    citations_collected.extend(new_citations)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
            else:
                # No tool calls — agent is done
                return AgentResponse(
                    content=assistant_msg.content,
                    citations=deduplicate_citations(citations_collected),
                    iterations=iteration + 1,
                )

        # Hit max iterations — return what we have with a warning
        return AgentResponse(
            content=assistant_msg.content + "\n\n(Note: I reached my reasoning limit. "
                    "The answer above is based on what I found so far.)",
            citations=deduplicate_citations(citations_collected),
            iterations=self.max_iterations,
            hit_limit=True,
        )
```

### Safety: What the Code Controls (Not the Prompt)

These invariants are enforced in `execute_tool()`, not in the system prompt. The model cannot bypass them regardless of what it reasons. This follows a critical principle from production agent engineering: **push safety into tools, not prompts. Prompts can be forgotten or misinterpreted. Code is absolute.**

| Invariant | Enforcement |
|---|---|
| **Project isolation** | Every search and file-read call has `project_id` injected by the code. The model never passes `project_id` — it's not even a tool parameter. A user's agent cannot access another user's indexed content. |
| **Token-scoped Drive access** | The user's `access_token` is injected by the code, never provided by the model. If the token expires mid-conversation, the tool returns an auth error and the agent can surface it. |
| **Bounded output** | Every tool enforces output size limits. `read_spreadsheet_rows` caps at 50 rows. `read_document_pages` caps at 5 pages. `hybrid_search` caps at 15 results. The model can request more within bounds, but the tool silently clamps to the maximum. |
| **Read-only access** | No tool can modify Drive files. The entire tool set is read-only by design. |

### Tool Design Principles

The tools follow patterns proven in production agent systems:

**1. Tools match human intent, not machine operations.** Not `get_embedding_for_query()` repeated in a pipeline — instead, `hybrid_search(query)`. Not `read_cell(row, col)` repeated 400 times — instead, `get_column_stats(column)`. The tools are designed at the level a human would describe the operation: "search for revenue info", "show me the spreadsheet structure", "read page 3 of the PDF".

**2. Observation tools return formatted, bounded data.** Every tool that returns content uses sensible defaults to prevent dumping thousands of rows or pages into the context window. `read_spreadsheet_rows` defaults to 30 rows (max 50). `hybrid_search` defaults to 8 results (max 15). Values are labeled for clarity: `A(Date)=2024-07-01` tells the model both the column letter and header name.

**3. Transform/action tools report what they did.** Even though this agent is read-only, every tool returns a human-readable summary the model can verify: `"Found 7 rows matching 'AWS' in sheet 'Q3 Actuals'"` or `"Pages 3-5 of 'Q3_summary.pdf' (12 pages total)"`. If 0 results are returned, the model knows to try a different approach.

**4. Tools accept multiple input formats.** A column can be referenced as `"A"`, `"Amount"`, or `"amount"`. A file can be referenced by `file_id` from a search result or discovered via folder structure. Flexibility in input, strictness in execution.

**5. Only require essential parameters.** Every tool minimizes `required` params and provides sensible defaults. The model shouldn't need to provide 5 arguments for a simple search. This reduces token usage and error surface.

### Tool Inventory

Tools are organized into six categories. Each category exists because the agent needs a specific capability — without any one category, there are questions it simply cannot answer.

---

#### Category 1: Search Tools

These are the primary entry point for most questions. The agent searches indexed content first, then drills deeper with other tools.

**`hybrid_search`** — Search across all indexed documents using combined semantic and keyword matching.

```json
{
    "name": "hybrid_search",
    "description": "Search across all indexed documents using combined semantic and keyword matching. Returns the most relevant chunks with source file info and content snippets. Use this as your FIRST tool for most questions. Prefer short, specific queries. Use file_type filter to narrow results (e.g., only PDFs, only spreadsheets).",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language search query. Be specific — 'Q3 revenue by region' works better than 'revenue'."
            },
            "file_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional filter: ['pdf', 'docx', 'xlsx', 'google_doc', 'google_sheet', 'image', 'txt']. Omit to search all."
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default 8, max 15). Use higher values for broad questions spanning many files.",
                "default": 8
            }
        },
        "required": ["query"]
    }
}
```

Implementation notes:
- Searches both `content_vector` and `questions_vector` fields for better recall (the questions_vector captures "what would someone ask about this chunk?")
- Returns formatted results: `[1] budget_2024.xlsx (Sheet: Q3, Row 14-28) — "Regional revenue breakdown showing North: $2.1M, South: $1.8M..."`
- Each result includes a `chunk_id` the agent can use with `read_chunk_context` to see surrounding content
- The `project_id` filter is injected by code — it is not a parameter the model sees or provides

**`search_within_file`** — Search within a specific file's indexed content.

```json
{
    "name": "search_within_file",
    "description": "Search within a specific file's indexed content. Use this when you already know WHICH file has the answer and need to find a specific section. More targeted than hybrid_search — avoids results from other files.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "The file_id from a previous search result or folder listing."
            },
            "query": {
                "type": "string",
                "description": "What to search for within this file."
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results (default 5, max 10).",
                "default": 5
            }
        },
        "required": ["file_id", "query"]
    }
}
```

Implementation: same hybrid search engine, but with an additional `file_id eq '{file_id}'` filter applied unconditionally alongside the `project_id` filter.

---

#### Category 2: Discovery Tools

The agent needs to understand what's in the folder before it can answer structural questions ("What files do we have about Q3?", "Is there a budget spreadsheet?").

**`get_folder_structure`** — Get the complete folder tree showing all files and subfolders.

```json
{
    "name": "get_folder_structure",
    "description": "Get the complete folder tree showing all files and subfolders. Returns file names, types, sizes, and folder hierarchy. Use this when the user asks what's in the folder, or when you need to find a specific file by name.",
    "parameters": {
        "type": "object",
        "properties": {
            "path_filter": {
                "type": "string",
                "description": "Optional: filter to a subfolder path (e.g., 'Q3 Reports/'). Omit to see everything."
            }
        },
        "required": []
    }
}
```

Returns a formatted tree:
```
📁 Project Alpha/
├── 📁 Financial/
│   ├── 📊 budget_2024.xlsx (3 sheets, 245 KB)
│   ├── 📄 expense_policy.pdf (12 pages, 1.2 MB)
│   └── 📝 notes.txt (2 KB)
├── 📁 Reports/
│   ├── 📄 Q3_summary.docx (18 pages)
│   └── 📄 Q3_presentation.pdf (24 slides)
└── 🖼️ org_chart.png (890 KB)

7 files across 2 subfolders. Last synced: 2024-01-15 14:30 UTC.
```

**`get_file_metadata`** — Get detailed metadata about a specific file.

```json
{
    "name": "get_file_metadata",
    "description": "Get detailed metadata about a specific file: size, type, last modified, page/sheet count, and a brief content summary from the index. Use this before reading a file to understand its structure.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "The file_id from a search result or folder listing."
            }
        },
        "required": ["file_id"]
    }
}
```

Returns metadata the agent can use to decide *how* to read the file — a 2-page PDF gets a different approach than a 1,000-row spreadsheet.

---

#### Category 3: Document Reading Tools

These tools let the agent read actual file content beyond what was captured in indexed chunks. Critical for when search results are close but not enough — the agent needs surrounding context, or a section that wasn't well-chunked.

**`read_document_pages`** — Read specific pages from a PDF or DOCX file.

```json
{
    "name": "read_document_pages",
    "description": "Read specific pages from a PDF or DOCX file. Returns the raw text content for the requested page range. Use this when search results reference a specific file and you need to read more context around a section. For large documents, read in small ranges (3-5 pages at a time) rather than all at once.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "The file_id from a search result or folder listing."
            },
            "start_page": {
                "type": "integer",
                "description": "First page to read (1-based).",
                "default": 1
            },
            "end_page": {
                "type": "integer",
                "description": "Last page to read (inclusive). Max 5 pages per call. Omit to read a single page."
            }
        },
        "required": ["file_id"]
    }
}
```

Implementation notes:
- Clamps `end_page - start_page` to a max of 5 pages per call. The model can call it multiple times to read more.
- For Google Docs, exports as plain text and splits by approximate page breaks.
- For scanned PDFs where OCR produced the indexed content, returns the OCR text for the requested pages.
- Returns: `"Pages 3-5 of 'Q3_summary.pdf' (12 pages total):\n\n[text content]"`

**`read_chunk_context`** — Expand a search result to see surrounding content.

```json
{
    "name": "read_chunk_context",
    "description": "Expand a search result to see surrounding content. Given a chunk_id from a previous search result, returns the chunk PLUS the chunks immediately before and after it in the same file. Use this when a search result looks relevant but is cut off or needs more context.",
    "parameters": {
        "type": "object",
        "properties": {
            "chunk_id": {
                "type": "string",
                "description": "The chunk_id from a hybrid_search or search_within_file result."
            }
        },
        "required": ["chunk_id"]
    }
}
```

This is a critical tool for handling the "chunk boundary problem" — when the answer to a question is split across two adjacent chunks. Instead of forcing the model to make multiple searches hoping to find both halves, it can expand a promising result.

**`get_document_outline`** — Get the heading structure / table of contents of a document.

```json
{
    "name": "get_document_outline",
    "description": "Get the heading structure / table of contents of a document. Returns a list of section headings with page numbers. Use this to understand a document's structure before deciding which pages to read. Works for PDFs with bookmarks, DOCX with heading styles, and Google Docs.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "The file_id of the document."
            }
        },
        "required": ["file_id"]
    }
}
```

Returns:
```
Outline of 'Q3_summary.pdf' (12 pages):
  1. Executive Summary .............. p.1
  2. Revenue Analysis ............... p.3
     2.1 By Region .................. p.3
     2.2 By Product Line ............ p.5
  3. Expense Breakdown .............. p.7
  4. Forecasts ...................... p.10
  5. Appendix ....................... p.12
```

The agent can then make an informed decision: "The user asked about expenses, I should read pages 7-9."

---

#### Category 4: Spreadsheet Tools

Spreadsheets are the hardest file type. A 1,000-row Excel file cannot be stuffed into context. These tools follow proven patterns — bounded views, formatted output, and search within the sheet. The agent can navigate a 1,000-row spreadsheet in 3-4 tool calls instead of attempting to read it all.

**`get_spreadsheet_overview`** — Get a structural overview of a spreadsheet.

```json
{
    "name": "get_spreadsheet_overview",
    "description": "Get a structural overview of a spreadsheet: sheet names, column headers, data types, row counts, and a preview of the first 5 rows per sheet. ALWAYS call this before reading spreadsheet data — it tells you what's available without loading the full file.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "The file_id of the spreadsheet."
            }
        },
        "required": ["file_id"]
    }
}
```

Returns:
```
Spreadsheet: 'budget_2024.xlsx' (3 sheets)

Sheet 'Q3 Actuals' (847 rows, 12 columns):
  Columns: A(Date) string | B(Department) string | C(Category) string |
           D(Description) string | E(Amount) number | F(Currency) string | ...
  Preview:
    Row 1: A(Date)=2024-07-01, B(Department)=Engineering, C(Category)=SaaS,
           D(Description)=AWS hosting, E(Amount)=14500, F(Currency)=USD
    Row 2: A(Date)=2024-07-01, B(Department)=Engineering, C(Category)=SaaS,
           D(Description)=Datadog, E(Amount)=3200, F(Currency)=USD
    ...

Sheet 'Budget Targets' (24 rows, 6 columns):
  Columns: A(Department) string | B(Q1 Budget) number | C(Q2 Budget) number | ...
  Preview:
    Row 1: A(Department)=Engineering, B(Q1 Budget)=450000, C(Q2 Budget)=475000
    ...

Sheet 'Notes' (8 rows, 2 columns):
  ...
```

The labeled format (`A(Date)=2024-07-01`) gives the model both the column letter and header name so it can reference either in subsequent tool calls.

**`read_spreadsheet_rows`** — Read a bounded range of rows from a spreadsheet.

```json
{
    "name": "read_spreadsheet_rows",
    "description": "Read a range of rows from a spreadsheet sheet. Returns formatted rows with column headers labeled. Use this to page through data — call repeatedly with different start values to scan a large sheet. Max 50 rows per call to keep responses manageable.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "The file_id of the spreadsheet."
            },
            "sheet_name": {
                "type": "string",
                "description": "Which sheet to read. Omit for the first sheet."
            },
            "start_row": {
                "type": "integer",
                "description": "First data row to read (1-based, after header).",
                "default": 1
            },
            "num_rows": {
                "type": "integer",
                "description": "How many rows to read (default 30, max 50).",
                "default": 30
            },
            "columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional: only return these columns (by header name or letter). Useful for wide sheets."
            }
        },
        "required": ["file_id"]
    }
}
```

The `columns` filter is important for wide sheets — if a spreadsheet has 20 columns but the user asked about expenses, the agent can request only `["Date", "Description", "Amount"]` and save context window space.

**`search_spreadsheet`** — Search for specific values or patterns within a spreadsheet.

```json
{
    "name": "search_spreadsheet",
    "description": "Search for specific values or patterns within a spreadsheet. Returns matching rows with row numbers. Use this instead of paging through hundreds of rows when you're looking for specific entries. Supports regex patterns and is case-insensitive.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "The file_id of the spreadsheet."
            },
            "pattern": {
                "type": "string",
                "description": "Search term or regex pattern. Matches against any cell in a row."
            },
            "sheet_name": {
                "type": "string",
                "description": "Which sheet to search. Omit for the first sheet."
            },
            "column": {
                "type": "string",
                "description": "Optional: limit search to a specific column (by header name or letter)."
            },
            "max_results": {
                "type": "integer",
                "description": "Max matching rows to return (default 20, max 50).",
                "default": 20
            }
        },
        "required": ["file_id", "pattern"]
    }
}
```

Returns: `"Found 7 rows matching 'AWS' in sheet 'Q3 Actuals':\n  Row 12: A(Date)=2024-07-01, D(Description)=AWS hosting, E(Amount)=14500\n  Row 45: ..."`

**`get_column_stats`** — Get summary statistics for a numeric column.

```json
{
    "name": "get_column_stats",
    "description": "Get summary statistics for a numeric column: sum, average, min, max, count, count of blanks, and the 5 most common values. Use this for questions like 'what's the total spend?' or 'what's the average deal size?' without needing to read every row.",
    "parameters": {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "The file_id of the spreadsheet."
            },
            "column": {
                "type": "string",
                "description": "Column to analyze (by header name or letter)."
            },
            "sheet_name": {
                "type": "string",
                "description": "Which sheet. Omit for the first sheet."
            },
            "group_by": {
                "type": "string",
                "description": "Optional: group stats by another column. E.g., column='Amount', group_by='Department' returns totals per department."
            }
        },
        "required": ["file_id", "column"]
    }
}
```

This is a compound tool — conceptually one operation ("summarize this column") but mechanically it reads every row, computes aggregations, and optionally groups. Without it, the agent would need to page through 1,000 rows 50 at a time, eating 20 iterations just to compute a sum.

Returns:
```
Stats for column 'Amount' in sheet 'Q3 Actuals' (847 rows):
  Sum: $1,247,500
  Average: $1,473
  Min: $12 (row 234)
  Max: $145,000 (row 8)
  Non-empty: 842 | Blank: 5

  Grouped by 'Department':
    Engineering: $487,200 (330 rows)
    Marketing: $312,800 (215 rows)
    Sales: $289,500 (198 rows)
    Operations: $158,000 (104 rows)
```

---

#### Category 5: Control Tools

**`report_inability`** — Graceful exit when the agent cannot answer.

```json
{
    "name": "report_inability",
    "description": "Use this when you've searched thoroughly but CANNOT answer the question. Explain what you searched for, what you found (or didn't find), and suggest what the user might do (e.g., 're-sync the folder', 'check if the file exists', 'the file may be in a format I can't read').",
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Why you can't answer — what you tried and what's missing."
            }
        },
        "required": ["reason"]
    }
}
```

Without this, a stuck agent loops through all 15 iterations burning tokens and time. With it, the agent exits immediately with a useful explanation. This mirrors the `report_failure` pattern from production agent systems.

**`request_clarification`** — Ask the user a disambiguating question.

```json
{
    "name": "request_clarification",
    "description": "Ask the user a clarifying question when the query is ambiguous. For example, if there are multiple files about 'budget' and you're not sure which one, or if the question could mean different things. Only use this after at least one search attempt — try to answer first.",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The clarifying question for the user."
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional: specific options for the user to pick from."
            }
        },
        "required": ["question"]
    }
}
```

---

### Tool Summary Table

| Category | Tool | Purpose | When the agent uses it |
|---|---|---|---|
| **Search** | `hybrid_search` | Vector + keyword search across all indexed content | First tool for most questions — semantic search with keyword fallback |
| **Search** | `search_within_file` | Search within a single file's chunks | Drill deeper after identifying the right file |
| **Discovery** | `get_folder_structure` | Tree view of all files and subfolders | "What's in this folder?", finding files by name |
| **Discovery** | `get_file_metadata` | File details: size, type, pages, modified date | Deciding how to read a file before reading it |
| **Document** | `read_document_pages` | Read specific pages from PDFs/DOCX (max 5 per call) | Going deeper than indexed chunks — raw content with surrounding context |
| **Document** | `read_chunk_context` | Expand a search result ±1 chunk | Handling chunk boundary problems — answers split across chunks |
| **Document** | `get_document_outline` | Heading structure / table of contents | Navigating large documents without reading everything |
| **Spreadsheet** | `get_spreadsheet_overview` | Sheet names, headers, row counts, types, preview | Understanding spreadsheet structure before diving in |
| **Spreadsheet** | `read_spreadsheet_rows` | Bounded row range (max 50 per call) | Paging through large sheets without blowing context |
| **Spreadsheet** | `search_spreadsheet` | Regex search across cells | Finding specific entries in 1,000-row sheets |
| **Spreadsheet** | `get_column_stats` | Sum, average, min, max, grouped aggregations | Answering numeric questions without reading every row |
| **Control** | `report_inability` | Graceful exit with explanation | Stopping the loop early when the answer isn't findable |
| **Control** | `request_clarification` | Ask user a disambiguating question | Handling genuinely ambiguous queries after trying to search first |

### System Prompt

```python
SYSTEM_PROMPT = """
You are an AI assistant that helps users find and understand information
in their Google Drive folders. You have access to a folder of documents
that has been indexed for search. The folder may contain PDFs, Word
documents, spreadsheets, text files, images, and Google Docs/Sheets.

## Your tools

SEARCH TOOLS — start here for most questions:
- hybrid_search: Search all indexed content (semantic + keyword). Use short, specific queries.
- search_within_file: Search within a specific file you've already identified.

DISCOVERY TOOLS — understand what's in the folder:
- get_folder_structure: See all files and subfolders.
- get_file_metadata: Get details about a specific file before reading it.

DOCUMENT READING TOOLS — go deeper into specific files:
- read_document_pages: Read specific pages of a PDF or document (max 5 pages per call).
- read_chunk_context: Expand a search result to see surrounding content.
- get_document_outline: Get the heading structure of a document.

SPREADSHEET TOOLS — work with Excel and Google Sheets data:
- get_spreadsheet_overview: See sheet names, headers, row counts, and a preview.
  Always call this first for any spreadsheet question.
- read_spreadsheet_rows: Read a range of rows (max 50 per call).
- search_spreadsheet: Find specific values or patterns in a sheet.
- get_column_stats: Get sum, average, min, max, and grouped breakdowns for a
  numeric column.

CONTROL TOOLS:
- report_inability: When you genuinely cannot answer after searching.
- request_clarification: When the question is ambiguous (only after trying to
  search first).

## How to approach questions

1. START WITH SEARCH. For almost every question, begin with hybrid_search. Use
   2-4 word queries that capture the key concepts. If the first search doesn't
   find enough, try different phrasings or synonyms.

2. DRILL DEEPER WHEN NEEDED. If search results reference a file but the chunk
   is incomplete, use read_chunk_context to expand, or read_document_pages to see
   more. For spreadsheet questions, get_spreadsheet_overview first, then use
   read_spreadsheet_rows, search_spreadsheet, or get_column_stats as appropriate.

3. DON'T READ EVERYTHING. Large documents and spreadsheets cannot fit in context.
   Use outlines, overviews, and targeted searches to find the relevant sections.
   Only read the specific pages or rows you need.

4. CROSS-REFERENCE WHEN APPROPRIATE. If information spans multiple files, search
   each one and synthesize. Note when files agree or conflict.

5. CITE YOUR SOURCES. Every factual claim in your answer must include a citation.
   Use the format [source: filename, page/section] or
   [source: filename, sheet, row range]. The user should be able to find exactly
   where the information came from.

6. BE HONEST ABOUT GAPS. If you searched and couldn't find something, say so.
   Don't guess or fabricate. Use report_inability if you've exhausted your
   search options.

## Spreadsheet-specific guidance

Spreadsheets in this folder may be messy — they may have title rows, merged cells,
multiple header rows, subtotals, or inconsistent formatting. When working with
spreadsheets:
- Always start with get_spreadsheet_overview to understand the structure.
- For "how much" / "total" / "average" questions, prefer get_column_stats over
  reading all rows.
- For "find all rows where..." questions, prefer search_spreadsheet over paging.
- Only use read_spreadsheet_rows when you need to see actual data in order and
  the other tools don't suffice.
- If a sheet has 500+ rows, NEVER try to read it all. Use stats and search instead.

## Project context
- Project: {project_name}
- Last synced: {last_synced}
- Total files: {file_count}
"""
```

### The Message History Pattern

The message history is the agent's memory. Each iteration, the full conversation — system prompt, user message, every assistant response, every tool call, every tool result — is sent to the LLM. The LLM sees everything it has done and can make informed decisions about what to do next.

```python
messages = [
    # 1. System prompt (instructions + tool summaries + project context)
    {"role": "system", "content": "You are an AI assistant..."},

    # 2. Previous chat turns (if any)
    {"role": "user", "content": "What was Q3 revenue?"},
    {"role": "assistant", "content": "Based on the budget spreadsheet, Q3 revenue was $1.2M..."},

    # 3. Current question
    {"role": "user", "content": "How does that break down by department?"},

    # 4. Agent's first tool call this iteration
    {"role": "assistant", "content": "Let me look at the departmental breakdown...",
     "tool_calls": [{"id": "call_1", "function": {"name": "get_column_stats",
                     "arguments": '{"file_id":"abc","column":"Amount","group_by":"Department"}'}}]},

    # 5. Tool result
    {"role": "tool", "tool_call_id": "call_1",
     "content": "Stats for column 'Amount' grouped by 'Department':\n  Engineering: $487,200..."},

    # 6. Agent's final response (no more tool calls — loop exits)
    # (This is what the next LLM call would produce)
]
```

### Context Management

As conversations grow, the message history will eventually approach the context window limit. The agent uses different strategies for within-question context and across-conversation context.

**Within a single question (agent loop):**
- Most questions resolve in 3-6 tool calls, well within context limits
- Tool results are bounded by design (max 50 rows, max 5 pages, max 15 search results)
- If a question is complex (10+ iterations), large tool results from early iterations are summarized: the full text is replaced with a compact note like `"[Earlier: searched 'Q3 revenue' — found 8 results across 3 files]"`
- The system prompt and most recent 3 tool results are always kept in full

**Across the chat session (multi-turn conversation):**
- Previous question/answer pairs are included as context for follow-up questions
- After 5+ turns, older turns are summarized using an LLM call: `"[Earlier in chat: User asked about Q3 revenue ($1.2M total). Then asked about top expenses (AWS $487K was largest).]"`
- The most recent 2 full turns are always preserved verbatim so the agent can handle "what about by department?" style follow-ups
- Citations from previous turns are preserved in the summary so the agent doesn't re-search for already-cited information

### Citation Tracking

Citations are tracked through the tool execution layer, not by the model. Every tool that returns content also returns structured citation metadata:

```python
@dataclass
class Citation:
    chunk_id: str
    file_id: str
    file_name: str
    source_url: str           # Google Drive URL for the file
    location: str             # "page 3", "Sheet 'Q3', rows 12-28", "section 2.1"
    snippet: str              # Brief excerpt showing the relevant content

async def execute_tool(...) -> tuple[str, list[Citation]]:
    """Every tool returns both its text result AND any citations generated."""
    # When hybrid_search returns results, each result becomes a Citation
    # When read_document_pages reads content, it creates a Citation for those pages
    # When get_column_stats computes stats, it creates a Citation for the sheet
    # The agent loop collects all citations and deduplicates at the end
```

The model references citations in its answer using `[source: filename]` notation. The frontend maps these to the collected `Citation` objects to render interactive tooltips with snippets and clickable links to the Drive file.

### Example Agent Walkthrough

To illustrate how the tools work together, here's a trace of the agent answering: "What department spent the most on SaaS tools in Q3?"

**Iteration 1 — Search first:**
```
Agent calls: hybrid_search(query="SaaS spending by department Q3")
Result: "[1] budget_2024.xlsx (Sheet: Q3 Actuals, rows 12-15) — 'AWS hosting $14,500,
         Datadog $3,200...'
         [2] expense_policy.pdf (page 4) — 'SaaS subscriptions require manager approval
         above $5,000...'"
```

**Iteration 2 — Identify the right file and understand its structure:**
```
Agent calls: get_spreadsheet_overview(file_id="budget_2024_id")
Result: "Sheet 'Q3 Actuals' (847 rows, 12 columns): A(Date), B(Department),
         C(Category), D(Description), E(Amount)..."
```

**Iteration 3 — Use stats tool to aggregate without reading all 847 rows:**
```
Agent calls: get_column_stats(file_id="budget_2024_id", column="Amount",
             sheet_name="Q3 Actuals", group_by="Department")
Result: "Stats grouped by 'Department': Engineering: $487,200, Marketing: $312,800..."
```

But wait — this is *all* spending, not just SaaS. The agent notices.

**Iteration 4 — Search within the spreadsheet for SaaS entries:**
```
Agent calls: search_spreadsheet(file_id="budget_2024_id", pattern="SaaS",
             column="Category", max_results=50)
Result: "Found 43 rows matching 'SaaS' in column 'Category':
         Row 1: Engineering, SaaS, AWS hosting, $14,500
         Row 2: Engineering, SaaS, Datadog, $3,200
         Row 5: Marketing, SaaS, HubSpot, $8,900
         ..."
```

**Iteration 5 — The agent now has enough context to reason and respond:**
```
Agent responds (no tool calls — loop exits):
"Engineering spent the most on SaaS tools in Q3, with $187,400 across 22
subscriptions. The largest were AWS hosting ($14,500/mo) and GitHub Enterprise
($12,000/mo). Marketing was second at $94,200, driven primarily by HubSpot
($8,900/mo) and Salesforce ($7,500/mo).
[source: budget_2024.xlsx, Sheet 'Q3 Actuals']"
```

Total: 5 iterations, ~8 seconds, with a precise answer drawn from 847 rows the agent never fully loaded into context.

### Evaluation Strategy

Following production agent best practices, evaluate at two levels:

**End-to-end metrics:**
- Did the agent answer the question correctly? (LLM-as-judge against golden answers)
- Were citations accurate? (Does the cited file actually contain the claimed information?)
- Iteration count per question (target: median 4, p95 under 10)
- Latency per question (target: median under 8s)
- Cost per question (track tokens consumed)

**Component-level checks:**
- Did the agent search before answering? (It should almost always search first)
- Did it use the right tool for the file type? (Spreadsheet questions should hit spreadsheet tools)
- Did it respect output bounds? (Never tried to read 100 spreadsheet rows at once)
- Did it give up appropriately? (Used `report_inability` instead of looping to max iterations)

**Golden dataset:** Build 50+ test cases covering:
- Single-file factual questions ("What was Q3 revenue?")
- Cross-file synthesis ("Compare the budget to actual expenses")
- Spreadsheet-specific questions ("What department spent the most?")
- Needle-in-haystack ("Find the clause about termination in the contract")
- Unanswerable questions ("What was Q5 revenue?" — should gracefully say not found)
- Messy file handling (spreadsheets with title rows, merged cells, OCR'd PDFs)

---

## Deployment

### Dockerfile (Main App)

```dockerfile
# Dockerfile

# Stage 1: Build frontend
FROM node:20-alpine AS frontend
WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Production
FROM python:3.12-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/app ./app
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic

# Copy built frontend
COPY --from=frontend /build/dist ./static

# Create directories
RUN mkdir -p /app/logs

# Non-root user for security
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
```

### Dockerfile (Worker)

```dockerfile
# Dockerfile.worker

FROM python:3.12-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy worker code
COPY worker ./worker
COPY backend/app/services ./app/services  # Shared services
COPY backend/app/config.py ./app/config.py

# Non-root user
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

CMD ["python", "-m", "worker.main"]
```

### Docker Compose (Local Development)

```yaml
# docker-compose.yml

version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/talk_to_folder
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
      - GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
      - AZURE_SEARCH_ENDPOINT=${AZURE_SEARCH_ENDPOINT}
      - AZURE_SEARCH_API_KEY=${AZURE_SEARCH_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - TEMPORAL_HOST=temporal:7233
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
      - SESSION_SECRET=${SESSION_SECRET}
    depends_on:
      - db
      - temporal

  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/talk_to_folder
      - AZURE_SEARCH_ENDPOINT=${AZURE_SEARCH_ENDPOINT}
      - AZURE_SEARCH_API_KEY=${AZURE_SEARCH_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - TEMPORAL_HOST=temporal:7233
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
    depends_on:
      - db
      - temporal

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: talk_to_folder
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  temporal:
    image: temporalio/auto-setup:1.22
    ports:
      - "7233:7233"
    environment:
      - DB=postgresql
      - DB_PORT=5432
      - POSTGRES_USER=postgres
      - POSTGRES_PWD=postgres
      - POSTGRES_SEEDS=db

volumes:
  postgres_data:
```

### Azure Deployment

```bash
# Build and push to Azure Container Registry
az acr build --registry <registry-name> --image talk-to-folder:latest .
az acr build --registry <registry-name> --image talk-to-folder-worker:latest -f Dockerfile.worker .

# Deploy to Azure App Service
az webapp create \
  --resource-group <rg> \
  --plan <plan> \
  --name talk-to-folder \
  --deployment-container-image-name <registry>.azurecr.io/talk-to-folder:latest

# Configure environment variables
az webapp config appsettings set \
  --resource-group <rg> \
  --name talk-to-folder \
  --settings \
    DATABASE_URL="..." \
    GOOGLE_CLIENT_ID="..." \
    # ... all other env vars
```

---

## Edge Cases & Error Handling

| Scenario | Detection | Handling |
|----------|-----------|----------|
| **Pasted URL is not a folder** | Drive API returns `mimeType != "application/vnd.google-apps.folder"` | Return error: "This link points to a single file, not a folder. Please paste a folder link." |
| **User lacks access to folder** | Drive API returns 403/404 | Return error: "You don't have access to this folder. Please check permissions." |
| **Some files inaccessible** | Per-file 403 during crawl | Log warning, skip file, include in sync summary |
| **Unsupported file type** | MIME type not in supported list | Skip with log, include in sync summary |
| **Very large file (>50MB)** | Check file size before download | Skip or truncate with warning |
| **PDF is scanned (no text)** | Text extraction returns empty | Fall back to vision-based OCR |
| **Sync times out** | Temporal workflow timeout | Retry with backoff, mark partial completion |
| **Google API rate limit** | 429 response | Exponential backoff in Temporal activity |
| **User chats during sync** | `sync_status == SYNCING` | Allow chat, search returns partial results, show "sync in progress" badge |
| **Empty folder** | No files found | Show message: "This folder is empty. Add some files and re-sync." |
| **Nested folder >10 levels deep** | Depth counter during crawl | Continue crawling (no limit), but warn if >100 files |
| **Duplicate file names** | Same name in different subfolders | Use full hierarchy path for disambiguation |
| **Google Docs with images** | Embedded images in doc | Extract images, process with vision model |
| **Chat token limit exceeded** | Message history too long | Summarize older turns, keep system prompt and recent context |
| **Agent hits max iterations** | Iteration counter reaches 15 | Return partial answer with warning, suggest user refine question |
| **Tool returns empty results** | Search finds nothing | Agent tries rephrased query or uses `report_inability` |
| **Spreadsheet with no clear header** | Overview shows messy structure | Agent reads first rows, uses judgment to identify header, works with available data |
| **Drive token expires mid-conversation** | Tool returns auth error | Agent surfaces error to user, suggests re-authenticating |

### Error Response Format

```python
# backend/app/schemas/error.py

class ErrorResponse(BaseModel):
    error: str
    error_code: str
    details: Optional[dict] = None

# Example usage
@app.exception_handler(DriveAccessError)
async def drive_access_error_handler(request, exc):
    return JSONResponse(
        status_code=403,
        content=ErrorResponse(
            error="Cannot access this Google Drive folder",
            error_code="DRIVE_ACCESS_DENIED",
            details={"folder_id": exc.folder_id}
        ).dict()
    )
```

---

## Future Enhancements

### Phase 2 (Post-MVP)

| Feature | Description |
|---------|-------------|
| **Incremental sync** | Use Drive webhook/push notifications for real-time updates instead of manual re-sync |
| **Collaborative folders** | Multiple users can chat with the same shared folder |
| **Export chat** | Download conversation as PDF/markdown |
| **Advanced filtering** | Search within specific date ranges, file types, subfolders |
| **Python code execution** | Agent can write and execute Python for complex data analysis (sandboxed) |

### Phase 3 (Scale)

| Feature | Description |
|---------|-------------|
| **Multi-folder projects** | Combine multiple Drive folders into one searchable corpus |
| **Slack/Teams integration** | Chat with folders directly from messaging apps |
| **Scheduled syncs** | Auto-sync folders on a schedule |
| **Usage analytics** | Track which files are most referenced, common questions |
| **Fine-tuned embeddings** | Domain-specific embedding model for better retrieval |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| **Sync completion rate** | >95% of folders sync successfully |
| **Query response time** | <8s median for typical questions |
| **Agent iteration count** | Median 4, p95 under 10 |
| **Citation accuracy** | >90% of citations link to relevant source material |
| **File type coverage** | Support for 90% of common file types in Drive |
| **Graceful failure rate** | >95% of unanswerable questions use `report_inability` instead of hallucinating |

---

## Timeline Estimate (3-Day Build)

| Day | Focus | Deliverables |
|-----|-------|--------------|
| **Day 1** | Foundation | Auth flow working, project CRUD, database models, basic UI shell |
| **Day 2** | Ingestion | Temporal worker, file extraction, chunking, indexing to Azure AI Search |
| **Day 3** | Agent + Polish | Agent loop with all 14 tools, chat UI with citations, deployment, video recording |

---

## Appendix: Key Dependencies

### Backend (requirements.txt)

```
fastapi==0.109.0
uvicorn==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0
sqlalchemy==2.0.25
alembic==1.13.1
asyncpg==0.29.0
httpx==0.26.0
python-multipart==0.0.6
python-jose==3.3.0
cryptography==41.0.7
google-auth==2.27.0
google-auth-oauthlib==1.2.0
google-api-python-client==2.116.0
azure-search-documents==11.4.0
openai==1.10.0
anthropic==0.18.0
temporalio==1.4.0
python-docx==1.1.0
openpyxl==3.1.2
pypdf==3.17.4
pdf2image==1.17.0
pytesseract==0.3.10
pillow==10.2.0
tiktoken==0.5.2
```

### Frontend (package.json dependencies)

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.21.0",
    "@tanstack/react-query": "^5.17.0",
    "axios": "^1.6.0",
    "zustand": "^4.4.0",
    "tailwindcss": "^3.4.0",
    "lucide-react": "^0.300.0"
  },
  "devDependencies": {
    "typescript": "^5.3.0",
    "vite": "^5.0.0",
    "@types/react": "^18.2.0"
  }
}
```