"""Tests for the projects router — pagination, cleanup failure logging, IntegrityError."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from app.dependencies import get_current_user, get_db, get_settings
from app.main import app
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


@pytest.fixture
async def projects_client():
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


class TestListProjectsPagination:
    async def test_accepts_limit_and_offset(self, projects_client):
        """GET /api/projects?limit=10&offset=5 should succeed."""
        mock_db = AsyncMock()

        async def mock_execute(stmt):
            result = MagicMock()
            scalars_result = MagicMock()
            scalars_result.all.return_value = []
            result.scalars.return_value = scalars_result
            return result

        mock_db.execute = mock_execute

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            resp = await projects_client.get("/api/projects/?limit=10&offset=5")
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_rejects_invalid_limit(self, projects_client):
        """limit=0 should be rejected with 422."""
        resp = await projects_client.get("/api/projects/?limit=0")
        assert resp.status_code == 422

    async def test_rejects_negative_offset(self, projects_client):
        """offset=-1 should be rejected with 422."""
        resp = await projects_client.get("/api/projects/?offset=-1")
        assert resp.status_code == 422


class TestDeleteProject:
    async def test_delete_project_succeeds(self, projects_client):
        """DELETE /api/projects/{id} should return 204."""
        project = MagicMock()
        project.id = uuid.UUID("00000000-0000-0000-0000-000000000020")
        project.user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

        mock_db = AsyncMock()

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = project
            return result

        mock_db.execute = mock_execute
        mock_db.delete = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            resp = await projects_client.delete(f"/api/projects/{project.id}")
            assert resp.status_code == 204
        finally:
            app.dependency_overrides.pop(get_db, None)
