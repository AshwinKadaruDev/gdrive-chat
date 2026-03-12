"""Tests for AuthGuardMiddleware — 401 for unauthenticated requests, CSRF header check."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.utils.security import SESSION_COOKIE_NAME, create_session
from app.dependencies import get_settings


@pytest.fixture
async def unauthed_client():
    """Unauthenticated test client — no cookies, no overrides."""
    app.dependency_overrides.pop(
        __import__("app.dependencies", fromlist=["get_current_user"]).get_current_user,
        None,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
async def authed_client_no_csrf():
    """Authenticated client WITHOUT X-Requested-With header."""
    settings = get_settings()
    token = create_session(
        uuid.UUID("00000000-0000-0000-0000-000000000001"), settings
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: token},
    ) as client:
        yield client


class TestAuthGuard:
    """Unauthenticated requests to /api/* should get 401."""

    async def test_projects_requires_auth(self, unauthed_client):
        resp = await unauthed_client.get("/api/projects")
        assert resp.status_code == 401

    async def test_chat_requires_auth(self, unauthed_client):
        resp = await unauthed_client.post(
            "/api/chat",
            json={"message": "hi"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 401

    async def test_sync_requires_auth(self, unauthed_client):
        resp = await unauthed_client.post(
            "/api/sync/some-id",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 401

    async def test_auth_routes_remain_accessible(self, unauthed_client):
        """GET /auth/me should return 401 from the dependency, not from the guard."""
        resp = await unauthed_client.get("/auth/me")
        # Could be 401 (from get_current_user) or 422 — but NOT blocked by guard
        assert resp.status_code in (401, 422)

    async def test_auth_login_accessible(self, unauthed_client):
        resp = await unauthed_client.get(
            "/auth/google/login", follow_redirects=False
        )
        assert resp.status_code == 307


class TestCSRFProtection:
    """State-changing methods on /api/* require X-Requested-With header."""

    async def test_post_without_csrf_header_returns_403(self, authed_client_no_csrf):
        resp = await authed_client_no_csrf.post(
            "/api/chat",
            json={"message": "hi"},
        )
        assert resp.status_code == 403
        assert "CSRF" in resp.json()["detail"]

    async def test_delete_without_csrf_header_returns_403(self, authed_client_no_csrf):
        resp = await authed_client_no_csrf.delete(
            "/api/chat/sessions/00000000-0000-0000-0000-000000000001",
        )
        assert resp.status_code == 403

    async def test_get_without_csrf_header_is_allowed(self, authed_client_no_csrf):
        """GET requests should not require the CSRF header."""
        resp = await authed_client_no_csrf.get("/api/projects")
        # May be 401 (if get_current_user fails) or 200, but NOT 403
        assert resp.status_code != 403
