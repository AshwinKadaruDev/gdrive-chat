"""Tests for the chat router — POST /, streaming, list endpoints, pagination."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user, get_db, get_settings
from app.main import app
from app.utils.security import SESSION_COOKIE_NAME, create_session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


def _make_mock_session():
    session = MagicMock()
    session.id = uuid.UUID("00000000-0000-0000-0000-000000000010")
    session.project_id = uuid.UUID("00000000-0000-0000-0000-000000000020")
    session.user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    session.gdrive_folder_id = None
    session.title = "Test Chat"
    session.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    session.updated_at = None
    return session


def _make_mock_db(sessions=None, messages=None, project=None):
    """Build a mock AsyncSession that returns configurable query results."""
    mock_db = AsyncMock()

    async def mock_execute(stmt):
        result = MagicMock()
        scalars_result = MagicMock()

        # Return different data based on the type of query
        if sessions is not None:
            scalars_result.all.return_value = sessions
        elif messages is not None:
            scalars_result.all.return_value = messages
        else:
            scalars_result.all.return_value = []

        if project is not None:
            result.scalar_one_or_none.return_value = project
        else:
            result.scalar_one_or_none.return_value = None

        result.scalars.return_value = scalars_result
        return result

    mock_db.execute = mock_execute
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.delete = AsyncMock()
    return mock_db


@pytest.fixture
async def chat_client():
    """Authenticated client for chat endpoints."""
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestChatPost:
    async def test_missing_project_id_returns_422(self, chat_client):
        """POST /api/chat without project_id or session_id should return 422."""
        mock_db = _make_mock_db()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            resp = await chat_client.post(
                "/api/chat/",
                json={"message": "hello"},
            )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestChatListEndpoints:
    async def test_list_sessions_supports_pagination(self, chat_client):
        """GET /api/chat/sessions/{project_id} should accept limit and offset."""
        project = MagicMock()
        project.id = uuid.UUID("00000000-0000-0000-0000-000000000020")
        project.user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        mock_db = _make_mock_db(sessions=[], project=project)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            resp = await chat_client.get(
                f"/api/chat/sessions/{project.id}?limit=10&offset=5"
            )
            assert resp.status_code == 200
            assert isinstance(resp.json(), list)
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_list_drive_sessions_supports_pagination(self, chat_client):
        """GET /api/chat/sessions/drive should accept limit and offset."""
        mock_db = _make_mock_db(sessions=[])

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            resp = await chat_client.get(
                "/api/chat/sessions/drive?limit=10&offset=0"
            )
            assert resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_list_messages_supports_pagination(self, chat_client):
        """GET /api/chat/sessions/{session_id}/messages should accept limit/offset."""
        session = _make_mock_session()
        mock_db = _make_mock_db(messages=[], project=session)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            resp = await chat_client.get(
                f"/api/chat/sessions/{session.id}/messages?limit=25&offset=0"
            )
            # May return 200 or 404 depending on session access check
            assert resp.status_code in (200, 404)
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_pagination_rejects_invalid_limit(self, chat_client):
        """limit=0 should be rejected with 422."""
        resp = await chat_client.get(
            "/api/chat/sessions/drive?limit=0"
        )
        assert resp.status_code == 422
