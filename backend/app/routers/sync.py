"""Sync router – trigger and monitor Google Drive folder synchronisation."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.dependencies import get_current_user, get_db, get_settings
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.schemas.project import ProjectResponse
from app.services.google_drive import GoogleDriveService
from app.utils.security import get_valid_access_token

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_user_project(
    project_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> Project:
    """Return the project if it belongs to *user*, else raise 404."""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == user.id,
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project


# ---------------------------------------------------------------------------
# POST /{project_id} – trigger sync
# ---------------------------------------------------------------------------
@router.post("/{project_id}", response_model=ProjectResponse)
async def trigger_sync(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Trigger a folder sync for the given project.

    Marks the project as ``SYNCING``, counts files via the Google Drive API,
    then marks it ``COMPLETED``.
    """
    logger.info(
        "[SYNC] trigger_sync called for project_id=%s by user=%s",
        project_id, user.id,
    )

    # Use row lock to prevent race conditions on sync status check
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id, Project.user_id == user.id)
        .with_for_update()
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    logger.info(
        "[SYNC] Project found: name=%s, folder_id=%s, current_status=%s",
        project.name, project.gdrive_folder_id, project.sync_status,
    )

    if project.sync_status == ProjectStatus.SYNCING:
        logger.warning("[SYNC] Sync already in progress for project %s", project_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A sync is already in progress for this project",
        )

    # Mark as syncing -------------------------------------------------------
    project.sync_status = ProjectStatus.SYNCING
    project.sync_error = None
    await db.flush()
    logger.info("[SYNC] Marked project %s as SYNCING", project_id)

    # Count files via Google Drive API ----------------------------------------
    try:
        user_access_token = await get_valid_access_token(user, settings, db)
        logger.info("[SYNC] Token ready (length=%d), counting files...", len(user_access_token))

        drive_service = GoogleDriveService()
        file_count = await drive_service.count_files(
            project.gdrive_folder_id, user_access_token
        )
        logger.info("[SYNC] Counted %d files in folder %s", file_count, project.gdrive_folder_id)

        project.files_total = file_count
        project.files_processed = file_count
        project.sync_status = ProjectStatus.COMPLETED
        project.last_synced_at = datetime.now(timezone.utc)
        project.sync_error = None
        await db.flush()
        logger.info(
            "[SYNC] Project %s synced: files_total=%d, status=COMPLETED",
            project_id, file_count,
        )
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code == 401:
            error_msg = "Google Drive authorization expired. Please sign in again."
        elif code == 403:
            error_msg = "Permission denied — check that the folder is shared with your account."
        else:
            error_msg = f"Google Drive API error (HTTP {code})."
        logger.error("[SYNC] FAILED for project %s: %s", project_id, error_msg, exc_info=True)
        project.sync_status = ProjectStatus.FAILED
        project.sync_error = error_msg
        await db.flush()
    except httpx.TimeoutException:
        error_msg = "Timed out connecting to Google Drive. Please try again."
        logger.error("[SYNC] FAILED for project %s: %s", project_id, error_msg)
        project.sync_status = ProjectStatus.FAILED
        project.sync_error = error_msg
        await db.flush()
    except Exception as exc:
        error_msg = f"Sync failed: {type(exc).__name__}: {exc}"
        logger.error(
            "[SYNC] FAILED for project %s: %s",
            project_id, error_msg,
            exc_info=True,
        )
        project.sync_status = ProjectStatus.FAILED
        project.sync_error = error_msg
        await db.flush()

    return project


# ---------------------------------------------------------------------------
# GET /{project_id}/status – check sync status
# ---------------------------------------------------------------------------
@router.get("/{project_id}/status", response_model=ProjectResponse)
async def get_sync_status(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current sync status for a project."""
    # Refresh from the DB so we get the latest status.
    project = await _get_user_project(project_id, user, db)
    logger.info(
        "[SYNC-STATUS] project=%s status=%s files=%d/%d",
        project_id, project.sync_status, project.files_processed, project.files_total,
    )
    return project
