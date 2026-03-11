import uuid
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings

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
