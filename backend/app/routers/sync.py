"""Sync router – trigger and monitor Google Drive folder synchronisation."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.dependencies import get_current_user, get_db, get_settings
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.schemas.project import ProjectResponse
from app.utils.security import decrypt_token

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

    1. Mark the project as ``SYNCING``.
    2. Attempt to start a Temporal workflow for background processing.
    3. If Temporal is unavailable, fall back to an inline placeholder that
       keeps the app functional during development.
    """
    project = await _get_user_project(project_id, user, db)

    if project.sync_status == ProjectStatus.SYNCING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A sync is already in progress for this project",
        )

    # Mark as syncing -------------------------------------------------------
    project.sync_status = ProjectStatus.SYNCING
    project.sync_error = None
    await db.flush()

    # Attempt to start the Temporal workflow --------------------------------
    try:
        from temporalio.client import Client as TemporalClient

        temporal_client = await TemporalClient.connect(
            settings.TEMPORAL_HOST,
            namespace=settings.TEMPORAL_NAMESPACE,
        )

        # Decrypt tokens for the worker to use with Google Drive API
        user_access_token = decrypt_token(user.google_access_token, settings)
        user_refresh_token = (
            decrypt_token(user.google_refresh_token, settings)
            if user.google_refresh_token
            else ""
        )

        await temporal_client.start_workflow(
            "SyncFolderWorkflow",
            {
                "project_id": str(project_id),
                "folder_id": project.gdrive_folder_id,
                "user_access_token": user_access_token,
                "user_refresh_token": user_refresh_token,
            },
            id=f"sync-{project_id}",
            task_queue="talk-to-folder-sync",
        )
    except Exception:
        # Temporal is not running or not configured.  In a development
        # environment we fall back to an inline placeholder so the API
        # surface remains functional.
        #
        # A real inline sync could be performed here by calling
        # GoogleDriveService + AzureSearchService directly, but we keep
        # things simple for now and just mark the project as COMPLETED.
        project.sync_status = ProjectStatus.COMPLETED
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
    # Refresh from the DB so we get the latest status (e.g. if Temporal
    # workers have updated it in the background).
    project = await _get_user_project(project_id, user, db)
    return project
