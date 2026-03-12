"""Database-based Google OAuth token retrieval for benchmark runs."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root + backend are on sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_BACKEND = str(Path(_PROJECT_ROOT) / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


async def get_access_token_from_db(user_email: str | None = None) -> str:
    """Connect to the DB, find a user, and return a valid access token.

    Uses the same token-refresh logic as the main app. If the token is
    expired, it will be refreshed via Google's OAuth endpoint and the
    new token persisted to the DB.
    """
    from app.dependencies import get_settings
    from app.models.user import User
    from app.utils.security import get_valid_access_token

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            if user_email:
                result = await db.execute(
                    select(User).where(User.email == user_email)
                )
            else:
                result = await db.execute(
                    select(User).order_by(User.created_at.asc()).limit(1)
                )
            user = result.scalar_one_or_none()
            if not user:
                raise RuntimeError(
                    f"No user found in database"
                    + (f" with email {user_email}" if user_email else "")
                )

            try:
                token = await get_valid_access_token(user, settings, db)
            except Exception as exc:
                # get_valid_access_token raises FastAPI HTTPException on
                # failure — convert to RuntimeError for benchmark use
                detail = getattr(exc, "detail", str(exc))
                raise RuntimeError(f"Token retrieval failed: {detail}") from exc

            await db.commit()  # persist any refreshed token
            return token
    finally:
        await engine.dispose()


async def resolve_access_token(
    access_token: str | None,
    user_email: str | None,
) -> str:
    """Return raw token if provided, otherwise fetch from DB."""
    if access_token:
        return access_token
    return await get_access_token_from_db(user_email)
