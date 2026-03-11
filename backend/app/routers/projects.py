"""Projects router – CRUD operations for Google Drive folder projects."""

from __future__ import annotations

import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.dependencies import get_current_user, get_db, get_settings
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.schemas.project import (
    FolderValidateRequest,
    FolderValidateResponse,
    ProjectCreate,
    ProjectResponse,
)
from app.services.google_drive import DriveValidationError, GoogleDriveService
from app.utils.security import get_valid_access_token

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FOLDER_ID_PATTERN = re.compile(
    r"(?:https?://)?drive\.google\.com/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]+)"
)


def _extract_folder_id(url: str) -> str:
    """
    Extract the Google Drive folder ID from a URL such as
    ``https://drive.google.com/drive/folders/1aBcD_eFgHiJk``

    Falls back to returning the raw string if it does not look like a URL
    (in case the caller already passed a bare folder ID).
    """
    match = _FOLDER_ID_PATTERN.search(url)
    if match:
        return match.group(1)
    # If the input looks like a bare folder ID (no slashes), accept it as-is.
    if "/" not in url and len(url) > 5:
        return url
    raise ValueError(f"Cannot parse Google Drive folder ID from: {url}")


async def _get_user_project(
    project_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> Project:
    """Return a project owned by *user* or raise 404."""
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
# POST /validate-folder – validate a Google Drive folder URL
# ---------------------------------------------------------------------------
@router.post("/validate-folder", response_model=FolderValidateResponse)
async def validate_folder(
    body: FolderValidateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Validate that a Google Drive URL points to an accessible folder."""
    try:
        folder_id = _extract_folder_id(body.gdrive_folder_url)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please enter a valid Google Drive folder URL.",
            headers={"X-Error-Code": "invalid_url"},
        )

    access_token = await get_valid_access_token(user, settings, db)
    try:
        metadata = await GoogleDriveService().validate_folder(
            folder_id, access_token
        )
    except DriveValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.message,
            headers={"X-Error-Code": exc.code},
        )

    return FolderValidateResponse(
        folder_id=metadata["id"],
        folder_name=metadata["name"],
        gdrive_folder_url=body.gdrive_folder_url,
    )


# ---------------------------------------------------------------------------
# GET / – list projects
# ---------------------------------------------------------------------------
@router.get("/", response_model=list[ProjectResponse])
async def list_projects(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all projects belonging to the current user."""
    result = await db.execute(
        select(Project)
        .where(Project.user_id == user.id)
        .order_by(Project.created_at.desc())
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# POST / – create project
# ---------------------------------------------------------------------------
@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Create a new project from a Google Drive folder URL.

    The folder ID is extracted from the provided URL.  If ``name`` is omitted
    the folder name is fetched from Google Drive automatically.
    """
    try:
        folder_id = _extract_folder_id(body.gdrive_folder_url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    # Duplicate check
    existing = await db.execute(
        select(Project).where(
            Project.user_id == user.id,
            Project.gdrive_folder_id == folder_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This folder has already been added.",
            headers={"X-Error-Code": "duplicate"},
        )

    # Auto-fetch folder name from Drive if not provided
    access_token = await get_valid_access_token(user, settings, db)
    name = body.name
    if not name:
        try:
            metadata = await GoogleDriveService().validate_folder(
                folder_id, access_token
            )
            name = metadata["name"]
        except Exception:
            name = folder_id  # last-resort fallback

    # Count files so the card shows the correct total immediately
    files_total = 0
    try:
        files_total = await GoogleDriveService().count_files(folder_id, access_token)
        logger.info("[PROJECT] Counted %d files in folder %s", files_total, folder_id)
    except Exception as exc:
        logger.warning("[PROJECT] Could not count files for %s: %s: %s", folder_id, type(exc).__name__, exc)

    project = Project(
        user_id=user.id,
        name=name,
        gdrive_folder_id=folder_id,
        gdrive_folder_url=body.gdrive_folder_url,
        sync_status=ProjectStatus.PENDING,
        files_total=files_total,
    )
    db.add(project)
    await db.flush()
    logger.info(
        "[PROJECT] Created project id=%s name=%s folder_id=%s files_total=%d",
        project.id, project.name, project.gdrive_folder_id, project.files_total,
    )
    return project


# ---------------------------------------------------------------------------
# GET /{project_id} – single project
# ---------------------------------------------------------------------------
@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a single project by ID."""
    return await _get_user_project(project_id, user, db)


# ---------------------------------------------------------------------------
# DELETE /{project_id} – delete project
# ---------------------------------------------------------------------------
@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Delete a project and remove its documents from the Azure AI Search index.
    """
    project = await _get_user_project(project_id, user, db)

    # Attempt to clean up the Azure AI Search index for this project.
    try:
        from app.services import AzureSearchService

        search_service = AzureSearchService(
            endpoint=settings.AZURE_SEARCH_ENDPOINT,
            api_key=settings.AZURE_SEARCH_API_KEY,
            index_name=settings.AZURE_SEARCH_INDEX_NAME,
        )
        await search_service.delete_by_project(str(project_id))
    except Exception:
        # Non-fatal – the project is still deleted from the database even if
        # index cleanup fails (e.g. service not configured yet).
        pass

    await db.delete(project)
    await db.flush()
