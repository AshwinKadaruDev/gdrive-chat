"""Tests for auth config: FRONTEND_URL redirect and cookie Secure flag."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.dependencies import get_settings
from app.main import app


def _settings_override(**overrides):
    """Return a Settings factory with specific overrides applied."""
    base = get_settings()
    values = {field: getattr(base, field) for field in Settings.model_fields}
    values.update(overrides)
    return Settings(**values)


def _patch_google_apis():
    """Mock both Google token and userinfo HTTP calls."""
    mock_client = AsyncMock()
    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    mock_token_resp.json.return_value = {
        "access_token": "fake-access",
        "refresh_token": "fake-refresh",
        "expires_in": 3600,
    }
    mock_userinfo_resp = MagicMock()
    mock_userinfo_resp.status_code = 200
    mock_userinfo_resp.json.return_value = {
        "email": "test@example.com",
        "name": "Test User",
    }
    mock_client.post.return_value = mock_token_resp
    mock_client.get.return_value = mock_userinfo_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return patch("app.routers.auth.httpx.AsyncClient", return_value=mock_client)


@pytest.fixture
def _mock_db():
    """Patch get_db to return a mock async session (no real DB needed)."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # new user
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()

    from app.dependencies import get_db

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.mark.usefixtures("_mock_db")
class TestAuthConfig:
    async def test_callback_redirects_to_frontend_url(self):
        settings = _settings_override(FRONTEND_URL="http://myapp.local:3000")
        app.dependency_overrides[get_settings] = lambda: settings

        with _patch_google_apis():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as client:
                resp = await client.get("/auth/google/callback", params={"code": "test-code"})

        assert resp.status_code == 307
        assert resp.headers["location"] == "http://myapp.local:3000"
        app.dependency_overrides.pop(get_settings, None)

    async def test_cookie_secure_true_when_https(self):
        settings = _settings_override(FRONTEND_URL="https://myapp.example.com")
        app.dependency_overrides[get_settings] = lambda: settings

        with _patch_google_apis():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as client:
                resp = await client.get("/auth/google/callback", params={"code": "test-code"})

        cookie_header = resp.headers.get("set-cookie", "")
        assert "Secure" in cookie_header
        app.dependency_overrides.pop(get_settings, None)

    async def test_cookie_secure_false_when_http(self):
        settings = _settings_override(FRONTEND_URL="http://localhost:5173")
        app.dependency_overrides[get_settings] = lambda: settings

        with _patch_google_apis():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as client:
                resp = await client.get("/auth/google/callback", params={"code": "test-code"})

        cookie_header = resp.headers.get("set-cookie", "")
        assert "Secure" not in cookie_header
        app.dependency_overrides.pop(get_settings, None)
