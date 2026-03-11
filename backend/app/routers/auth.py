"""Authentication router – Google OAuth 2.0 login/callback, logout, and /me."""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.dependencies import get_current_user, get_db, get_settings
from app.models.user import User
from app.schemas.user import UserResponse
from app.utils.security import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE,
    create_session,
    delete_session,
    encrypt_token,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Google OAuth helpers
# ---------------------------------------------------------------------------

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
OAUTH_SCOPES = "openid email profile https://www.googleapis.com/auth/drive.readonly"


# ---------------------------------------------------------------------------
# GET /google/login
# ---------------------------------------------------------------------------
@router.get("/google/login")
async def google_login(settings: Settings = Depends(get_settings)):
    """Redirect the user to the Google OAuth consent screen."""

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": OAUTH_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

    return Response(
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers={"Location": url},
    )


# ---------------------------------------------------------------------------
# GET /google/callback
# ---------------------------------------------------------------------------
@router.get("/google/callback")
async def google_callback(
    code: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Handle the OAuth callback from Google.

    1. Exchange the authorization code for tokens.
    2. Fetch user profile information.
    3. Create or update the User row (encrypting tokens at rest).
    4. Create an application session and set the session cookie.
    5. Redirect to the frontend.
    """

    # 1. Exchange code for tokens -------------------------------------------
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

    if token_response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to exchange authorization code for tokens",
        )

    token_data = token_response.json()
    access_token: str = token_data["access_token"]
    refresh_token: str | None = token_data.get("refresh_token")
    expires_in: int | None = token_data.get("expires_in")

    # 2. Fetch user info ----------------------------------------------------
    async with httpx.AsyncClient() as client:
        userinfo_response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if userinfo_response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to fetch user info from Google",
        )

    userinfo = userinfo_response.json()
    email: str = userinfo["email"]
    name: str = userinfo.get("name", email)
    picture_url: str | None = userinfo.get("picture")

    # 3. Upsert user -------------------------------------------------------
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    encrypted_access = encrypt_token(access_token, settings)
    encrypted_refresh = (
        encrypt_token(refresh_token, settings) if refresh_token else None
    )
    token_expires_at = (
        datetime.now(timezone.utc).replace(microsecond=0)
        if expires_in is None
        else datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() + expires_in, tz=timezone.utc
        )
    )

    if user is None:
        user = User(
            email=email,
            name=name,
            picture_url=picture_url,
            google_access_token=encrypted_access,
            google_refresh_token=encrypted_refresh,
            token_expires_at=token_expires_at,
        )
        db.add(user)
    else:
        user.name = name
        user.picture_url = picture_url
        user.google_access_token = encrypted_access
        if encrypted_refresh is not None:
            user.google_refresh_token = encrypted_refresh
        user.token_expires_at = token_expires_at

    await db.flush()

    # 4. Create session and set cookie --------------------------------------
    session_id = create_session(user.id, settings)

    response = Response(
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers={"Location": settings.FRONTEND_URL},
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=settings.FRONTEND_URL.startswith("https"),
        max_age=SESSION_MAX_AGE,
        path="/",
    )
    return response


# ---------------------------------------------------------------------------
# POST /logout
# ---------------------------------------------------------------------------
@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request):
    """Clear the session cookie and invalidate the server-side session."""

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        delete_session(session_id)

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )
    return response


# ---------------------------------------------------------------------------
# GET /me
# ---------------------------------------------------------------------------
@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    """Return the current authenticated user's profile."""
    return user
