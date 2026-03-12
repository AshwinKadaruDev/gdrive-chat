import uuid
from functools import lru_cache
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.utils.security import SESSION_COOKIE_NAME, validate_session


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (loaded once from env / .env)."""
    return Settings()


# Lazy-initialised engine and session factory.
# They are created on first call to get_db() so that Settings are available.
_engine = None
_async_session_factory = None


def _init_db() -> async_sessionmaker[AsyncSession]:
    global _engine, _async_session_factory
    if _async_session_factory is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
        )
        _async_session_factory = async_sessionmaker(
            _engine,
            expire_on_commit=False,
        )
    return _async_session_factory


async def dispose_engine() -> None:
    """Dispose the async engine on shutdown."""
    global _engine, _async_session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, rolling back on error."""
    factory = _init_db()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Extract the current user from the session cookie.

    Raises 401 if no valid session is found.
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user_id_str = validate_session(session_id, settings)
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    # Import here to avoid circular imports at module level
    from app.models.user import User

    user_id = uuid.UUID(user_id_str)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user
