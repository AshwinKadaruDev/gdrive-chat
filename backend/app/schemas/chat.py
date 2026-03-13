import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatSessionCreate(BaseModel):
    project_id: uuid.UUID


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    gdrive_folder_id: Optional[str] = None
    title: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class CitationSchema(BaseModel):
    chunk_id: str
    file_id: str
    file_name: str
    source_url: Optional[str] = None
    location: Optional[str] = None
    snippet: str


class MessageCreate(BaseModel):
    content: str


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    citations: Optional[list[CitationSchema]] = None
    created_at: datetime

    @field_validator("role", mode="before")
    @classmethod
    def lowercase_role(cls, v: str) -> str:
        return v.value.lower() if hasattr(v, "value") else v.lower()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=32000)
    session_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    gdrive_folder_id: Optional[str] = None
    model: Optional[str] = None


class ChatResponse(BaseModel):
    message: MessageResponse
    session_id: uuid.UUID
