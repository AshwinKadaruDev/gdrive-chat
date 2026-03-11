"""Tests for Drive-only tool handlers in tool_executor."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.tool_executor import execute_tool


@pytest.fixture
def drive_service():
    svc = AsyncMock()
    svc.search_files = AsyncMock()
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


class TestSearchDrive:
    @pytest.mark.asyncio
    async def test_returns_formatted_results(self, drive_service, null_search, null_embeddings):
        drive_service.search_files.return_value = [
            {
                "id": "file1",
                "name": "report.pdf",
                "mimeType": "application/pdf",
                "size": "1024",
                "modifiedTime": "2026-01-01T00:00:00Z",
                "webViewLink": "https://drive.google.com/file/d/file1",
            },
        ]

        result, citations = await execute_tool(
            tool_name="search_drive",
            tool_args={"query": "quarterly report"},
            project_id="folder123",
            access_token="token",
            search_service=null_search,
            drive_service=drive_service,
            embeddings_service=null_embeddings,
        )

        assert "Found 1 files" in result
        assert "report.pdf" in result
        assert len(citations) == 1
        assert citations[0].file_id == "file1"
        assert citations[0].file_name == "report.pdf"
        drive_service.search_files.assert_called_once_with(
            folder_id="folder123",
            query="quarterly report",
            access_token="token",
            file_types=None,
        )

    @pytest.mark.asyncio
    async def test_no_results(self, drive_service, null_search, null_embeddings):
        drive_service.search_files.return_value = []

        result, citations = await execute_tool(
            tool_name="search_drive",
            tool_args={"query": "nonexistent"},
            project_id="folder123",
            access_token="token",
            search_service=null_search,
            drive_service=drive_service,
            embeddings_service=null_embeddings,
        )

        assert "No files found" in result
        assert citations == []


class TestGetFileContent:
    @pytest.mark.asyncio
    async def test_returns_google_doc_text(self, drive_service, null_search, null_embeddings):
        drive_service.get_file_metadata.return_value = {
            "mimeType": "application/vnd.google-apps.document",
            "name": "My Doc",
            "webViewLink": "https://drive.google.com/file/d/doc1",
        }
        drive_service.export_google_doc.return_value = "Hello world document content"

        result, citations = await execute_tool(
            tool_name="get_file_content",
            tool_args={"file_id": "doc1"},
            project_id="folder123",
            access_token="token",
            search_service=null_search,
            drive_service=drive_service,
            embeddings_service=null_embeddings,
        )

        assert "Hello world document content" in result
        assert "My Doc" in result
        assert len(citations) == 1
        assert citations[0].file_name == "My Doc"

    @pytest.mark.asyncio
    async def test_truncates_long_content(self, drive_service, null_search, null_embeddings):
        drive_service.get_file_metadata.return_value = {
            "mimeType": "application/vnd.google-apps.document",
            "name": "Big Doc",
            "webViewLink": None,
        }
        drive_service.export_google_doc.return_value = "x" * 100

        result, citations = await execute_tool(
            tool_name="get_file_content",
            tool_args={"file_id": "doc1", "max_chars": 50},
            project_id="folder123",
            access_token="token",
            search_service=null_search,
            drive_service=drive_service,
            embeddings_service=null_embeddings,
        )

        assert "truncated" in result
        # Content should be at most 50 chars of the actual text
        # (plus the header line)
        content_after_header = result.split("\n\n", 1)[1]
        assert len(content_after_header) == 50

    @pytest.mark.asyncio
    async def test_plain_text_file(self, drive_service, null_search, null_embeddings):
        drive_service.get_file_metadata.return_value = {
            "mimeType": "text/plain",
            "name": "readme.txt",
            "webViewLink": None,
        }
        drive_service.download_file.return_value = b"Plain text content"

        result, citations = await execute_tool(
            tool_name="get_file_content",
            tool_args={"file_id": "txt1"},
            project_id="folder123",
            access_token="token",
            search_service=null_search,
            drive_service=drive_service,
            embeddings_service=null_embeddings,
        )

        assert "Plain text content" in result
        assert len(citations) == 1


class TestSearchWithinFileText:
    @pytest.mark.asyncio
    async def test_finds_matches(self, drive_service, null_search, null_embeddings):
        drive_service.get_file_metadata.return_value = {
            "mimeType": "text/plain",
            "name": "notes.txt",
            "webViewLink": None,
        }
        drive_service.download_file.return_value = (
            b"Line one\nThe answer is 42\nLine three\n"
        )

        result, citations = await execute_tool(
            tool_name="search_within_file_text",
            tool_args={"file_id": "file1", "query": "answer"},
            project_id="folder123",
            access_token="token",
            search_service=null_search,
            drive_service=drive_service,
            embeddings_service=null_embeddings,
        )

        assert "1 matches" in result
        assert "answer is 42" in result
        assert len(citations) == 1
        assert citations[0].location == "Line 2"

    @pytest.mark.asyncio
    async def test_no_matches(self, drive_service, null_search, null_embeddings):
        drive_service.get_file_metadata.return_value = {
            "mimeType": "text/plain",
            "name": "notes.txt",
            "webViewLink": None,
        }
        drive_service.download_file.return_value = b"Nothing here"

        result, citations = await execute_tool(
            tool_name="search_within_file_text",
            tool_args={"file_id": "file1", "query": "missing"},
            project_id="folder123",
            access_token="token",
            search_service=null_search,
            drive_service=drive_service,
            embeddings_service=null_embeddings,
        )

        assert "No matches" in result
        assert citations == []

    @pytest.mark.asyncio
    async def test_case_insensitive(self, drive_service, null_search, null_embeddings):
        drive_service.get_file_metadata.return_value = {
            "mimeType": "text/plain",
            "name": "doc.txt",
            "webViewLink": None,
        }
        drive_service.download_file.return_value = b"The IMPORTANT thing"

        result, citations = await execute_tool(
            tool_name="search_within_file_text",
            tool_args={"file_id": "file1", "query": "important"},
            project_id="folder123",
            access_token="token",
            search_service=null_search,
            drive_service=drive_service,
            embeddings_service=null_embeddings,
        )

        assert "1 matches" in result
        assert len(citations) == 1
