"""Tests for spreadsheet tool handlers — Google Sheets export path."""

import io
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.tool_executor import (
    _download_spreadsheet_bytes,
    execute_tool,
)

GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _make_xlsx_bytes() -> bytes:
    """Create a minimal valid xlsx file in memory."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Name", "Value"])
    ws.append(["Alice", 10])
    ws.append(["Bob", 20])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def xlsx_bytes():
    return _make_xlsx_bytes()


@pytest.fixture
def drive_service():
    svc = AsyncMock()
    svc.get_file_metadata = AsyncMock()
    svc.download_file = AsyncMock()
    svc.export_google_doc = AsyncMock()
    return svc


@pytest.fixture
def null_search():
    return MagicMock()


@pytest.fixture
def null_embeddings():
    return MagicMock()


class TestDownloadSpreadsheetBytes:
    """_download_spreadsheet_bytes should export Google Sheets as xlsx bytes."""

    async def test_google_sheet_exports_as_xlsx(self, drive_service, xlsx_bytes):
        drive_service.get_file_metadata.return_value = {
            "mimeType": GOOGLE_SHEET_MIME,
            "name": "My Sheet",
        }
        drive_service.export_google_doc.return_value = xlsx_bytes

        content, name, mime = await _download_spreadsheet_bytes(
            "sheet1", "token", drive_service
        )

        assert content == xlsx_bytes
        assert name == "My Sheet"
        drive_service.export_google_doc.assert_called_once_with(
            file_id="sheet1",
            access_token="token",
            mime_type=XLSX_MIME,
            as_bytes=True,
        )
        # download_file should NOT be called for native Google Sheets
        drive_service.download_file.assert_not_called()

    async def test_uploaded_xlsx_downloads_directly(self, drive_service, xlsx_bytes):
        drive_service.get_file_metadata.return_value = {
            "mimeType": XLSX_MIME,
            "name": "uploaded.xlsx",
        }
        drive_service.download_file.return_value = xlsx_bytes

        content, name, mime = await _download_spreadsheet_bytes(
            "file1", "token", drive_service
        )

        assert content == xlsx_bytes
        assert name == "uploaded.xlsx"
        drive_service.download_file.assert_called_once()
        drive_service.export_google_doc.assert_not_called()


class TestSpreadsheetOverviewGoogleSheet:
    """get_spreadsheet_overview should work with native Google Sheets."""

    async def test_overview_with_google_sheet(
        self, drive_service, xlsx_bytes, null_search, null_embeddings
    ):
        drive_service.get_file_metadata.return_value = {
            "mimeType": GOOGLE_SHEET_MIME,
            "name": "My Sheet",
        }
        drive_service.export_google_doc.return_value = xlsx_bytes

        result, citations = await execute_tool(
            tool_name="get_spreadsheet_overview",
            tool_args={"file_id": "sheet1"},
            project_id="folder1",
            access_token="token",
            search_service=null_search,
            drive_service=drive_service,
            embeddings_service=null_embeddings,
        )

        assert "My Sheet" in result
        assert "Sheet1" in result
        assert "Name" in result
        assert "Value" in result
        # Should use export, not download
        drive_service.export_google_doc.assert_called_once()
        drive_service.download_file.assert_not_called()


class TestReadSpreadsheetRowsGoogleSheet:
    """read_spreadsheet_rows should work with native Google Sheets."""

    async def test_reads_rows_from_google_sheet(
        self, drive_service, xlsx_bytes, null_search, null_embeddings
    ):
        drive_service.get_file_metadata.return_value = {
            "mimeType": GOOGLE_SHEET_MIME,
            "name": "Data Sheet",
        }
        drive_service.export_google_doc.return_value = xlsx_bytes

        result, citations = await execute_tool(
            tool_name="read_spreadsheet_rows",
            tool_args={
                "file_id": "sheet1",
                "sheet_name": "Sheet1",
                "start_row": 1,
                "end_row": 3,
            },
            project_id="folder1",
            access_token="token",
            search_service=null_search,
            drive_service=drive_service,
            embeddings_service=null_embeddings,
        )

        assert "Alice" in result
        assert "Bob" in result


class TestSearchSpreadsheetGoogleSheet:
    """search_spreadsheet should work with native Google Sheets."""

    async def test_searches_google_sheet(
        self, drive_service, xlsx_bytes, null_search, null_embeddings
    ):
        drive_service.get_file_metadata.return_value = {
            "mimeType": GOOGLE_SHEET_MIME,
            "name": "Data Sheet",
        }
        drive_service.export_google_doc.return_value = xlsx_bytes

        result, citations = await execute_tool(
            tool_name="search_spreadsheet",
            tool_args={"file_id": "sheet1", "query": "Alice"},
            project_id="folder1",
            access_token="token",
            search_service=null_search,
            drive_service=drive_service,
            embeddings_service=null_embeddings,
        )

        assert "Alice" in result
        assert "1 matching" in result


class TestColumnStatsGoogleSheet:
    """get_column_stats should work with native Google Sheets."""

    async def test_stats_from_google_sheet(
        self, drive_service, xlsx_bytes, null_search, null_embeddings
    ):
        drive_service.get_file_metadata.return_value = {
            "mimeType": GOOGLE_SHEET_MIME,
            "name": "Data Sheet",
        }
        drive_service.export_google_doc.return_value = xlsx_bytes

        result, citations = await execute_tool(
            tool_name="get_column_stats",
            tool_args={
                "file_id": "sheet1",
                "sheet_name": "Sheet1",
                "column_name": "Value",
            },
            project_id="folder1",
            access_token="token",
            search_service=null_search,
            drive_service=drive_service,
            embeddings_service=null_embeddings,
        )

        assert "Count: 2" in result
        assert "Sum: 30" in result
        assert "Mean: 15" in result
