"""Tests for get_valid_access_token in utils/security.py."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.utils.security import get_valid_access_token


def _make_user(expires_in_minutes: int = 60, has_refresh: bool = True):
    """Create a mock User with configurable token expiry."""
    user = MagicMock()
    user.email = "test@example.com"
    user.google_access_token = "encrypted-access-token"
    user.google_refresh_token = "encrypted-refresh-token" if has_refresh else None
    user.token_expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)
    return user


def _make_settings():
    settings = MagicMock()
    settings.ENCRYPTION_KEY = "dGVzdC1rZXktMTIzNDU2Nzg5MDEyMzQ1Ng=="
    settings.GOOGLE_CLIENT_ID = "test-client-id"
    settings.GOOGLE_CLIENT_SECRET = "test-client-secret"
    return settings


class TestGetValidAccessToken:

    @patch("app.utils.security.decrypt_token", return_value="valid-access-token")
    async def test_returns_current_token_when_not_expired(self, mock_decrypt):
        user = _make_user(expires_in_minutes=30)
        settings = _make_settings()
        db = AsyncMock()

        token = await get_valid_access_token(user, settings, db)

        assert token == "valid-access-token"
        mock_decrypt.assert_called_once_with("encrypted-access-token", settings)
        # Should NOT have called db.flush (no refresh needed)
        db.flush.assert_not_called()

    @patch("app.utils.security.encrypt_token", return_value="new-encrypted-token")
    @patch("app.utils.security.decrypt_token", return_value="old-refresh-token")
    async def test_refreshes_when_token_expired(self, mock_decrypt, mock_encrypt):
        user = _make_user(expires_in_minutes=-10)  # expired 10 minutes ago
        settings = _make_settings()
        db = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "fresh-access-token",
            "expires_in": 3600,
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.utils.security.httpx.AsyncClient", return_value=mock_client):
            token = await get_valid_access_token(user, settings, db)

        assert token == "fresh-access-token"
        # Should have persisted the new token to the user
        assert user.google_access_token == "new-encrypted-token"
        assert user.token_expires_at > datetime.now(timezone.utc)
        db.flush.assert_called_once()

    @patch("app.utils.security.decrypt_token", return_value="old-refresh-token")
    async def test_refreshes_when_within_buffer(self, mock_decrypt):
        """Token expiring within 5 minutes should trigger refresh."""
        user = _make_user(expires_in_minutes=3)  # expires in 3 min, buffer is 5
        settings = _make_settings()
        db = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "fresh-token",
            "expires_in": 3600,
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.utils.security.httpx.AsyncClient", return_value=mock_client):
            with patch("app.utils.security.encrypt_token", return_value="enc"):
                token = await get_valid_access_token(user, settings, db)

        assert token == "fresh-token"

    async def test_raises_401_when_no_refresh_token(self):
        user = _make_user(expires_in_minutes=-10, has_refresh=False)
        settings = _make_settings()
        db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_valid_access_token(user, settings, db)

        assert exc_info.value.status_code == 401
        assert "sign in again" in exc_info.value.detail.lower()

    @patch("app.utils.security.decrypt_token", return_value="old-refresh-token")
    async def test_raises_401_when_google_rejects_refresh(self, mock_decrypt):
        user = _make_user(expires_in_minutes=-10)
        settings = _make_settings()
        db = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"error": "invalid_grant"}'

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.utils.security.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(HTTPException) as exc_info:
                await get_valid_access_token(user, settings, db)

        assert exc_info.value.status_code == 401

    @patch("app.utils.security.decrypt_token", return_value="old-refresh-token")
    async def test_refreshes_when_no_expires_at(self, mock_decrypt):
        """If token_expires_at is None (legacy), proactively refresh."""
        user = _make_user()
        user.token_expires_at = None
        settings = _make_settings()
        db = AsyncMock()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "fresh-token",
            "expires_in": 3600,
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.utils.security.httpx.AsyncClient", return_value=mock_client):
            with patch("app.utils.security.encrypt_token", return_value="enc"):
                token = await get_valid_access_token(user, settings, db)

        assert token == "fresh-token"
        db.flush.assert_called_once()
