import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ChatSessionCreate(BaseModel):
    project_id: uuid.UUID


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    agent_type: str = "RAG"
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
    role: str
    content: str
    citations: Optional[list[CitationSchema]] = None
    created_at: datetime


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[uuid.UUID] = None
    project_id: Optional[uuid.UUID] = None
    agent_type: str = "rag"
    gdrive_folder_id: Optional[str] = None


class ChatResponse(BaseModel):
    message: MessageResponse
    session_id: uuid.UUID
