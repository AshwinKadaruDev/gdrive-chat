"""Activity: chunk extracted content into smaller pieces for embedding."""

from __future__ import annotations

import logging
import re
import uuid

import tiktoken
from temporalio import activity

logger = logging.getLogger(__name__)

# Target chunk sizes (in tokens)
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50

# Lazy-loaded tokenizer
_encoder: tiktoken.Encoding | None = None


def _get_encoder() -> tiktoken.Encoding:
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def _count_tokens(text: str) -> int:
    return len(_get_encoder().encode(text))


@activity.defn
async def chunk_content(extracted: dict, file_info: dict) -> list[dict]:
    """Split extracted content into chunks.

    Spreadsheets: one chunk per sheet.
    Documents: split by headings, then paragraphs, then fixed window.

    Returns list of chunk dicts.
    """
    extraction_type = extracted.get("extraction_type", "")
    sheets = extracted.get("sheets")
    text = extracted.get("text", "")
    file_id = file_info.get("id", "")
    file_name = file_info.get("name", "")
    file_type = file_info.get("mimeType", "")
    hierarchy = file_info.get("hierarchy", "")
    source_url = file_info.get("webViewLink", "")

    base_meta = {
        "file_id": file_id,
        "file_name": file_name,
        "file_type": file_type,
        "hierarchy": hierarchy,
        "source_url": source_url,
    }

    # Spreadsheets: one chunk per sheet
    if sheets and extraction_type in ("google_sheets", "xlsx"):
        return _chunk_spreadsheet(sheets, base_meta)

    # Documents and other text
    return _chunk_document(text, base_meta, extraction_type)


def _chunk_spreadsheet(sheets: list[dict], base_meta: dict) -> list[dict]:
    """Create one chunk per spreadsheet sheet."""
    chunks = []
    for sheet in sheets:
        sheet_text = sheet.get("text", "").strip()
        if not sheet_text:
            continue

        # If a single sheet is very large, split it into fixed-window chunks
        if _count_tokens(sheet_text) > CHUNK_SIZE * 2:
            sub_chunks = _fixed_window_split(sheet_text)
            for i, sub_text in enumerate(sub_chunks):
                chunks.append(
                    _make_chunk(
                        text=sub_text,
                        base_meta=base_meta,
                        section_heading=sheet["name"],
                        sheet_name=sheet["name"],
                        page_number=i + 1,
                    )
                )
        else:
            chunks.append(
                _make_chunk(
                    text=sheet_text,
                    base_meta=base_meta,
                    section_heading=sheet["name"],
                    sheet_name=sheet["name"],
                )
            )
    return chunks


def _chunk_document(text: str, base_meta: dict, extraction_type: str) -> list[dict]:
    """Chunk a document by headings, then paragraphs, then fixed window."""
    if not text.strip():
        return []

    # Try splitting by headings (markdown-style or extracted headings)
    sections = _split_by_headings(text)

    chunks = []
    for section_heading, section_text in sections:
        if not section_text.strip():
            continue

        token_count = _count_tokens(section_text)

        if token_count <= CHUNK_SIZE:
            # Section fits in one chunk
            chunks.append(
                _make_chunk(
                    text=section_text.strip(),
                    base_meta=base_meta,
                    section_heading=section_heading,
                )
            )
        else:
            # Section is too large; split by paragraphs then fixed window
            paragraphs = _split_by_paragraphs(section_text)
            current_text = ""
            current_tokens = 0

            for para in paragraphs:
                para_tokens = _count_tokens(para)

                if para_tokens > CHUNK_SIZE:
                    # Paragraph itself is too big: flush current, then fixed-window the paragraph
                    if current_text.strip():
                        chunks.append(
                            _make_chunk(
                                text=current_text.strip(),
                                base_meta=base_meta,
                                section_heading=section_heading,
                            )
                        )
                        current_text = ""
                        current_tokens = 0

                    for sub in _fixed_window_split(para):
                        chunks.append(
                            _make_chunk(
                                text=sub,
                                base_meta=base_meta,
                                section_heading=section_heading,
                            )
                        )

                elif current_tokens + para_tokens > CHUNK_SIZE:
                    # Adding this paragraph would exceed limit; flush current chunk
                    if current_text.strip():
                        chunks.append(
                            _make_chunk(
                                text=current_text.strip(),
                                base_meta=base_meta,
                                section_heading=section_heading,
                            )
                        )

                    # Start new chunk with overlap from end of previous text
                    overlap_text = _get_overlap_text(current_text)
                    current_text = overlap_text + para + "\n\n"
                    current_tokens = _count_tokens(current_text)
                else:
                    current_text += para + "\n\n"
                    current_tokens += para_tokens

            # Flush remaining text
            if current_text.strip():
                chunks.append(
                    _make_chunk(
                        text=current_text.strip(),
                        base_meta=base_meta,
                        section_heading=section_heading,
                    )
                )

    # Handle PDF page numbers if extraction_type indicates pages
    if extraction_type in ("pdf_text",):
        _assign_page_numbers(chunks, text)

    return chunks


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """Split text by markdown-style headings (# Heading) or all-caps lines.

    Returns list of (heading, section_text) tuples.
    """
    # Match markdown headings: # Heading, ## Heading, etc.
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    matches = list(heading_pattern.finditer(text))

    if not matches:
        # No headings found; return the entire text as one section
        return [("", text)]

    sections: list[tuple[str, str]] = []

    # Text before the first heading
    pre_text = text[: matches[0].start()].strip()
    if pre_text:
        sections.append(("", pre_text))

    for i, match in enumerate(matches):
        heading = match.group(2).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()
        sections.append((heading, section_text))

    return sections


def _split_by_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs (double newline separated)."""
    paragraphs = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paragraphs if p.strip()]


def _fixed_window_split(text: str) -> list[str]:
    """Split text into fixed-size token windows with overlap."""
    encoder = _get_encoder()
    tokens = encoder.encode(text)
    chunks = []

    start = 0
    while start < len(tokens):
        end = start + CHUNK_SIZE
        chunk_tokens = tokens[start:end]
        chunk_text = encoder.decode(chunk_tokens)
        chunks.append(chunk_text)

        if end >= len(tokens):
            break
        start = end - CHUNK_OVERLAP

    return chunks


def _get_overlap_text(text: str) -> str:
    """Get the last CHUNK_OVERLAP tokens of text for overlap."""
    if not text.strip():
        return ""
    encoder = _get_encoder()
    tokens = encoder.encode(text)
    if len(tokens) <= CHUNK_OVERLAP:
        return text
    overlap_tokens = tokens[-CHUNK_OVERLAP:]
    return encoder.decode(overlap_tokens)


def _assign_page_numbers(chunks: list[dict], original_text: str) -> None:
    """Try to assign page numbers to chunks based on [Page N] markers in the text."""
    page_pattern = re.compile(r"\[Page\s+(\d+)\]")

    for chunk in chunks:
        chunk_text = chunk.get("text", "")
        match = page_pattern.search(chunk_text)
        if match:
            chunk["page_number"] = int(match.group(1))


def _make_chunk(
    text: str,
    base_meta: dict,
    section_heading: str = "",
    page_number: int | None = None,
    sheet_name: str | None = None,
) -> dict:
    """Create a standardized chunk dict."""
    return {
        "chunk_id": str(uuid.uuid4()),
        "text": text,
        "file_id": base_meta["file_id"],
        "file_name": base_meta["file_name"],
        "file_type": base_meta["file_type"],
        "hierarchy": base_meta["hierarchy"],
        "source_url": base_meta["source_url"],
        "section_heading": section_heading,
        "page_number": page_number,
        "sheet_name": sheet_name,
    }
