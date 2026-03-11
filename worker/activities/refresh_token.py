"""Activity: refresh an expired Google OAuth access token."""

from __future__ import annotations

import logging
import os

import httpx
from temporalio import activity
from temporalio.exceptions import ApplicationError

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


@activity.defn
async def refresh_google_token(refresh_token: str) -> str:
    """Exchange a Google refresh token for a new access token.

    Reads GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET from env vars.

    Returns:
        The new access token string.

    Raises:
        ApplicationError (non-retryable): If the refresh token is invalid,
        revoked, or the OAuth credentials are misconfigured.
    """
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        raise ApplicationError(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set",
            type="CONFIG_ERROR",
            non_retryable=True,
        )

    if not refresh_token:
        raise ApplicationError(
            "No refresh token available. Please sign in again.",
            type="TOKEN_EXPIRED",
            non_retryable=True,
        )

    activity.logger.info("[REFRESH] Refreshing Google access token...")

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )

    if response.status_code != 200:
        logger.error(
            "[REFRESH] Token refresh failed: status=%d body=%s",
            response.status_code,
            response.text[:500],
        )
        raise ApplicationError(
            "Google Drive authorization has expired or been revoked. "
            "Please sign in again and re-sync your folder.",
            type="TOKEN_EXPIRED",
            non_retryable=True,
        )

    new_token = response.json().get("access_token", "")
    if not new_token:
        raise ApplicationError(
            "Google returned an empty access token. Please sign in again.",
            type="TOKEN_EXPIRED",
            non_retryable=True,
        )

    activity.logger.info("[REFRESH] Successfully refreshed access token (length=%d)", len(new_token))
    return new_token
