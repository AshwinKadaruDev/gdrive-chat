import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.project import ProjectStatus


class ProjectCreate(BaseModel):
    gdrive_folder_url: str = Field(..., max_length=500)
    name: str | None = Field(default=None, max_length=255)


class FolderValidateRequest(BaseModel):
    gdrive_folder_url: str = Field(..., max_length=500)


class FolderValidateResponse(BaseModel):
    folder_id: str
    folder_name: str
    gdrive_folder_url: str


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    gdrive_folder_id: Optional[str] = None
    gdrive_folder_url: Optional[str] = None
    sync_status: ProjectStatus
    files_total: int
    files_processed: int
    last_synced_at: Optional[datetime] = None
    sync_error: Optional[str] = None
    created_at: datetime
