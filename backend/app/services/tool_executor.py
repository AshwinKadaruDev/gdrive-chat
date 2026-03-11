"""
Tool executor for the FolderAgent.

Routes tool calls to the appropriate handler, injects project_id and
access_token (never from the model), and returns a formatted result
string plus a list of citations.
"""

from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """Represents a source citation from a search result."""

    chunk_id: str
    file_id: str
    file_name: str
    source_url: str | None = None
    location: str | None = None
    snippet: str = ""


async def execute_tool(
    tool_name: str,
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    """
    Execute a tool by name and return (result_string, citations_list).

    project_id and access_token are always injected server-side and never
    taken from the model's arguments.
    """
    handlers = {
        "hybrid_search": _handle_hybrid_search,
        "search_within_file": _handle_search_within_file,
        "get_folder_structure": _handle_get_folder_structure,
        "get_file_metadata": _handle_get_file_metadata,
        "read_document_pages": _handle_read_document_pages,
        "read_chunk_context": _handle_read_chunk_context,
        "get_document_outline": _handle_get_document_outline,
        "get_spreadsheet_overview": _handle_get_spreadsheet_overview,
        "read_spreadsheet_rows": _handle_read_spreadsheet_rows,
        "search_spreadsheet": _handle_search_spreadsheet,
        "get_column_stats": _handle_get_column_stats,
        "report_inability": _handle_report_inability,
        "request_clarification": _handle_request_clarification,
        # Drive-only tools
        "search_drive": _handle_search_drive,
        "get_file_content": _handle_get_file_content,
        "search_within_file_text": _handle_search_within_file_text,
    }

    handler = handlers.get(tool_name)
    if handler is None:
        logger.warning("[TOOL] Unknown tool requested: %s", tool_name)
        return f"Unknown tool: {tool_name}", []

    logger.info("[TOOL] Executing %s(args=%s, project_id=%s)", tool_name, tool_args, project_id)
    try:
        result_str, citations = await handler(
            tool_args=tool_args,
            project_id=project_id,
            access_token=access_token,
            search_service=search_service,
            drive_service=drive_service,
            embeddings_service=embeddings_service,
        )
        logger.info(
            "[TOOL] %s completed: result_length=%d, citations=%d",
            tool_name, len(result_str), len(citations),
        )
        return result_str, citations
    except Exception as exc:
        logger.exception("[TOOL] Error executing %s: %s", tool_name, exc)
        return f"Error executing {tool_name}: {exc}", []


# ------------------------------------------------------------------ #
# Tool handlers
# ------------------------------------------------------------------ #


async def _handle_hybrid_search(
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    query = tool_args["query"]
    file_types = tool_args.get("file_types")
    top_k = tool_args.get("top_k", 8)

    query_vector = await embeddings_service.get_embedding(query)
    results = await search_service.hybrid_search(
        query=query,
        query_vector=query_vector,
        project_id=project_id,
        file_types=file_types,
        top_k=min(top_k, 20),
    )

    if not results:
        return "No results found.", []

    citations: list[Citation] = []
    formatted_parts: list[str] = []
    for i, r in enumerate(results, 1):
        location_parts: list[str] = []
        if r.get("section_heading"):
            location_parts.append(f"Section: {r['section_heading']}")
        if r.get("page_number"):
            location_parts.append(f"Page {r['page_number']}")
        if r.get("sheet_name"):
            location_parts.append(f"Sheet: {r['sheet_name']}")
        location = ", ".join(location_parts) if location_parts else None

        content = r.get("content", "")
        snippet = content[:300] if content else ""

        citations.append(
            Citation(
                chunk_id=r.get("chunk_id", ""),
                file_id=r.get("file_id", ""),
                file_name=r.get("file_name", ""),
                source_url=r.get("source_url"),
                location=location,
                snippet=snippet,
            )
        )
        formatted_parts.append(
            f"[Result {i}] File: {r.get('file_name', 'unknown')}"
            + (f" | {location}" if location else "")
            + f"\n{content}\n"
        )

    return "\n".join(formatted_parts), citations


async def _handle_search_within_file(
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    query = tool_args["query"]
    file_id = tool_args["file_id"]
    top_k = tool_args.get("top_k", 5)

    query_vector = await embeddings_service.get_embedding(query)
    results = await search_service.search_within_file(
        query=query,
        query_vector=query_vector,
        file_id=file_id,
        project_id=project_id,
        top_k=top_k,
    )

    if not results:
        return "No results found in this file.", []

    citations: list[Citation] = []
    formatted_parts: list[str] = []
    for i, r in enumerate(results, 1):
        location = None
        if r.get("page_number"):
            location = f"Page {r['page_number']}"
        if r.get("section_heading"):
            loc_parts = [r["section_heading"]]
            if location:
                loc_parts.append(location)
            location = ", ".join(loc_parts)

        content = r.get("content", "")
        snippet = content[:300] if content else ""

        citations.append(
            Citation(
                chunk_id=r.get("chunk_id", ""),
                file_id=r.get("file_id", ""),
                file_name=r.get("file_name", ""),
                source_url=r.get("source_url"),
                location=location,
                snippet=snippet,
            )
        )
        formatted_parts.append(
            f"[Result {i}] {r.get('file_name', 'unknown')}"
            + (f" | {location}" if location else "")
            + f"\n{content}\n"
        )

    return "\n".join(formatted_parts), citations


async def _handle_get_folder_structure(
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    # The project_id is used as the Google Drive folder_id
    files = await drive_service.list_folder(
        folder_id=project_id, access_token=access_token
    )

    if not files:
        return "No files found in the folder.", []

    # Build a simple tree representation
    lines: list[str] = []
    folders: dict[str, list[dict]] = {}
    root_files: list[dict] = []

    for f in files:
        parents = f.get("parents", [])
        if parents and parents[0] != project_id:
            parent_id = parents[0]
            folders.setdefault(parent_id, []).append(f)
        else:
            root_files.append(f)

    def _format_file(f: dict, indent: int = 0) -> str:
        prefix = "  " * indent
        mime = f.get("mimeType", "")
        size = f.get("size", "")
        size_str = f" ({_format_size(int(size))})" if size else ""
        is_folder = mime == "application/vnd.google-apps.folder"
        icon = "[folder]" if is_folder else "[file]"
        return f"{prefix}{icon} {f.get('name', 'unknown')}{size_str} (id: {f.get('id', '')})"

    def _render(file_list: list[dict], indent: int = 0) -> None:
        for f in file_list:
            lines.append(_format_file(f, indent))
            if f.get("mimeType") == "application/vnd.google-apps.folder":
                children = folders.get(f["id"], [])
                _render(children, indent + 1)

    _render(root_files)

    return "\n".join(lines) if lines else "Empty folder.", []


def _format_size(size_bytes: int) -> str:
    """Format bytes into a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} TB"


async def _handle_get_file_metadata(
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    file_id = tool_args["file_id"]
    metadata = await drive_service.get_file_metadata(
        file_id=file_id, access_token=access_token
    )
    return json.dumps(metadata, indent=2), []


async def _handle_read_document_pages(
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    file_id = tool_args["file_id"]
    start_page = tool_args["start_page"]
    end_page = tool_args["end_page"]

    # First get metadata to determine file type
    metadata = await drive_service.get_file_metadata(
        file_id=file_id, access_token=access_token
    )
    mime_type = metadata.get("mimeType", "")
    file_name = metadata.get("name", "unknown")

    if "google-apps.document" in mime_type:
        # Export Google Doc as plain text
        text = await drive_service.export_google_doc(
            file_id=file_id, access_token=access_token
        )
        # Simple page approximation: ~3000 chars per page
        chars_per_page = 3000
        start_char = (start_page - 1) * chars_per_page
        end_char = end_page * chars_per_page
        page_text = text[start_char:end_char]
        return f"Content from {file_name} (pages {start_page}-{end_page}):\n\n{page_text}", []

    # Download binary file
    content = await drive_service.download_file(
        file_id=file_id, access_token=access_token
    )

    if mime_type == "application/pdf" or file_name.lower().endswith(".pdf"):
        from app.utils.file_parsers import extract_pdf_text

        full_text = extract_pdf_text(content)
        # Split by form feed or approximate pages
        pages = full_text.split("\f") if "\f" in full_text else _split_into_pages(full_text)
        selected = pages[max(0, start_page - 1) : end_page]
        page_text = "\n\n--- Page Break ---\n\n".join(selected)
        return f"Content from {file_name} (pages {start_page}-{end_page}):\n\n{page_text}", []

    if (
        mime_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or file_name.lower().endswith(".docx")
    ):
        from app.utils.file_parsers import extract_docx_text

        full_text = extract_docx_text(content)
        pages = _split_into_pages(full_text)
        selected = pages[max(0, start_page - 1) : end_page]
        page_text = "\n\n--- Page Break ---\n\n".join(selected)
        return f"Content from {file_name} (pages {start_page}-{end_page}):\n\n{page_text}", []

    return f"Unsupported file type for page reading: {mime_type}", []


def _split_into_pages(text: str, chars_per_page: int = 3000) -> list[str]:
    """Split text into approximate pages."""
    pages: list[str] = []
    for i in range(0, len(text), chars_per_page):
        pages.append(text[i : i + chars_per_page])
    return pages if pages else [""]


async def _handle_read_chunk_context(
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    chunk_id = tool_args["chunk_id"]
    result = await search_service.get_chunk_with_neighbors(
        chunk_id=chunk_id, project_id=project_id
    )

    parts: list[str] = []
    citations: list[Citation] = []

    if result.get("previous"):
        prev = result["previous"]
        parts.append(f"[Previous chunk]\n{prev.get('content', '')}\n")

    if result.get("chunk"):
        chunk = result["chunk"]
        parts.append(f"[Current chunk]\n{chunk.get('content', '')}\n")
        citations.append(
            Citation(
                chunk_id=chunk.get("chunk_id", ""),
                file_id=chunk.get("file_id", ""),
                file_name=chunk.get("file_name", ""),
                source_url=chunk.get("source_url"),
                location=chunk.get("section_heading"),
                snippet=chunk.get("content", "")[:300],
            )
        )
    else:
        parts.append("Chunk not found.")

    if result.get("next"):
        nxt = result["next"]
        parts.append(f"[Next chunk]\n{nxt.get('content', '')}\n")

    return "\n".join(parts), citations


async def _handle_get_document_outline(
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    file_id = tool_args["file_id"]

    # Search for all chunks of this file and extract section headings
    results = await search_service.search_within_file(
        query="*",
        query_vector=await embeddings_service.get_embedding("document outline structure"),
        file_id=file_id,
        project_id=project_id,
        top_k=100,
    )

    if not results:
        return "No outline information available for this document.", []

    seen_headings: set[str] = set()
    outline_lines: list[str] = []

    for r in results:
        heading = r.get("section_heading")
        page = r.get("page_number")
        if heading and heading not in seen_headings:
            seen_headings.add(heading)
            page_str = f" (page {page})" if page else ""
            outline_lines.append(f"- {heading}{page_str}")

    if not outline_lines:
        return "No section headings found in this document.", []

    file_name = results[0].get("file_name", "unknown")
    return f"Outline of {file_name}:\n" + "\n".join(outline_lines), []


async def _download_spreadsheet_bytes(
    file_id: str,
    access_token: str,
    drive_service: "GoogleDriveService",
) -> tuple[bytes, str, str]:
    """Download spreadsheet bytes, handling native Google Sheets via export.

    Returns (content_bytes, file_name, mime_type).
    """
    metadata = await drive_service.get_file_metadata(
        file_id=file_id, access_token=access_token
    )
    mime_type = metadata.get("mimeType", "")
    file_name = metadata.get("name", "unknown")

    if "google-apps.spreadsheet" in mime_type:
        content = await drive_service.export_google_doc(
            file_id=file_id,
            access_token=access_token,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_bytes=True,
        )
    else:
        content = await drive_service.download_file(
            file_id=file_id, access_token=access_token
        )

    return content, file_name, mime_type


async def _handle_get_spreadsheet_overview(
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    file_id = tool_args["file_id"]

    content, file_name, mime_type = await _download_spreadsheet_bytes(
        file_id, access_token, drive_service
    )

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)

    overview_lines: list[str] = [f"Spreadsheet: {file_name}", ""]

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        max_row = ws.max_row or 0
        max_col = ws.max_column or 0

        overview_lines.append(f"Sheet: {sheet_name}")
        overview_lines.append(f"  Rows: {max_row}, Columns: {max_col}")

        # Get column headers (first row)
        headers: list[str] = []
        if max_row > 0:
            for cell in ws[1]:
                headers.append(str(cell.value) if cell.value is not None else "")
            overview_lines.append(f"  Headers: {', '.join(headers)}")

        # Sample data (rows 2-4)
        if max_row > 1:
            overview_lines.append("  Sample data:")
            for row_idx in range(2, min(5, max_row + 1)):
                row_vals = []
                for cell in ws[row_idx]:
                    row_vals.append(str(cell.value) if cell.value is not None else "")
                overview_lines.append(f"    Row {row_idx}: {', '.join(row_vals)}")

        overview_lines.append("")

    wb.close()
    return "\n".join(overview_lines), []


async def _handle_read_spreadsheet_rows(
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    file_id = tool_args["file_id"]
    sheet_name = tool_args["sheet_name"]
    start_row = tool_args["start_row"]
    end_row = tool_args["end_row"]

    content, _file_name, _mime_type = await _download_spreadsheet_bytes(
        file_id, access_token, drive_service
    )

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)

    if sheet_name not in wb.sheetnames:
        wb.close()
        return f"Sheet '{sheet_name}' not found. Available sheets: {', '.join(wb.sheetnames)}", []

    ws = wb[sheet_name]

    # Get headers from row 1
    headers: list[str] = []
    if ws.max_row and ws.max_row > 0:
        for cell in ws[1]:
            headers.append(str(cell.value) if cell.value is not None else "")

    lines: list[str] = []
    if headers:
        lines.append(" | ".join(headers))
        lines.append("-" * len(lines[0]))

    for row_idx in range(max(1, start_row), min(end_row + 1, (ws.max_row or 0) + 1)):
        row_vals: list[str] = []
        for cell in ws[row_idx]:
            row_vals.append(str(cell.value) if cell.value is not None else "")
        lines.append(f"Row {row_idx}: {' | '.join(row_vals)}")

    wb.close()
    return "\n".join(lines) if lines else "No data found in the specified range.", []


async def _handle_search_spreadsheet(
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    file_id = tool_args["file_id"]
    query = tool_args["query"].lower()
    target_sheet = tool_args.get("sheet_name")

    content, _file_name, _mime_type = await _download_spreadsheet_bytes(
        file_id, access_token, drive_service
    )

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)

    matches: list[str] = []
    sheets_to_search = [target_sheet] if target_sheet else wb.sheetnames

    for sn in sheets_to_search:
        if sn not in wb.sheetnames:
            continue
        ws = wb[sn]

        # Get headers
        headers: list[str] = []
        if ws.max_row and ws.max_row > 0:
            for cell in ws[1]:
                headers.append(str(cell.value) if cell.value is not None else "")

        for row_idx in range(1, (ws.max_row or 0) + 1):
            row_vals: list[str] = []
            found = False
            for cell in ws[row_idx]:
                val = str(cell.value) if cell.value is not None else ""
                row_vals.append(val)
                if query in val.lower():
                    found = True
            if found:
                matches.append(f"Sheet '{sn}', Row {row_idx}: {' | '.join(row_vals)}")

        if len(matches) >= 50:
            break

    wb.close()

    if not matches:
        return f"No matches found for '{tool_args['query']}'.", []

    return f"Found {len(matches)} matching rows:\n" + "\n".join(matches), []


async def _handle_get_column_stats(
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    file_id = tool_args["file_id"]
    sheet_name = tool_args["sheet_name"]
    column_name = tool_args["column_name"]

    content, _file_name, _mime_type = await _download_spreadsheet_bytes(
        file_id, access_token, drive_service
    )

    import openpyxl
    import statistics

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)

    if sheet_name not in wb.sheetnames:
        wb.close()
        return f"Sheet '{sheet_name}' not found.", []

    ws = wb[sheet_name]

    # Find the column index
    col_idx: int | None = None
    if ws.max_row and ws.max_row > 0:
        for i, cell in enumerate(ws[1]):
            if str(cell.value).strip().lower() == column_name.strip().lower():
                col_idx = i
                break

    if col_idx is None:
        headers = []
        if ws.max_row and ws.max_row > 0:
            for cell in ws[1]:
                headers.append(str(cell.value) if cell.value is not None else "")
        wb.close()
        return (
            f"Column '{column_name}' not found. Available columns: {', '.join(headers)}",
            [],
        )

    # Collect numeric values
    values: list[float] = []
    for row_idx in range(2, (ws.max_row or 0) + 1):
        row_cells = list(ws[row_idx])
        if col_idx < len(row_cells):
            val = row_cells[col_idx].value
            if val is not None:
                try:
                    values.append(float(val))
                except (ValueError, TypeError):
                    pass

    wb.close()

    if not values:
        return f"No numeric values found in column '{column_name}'.", []

    stats_lines = [
        f"Statistics for column '{column_name}' in sheet '{sheet_name}':",
        f"  Count: {len(values)}",
        f"  Sum: {sum(values):.2f}",
        f"  Mean: {statistics.mean(values):.2f}",
        f"  Median: {statistics.median(values):.2f}",
        f"  Min: {min(values):.2f}",
        f"  Max: {max(values):.2f}",
    ]
    if len(values) >= 2:
        stats_lines.append(f"  Std Dev: {statistics.stdev(values):.2f}")

    return "\n".join(stats_lines), []


async def _handle_report_inability(
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    reason = tool_args["reason"]
    return reason, []


async def _handle_request_clarification(
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    question = tool_args["question"]
    return question, []


# ------------------------------------------------------------------ #
# Drive-only tool handlers
# ------------------------------------------------------------------ #


async def _handle_search_drive(
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    query = tool_args["query"]
    file_types = tool_args.get("file_types")

    results = await drive_service.search_files(
        folder_id=project_id,
        query=query,
        access_token=access_token,
        file_types=file_types,
    )

    if not results:
        return "No files found matching your query.", []

    citations: list[Citation] = []
    formatted_parts: list[str] = []
    for i, f in enumerate(results, 1):
        file_id = f.get("id", "")
        file_name = f.get("name", "unknown")
        mime_type = f.get("mimeType", "")
        size = f.get("size", "")
        size_str = f" ({_format_size(int(size))})" if size else ""
        modified = f.get("modifiedTime", "")
        web_link = f.get("webViewLink")

        citations.append(
            Citation(
                chunk_id=f"drive-search-{file_id}",
                file_id=file_id,
                file_name=file_name,
                source_url=web_link,
                location=None,
                snippet=f"Found via Drive search for '{query}'",
            )
        )
        formatted_parts.append(
            f"[Result {i}] {file_name}{size_str}\n"
            f"  ID: {file_id}\n"
            f"  Type: {mime_type}\n"
            f"  Modified: {modified}\n"
        )

    return f"Found {len(results)} files:\n\n" + "\n".join(formatted_parts), citations


async def _handle_get_file_content(
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    file_id = tool_args["file_id"]
    max_chars = tool_args.get("max_chars", 50000)

    metadata = await drive_service.get_file_metadata(
        file_id=file_id, access_token=access_token
    )
    mime_type = metadata.get("mimeType", "")
    file_name = metadata.get("name", "unknown")
    web_link = metadata.get("webViewLink")

    # Google Docs/Sheets/Slides — export as plain text
    if "google-apps.document" in mime_type:
        text = await drive_service.export_google_doc(
            file_id=file_id, access_token=access_token
        )
    elif "google-apps.spreadsheet" in mime_type:
        text = await drive_service.export_google_doc(
            file_id=file_id,
            access_token=access_token,
            mime_type="text/csv",
        )
    elif "google-apps.presentation" in mime_type:
        text = await drive_service.export_google_doc(
            file_id=file_id, access_token=access_token
        )
    else:
        # Binary file — download and parse
        content = await drive_service.download_file(
            file_id=file_id, access_token=access_token
        )

        if mime_type == "application/pdf" or file_name.lower().endswith(".pdf"):
            from app.utils.file_parsers import extract_pdf_text
            text = extract_pdf_text(content)
        elif (
            mime_type
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            or file_name.lower().endswith(".docx")
        ):
            from app.utils.file_parsers import extract_docx_text
            text = extract_docx_text(content)
        elif mime_type.startswith("text/") or file_name.lower().endswith(".txt"):
            text = content.decode("utf-8", errors="replace")
        else:
            text = f"[Unsupported file type: {mime_type}. Cannot extract text.]"

    truncated = len(text) > max_chars
    text = text[:max_chars]

    citation = Citation(
        chunk_id=f"file-content-{file_id}",
        file_id=file_id,
        file_name=file_name,
        source_url=web_link,
        location=None,
        snippet=text[:300],
    )

    header = f"Content of {file_name}"
    if truncated:
        header += f" (truncated to {max_chars} characters)"
    header += ":\n\n"

    return header + text, [citation]


async def _handle_search_within_file_text(
    tool_args: dict,
    project_id: str,
    access_token: str,
    search_service: "AzureSearchService",
    drive_service: "GoogleDriveService",
    embeddings_service: "EmbeddingsService",
) -> tuple[str, list[Citation]]:
    file_id = tool_args["file_id"]
    query = tool_args["query"]
    context_chars = tool_args.get("context_chars", 200)

    metadata = await drive_service.get_file_metadata(
        file_id=file_id, access_token=access_token
    )
    mime_type = metadata.get("mimeType", "")
    file_name = metadata.get("name", "unknown")
    web_link = metadata.get("webViewLink")

    # Get the full text
    if "google-apps.document" in mime_type:
        text = await drive_service.export_google_doc(
            file_id=file_id, access_token=access_token
        )
    elif "google-apps.spreadsheet" in mime_type:
        text = await drive_service.export_google_doc(
            file_id=file_id,
            access_token=access_token,
            mime_type="text/csv",
        )
    else:
        content = await drive_service.download_file(
            file_id=file_id, access_token=access_token
        )
        if mime_type == "application/pdf" or file_name.lower().endswith(".pdf"):
            from app.utils.file_parsers import extract_pdf_text
            text = extract_pdf_text(content)
        elif (
            mime_type
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            or file_name.lower().endswith(".docx")
        ):
            from app.utils.file_parsers import extract_docx_text
            text = extract_docx_text(content)
        else:
            text = content.decode("utf-8", errors="replace")

    # Case-insensitive search for matches
    query_lower = query.lower()
    lines = text.split("\n")
    matches: list[str] = []
    citations: list[Citation] = []

    for line_num, line in enumerate(lines, 1):
        if query_lower in line.lower():
            # Find the match position within the line for context
            idx = line.lower().index(query_lower)
            start = max(0, idx - context_chars)
            end = min(len(line), idx + len(query) + context_chars)
            passage = line[start:end]

            matches.append(f"Line {line_num}: ...{passage}...")

            if len(citations) < 5:  # Cap citations at 5
                citations.append(
                    Citation(
                        chunk_id=f"text-search-{file_id}-L{line_num}",
                        file_id=file_id,
                        file_name=file_name,
                        source_url=web_link,
                        location=f"Line {line_num}",
                        snippet=passage[:300],
                    )
                )

            if len(matches) >= 20:
                break

    if not matches:
        return f"No matches for '{query}' found in {file_name}.", []

    result = f"Found {len(matches)} matches for '{query}' in {file_name}:\n\n"
    result += "\n\n".join(matches)
    return result, citations
