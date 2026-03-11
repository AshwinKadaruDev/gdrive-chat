"""
Tool definitions for the FolderAgent.

Each tool follows the OpenAI function calling schema format so that
they can be used with both OpenAI and Anthropic (after conversion).

Tools are grouped into:
- RAG_ONLY_TOOLS: require pre-indexed Azure AI Search data
- DRIVE_ONLY_TOOLS: use Google Drive API directly (no pre-indexing)
- SHARED_TOOLS: common to both agent types

Composed sets:
- RAG_AGENT_TOOLS = RAG_ONLY_TOOLS + SHARED_TOOLS (13 tools)
- DRIVE_AGENT_TOOLS = DRIVE_ONLY_TOOLS + SHARED_TOOLS (12 tools)
- ALL_TOOL_DEFINITIONS = RAG_AGENT_TOOLS (backward compat)
"""

# ------------------------------------------------------------------ #
# RAG-only tools (require Azure AI Search index)
# ------------------------------------------------------------------ #

RAG_ONLY_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "hybrid_search",
            "description": (
                "Search across ALL files in the project using both semantic similarity "
                "and keyword matching. Use this as the primary search tool when you need "
                "to find information across the entire folder. Returns the most relevant "
                "chunks of content ranked by combined text and vector relevance."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query. Can be a natural language question or keywords.",
                    },
                    "file_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional list of file types to filter by (e.g., ['pdf', 'docx', 'xlsx']). "
                            "Leave empty to search all file types."
                        ),
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default 8, max 20).",
                        "default": 8,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_within_file",
            "description": (
                "Search within a SPECIFIC file by file_id. Use this when you already "
                "know which file contains the answer and want to find the relevant "
                "section. More precise than hybrid_search for targeted lookups."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                    "file_id": {
                        "type": "string",
                        "description": "The Google Drive file ID to search within.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default 5).",
                        "default": 5,
                    },
                },
                "required": ["query", "file_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_chunk_context",
            "description": (
                "Read a specific chunk and its surrounding context (previous and next "
                "chunks). Use this when a search result snippet is too short and you "
                "need more context around a specific passage."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chunk_id": {
                        "type": "string",
                        "description": "The chunk ID from a previous search result.",
                    },
                },
                "required": ["chunk_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_outline",
            "description": (
                "Get the outline / table of contents of a document, showing section "
                "headings and page numbers. Use this to understand the structure of "
                "a long document before reading specific sections."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "The Google Drive file ID of the document.",
                    },
                },
                "required": ["file_id"],
            },
        },
    },
]

# ------------------------------------------------------------------ #
# Drive-only tools (use Google Drive API directly, no pre-indexing)
# ------------------------------------------------------------------ #

DRIVE_ONLY_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_drive",
            "description": (
                "Search for files in the Google Drive folder using keyword matching. "
                "This is the primary search tool — use it to find files whose content "
                "contains the given query terms. Returns file names, IDs, and snippets. "
                "Note: this uses Google Drive full-text search (keyword-based), not "
                "semantic/vector search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query. Use specific keywords for best results.",
                    },
                    "file_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional list of MIME type fragments to filter by "
                            "(e.g., ['pdf', 'spreadsheet', 'document']). "
                            "Leave empty to search all file types."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_content",
            "description": (
                "Download and read the full text content of a file by its file_id. "
                "Supports PDF, DOCX, Google Docs, and plain text files. "
                "Returns the extracted text, truncated to max_chars if the file is very large."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "The Google Drive file ID of the file to read.",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters to return (default 50000).",
                        "default": 50000,
                    },
                },
                "required": ["file_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_within_file_text",
            "description": (
                "Search for a query string within a specific file's text content. "
                "Downloads and parses the file, then performs case-insensitive text "
                "search, returning matching passages with surrounding context and "
                "line numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "The Google Drive file ID of the file to search within.",
                    },
                    "query": {
                        "type": "string",
                        "description": "The text to search for within the file.",
                    },
                    "context_chars": {
                        "type": "integer",
                        "description": "Number of characters of context to show around each match (default 200).",
                        "default": 200,
                    },
                },
                "required": ["file_id", "query"],
            },
        },
    },
]

# ------------------------------------------------------------------ #
# Shared tools (common to both RAG and Drive agents)
# ------------------------------------------------------------------ #

SHARED_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_folder_structure",
            "description": (
                "Get the complete folder and file structure of the project. Returns "
                "a tree view showing all files and sub-folders with their names, types, "
                "and sizes. Use this to understand what files are available before searching."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_metadata",
            "description": (
                "Get detailed metadata for a specific file including name, type, size, "
                "modification time, and download link. Use this to learn about a file "
                "before reading its contents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "The Google Drive file ID.",
                    },
                },
                "required": ["file_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_document_pages",
            "description": (
                "Read specific pages from a document (PDF, DOCX, or Google Doc). "
                "Returns the full text content of the requested pages. Use this when "
                "you need to read exact content from known page numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "The Google Drive file ID of the document.",
                    },
                    "start_page": {
                        "type": "integer",
                        "description": "The starting page number (1-indexed).",
                    },
                    "end_page": {
                        "type": "integer",
                        "description": "The ending page number (inclusive).",
                    },
                },
                "required": ["file_id", "start_page", "end_page"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spreadsheet_overview",
            "description": (
                "Get an overview of a spreadsheet including sheet names, row/column "
                "counts, column headers, and sample data. Use this to understand the "
                "structure of a spreadsheet before querying specific data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "The Google Drive file ID of the spreadsheet.",
                    },
                },
                "required": ["file_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_spreadsheet_rows",
            "description": (
                "Read specific rows from a spreadsheet sheet. Returns the data as "
                "a formatted table. Use this to read actual data after understanding "
                "the spreadsheet structure via get_spreadsheet_overview."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "The Google Drive file ID of the spreadsheet.",
                    },
                    "sheet_name": {
                        "type": "string",
                        "description": "Name of the sheet to read from.",
                    },
                    "start_row": {
                        "type": "integer",
                        "description": "Starting row number (1-indexed, 1 is usually the header).",
                    },
                    "end_row": {
                        "type": "integer",
                        "description": "Ending row number (inclusive).",
                    },
                },
                "required": ["file_id", "sheet_name", "start_row", "end_row"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_spreadsheet",
            "description": (
                "Search for specific values or patterns within a spreadsheet. "
                "Returns matching rows with their row numbers and sheet names. "
                "Use this to find specific data points in large spreadsheets."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "The Google Drive file ID of the spreadsheet.",
                    },
                    "query": {
                        "type": "string",
                        "description": "The search term to look for in cell values.",
                    },
                    "sheet_name": {
                        "type": "string",
                        "description": "Optional: limit search to a specific sheet.",
                    },
                },
                "required": ["file_id", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_column_stats",
            "description": (
                "Get statistical summary of a numeric column in a spreadsheet "
                "including count, sum, mean, median, min, max, and standard deviation. "
                "Use this for quick numerical analysis of spreadsheet data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "The Google Drive file ID of the spreadsheet.",
                    },
                    "sheet_name": {
                        "type": "string",
                        "description": "Name of the sheet containing the column.",
                    },
                    "column_name": {
                        "type": "string",
                        "description": "The name of the column header to analyze.",
                    },
                },
                "required": ["file_id", "sheet_name", "column_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_inability",
            "description": (
                "Report that you cannot answer the question with the available data. "
                "Use this ONLY after exhausting all search strategies. Explain what "
                "you tried and why the information is not available."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Explanation of what was tried and why the answer could not be found.",
                    },
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_clarification",
            "description": (
                "Ask the user for clarification when the question is ambiguous or "
                "you need more information to provide a good answer. Use this sparingly "
                "and only when truly needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The clarifying question to ask the user.",
                    },
                },
                "required": ["question"],
            },
        },
    },
]

# ------------------------------------------------------------------ #
# Composed tool sets
# ------------------------------------------------------------------ #

RAG_AGENT_TOOLS: list[dict] = RAG_ONLY_TOOLS + SHARED_TOOLS
DRIVE_AGENT_TOOLS: list[dict] = DRIVE_ONLY_TOOLS + SHARED_TOOLS

# Backward compat alias
ALL_TOOL_DEFINITIONS: list[dict] = RAG_AGENT_TOOLS
