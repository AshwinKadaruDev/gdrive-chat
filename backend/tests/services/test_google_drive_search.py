"""Tests for GoogleDriveService.search_files (recursive) and export_google_doc(as_bytes)."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.services.google_drive import GoogleDriveService

FOLDER_MIME = "application/vnd.google-apps.folder"

_FAKE_REQUEST = httpx.Request("GET", "https://www.googleapis.com/drive/v3/files")


def _file(id: str, name: str, mime: str = "application/pdf") -> dict:
    return {"id": id, "name": name, "mimeType": mime}


def _folder(id: str, name: str) -> dict:
    return _file(id, name, FOLDER_MIME)


def _api_response(files: list[dict], next_page_token: str | None = None) -> httpx.Response:
    body = {"files": files}
    if next_page_token:
        body["nextPageToken"] = next_page_token
    return httpx.Response(200, json=body, request=_FAKE_REQUEST)


class TestSearchFilesRecursive:
    """search_files should find files in subfolders, not just direct children."""

    async def test_searches_subfolders(self):
        """Files in subfolders appear in search results."""
        svc = GoogleDriveService()

        # list_folder returns root + subfolder contents
        root_items = [_folder("sub1", "Sub"), _file("f1", "root.pdf")]
        sub1_items = [_file("f2", "nested.pdf")]

        # Mock list_folder to return all items (it's recursive itself)
        svc.list_folder = AsyncMock(return_value=root_items + sub1_items)

        # Mock the search API call — it should include both root and sub1 in parents
        search_response = _api_response([
            _file("f1", "root.pdf"),
            _file("f2", "nested.pdf"),
        ])
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=search_response)

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.search_files("root", "test query", "token")

        assert len(result) == 2
        # Verify the search query includes both folder IDs
        call_kwargs = mock_client.get.call_args
        q_param = call_kwargs[1]["params"]["q"]
        assert "'root' in parents" in q_param
        assert "'sub1' in parents" in q_param

    async def test_deduplicates_results(self):
        """Same file ID appearing in multiple batches is deduplicated."""
        svc = GoogleDriveService()

        # Many subfolders to trigger batching (>30)
        folders = [_folder(f"sub{i}", f"Sub {i}") for i in range(35)]
        svc.list_folder = AsyncMock(return_value=folders)

        # Both batches return the same file
        dup_file = _file("f1", "found.pdf")
        search_response = _api_response([dup_file])
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=search_response)

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.search_files("root", "query", "token")

        # Only 1 result despite being returned by both batches
        assert len(result) == 1
        assert result[0]["id"] == "f1"

    async def test_no_subfolders(self):
        """When there are no subfolders, only root is searched."""
        svc = GoogleDriveService()
        svc.list_folder = AsyncMock(return_value=[_file("f1", "a.pdf")])

        search_response = _api_response([_file("f1", "a.pdf")])
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=search_response)

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.search_files("root", "query", "token")

        assert len(result) == 1
        q_param = mock_client.get.call_args[1]["params"]["q"]
        assert "'root' in parents" in q_param

    async def test_empty_results(self):
        """Returns empty list when no files match."""
        svc = GoogleDriveService()
        svc.list_folder = AsyncMock(return_value=[])

        search_response = _api_response([])
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=search_response)

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.search_files("root", "query", "token")

        assert result == []


class TestExportGoogleDocAsBytes:
    """export_google_doc with as_bytes=True should return raw bytes."""

    async def test_returns_text_by_default(self):
        svc = GoogleDriveService()
        resp = httpx.Response(200, text="Hello text", request=_FAKE_REQUEST)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.export_google_doc("file1", "token")

        assert isinstance(result, str)
        assert result == "Hello text"

    async def test_returns_bytes_when_requested(self):
        svc = GoogleDriveService()
        binary_content = b"\x50\x4b\x03\x04xlsx-bytes"
        resp = httpx.Response(200, content=binary_content, request=_FAKE_REQUEST)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await svc.export_google_doc(
                "file1", "token",
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_bytes=True,
            )

        assert isinstance(result, bytes)
        assert result == binary_content
