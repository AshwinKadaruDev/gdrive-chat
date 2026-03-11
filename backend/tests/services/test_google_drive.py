"""Tests for GoogleDriveService.list_folder / count_files."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.services.google_drive import GoogleDriveService

FOLDER_MIME = "application/vnd.google-apps.folder"


def _file(id: str, name: str, mime: str = "application/pdf") -> dict:
    return {"id": id, "name": name, "mimeType": mime}


def _folder(id: str, name: str) -> dict:
    return _file(id, name, FOLDER_MIME)


_FAKE_REQUEST = httpx.Request("GET", "https://www.googleapis.com/drive/v3/files")


def _api_response(files: list[dict], next_page_token: str | None = None) -> httpx.Response:
    body = {"files": files}
    if next_page_token:
        body["nextPageToken"] = next_page_token
    return httpx.Response(200, json=body, request=_FAKE_REQUEST)


class TestListFolder:
    async def test_flat_folder_returns_all_files(self):
        """A folder with only files (no subfolders) returns them all."""
        files = [_file("f1", "a.pdf"), _file("f2", "b.docx")]
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_api_response(files))

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            svc = GoogleDriveService()
            result = await svc.list_folder("root", "token")

        assert len(result) == 2
        assert {f["id"] for f in result} == {"f1", "f2"}

    async def test_pagination(self):
        """Follows nextPageToken to fetch all pages."""
        page1 = _api_response([_file("f1", "a.pdf")], next_page_token="page2")
        page2 = _api_response([_file("f2", "b.pdf")])
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[page1, page2])

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            svc = GoogleDriveService()
            result = await svc.list_folder("root", "token")

        assert len(result) == 2
        assert mock_client.get.call_count == 2

    async def test_recurses_into_subfolders(self):
        """Subfolders are traversed and their files appear in the result."""
        root_files = [_folder("sub1", "Sub 1"), _file("f1", "root.pdf")]
        sub1_files = [_file("f2", "nested.pdf")]

        def route_get(*args, **kwargs):
            q = kwargs.get("params", {}).get("q", "")
            if "'root'" in q:
                return _api_response(root_files)
            if "'sub1'" in q:
                return _api_response(sub1_files)
            return _api_response([])

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=route_get)

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            svc = GoogleDriveService()
            result = await svc.list_folder("root", "token")

        ids = {f["id"] for f in result}
        assert ids == {"sub1", "f1", "f2"}

    async def test_concurrent_subfolder_traversal(self):
        """Multiple subfolders are traversed concurrently via asyncio.gather."""
        root_files = [_folder("s1", "S1"), _folder("s2", "S2")]
        s1_files = [_file("f1", "a.pdf")]
        s2_files = [_file("f2", "b.pdf")]

        def route_get(*args, **kwargs):
            q = kwargs.get("params", {}).get("q", "")
            if "'root'" in q:
                return _api_response(root_files)
            if "'s1'" in q:
                return _api_response(s1_files)
            if "'s2'" in q:
                return _api_response(s2_files)
            return _api_response([])

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=route_get)

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            svc = GoogleDriveService()
            result = await svc.list_folder("root", "token")

        # All items: 2 folders + 2 files
        assert len(result) == 4
        ids = {f["id"] for f in result}
        assert ids == {"s1", "s2", "f1", "f2"}
        # 3 API calls total: root + s1 + s2
        assert mock_client.get.call_count == 3

    async def test_deep_nesting(self):
        """Handles folders nested multiple levels deep."""
        root_files = [_folder("l1", "Level 1")]
        l1_files = [_folder("l2", "Level 2")]
        l2_files = [_file("f1", "deep.pdf")]

        def route_get(*args, **kwargs):
            q = kwargs.get("params", {}).get("q", "")
            if "'root'" in q:
                return _api_response(root_files)
            if "'l1'" in q:
                return _api_response(l1_files)
            if "'l2'" in q:
                return _api_response(l2_files)
            return _api_response([])

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=route_get)

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            svc = GoogleDriveService()
            result = await svc.list_folder("root", "token")

        assert len(result) == 3
        assert {f["id"] for f in result} == {"l1", "l2", "f1"}

    async def test_empty_folder(self):
        """An empty folder returns an empty list."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_api_response([]))

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            svc = GoogleDriveService()
            result = await svc.list_folder("root", "token")

        assert result == []

    async def test_api_error_propagates(self):
        """HTTP errors from the Drive API propagate as httpx.HTTPStatusError."""
        error_response = httpx.Response(403, json={"error": "forbidden"}, request=httpx.Request("GET", "http://test"))
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=error_response)

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            svc = GoogleDriveService()
            with pytest.raises(httpx.HTTPStatusError):
                await svc.list_folder("root", "token")

    async def test_shared_client_passed_to_recursive(self):
        """list_folder creates one AsyncClient and passes it to all recursive calls."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_api_response([]))

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            svc = GoogleDriveService()
            await svc.list_folder("root", "token")

        # Only one AsyncClient was created
        MockClient.assert_called_once_with(timeout=30.0)


class TestCountFiles:
    async def test_counts_non_folder_files(self):
        """count_files excludes folders from the count."""
        root_files = [_folder("s1", "Folder"), _file("f1", "a.pdf"), _file("f2", "b.docx")]
        sub_files = [_file("f3", "c.pdf")]

        def route_get(*args, **kwargs):
            q = kwargs.get("params", {}).get("q", "")
            if "'root'" in q:
                return _api_response(root_files)
            if "'s1'" in q:
                return _api_response(sub_files)
            return _api_response([])

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=route_get)

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            svc = GoogleDriveService()
            count = await svc.count_files("root", "token")

        # 3 non-folder files (f1, f2, f3); s1 is a folder and excluded
        assert count == 3

    async def test_empty_folder_returns_zero(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_api_response([]))

        with patch("httpx.AsyncClient") as MockClient:
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            svc = GoogleDriveService()
            count = await svc.count_files("root", "token")

        assert count == 0
