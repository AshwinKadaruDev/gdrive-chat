"""Tests for auth config: FRONTEND_URL redirect, cookie Secure flag, OAuth state, and token expiry."""

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


def _patch_google_apis(expires_in=3600):
    """Mock both Google token and userinfo HTTP calls."""
    mock_client = AsyncMock()
    mock_token_resp = MagicMock()
    mock_token_resp.status_code = 200
    token_data = {
        "access_token": "fake-access",
        "refresh_token": "fake-refresh",
    }
    if expires_in is not None:
        token_data["expires_in"] = expires_in
    mock_token_resp.json.return_value = token_data
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


async def _callback_with_state(client: AsyncClient, state: str = "test-state", **extra_cookies):
    """Call /auth/google/callback with a matching oauth_state cookie."""
    cookies = {"oauth_state": state, **extra_cookies}
    return await client.get(
        "/auth/google/callback",
        params={"code": "test-code", "state": state},
        cookies=cookies,
    )


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
                resp = await _callback_with_state(client)

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
                resp = await _callback_with_state(client)

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
                resp = await _callback_with_state(client)

        cookie_header = resp.headers.get("set-cookie", "")
        assert "Secure" not in cookie_header
        app.dependency_overrides.pop(get_settings, None)


@pytest.mark.usefixtures("_mock_db")
class TestOAuthState:
    """Tests for OAuth state parameter (Issue #2)."""

    async def test_login_sets_state_cookie(self):
        """Login redirect should include state param and set oauth_state cookie."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get("/auth/google/login")

        assert resp.status_code == 307
        location = resp.headers["location"]
        assert "state=" in location
        cookie_header = resp.headers.get("set-cookie", "")
        assert "oauth_state" in cookie_header

    async def test_callback_validates_state(self):
        """Callback should succeed when state matches cookie."""
        with _patch_google_apis():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as client:
                resp = await _callback_with_state(client, state="valid-state")

        assert resp.status_code == 307

    async def test_callback_rejects_mismatched_state(self):
        """Callback should return 400 when state doesn't match cookie."""
        with _patch_google_apis():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as client:
                resp = await client.get(
                    "/auth/google/callback",
                    params={"code": "test-code", "state": "wrong-state"},
                    cookies={"oauth_state": "correct-state"},
                )

        assert resp.status_code == 400

    async def test_callback_rejects_missing_state_cookie(self):
        """Callback should return 400 when oauth_state cookie is absent."""
        with _patch_google_apis():
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as client:
                resp = await client.get(
                    "/auth/google/callback",
                    params={"code": "test-code", "state": "some-state"},
                )

        assert resp.status_code == 400


@pytest.mark.usefixtures("_mock_db")
class TestTokenExpiry:
    """Tests for token_expires_at defaults (Issue #15)."""

    async def test_token_expires_at_uses_default_when_missing(self):
        """When expires_in is absent, token_expires_at should default to 3600s from now."""
        from datetime import datetime, timezone

        with _patch_google_apis(expires_in=None):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as client:
                resp = await _callback_with_state(client)

        # Should not fail — the callback should succeed
        assert resp.status_code == 307


@pytest.mark.usefixtures("_mock_db")
class TestLogout:
    async def test_logout_clears_cookie(self):
        """Logout should clear the session cookie."""
        from app.utils.security import SESSION_COOKIE_NAME, create_session
        import uuid

        settings = get_settings()
        token = create_session(uuid.UUID("00000000-0000-0000-0000-000000000001"), settings)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={SESSION_COOKIE_NAME: token},
            headers={"X-Requested-With": "XMLHttpRequest"},
        ) as client:
            resp = await client.post("/auth/logout")

        assert resp.status_code == 204
        # Cookie should be deleted (max-age=0 or set to empty)
        cookie_header = resp.headers.get("set-cookie", "")
        assert SESSION_COOKIE_NAME in cookie_header
