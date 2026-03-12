"""Tests for the sync router — trigger sync, error handling, race conditions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user, get_db, get_settings
from app.main import app
from app.models.project import ProjectStatus
from app.utils.security import SESSION_COOKIE_NAME, create_session


def _make_mock_user():
    user = MagicMock()
    user.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    user.email = "test@example.com"
    user.name = "Test User"
    user.picture_url = None
    user.google_access_token = "encrypted-test-token"
    user.google_refresh_token = "encrypted-test-refresh"
    user.token_expires_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
    return user


def _make_mock_project(status=ProjectStatus.COMPLETED):
    project = MagicMock()
    project.id = uuid.UUID("00000000-0000-0000-0000-000000000020")
    project.user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    project.name = "Test Project"
    project.gdrive_folder_id = "folder-abc"
    project.gdrive_folder_url = "https://drive.google.com/drive/folders/folder-abc"
    project.sync_status = status
    project.sync_error = None
    project.files_total = 10
    project.files_processed = 10
    project.last_synced_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    project.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    project.updated_at = None
    return project


@pytest.fixture
async def sync_client():
    mock_user = _make_mock_user()
    app.dependency_overrides[get_current_user] = lambda: mock_user

    settings = get_settings()
    token = create_session(mock_user.id, settings)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: token},
        headers={"X-Requested-With": "XMLHttpRequest"},
    ) as client:
        yield client
    app.dependency_overrides.clear()


class TestTriggerSync:
    async def test_409_when_already_syncing(self, sync_client):
        """POST /api/sync/{id} returns 409 if project is already SYNCING."""
        project = _make_mock_project(status=ProjectStatus.SYNCING)
        mock_db = AsyncMock()

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = project
            return result

        mock_db.execute = mock_execute
        mock_db.flush = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            resp = await sync_client.post(f"/api/sync/{project.id}")
            assert resp.status_code == 409
            assert "already in progress" in resp.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_timeout_sets_failed_with_message(self, sync_client):
        """Timeout during sync sets FAILED status with descriptive message."""
        project = _make_mock_project(status=ProjectStatus.COMPLETED)
        mock_db = AsyncMock()

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = project
            return result

        mock_db.execute = mock_execute
        mock_db.flush = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            with patch(
                "app.routers.sync.get_valid_access_token",
                new_callable=AsyncMock,
                side_effect=httpx.ReadTimeout("timeout"),
            ):
                resp = await sync_client.post(f"/api/sync/{project.id}")
                assert resp.status_code == 200
                assert project.sync_status == ProjectStatus.FAILED
                assert "timed out" in (project.sync_error or "").lower()
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_401_drive_error_sets_auth_message(self, sync_client):
        """401 from Drive API sets auth-expired error message."""
        project = _make_mock_project(status=ProjectStatus.COMPLETED)
        mock_db = AsyncMock()

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = project
            return result

        mock_db.execute = mock_execute
        mock_db.flush = AsyncMock()

        async def override_get_db():
            yield mock_db

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_request = MagicMock()

        app.dependency_overrides[get_db] = override_get_db
        try:
            with patch(
                "app.routers.sync.get_valid_access_token",
                new_callable=AsyncMock,
                return_value="token-123",
            ), patch(
                "app.routers.sync.GoogleDriveService"
            ) as MockDrive:
                MockDrive.return_value.count_files = AsyncMock(
                    side_effect=httpx.HTTPStatusError(
                        "401", request=mock_request, response=mock_response
                    )
                )
                resp = await sync_client.post(f"/api/sync/{project.id}")
                assert resp.status_code == 200
                assert project.sync_status == ProjectStatus.FAILED
                assert "authorization" in (project.sync_error or "").lower()
        finally:
            app.dependency_overrides.pop(get_db, None)
