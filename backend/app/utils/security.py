import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "session_id"

# Session TTL in seconds (24 hours)
SESSION_MAX_AGE = 60 * 60 * 24

# In-memory set of explicitly-invalidated session tokens (e.g. from logout).
# Only needs to survive until the token's TTL expires naturally.
_revoked: set[str] = set()


def _get_fernet(settings: Settings) -> Fernet:
    """Create a Fernet cipher from the configured encryption key."""
    return Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt_token(token: str, settings: Settings) -> str:
    """Encrypt a token string using Fernet symmetric encryption."""
    f = _get_fernet(settings)
    return f.encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str, settings: Settings) -> str:
    """Decrypt a Fernet-encrypted token string."""
    f = _get_fernet(settings)
    return f.decrypt(encrypted_token.encode()).decode()


def create_session(user_id: uuid.UUID, settings: Settings) -> str:
    """
    Create a stateless session token.

    The cookie value is the Fernet-encrypted user_id.  Fernet embeds a
    timestamp so ``validate_session`` can enforce a TTL without any
    server-side state.
    """
    f = _get_fernet(settings)
    return f.encrypt(str(user_id).encode()).decode()


def validate_session(session_id: str, settings: Settings) -> Optional[str]:
    """
    Validate a session token and return the user_id, or None.

    Uses Fernet's built-in timestamp to enforce ``SESSION_MAX_AGE``.
    """
    if session_id in _revoked:
        return None
    try:
        f = _get_fernet(settings)
        user_id_bytes = f.decrypt(
            session_id.encode(), ttl=SESSION_MAX_AGE
        )
        return user_id_bytes.decode()
    except (InvalidToken, Exception):
        return None


def delete_session(session_id: str) -> None:
    """Revoke a session token so it can't be reused before TTL expiry."""
    _revoked.add(session_id)


# ---------------------------------------------------------------------------
# Google OAuth token refresh
# ---------------------------------------------------------------------------

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Refresh if the token expires within this buffer
_EXPIRY_BUFFER = timedelta(minutes=5)


async def get_valid_access_token(
    user: "object",  # app.models.user.User — quoted to avoid circular import
    settings: Settings,
    db: AsyncSession,
) -> str:
    """Return a valid Google access token, refreshing it if expired.

    1. Checks ``user.token_expires_at`` against the current time.
    2. If still valid, decrypts and returns the stored access token.
    3. If expired (or about to expire), uses the refresh token to get a new one,
       updates the user row in the DB, and returns the fresh token.
    4. Raises ``HTTPException(401)`` if refresh is impossible (no refresh token,
       revoked access, etc.).
    """
    from fastapi import HTTPException, status  # deferred to avoid import cycles

    now = datetime.now(timezone.utc)
    expires_at = getattr(user, "token_expires_at", None)

    # If the token isn't expired yet, just return it
    if expires_at and expires_at > now + _EXPIRY_BUFFER:
        return decrypt_token(user.google_access_token, settings)

    # Token is expired or about to expire — refresh it
    logger.info("[AUTH] Access token expired for user=%s, refreshing...", user.email)

    refresh_token_encrypted = getattr(user, "google_refresh_token", None)
    if not refresh_token_encrypted:
        logger.error("[AUTH] No refresh token stored for user=%s", user.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your Google session has expired. Please sign in again.",
        )

    refresh_token = decrypt_token(refresh_token_encrypted, settings)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )

        if resp.status_code != 200:
            logger.error(
                "[AUTH] Token refresh failed for user=%s: status=%d body=%s",
                user.email, resp.status_code, resp.text[:500],
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Your Google session has expired. Please sign in again.",
            )

        token_data = resp.json()
        new_access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)

        # Persist the refreshed token to the DB
        user.google_access_token = encrypt_token(new_access_token, settings)
        user.token_expires_at = now + timedelta(seconds=expires_in)
        await db.flush()

        logger.info(
            "[AUTH] Token refreshed for user=%s, expires in %ds",
            user.email, expires_in,
        )
        return new_access_token

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[AUTH] Token refresh error for user=%s: %s", user.email, exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your Google session has expired. Please sign in again.",
        ) from exc
