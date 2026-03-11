# Google Drive Agent — Developer Specification

> **Version:** 1.0
> **Date:** March 10, 2026
> **Approach:** Direct Google Drive API v3 (no MCP)
> **Stack:** React (web) or Expo (mobile) · Node.js/Python backend · LLM with tool-calling

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Authentication — OAuth2 with PKCE](#3-authentication--oauth2-with-pkce)
4. [Google Drive API v3 — Core Endpoints](#4-google-drive-api-v3--core-endpoints)
5. [Search Query Language — Complete Reference](#5-search-query-language--complete-reference)
6. [File Download & Export](#6-file-download--export)
7. [Google Workspace MIME Types](#7-google-workspace-mime-types)
8. [Document Parsing Pipeline](#8-document-parsing-pipeline)
9. [Agent Tool Definitions](#9-agent-tool-definitions)
10. [Agentic Search Flow](#10-agentic-search-flow)
11. [Chunking & Citation Metadata](#11-chunking--citation-metadata)
12. [Rate Limits & Error Handling](#12-rate-limits--error-handling)
13. [API Client Setup — Node.js & Python](#13-api-client-setup--nodejs--python)
14. [Folder Link Parsing](#14-folder-link-parsing)
15. [Recursive Folder Traversal](#15-recursive-folder-traversal)
16. [End-to-End Example Flow](#16-end-to-end-example-flow)

---

## 1. Project Overview

### What We're Building

An AI agent that connects to a user's Google Drive, accepts a folder link, and answers natural language questions about the files inside that folder. The agent must handle PDFs, DOCX, XLSX, Google Docs, Google Sheets, TXT, and other common formats. It must provide citations back to specific files, pages, and sections.

### Why Direct API (Not MCP)

We chose to build directly on the Google Drive API v3 instead of using MCP (Model Context Protocol) servers for these reasons:

- **Binary file support:** MCP servers cannot parse PDFs, DOCX, or XLSX — they fail on UTF-8 decoding. We need full control over the parsing pipeline.
- **Targeted search:** Finding a specific paragraph in a 100-page PDF requires download → parse → chunk → search-within-file. No MCP server provides this.
- **Folder scale:** MCP servers hit context window limits at ~30 documents. We need to handle folders with hundreds of files.
- **Custom OAuth:** MCP auth is designed for desktop apps (Claude Desktop, Cursor). We need standard OAuth2 PKCE for a React/Expo web app.
- **Production stability:** The official Anthropic MCP server for Google Drive was archived in May 2025. Community forks are maintained by individuals. Google Drive API v3 is battle-tested with official SDKs.

### User Flow

1. User opens the web/mobile app
2. User authenticates their Google account (OAuth2)
3. User pastes a Google Drive folder link
4. Agent crawls the folder, parses all files
5. User asks natural language questions
6. Agent searches across all parsed files, answers with citations

---

## 2. Architecture

```
┌─────────────────────────────────────────────────┐
│                  React / Expo UI                 │
│  ┌───────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Google     │  │ Folder   │  │ Chat         │  │
│  │ Login Btn  │  │ Link     │  │ Interface    │  │
│  └─────┬─────┘  └────┬─────┘  └──────┬───────┘  │
└────────┼──────────────┼───────────────┼──────────┘
         │              │               │
         ▼              ▼               ▼
┌─────────────────────────────────────────────────┐
│                 Backend API Server               │
│  (Node.js/Express or Python/FastAPI)             │
│                                                  │
│  ┌──────────────┐  ┌─────────────────────────┐   │
│  │ Auth Service  │  │ Agent Orchestrator      │   │
│  │ - OAuth2 PKCE │  │ - LLM tool-calling loop │   │
│  │ - Token store │  │ - Conversation state    │   │
│  │ - Refresh     │  │ - Tool dispatch         │   │
│  └──────┬───────┘  └──────────┬──────────────┘   │
│         │                     │                   │
│  ┌──────┴───────┐  ┌─────────┴────────────────┐  │
│  │ Drive API    │  │ Document Parser          │  │
│  │ Wrapper      │  │ - PDF  → pdfplumber      │  │
│  │ - search()   │  │ - DOCX → python-docx     │  │
│  │ - list()     │  │ - XLSX → openpyxl        │  │
│  │ - download() │  │ - GDocs → export as text │  │
│  │ - export()   │  │ - MarkItDown (unified)   │  │
│  └──────┬───────┘  └──────────────────────────┘  │
│         │                                         │
└─────────┼─────────────────────────────────────────┘
          │
          ▼
┌─────────────────────┐
│  Google Drive API   │
│  v3 (REST)          │
│  googleapis.com     │
└─────────────────────┘
```

---

## 3. Authentication — OAuth2 with PKCE

### Overview

We use the **Authorization Code flow with PKCE** (Proof Key for Code Exchange). PKCE is mandatory for single-page applications because client secrets cannot be stored securely in frontend code.

### Required Google Cloud Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project
3. Enable the **Google Drive API**
4. Create OAuth 2.0 credentials (Web application type)
5. Set authorized redirect URIs (e.g., `http://localhost:3000/callback`)
6. Note your `client_id` and `client_secret`

### OAuth2 Scopes

For a read-only agent, use:

```
https://www.googleapis.com/auth/drive.readonly
```

All available Drive scopes:

| Scope | URI | Description |
|-------|-----|-------------|
| Full access | `https://www.googleapis.com/auth/drive` | Read, edit, create, delete all files |
| Read only | `https://www.googleapis.com/auth/drive.readonly` | View all files (recommended for agent) |
| File-level | `https://www.googleapis.com/auth/drive.file` | Only files opened/created by the app |
| Metadata only | `https://www.googleapis.com/auth/drive.metadata.readonly` | View file metadata, not content |

### Step 1: Generate PKCE Code Verifier and Challenge

```javascript
// Generate a cryptographically random code verifier
function generateCodeVerifier() {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return base64URLEncode(array);
}

// Create the SHA-256 code challenge
async function generateCodeChallenge(verifier) {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return base64URLEncode(new Uint8Array(digest));
}

function base64URLEncode(buffer) {
  return btoa(String.fromCharCode(...buffer))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}
```

### Step 2: Redirect User to Google Authorization

```
GET https://accounts.google.com/o/oauth2/v2/auth
```

**Parameters:**

| Parameter | Value |
|-----------|-------|
| `client_id` | Your OAuth 2.0 client ID |
| `redirect_uri` | `http://localhost:3000/callback` |
| `response_type` | `code` |
| `scope` | `https://www.googleapis.com/auth/drive.readonly` |
| `access_type` | `offline` (required for refresh tokens) |
| `code_challenge` | The SHA-256 challenge from Step 1 |
| `code_challenge_method` | `S256` |
| `prompt` | `consent` (force consent screen to get refresh token) |

**Full URL example:**

```
https://accounts.google.com/o/oauth2/v2/auth?
  client_id=YOUR_CLIENT_ID&
  redirect_uri=http://localhost:3000/callback&
  response_type=code&
  scope=https://www.googleapis.com/auth/drive.readonly&
  access_type=offline&
  code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&
  code_challenge_method=S256&
  prompt=consent
```

### Step 3: Exchange Authorization Code for Tokens

After the user approves, Google redirects to your `redirect_uri` with a `code` parameter.

```
POST https://oauth2.googleapis.com/token
Content-Type: application/x-www-form-urlencoded
```

**Request body:**

```
code=4/0AX4XfWh...
&client_id=YOUR_CLIENT_ID
&client_secret=YOUR_CLIENT_SECRET
&redirect_uri=http://localhost:3000/callback
&grant_type=authorization_code
&code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
```

**Response:**

```json
{
  "access_token": "ya29.a0AfH6SMBx...",
  "expires_in": 3599,
  "refresh_token": "1//0gqb...",
  "scope": "https://www.googleapis.com/auth/drive.readonly",
  "token_type": "Bearer"
}
```

**Important:** Store `refresh_token` securely in your backend database. It does not expire unless revoked. Access tokens expire in ~1 hour.

### Step 4: Refresh Access Token

```
POST https://oauth2.googleapis.com/token
Content-Type: application/x-www-form-urlencoded
```

**Request body:**

```
client_id=YOUR_CLIENT_ID
&client_secret=YOUR_CLIENT_SECRET
&refresh_token=1//0gqb...
&grant_type=refresh_token
```

**Response:**

```json
{
  "access_token": "ya29.a0NEW_TOKEN...",
  "expires_in": 3599,
  "scope": "https://www.googleapis.com/auth/drive.readonly",
  "token_type": "Bearer"
}
```

---

## 4. Google Drive API v3 — Core Endpoints

### Base URL

```
https://www.googleapis.com/drive/v3
```

All requests require the `Authorization: Bearer {ACCESS_TOKEN}` header.

### 4.1 files.list — Search and List Files

```
GET https://www.googleapis.com/drive/v3/files
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | — | Search query (see Section 5 for full syntax) |
| `fields` | string | minimal | Fields to include in response |
| `pageSize` | integer | 100 | Results per page (1–1000) |
| `pageToken` | string | — | Continuation token from previous response |
| `corpora` | string | `user` | Search scope: `user`, `domain`, `drive`, `allDrives` |
| `orderBy` | string | — | Sort order (see below) |
| `spaces` | string | `drive` | Spaces to search: `drive`, `appDataFolder` |
| `supportsAllDrives` | boolean | false | Include shared drive results |
| `includeItemsFromAllDrives` | boolean | false | Include shared drive items |

**orderBy values:** `createdTime`, `folder`, `modifiedByMeTime`, `modifiedTime`, `name`, `name_natural`, `quotaBytesUsed`, `recency`, `sharedWithMeTime`, `starred`, `viewedByMeTime`. Append ` desc` for descending.

**Example request — search for PDFs containing "quarterly report":**

```bash
curl -X GET \
  "https://www.googleapis.com/drive/v3/files?q=fullText+contains+'quarterly+report'+and+mimeType='application/pdf'&pageSize=20&fields=nextPageToken,files(id,name,mimeType,modifiedTime,size,webViewLink,parents)&orderBy=modifiedTime+desc" \
  -H "Authorization: Bearer ya29.a0AfH6SMBx..."
```

**Response:**

```json
{
  "kind": "drive#fileList",
  "nextPageToken": "~!!~AI9...==",
  "incompleteSearch": false,
  "files": [
    {
      "id": "1BwwA4sRtkm3VQZLbiJcaIIQyS4bP3Ha9W",
      "name": "Q4 2025 Quarterly Report.pdf",
      "mimeType": "application/pdf",
      "modifiedTime": "2026-01-15T10:30:00.000Z",
      "size": "2549632",
      "webViewLink": "https://drive.google.com/file/d/1BwwA4sRtkm3VQZLbiJcaIIQyS4bP3Ha9W/view",
      "parents": ["1FolderABC123"]
    },
    {
      "id": "1CxxB5tUukn4WRaMdjKdRuT5qC4Hb0Ib0X",
      "name": "Quarterly Report Summary.pdf",
      "mimeType": "application/pdf",
      "modifiedTime": "2025-10-20T08:15:00.000Z",
      "size": "1048576",
      "webViewLink": "https://drive.google.com/file/d/1CxxB5tUukn4WRaMdjKdRuT5qC4Hb0Ib0X/view",
      "parents": ["1FolderABC123"]
    }
  ]
}
```

### 4.2 files.get — Get File Metadata

```
GET https://www.googleapis.com/drive/v3/files/{fileId}
```

**Example request:**

```bash
curl -X GET \
  "https://www.googleapis.com/drive/v3/files/1BwwA4sRtkm3VQZLbiJcaIIQyS4bP3Ha9W?fields=id,name,mimeType,size,modifiedTime,webViewLink,parents,owners" \
  -H "Authorization: Bearer ya29.a0AfH6SMBx..."
```

**Response — Full File Resource:**

```json
{
  "kind": "drive#file",
  "id": "1BwwA4sRtkm3VQZLbiJcaIIQyS4bP3Ha9W",
  "name": "Q4 2025 Quarterly Report.pdf",
  "mimeType": "application/pdf",
  "size": "2549632",
  "createdTime": "2025-09-01T09:00:00.000Z",
  "modifiedTime": "2026-01-15T10:30:00.000Z",
  "webViewLink": "https://drive.google.com/file/d/1BwwA4sRtkm3VQZLbiJcaIIQyS4bP3Ha9W/view",
  "parents": ["1FolderABC123"],
  "owners": [
    {
      "displayName": "Jane Smith",
      "emailAddress": "jane@company.com"
    }
  ],
  "trashed": false,
  "starred": false,
  "shared": true
}
```

### 4.3 files.get (alt=media) — Download Binary File Content

```
GET https://www.googleapis.com/drive/v3/files/{fileId}?alt=media
```

This downloads the actual file bytes. Use for PDFs, DOCX, XLSX, images, and any non-Google-Workspace file.

**Example request:**

```bash
curl -X GET \
  "https://www.googleapis.com/drive/v3/files/1BwwA4sRtkm3VQZLbiJcaIIQyS4bP3Ha9W?alt=media" \
  -H "Authorization: Bearer ya29.a0AfH6SMBx..." \
  --output downloaded_file.pdf
```

**Response:** Raw file bytes (binary content). No JSON wrapper.

**Important:** This does NOT work for Google Workspace files (Google Docs, Sheets, Slides). Use `files.export` for those — see next section.

### 4.4 files.export — Export Google Workspace Files

```
GET https://www.googleapis.com/drive/v3/files/{fileId}/export?mimeType={exportMimeType}
```

Use this for native Google Workspace files (Docs, Sheets, Slides). Export limit: **10 MB**.

**Example — export Google Doc as plain text:**

```bash
curl -X GET \
  "https://www.googleapis.com/drive/v3/files/1DocID123/export?mimeType=text/plain" \
  -H "Authorization: Bearer ya29.a0AfH6SMBx..."
```

**Response:** Raw text content of the document.

**Example — export Google Sheet as CSV:**

```bash
curl -X GET \
  "https://www.googleapis.com/drive/v3/files/1SheetID456/export?mimeType=text/csv" \
  -H "Authorization: Bearer ya29.a0AfH6SMBx..."
```

### Export MIME Type Reference

**From Google Docs:**

| Export Format | MIME Type |
|---------------|-----------|
| Plain text | `text/plain` |
| HTML | `text/html` |
| PDF | `application/pdf` |
| DOCX | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| RTF | `application/rtf` |
| ODT | `application/vnd.oasis.opendocument.text` |
| EPUB | `application/epub+zip` |

**From Google Sheets:**

| Export Format | MIME Type |
|---------------|-----------|
| XLSX | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| CSV | `text/csv` |
| TSV | `text/tab-separated-values` |
| PDF | `application/pdf` |
| ODS | `application/vnd.oasis.opendocument.spreadsheet` |

**From Google Slides:**

| Export Format | MIME Type |
|---------------|-----------|
| PPTX | `application/vnd.openxmlformats-officedocument.presentationml.presentation` |
| PDF | `application/pdf` |
| Plain text | `text/plain` |
| PNG | `image/png` |
| JPEG | `image/jpeg` |

---

## 5. Search Query Language — Complete Reference

The `q` parameter in `files.list` uses a structured query language. This is the primary way your agent finds relevant files.

### All Searchable Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `name` | string | File name | `name contains 'report'` |
| `fullText` | string | File content + name + description | `fullText contains 'revenue'` |
| `mimeType` | string | MIME type | `mimeType = 'application/pdf'` |
| `modifiedTime` | datetime | Last modified | `modifiedTime > '2026-01-01T00:00:00'` |
| `createdTime` | datetime | Created date | `createdTime > '2025-06-01T00:00:00'` |
| `viewedByMeTime` | datetime | Last viewed by me | `viewedByMeTime > '2026-03-01T00:00:00'` |
| `trashed` | boolean | In trash | `trashed = false` |
| `starred` | boolean | Starred | `starred = true` |
| `parents` | collection | Parent folder ID | `'1FolderABC' in parents` |
| `owners` | collection | Owner email | `'jane@co.com' in owners` |
| `writers` | collection | Writer email | `'jane@co.com' in writers` |
| `readers` | collection | Reader email | `'jane@co.com' in readers` |
| `sharedWithMe` | boolean | Shared with current user | `sharedWithMe = true` |
| `visibility` | string | `limited`, `shared`, `public` | `visibility = 'limited'` |
| `properties` | key-value | Custom file properties | `properties has { key='status' and value='final' }` |
| `appProperties` | key-value | App-specific properties | `appProperties has { key='indexed' and value='true' }` |

### All Operators

| Operator | Usage | Example |
|----------|-------|---------|
| `contains` | Substring/token match | `name contains 'budget'` |
| `=` | Exact match | `mimeType = 'application/pdf'` |
| `!=` | Not equal | `mimeType != 'application/vnd.google-apps.folder'` |
| `<` | Less than | `modifiedTime < '2026-01-01T00:00:00'` |
| `<=` | Less or equal | `size <= 10485760` |
| `>` | Greater than | `modifiedTime > '2025-01-01T00:00:00'` |
| `>=` | Greater or equal | `size >= 1024` |
| `in` | Member of collection | `'folderId123' in parents` |
| `and` | Logical AND | `name contains 'Q4' and mimeType = 'application/pdf'` |
| `or` | Logical OR | `name contains 'draft' or name contains 'final'` |
| `not` | Logical NOT | `not name contains 'archive'` |
| `has` | Property matching | `properties has { key='dept' and value='finance' }` |

### fullText Search — Key Behavior

The `fullText contains` operator is the primary way to search inside file contents. Important details:

- **Token-based matching:** Searches for complete word tokens, not substrings. `fullText contains 'Hello'` will NOT match "HelloWorld".
- **Indexing:** Google automatically indexes the contents of uploaded PDFs, DOCX, XLSX, TXT, HTML, and all Google Workspace files.
- **Phrase search:** Use double quotes inside single quotes for exact phrases: `fullText contains '"quarterly revenue"'`
- **File-level results:** Returns files that contain the search term, NOT the specific paragraph or page. Your agent must download and search within the file for targeted extraction.
- **Limitations:** Does not support wildcards, regex, or fuzzy matching.

### Query Examples for Common Agent Operations

```
# Find all files in a specific folder
'1FolderABC123' in parents and trashed = false

# Find PDFs containing specific text
fullText contains 'project timeline' and mimeType = 'application/pdf'

# Find recently modified documents
modifiedTime > '2026-02-01T00:00:00' and mimeType != 'application/vnd.google-apps.folder'

# Find files by name pattern in a folder
'1FolderABC123' in parents and name contains 'report' and trashed = false

# Find Google Docs OR PDFs containing a term
fullText contains 'budget' and (mimeType = 'application/vnd.google-apps.document' or mimeType = 'application/pdf')

# Find all non-folder items in a folder
'1FolderABC123' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false

# Find all subfolders of a folder
'1FolderABC123' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false

# Find files modified in the last 7 days
modifiedTime > '2026-03-03T00:00:00' and trashed = false
```

### Special Characters

- Escape single quotes: `name contains 'O\'Reilly'`
- Escape backslashes: `name contains 'C:\\\\Users'`
- Underscores are treated as spaces in search tokens

---

## 6. File Download & Export

### Decision Tree: How to Get File Content

```
Is it a Google Workspace file?
  (mimeType starts with "application/vnd.google-apps.")
  │
  ├─ YES → Use files.export()
  │         Export Google Docs as text/plain
  │         Export Google Sheets as text/csv
  │         Export Google Slides as text/plain
  │
  └─ NO → Use files.get(alt=media)
           Download raw bytes
           Then parse locally based on mimeType:
             application/pdf           → pdfplumber / PyMuPDF
             application/vnd...docx    → python-docx / mammoth
             application/vnd...xlsx    → openpyxl / SheetJS
             text/plain                → read directly
             text/csv                  → read directly
```

### Node.js — Download Binary File

```javascript
const { google } = require('googleapis');

async function downloadFile(auth, fileId) {
  const drive = google.drive({ version: 'v3', auth });

  const response = await drive.files.get(
    { fileId: fileId, alt: 'media' },
    { responseType: 'arraybuffer' }
  );

  return Buffer.from(response.data);
}
```

### Node.js — Export Google Doc as Text

```javascript
async function exportGoogleDoc(auth, fileId) {
  const drive = google.drive({ version: 'v3', auth });

  const response = await drive.files.export({
    fileId: fileId,
    mimeType: 'text/plain'
  });

  return response.data; // plain text string
}
```

### Python — Download Binary File

```python
from googleapiclient.http import MediaIoBaseDownload
import io

def download_file(service, file_id):
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    buffer.seek(0)
    return buffer
```

### Python — Export Google Doc as Text

```python
def export_google_doc(service, file_id):
    response = service.files().export(
        fileId=file_id,
        mimeType='text/plain'
    ).execute()

    return response.decode('utf-8')
```

---

## 7. Google Workspace MIME Types

Your agent needs to identify file types to decide how to download and parse them. Here's the complete mapping:

### Google Workspace Types (use files.export)

| Type | MIME Type |
|------|-----------|
| Google Docs | `application/vnd.google-apps.document` |
| Google Sheets | `application/vnd.google-apps.spreadsheet` |
| Google Slides | `application/vnd.google-apps.presentation` |
| Google Drawing | `application/vnd.google-apps.drawing` |
| Google Forms | `application/vnd.google-apps.form` |
| Google Sites | `application/vnd.google-apps.site` |
| Google Apps Script | `application/vnd.google-apps.script` |
| Google Folder | `application/vnd.google-apps.folder` |
| Google Shortcut | `application/vnd.google-apps.shortcut` |

### Common Uploaded File Types (use files.get with alt=media)

| Type | MIME Type |
|------|-----------|
| PDF | `application/pdf` |
| Word (DOCX) | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| Excel (XLSX) | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| PowerPoint (PPTX) | `application/vnd.openxmlformats-officedocument.presentationml.presentation` |
| Plain Text | `text/plain` |
| CSV | `text/csv` |
| HTML | `text/html` |
| JSON | `application/json` |
| PNG | `image/png` |
| JPEG | `image/jpeg` |

---

## 8. Document Parsing Pipeline

After downloading a file, you need to extract its text content. Use different libraries based on file type.

### Recommended Libraries

| File Type | Python Library | Node.js Library | Install |
|-----------|---------------|-----------------|---------|
| PDF | `pdfplumber` | `pdf-parse` | `pip install pdfplumber` / `npm install pdf-parse` |
| DOCX | `python-docx` | `mammoth` | `pip install python-docx` / `npm install mammoth` |
| XLSX | `openpyxl` | `xlsx` (SheetJS) | `pip install openpyxl` / `npm install xlsx` |
| All formats | `markitdown` | — | `pip install 'markitdown[all]'` |
| PDF (LLM-optimized) | `pymupdf4llm` | — | `pip install pymupdf4llm` |

### Python: Parse PDF with Page Numbers

```python
import pdfplumber

def parse_pdf(file_buffer, file_id, file_name):
    """Parse a PDF and return chunks with page numbers."""
    chunks = []

    with pdfplumber.open(file_buffer) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            chunks.append({
                "file_id": file_id,
                "file_name": file_name,
                "page_number": page.page_number,
                "text": text,
                "tables": page.extract_tables()  # also extract any tables
            })

    return chunks
```

### Python: Parse DOCX with Paragraph Tracking

```python
from docx import Document

def parse_docx(file_buffer, file_id, file_name):
    """Parse a DOCX and return chunks with paragraph indices."""
    doc = Document(file_buffer)
    chunks = []

    current_section = "Document Start"

    for i, paragraph in enumerate(doc.paragraphs):
        text = paragraph.text.strip()
        if not text:
            continue

        # Track section headings
        if paragraph.style.name.startswith('Heading'):
            current_section = text

        chunks.append({
            "file_id": file_id,
            "file_name": file_name,
            "paragraph_index": i,
            "section": current_section,
            "style": paragraph.style.name,
            "text": text
        })

    return chunks
```

### Python: Parse XLSX with Cell References

```python
from openpyxl import load_workbook

def parse_xlsx(file_buffer, file_id, file_name):
    """Parse an XLSX and return sheet data with cell references."""
    wb = load_workbook(file_buffer, data_only=True)
    sheets = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = []

        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=False):
            row_data = []
            for cell in row:
                if cell.value is not None:
                    row_data.append({
                        "cell_ref": cell.coordinate,  # e.g. "A1"
                        "value": str(cell.value)
                    })
            if row_data:
                rows.append(row_data)

        sheets.append({
            "file_id": file_id,
            "file_name": file_name,
            "sheet_name": sheet_name,
            "rows": rows
        })

    return sheets
```

### Python: Unified Parser with MarkItDown

```python
from markitdown import MarkItDown

def parse_any_file(file_path):
    """Parse any supported file type to markdown."""
    md = MarkItDown()
    result = md.convert(file_path)
    return result.text_content

# Supports: PDF, DOCX, PPTX, XLSX, HTML, TXT, images, audio, ZIP
```

### Node.js: Parse PDF

```javascript
const pdfParse = require('pdf-parse');

async function parsePDF(buffer, fileId, fileName) {
  const data = await pdfParse(buffer);

  return {
    file_id: fileId,
    file_name: fileName,
    text: data.text,
    num_pages: data.numpages,
    // Note: pdf-parse does not provide per-page text natively.
    // For per-page extraction, consider using pdf.js or pdfplumber via Python.
  };
}
```

### Node.js: Parse DOCX

```javascript
const mammoth = require('mammoth');

async function parseDOCX(buffer, fileId, fileName) {
  const result = await mammoth.extractRawText({ buffer: buffer });

  return {
    file_id: fileId,
    file_name: fileName,
    text: result.value,
    warnings: result.messages
  };
}
```

### Node.js: Parse XLSX

```javascript
const XLSX = require('xlsx');

function parseXLSX(buffer, fileId, fileName) {
  const workbook = XLSX.read(buffer, { type: 'buffer' });
  const sheets = [];

  for (const sheetName of workbook.SheetNames) {
    const worksheet = workbook.Sheets[sheetName];
    const jsonData = XLSX.utils.sheet_to_json(worksheet, { header: 1 });

    sheets.push({
      file_id: fileId,
      file_name: fileName,
      sheet_name: sheetName,
      data: jsonData
    });
  }

  return sheets;
}
```

---

## 9. Agent Tool Definitions

These are the tools you expose to the LLM. The agent decides when and how to call them.

### Tool 1: search_drive

Searches Google Drive using the `files.list` API with the `q` parameter.

**Anthropic (Claude) format:**

```json
{
  "name": "search_drive",
  "description": "Search for files in the user's Google Drive folder. Use this to find files relevant to the user's question. Returns file metadata (id, name, type, modification date) but NOT file contents. You must use get_file_content to read a file after finding it.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Search keywords. This will be used in a fullText contains query against Google Drive. Use specific terms the user is asking about."
      },
      "folder_id": {
        "type": "string",
        "description": "Google Drive folder ID to scope the search to. Use the root folder ID from the user's pasted link."
      },
      "file_types": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Optional MIME types to filter by. E.g. ['application/pdf', 'application/vnd.google-apps.document']"
      },
      "max_results": {
        "type": "integer",
        "description": "Maximum number of results. Default 20.",
        "default": 20
      }
    },
    "required": ["query", "folder_id"]
  }
}
```

### Tool 2: list_folder

Lists all files and subfolders in a specific folder.

```json
{
  "name": "list_folder",
  "description": "List all files and subfolders in a Google Drive folder. Use this to explore folder structure when you need to understand how files are organized, or when fullText search doesn't find what you need.",
  "input_schema": {
    "type": "object",
    "properties": {
      "folder_id": {
        "type": "string",
        "description": "The Google Drive folder ID to list contents of."
      },
      "include_subfolders": {
        "type": "boolean",
        "description": "If true, recursively list all files in subfolders too. Use with caution on large folder trees.",
        "default": false
      }
    },
    "required": ["folder_id"]
  }
}
```

### Tool 3: get_file_content

Downloads and parses a specific file, returning its text content.

```json
{
  "name": "get_file_content",
  "description": "Download and parse a specific file from Google Drive. Returns the text content of the file. For PDFs, includes page numbers. For DOCX, includes section headings. For XLSX, includes sheet names and cell data. Use this after search_drive finds relevant files.",
  "input_schema": {
    "type": "object",
    "properties": {
      "file_id": {
        "type": "string",
        "description": "The Google Drive file ID to download and parse."
      },
      "page_range": {
        "type": "string",
        "description": "Optional. For PDFs only. Specify pages to extract, e.g. '1-5' or '3,7,12'. Omit to extract all pages."
      }
    },
    "required": ["file_id"]
  }
}
```

### Tool 4: search_within_file

Searches for specific text within an already-parsed file. This is the key tool for finding specific paragraphs.

```json
{
  "name": "search_within_file",
  "description": "Search for specific text or keywords within a file's content. Use this when you need to find a specific paragraph, sentence, or data point within a large document. Returns matching passages with surrounding context and their location (page number, section, paragraph index).",
  "input_schema": {
    "type": "object",
    "properties": {
      "file_id": {
        "type": "string",
        "description": "The Google Drive file ID to search within."
      },
      "search_terms": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Terms to search for within the file. Multiple terms are OR'd together."
      },
      "context_chars": {
        "type": "integer",
        "description": "Number of characters of context to include around each match. Default 500.",
        "default": 500
      }
    },
    "required": ["file_id", "search_terms"]
  }
}
```

### Tool 5: get_folder_summary

Returns a high-level summary of what's in the folder (counts, file types, recent activity).

```json
{
  "name": "get_folder_summary",
  "description": "Get a summary overview of a Google Drive folder: total file count, file types breakdown, most recently modified files, subfolder structure. Use this at the start of a conversation to understand what the user's folder contains.",
  "input_schema": {
    "type": "object",
    "properties": {
      "folder_id": {
        "type": "string",
        "description": "The Google Drive folder ID to summarize."
      }
    },
    "required": ["folder_id"]
  }
}
```

---

## 10. Agentic Search Flow

This is how the agent should reason about finding information. The LLM orchestrates these tools in a loop.

### Flow Diagram

```
User asks: "What was the projected revenue for Q3 mentioned in the financial docs?"
    │
    ▼
Agent thinks: "I need to search for financial documents mentioning revenue and Q3"
    │
    ▼
Tool call: search_drive(query="projected revenue Q3", folder_id="root_folder")
    │
    ▼
Results: 3 files found
  - "FY2025 Financial Plan.pdf" (42 pages)
  - "Q3 Revenue Forecast.xlsx"
  - "Board Meeting Notes - Q3.docx"
    │
    ▼
Agent thinks: "The PDF and XLSX look most relevant. Let me check the PDF first."
    │
    ▼
Tool call: search_within_file(file_id="pdf_id", search_terms=["projected revenue", "Q3 forecast", "revenue projection"])
    │
    ▼
Results: 2 matches found
  - Page 12, Section "Revenue Projections": "...projected Q3 revenue of $4.2M based on..."
  - Page 28, Section "Quarterly Breakdown": "...Q3 target adjusted to $4.5M following..."
    │
    ▼
Agent thinks: "Found it. Let me also check the XLSX for exact numbers."
    │
    ▼
Tool call: get_file_content(file_id="xlsx_id")
    │
    ▼
Results: Sheet "Q3 Forecast" has revenue projections by month
    │
    ▼
Agent responds to user with answer + citations:
  "The projected Q3 revenue was $4.2M (FY2025 Financial Plan.pdf, p. 12),
   later adjusted to $4.5M (FY2025 Financial Plan.pdf, p. 28).
   The monthly breakdown is in Q3 Revenue Forecast.xlsx, Sheet 'Q3 Forecast'."
```

### Retry Strategy

If `search_drive` returns no results:

1. **Broaden the query** — remove specific terms, try synonyms
2. **List the folder** — use `list_folder` to see all files, then pick promising ones by name
3. **Explore subfolders** — use `list_folder(include_subfolders=true)` to find nested files
4. **Read file by file** — for small folders, `get_file_content` on each file and search within

---

## 11. Chunking & Citation Metadata

When files are large (100+ pages), you need to chunk them into smaller pieces for the LLM context window. Each chunk must carry citation metadata.

### Chunk Object Schema

```json
{
  "chunk_id": "1BwwA4s_chunk_0012",
  "file_id": "1BwwA4sRtkm3VQZLbiJcaIIQyS4bP3Ha9W",
  "file_name": "FY2025 Financial Plan.pdf",
  "file_type": "application/pdf",
  "page_number": 12,
  "section": "Revenue Projections",
  "paragraph_index": 45,
  "chunk_index": 12,
  "text": "Based on current growth trends and market analysis, the projected Q3 revenue is $4.2M, representing a 15% year-over-year increase...",
  "chunk_length_chars": 487,
  "web_view_link": "https://drive.google.com/file/d/1BwwA4sRtkm3VQZLbiJcaIIQyS4bP3Ha9W/view",
  "citation": "FY2025 Financial Plan.pdf, p. 12, Section: Revenue Projections"
}
```

### Chunking Parameters

| Parameter | Recommended Value | Notes |
|-----------|-------------------|-------|
| Chunk size | 400–512 tokens (~300 words) | Balance between context and specificity |
| Overlap | 50–100 tokens | Prevents splitting mid-sentence at chunk boundaries |
| Splitting strategy | Paragraph boundaries first | Preserves logical flow |

### Python: Chunking Implementation

```python
def chunk_text(text, file_id, file_name, page_number=None,
               section=None, chunk_size=1500, overlap=200):
    """
    Split text into overlapping chunks with metadata.
    chunk_size and overlap are in characters.
    """
    chunks = []
    paragraphs = text.split('\n\n')

    current_chunk = ""
    chunk_index = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current_chunk) + len(para) > chunk_size and current_chunk:
            # Save current chunk
            chunks.append({
                "chunk_id": f"{file_id}_chunk_{chunk_index:04d}",
                "file_id": file_id,
                "file_name": file_name,
                "page_number": page_number,
                "section": section,
                "chunk_index": chunk_index,
                "text": current_chunk.strip(),
                "chunk_length_chars": len(current_chunk.strip()),
                "citation": _format_citation(file_name, page_number, section)
            })

            # Start new chunk with overlap from end of previous
            overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
            current_chunk = overlap_text + "\n\n" + para
            chunk_index += 1
        else:
            current_chunk += "\n\n" + para if current_chunk else para

    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append({
            "chunk_id": f"{file_id}_chunk_{chunk_index:04d}",
            "file_id": file_id,
            "file_name": file_name,
            "page_number": page_number,
            "section": section,
            "chunk_index": chunk_index,
            "text": current_chunk.strip(),
            "chunk_length_chars": len(current_chunk.strip()),
            "citation": _format_citation(file_name, page_number, section)
        })

    return chunks


def _format_citation(file_name, page_number, section):
    parts = [file_name]
    if page_number:
        parts.append(f"p. {page_number}")
    if section:
        parts.append(f"Section: {section}")
    return ", ".join(parts)
```

---

## 12. Rate Limits & Error Handling

### Google Drive API Quotas

| Limit | Value |
|-------|-------|
| Per user | 20,000 requests per 100 seconds |
| Per project | 20,000 requests per 100 seconds |
| Write operations | 3 requests per second sustained |
| Batch requests | Max 100 per batch call |
| Export file size | 10 MB max |
| Folder children | 500,000 items max |
| Folder nesting | 100 levels max |

### Error Codes

| HTTP Code | Meaning | Action |
|-----------|---------|--------|
| 401 | Token expired | Refresh the access token, retry |
| 403 | Rate limit exceeded | Exponential backoff, retry |
| 404 | File not found | File may have been deleted or user lacks access |
| 429 | Too many requests | Exponential backoff, retry |
| 500 | Server error | Retry with backoff |

### Exponential Backoff Implementation

```python
import time
import random

def api_call_with_retry(func, max_retries=5):
    """Execute an API call with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise

            status_code = getattr(e, 'status_code', None) or getattr(e, 'resp', {}).get('status')

            if status_code in (429, 403, 500, 503):
                wait = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(wait)
            elif status_code == 401:
                # Refresh token and retry
                refresh_access_token()
            else:
                raise
```

```javascript
async function apiCallWithRetry(fn, maxRetries = 5) {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      if (attempt === maxRetries - 1) throw error;

      const status = error.code || error.response?.status;

      if ([429, 403, 500, 503].includes(status)) {
        const wait = Math.pow(2, attempt) * 1000 + Math.random() * 1000;
        await new Promise(resolve => setTimeout(resolve, wait));
      } else if (status === 401) {
        await refreshAccessToken();
      } else {
        throw error;
      }
    }
  }
}
```

---

## 13. API Client Setup — Node.js & Python

### Node.js Setup

```bash
npm install googleapis google-auth-library
```

```javascript
const { google } = require('googleapis');
const { OAuth2Client } = require('google-auth-library');

// Initialize OAuth2 client
const oauth2Client = new OAuth2Client(
  process.env.GOOGLE_CLIENT_ID,
  process.env.GOOGLE_CLIENT_SECRET,
  process.env.GOOGLE_REDIRECT_URI
);

// Set credentials (after token exchange)
oauth2Client.setCredentials({
  access_token: 'ya29.a0AfH6SMBx...',
  refresh_token: '1//0gqb...'
});

// Handle automatic token refresh
oauth2Client.on('tokens', (tokens) => {
  if (tokens.refresh_token) {
    // Store the new refresh token in your database
    saveRefreshToken(tokens.refresh_token);
  }
  // tokens.access_token is the new access token
});

// Initialize Drive client
const drive = google.drive({ version: 'v3', auth: oauth2Client });

// Example: List files
async function listFiles(query, pageSize = 20) {
  const response = await drive.files.list({
    q: query,
    pageSize: pageSize,
    fields: 'nextPageToken, files(id, name, mimeType, modifiedTime, size, webViewLink, parents)',
    orderBy: 'modifiedTime desc'
  });

  return response.data;
}
```

### Python Setup

```bash
pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
```

```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def get_drive_service(access_token, refresh_token, client_id, client_secret):
    """Create an authenticated Drive API service."""
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri='https://oauth2.googleapis.com/token'
    )

    service = build('drive', 'v3', credentials=creds)
    return service


def search_files(service, query, page_size=20):
    """Search for files using Drive API."""
    results = service.files().list(
        q=query,
        pageSize=page_size,
        fields="nextPageToken, files(id, name, mimeType, modifiedTime, size, webViewLink, parents)",
        orderBy="modifiedTime desc"
    ).execute()

    return results
```

---

## 14. Folder Link Parsing

Users will paste Google Drive links. You need to extract the folder ID.

### Supported URL Formats

```
https://drive.google.com/drive/folders/1ABC-xyz123
https://drive.google.com/drive/folders/1ABC-xyz123?usp=sharing
https://drive.google.com/drive/u/0/folders/1ABC-xyz123
https://drive.google.com/drive/u/1/folders/1ABC-xyz123?usp=drive_link
```

### Regex Parser

```javascript
function extractFolderId(url) {
  // Match folder ID from various Google Drive URL formats
  const patterns = [
    /\/folders\/([a-zA-Z0-9_-]+)/,
    /\/drive\/.*folders\/([a-zA-Z0-9_-]+)/,
    /id=([a-zA-Z0-9_-]+)/
  ];

  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match) return match[1];
  }

  return null;
}

// Examples:
extractFolderId("https://drive.google.com/drive/folders/1ABC-xyz123");
// => "1ABC-xyz123"

extractFolderId("https://drive.google.com/drive/u/0/folders/1ABC-xyz123?usp=sharing");
// => "1ABC-xyz123"
```

```python
import re

def extract_folder_id(url: str) -> str | None:
    """Extract folder ID from a Google Drive URL."""
    patterns = [
        r'/folders/([a-zA-Z0-9_-]+)',
        r'/drive/.*folders/([a-zA-Z0-9_-]+)',
        r'id=([a-zA-Z0-9_-]+)'
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None
```

---

## 15. Recursive Folder Traversal

Google Drive API does NOT support recursive listing natively. You must implement it yourself.

### Python Implementation

```python
def crawl_folder_recursive(service, folder_id, max_depth=10, current_depth=0):
    """
    Recursively list all files in a folder and its subfolders.
    Returns a flat list of all file metadata.
    """
    if current_depth >= max_depth:
        return []

    all_files = []
    page_token = None

    while True:
        query = f"'{folder_id}' in parents and trashed = false"

        response = service.files().list(
            q=query,
            pageSize=1000,
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, size, webViewLink, parents)",
            pageToken=page_token
        ).execute()

        files = response.get('files', [])

        for file in files:
            if file['mimeType'] == 'application/vnd.google-apps.folder':
                # It's a subfolder — recurse into it
                subfolder_files = crawl_folder_recursive(
                    service,
                    file['id'],
                    max_depth,
                    current_depth + 1
                )
                all_files.extend(subfolder_files)
            else:
                # It's a file — add to results
                all_files.append(file)

        page_token = response.get('nextPageToken')
        if not page_token:
            break

    return all_files
```

### Node.js Implementation

```javascript
async function crawlFolderRecursive(drive, folderId, maxDepth = 10, currentDepth = 0) {
  if (currentDepth >= maxDepth) return [];

  const allFiles = [];
  let pageToken = null;

  do {
    const response = await drive.files.list({
      q: `'${folderId}' in parents and trashed = false`,
      pageSize: 1000,
      fields: 'nextPageToken, files(id, name, mimeType, modifiedTime, size, webViewLink, parents)',
      pageToken: pageToken
    });

    const files = response.data.files || [];

    for (const file of files) {
      if (file.mimeType === 'application/vnd.google-apps.folder') {
        const subfolderFiles = await crawlFolderRecursive(
          drive, file.id, maxDepth, currentDepth + 1
        );
        allFiles.push(...subfolderFiles);
      } else {
        allFiles.push(file);
      }
    }

    pageToken = response.data.nextPageToken;
  } while (pageToken);

  return allFiles;
}
```

---

## 16. End-to-End Example Flow

### Step 1: User Pastes Folder Link

```
User pastes: https://drive.google.com/drive/folders/1ABC-xyz123
```

### Step 2: Backend Extracts Folder ID and Crawls

```python
folder_id = extract_folder_id(user_url)  # "1ABC-xyz123"
all_files = crawl_folder_recursive(service, folder_id)

# Result: flat list of all files with metadata
# [
#   { "id": "fileA", "name": "Project Plan.pdf", "mimeType": "application/pdf", ... },
#   { "id": "fileB", "name": "Budget.xlsx", "mimeType": "application/vnd...sheet", ... },
#   { "id": "fileC", "name": "Meeting Notes", "mimeType": "application/vnd.google-apps.document", ... },
#   ...
# ]
```

### Step 3: Store File Index

Store the file list in your backend (database or in-memory) so the agent tools can reference it without re-crawling:

```python
# Simple in-memory index
file_index = {
    "folder_id": folder_id,
    "files": all_files,
    "file_count": len(all_files),
    "indexed_at": datetime.now().isoformat()
}
```

### Step 4: User Asks a Question

```
User: "What is the timeline for Phase 2 of the project?"
```

### Step 5: Agent Orchestration Loop

```python
# The LLM receives the question + available tools
# It decides to call search_drive first

# LLM calls: search_drive(query="Phase 2 timeline", folder_id="1ABC-xyz123")
# Backend executes:
results = service.files().list(
    q="fullText contains 'Phase 2' and '1ABC-xyz123' in parents and trashed = false",
    fields="files(id, name, mimeType)"
).execute()
# Returns: [{ "id": "fileA", "name": "Project Plan.pdf", ... }]

# LLM sees results, decides to read the file
# LLM calls: get_file_content(file_id="fileA")
# Backend: downloads PDF, parses with pdfplumber, returns text with page numbers

# LLM sees the full text, calls: search_within_file(file_id="fileA", search_terms=["Phase 2", "timeline"])
# Backend: searches parsed text, returns matching passages with page numbers

# LLM composes final answer with citations
```

### Step 6: Agent Returns Answer with Citations

```
Agent: "According to the Project Plan (Project Plan.pdf, p. 8, Section: 'Project
Phases'), Phase 2 is scheduled to begin on June 1, 2026 and run through
September 30, 2026. The key milestones include:
- Design review: June 15 (Project Plan.pdf, p. 8)
- Development complete: August 30 (Project Plan.pdf, p. 9)
- QA sign-off: September 15 (Project Plan.pdf, p. 9)"
```

---

## Appendix A: Environment Variables

```bash
# Google OAuth
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:3000/callback

# LLM API
ANTHROPIC_API_KEY=sk-ant-...
# or
OPENAI_API_KEY=sk-...

# App
PORT=3001
NODE_ENV=development
```

## Appendix B: Recommended Fields Parameter

Always use the `fields` parameter to avoid over-fetching:

```
fields=nextPageToken, files(id, name, mimeType, modifiedTime, size, webViewLink, parents)
```

This returns only the fields you need, reducing response size and improving performance.

## Appendix C: Key Decision — When fullText Search Is Not Enough

Google Drive's `fullText contains` is keyword-based and file-level. For your agent to find specific paragraphs in large documents:

1. **Use `fullText contains`** to narrow down to candidate files (fast, server-side)
2. **Download and parse** the candidate files (pdfplumber, python-docx, etc.)
3. **Search within parsed text** using string matching or regex (precise, paragraph-level)
4. **Return matches with metadata** (page number, section, surrounding context)

This two-stage approach (Drive API narrows → local parsing targets) is how you achieve paragraph-level precision across hundreds of files.

---

*End of specification.*