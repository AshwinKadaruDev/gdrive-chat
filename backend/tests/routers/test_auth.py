"""Tests for the auth router — JSONDecodeError guards on Google responses."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_db
from app.main import app


@pytest.fixture
async def auth_client():
    """Unauthenticated client for auth endpoints (no session needed)."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


class TestGoogleCallbackJSONGuard:
    async def test_malformed_token_response_returns_502(self, auth_client):
        """If Google token endpoint returns invalid JSON, callback returns 502."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            # Mock the httpx.AsyncClient to return malformed JSON
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.side_effect = ValueError("No JSON object")

            with patch("app.routers.auth.httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                resp = await auth_client.get(
                    "/auth/google/callback?code=test-code&state=test-state",
                    cookies={"oauth_state": "test-state"},
                    follow_redirects=False,
                )
                assert resp.status_code == 502
                assert "token" in resp.json()["detail"].lower()
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_malformed_userinfo_response_returns_502(self, auth_client):
        """If Google userinfo endpoint returns invalid JSON, callback returns 502."""
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        try:
            # First call (token exchange) returns valid JSON
            token_response = MagicMock()
            token_response.status_code = 200
            token_response.json.return_value = {
                "access_token": "test-access",
                "refresh_token": "test-refresh",
                "expires_in": 3600,
            }

            # Second call (userinfo) returns invalid JSON
            userinfo_response = MagicMock()
            userinfo_response.status_code = 200
            userinfo_response.json.side_effect = ValueError("No JSON object")

            call_count = 0

            with patch("app.routers.auth.httpx.AsyncClient") as MockClient:
                mock_client = AsyncMock()

                async def mock_post(*args, **kwargs):
                    return token_response

                async def mock_get(*args, **kwargs):
                    return userinfo_response

                mock_client.post = mock_post
                mock_client.get = mock_get
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = mock_client

                resp = await auth_client.get(
                    "/auth/google/callback?code=test-code&state=test-state",
                    cookies={"oauth_state": "test-state"},
                    follow_redirects=False,
                )
                assert resp.status_code == 502
                assert "userinfo" in resp.json()["detail"].lower()
        finally:
            app.dependency_overrides.pop(get_db, None)
