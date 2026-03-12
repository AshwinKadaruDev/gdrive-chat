"""Tests for tool argument validation — every handler rejects missing required args gracefully."""

import pytest
from unittest.mock import MagicMock

from app.services.tool_executor import execute_tool


# The 12 handlers and their required arguments
TOOL_REQUIRED_ARGS = {
    "get_folder_structure": [],  # no required args
    "get_file_metadata": ["file_id"],
    "read_document_pages": ["file_id", "start_page", "end_page"],
    "get_spreadsheet_overview": ["file_id"],
    "read_spreadsheet_rows": ["file_id", "sheet_name", "start_row", "end_row"],
    "search_spreadsheet": ["file_id", "query"],
    "get_column_stats": ["file_id", "sheet_name", "column_name"],
    "report_inability": ["reason"],
    "request_clarification": ["question"],
    "search_drive": ["query"],
    "get_file_content": ["file_id"],
    "search_within_file_text": ["file_id", "query"],
}


@pytest.fixture
def mock_services():
    return {
        "drive_service": MagicMock(),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,required_args",
    [
        (name, args)
        for name, args in TOOL_REQUIRED_ARGS.items()
        if args  # skip tools with no required args
    ],
)
async def test_empty_args_returns_error(tool_name, required_args, mock_services):
    """Calling any tool with empty args should return an Error string, not crash."""
    result, citations = await execute_tool(
        tool_name=tool_name,
        tool_args={},
        project_id="proj-123",
        access_token="token",
        **mock_services,
    )

    assert "Error:" in result
    assert "required" in result.lower()
    assert citations == []


@pytest.mark.asyncio
async def test_unknown_tool_returns_error(mock_services):
    result, citations = await execute_tool(
        tool_name="nonexistent_tool",
        tool_args={},
        project_id="proj-123",
        access_token="token",
        **mock_services,
    )

    assert "Unknown tool" in result
    assert citations == []
