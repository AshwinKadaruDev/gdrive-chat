"""Tests for the POST /api/projects/validate-folder endpoint."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.google_drive import DriveValidationError

VALID_URL = "https://drive.google.com/drive/folders/1aBcD_eFgHiJk"
FOLDER_ID = "1aBcD_eFgHiJk"


@pytest.mark.anyio
class TestValidateFolder:
    """POST /api/projects/validate-folder"""

    @patch("app.routers.projects.get_valid_access_token", new_callable=AsyncMock, return_value="access-tok")
    @patch("app.routers.projects.GoogleDriveService")
    async def test_valid_folder(self, MockDrive, _tok, test_client):
        instance = MockDrive.return_value
        instance.validate_folder = AsyncMock(
            return_value={
                "id": FOLDER_ID,
                "name": "Product Docs",
                "mimeType": "application/vnd.google-apps.folder",
                "webViewLink": "https://drive.google.com/...",
            }
        )

        resp = await test_client.post(
            "/api/projects/validate-folder",
            json={"gdrive_folder_url": VALID_URL},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["folder_id"] == FOLDER_ID
        assert body["folder_name"] == "Product Docs"
        assert body["gdrive_folder_url"] == VALID_URL

    async def test_invalid_url_format(self, test_client):
        # URL with slashes but not matching Drive pattern → ValueError
        resp = await test_client.post(
            "/api/projects/validate-folder",
            json={"gdrive_folder_url": "https://example.com/bad/url"},
        )
        assert resp.status_code == 422

    @patch("app.routers.projects.get_valid_access_token", new_callable=AsyncMock, return_value="access-tok")
    @patch("app.routers.projects.GoogleDriveService")
    async def test_not_a_folder(self, MockDrive, _tok, test_client):
        instance = MockDrive.return_value
        instance.validate_folder = AsyncMock(
            side_effect=DriveValidationError(
                "not_a_folder",
                "That URL points to a file, not a folder.",
            )
        )

        resp = await test_client.post(
            "/api/projects/validate-folder",
            json={"gdrive_folder_url": VALID_URL},
        )
        assert resp.status_code == 422
        assert "file, not a folder" in resp.json()["detail"]

    @patch("app.routers.projects.get_valid_access_token", new_callable=AsyncMock, return_value="access-tok")
    @patch("app.routers.projects.GoogleDriveService")
    async def test_no_access(self, MockDrive, _tok, test_client):
        instance = MockDrive.return_value
        instance.validate_folder = AsyncMock(
            side_effect=DriveValidationError(
                "no_access",
                "You don't have access to this folder.",
            )
        )

        resp = await test_client.post(
            "/api/projects/validate-folder",
            json={"gdrive_folder_url": VALID_URL},
        )
        assert resp.status_code == 422
        assert "access" in resp.json()["detail"].lower()

    @patch("app.routers.projects.get_valid_access_token", new_callable=AsyncMock, return_value="access-tok")
    @patch("app.routers.projects.GoogleDriveService")
    async def test_not_found(self, MockDrive, _tok, test_client):
        instance = MockDrive.return_value
        instance.validate_folder = AsyncMock(
            side_effect=DriveValidationError(
                "not_found",
                "We couldn't find that folder.",
            )
        )

        resp = await test_client.post(
            "/api/projects/validate-folder",
            json={"gdrive_folder_url": VALID_URL},
        )
        assert resp.status_code == 422
        assert "find" in resp.json()["detail"].lower()
