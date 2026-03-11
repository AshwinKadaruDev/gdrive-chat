"""Chat router – converse with a project's indexed folder contents."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.dependencies import get_current_user, get_db, get_settings
from app.models.chat import AgentType, ChatSession
from app.models.message import Message, MessageRole
from app.models.project import Project
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatSessionResponse,
    MessageResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _verify_project_access(
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


async def _verify_session_access(
    session_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> ChatSession:
    """Return the chat session if the user owns it, else 404.

    For RAG sessions, ownership is verified through the parent project.
    For Drive sessions (no project), ownership is verified via user_id.
    """
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    # Drive sessions: check user_id directly
    if session.project_id is None:
        if session.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found",
            )
        return session

    # RAG sessions: verify via project ownership
    project_result = await db.execute(
        select(Project).where(
            Project.id == session.project_id,
            Project.user_id == user.id,
        )
    )
    if project_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )
    return session


# ---------------------------------------------------------------------------
# POST / – main chat endpoint
# ---------------------------------------------------------------------------
@router.post("/", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Send a message and receive an AI-generated response.

    * If ``session_id`` is provided, the message is appended to an existing
      chat session.
    * If ``session_id`` is ``None``, a new ``ChatSession`` is created
      automatically.  The caller must include a ``project_id`` (for RAG)
      or ``gdrive_folder_id`` (for Drive) in the request body.
    """

    is_drive = body.agent_type.lower() == "drive"
    logger.info(
        "[CHAT] New message: agent_type=%s, session_id=%s, folder_id=%s, msg=%r",
        body.agent_type, body.session_id, body.gdrive_folder_id, body.message[:80],
    )

    # Resolve or create the chat session ------------------------------------
    if body.session_id is not None:
        session = await _verify_session_access(body.session_id, user, db)
        logger.info("[CHAT] Using existing session %s", session.id)
    else:
        if is_drive:
            # Drive Chat — requires gdrive_folder_id
            if not body.gdrive_folder_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="gdrive_folder_id is required for Drive Chat sessions.",
                )
            session = ChatSession(
                agent_type=AgentType.DRIVE,
                user_id=user.id,
                gdrive_folder_id=body.gdrive_folder_id,
                title=body.message[:120],
            )
        else:
            # RAG Chat — requires project_id
            project_id = body.project_id
            if project_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Either session_id or project_id must be provided. "
                        "Pass session_id to continue an existing conversation, "
                        "or project_id to start a new one."
                    ),
                )
            await _verify_project_access(project_id, user, db)
            session = ChatSession(
                project_id=project_id,
                user_id=user.id,
                agent_type=AgentType.RAG,
                title=body.message[:120],
            )
        db.add(session)
        await db.flush()
        logger.info("[CHAT] Created new session %s (type=%s)", session.id, session.agent_type)

    # Persist the user message ----------------------------------------------
    user_message = Message(
        chat_session_id=session.id,
        role=MessageRole.USER,
        content=body.message,
    )
    db.add(user_message)
    await db.flush()

    # Call the FolderAgent ---------------------------------------------------
    answer_text: str
    citations: list[dict] | None = None

    try:
        from app.services import (
            DRIVE_AGENT_TOOLS,
            DRIVE_SYSTEM_PROMPT,
            AzureSearchService,
            EmbeddingsService,
            FolderAgent,
            GoogleDriveService,
            LLMClient,
        )
        from app.utils.security import decrypt_token

        llm_client = LLMClient(
            anthropic_api_key=settings.ANTHROPIC_API_KEY,
            openai_api_key=settings.OPENAI_API_KEY,
        )
        drive_service = GoogleDriveService()

        if is_drive or session.agent_type == AgentType.DRIVE:
            # Drive agent — no search/embeddings services needed
            agent = FolderAgent(
                llm_client=llm_client,
                drive_service=drive_service,
                tools=DRIVE_AGENT_TOOLS,
                system_prompt=DRIVE_SYSTEM_PROMPT,
            )
            folder_id = session.gdrive_folder_id or body.gdrive_folder_id or ""
        else:
            # RAG agent — needs Azure Search + embeddings
            search_service = AzureSearchService(
                endpoint=settings.AZURE_SEARCH_ENDPOINT,
                api_key=settings.AZURE_SEARCH_API_KEY,
                index_name=settings.AZURE_SEARCH_INDEX_NAME,
            )
            embeddings_service = EmbeddingsService(
                api_key=settings.OPENAI_API_KEY,
            )
            agent = FolderAgent(
                llm_client=llm_client,
                drive_service=drive_service,
                search_service=search_service,
                embeddings_service=embeddings_service,
            )
            folder_id = str(session.project_id)

        # Decrypt the user's Google access token for Drive API calls
        user_access_token = decrypt_token(
            user.google_access_token, settings
        )

        # Build chat history from prior messages in this session
        history_result = await db.execute(
            select(Message)
            .where(
                Message.chat_session_id == session.id,
                Message.id != user_message.id,
            )
            .order_by(Message.created_at.asc())
        )
        prior_messages = history_result.scalars().all()
        chat_history = [
            {"role": msg.role.value.lower(), "content": msg.content}
            for msg in prior_messages
        ]

        agent_result = await agent.answer(
            question=body.message,
            project_id=folder_id,
            user_access_token=user_access_token,
            chat_history=chat_history if chat_history else None,
        )
        answer_text = agent_result.content
        citations = (
            [
                {
                    "chunk_id": c.chunk_id,
                    "file_id": c.file_id,
                    "file_name": c.file_name,
                    "source_url": c.source_url,
                    "location": c.location,
                    "snippet": c.snippet,
                }
                for c in agent_result.citations
            ]
            if agent_result.citations
            else None
        )
    except Exception as exc:
        logger.error(
            "[CHAT] Agent failed for session %s: %s: %s",
            session.id, type(exc).__name__, exc,
            exc_info=True,
        )
        answer_text = (
            "The AI agent encountered an error. "
            "Please check the server logs for details. "
            f"Error: {type(exc).__name__}: {exc}"
        )
        citations = None

    # Persist the assistant message -----------------------------------------
    assistant_message = Message(
        chat_session_id=session.id,
        role=MessageRole.ASSISTANT,
        content=answer_text,
        citations=citations,
    )
    db.add(assistant_message)
    await db.flush()

    return ChatResponse(
        message=MessageResponse(
            id=assistant_message.id,
            role=assistant_message.role.value,
            content=assistant_message.content,
            citations=citations,
            created_at=assistant_message.created_at,
        ),
        session_id=session.id,
    )


# ---------------------------------------------------------------------------
# POST /stream – SSE streaming chat endpoint
# ---------------------------------------------------------------------------
@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Streaming chat endpoint using Server-Sent Events.

    Sends events: ``status``, ``delta``, ``citations``, ``done``.
    The agent's tool-calling loop runs server-side; only status updates
    and the final answer tokens are streamed to the client.
    """
    is_drive = body.agent_type.lower() == "drive"
    logger.info(
        "[CHAT-STREAM] New streaming message: agent_type=%s, session_id=%s, folder_id=%s, msg=%r",
        body.agent_type, body.session_id, body.gdrive_folder_id, body.message[:80],
    )

    # Resolve or create the chat session
    if body.session_id is not None:
        session = await _verify_session_access(body.session_id, user, db)
        logger.info("[CHAT-STREAM] Using existing session %s", session.id)
    else:
        if is_drive:
            if not body.gdrive_folder_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="gdrive_folder_id is required for Drive Chat sessions.",
                )
            session = ChatSession(
                agent_type=AgentType.DRIVE,
                user_id=user.id,
                gdrive_folder_id=body.gdrive_folder_id,
                title=body.message[:120],
            )
        else:
            project_id = body.project_id
            if project_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Either session_id or project_id must be provided.",
                )
            await _verify_project_access(project_id, user, db)
            session = ChatSession(
                project_id=project_id,
                user_id=user.id,
                agent_type=AgentType.RAG,
                title=body.message[:120],
            )
        db.add(session)
        await db.flush()

    # Persist user message
    user_message = Message(
        chat_session_id=session.id,
        role=MessageRole.USER,
        content=body.message,
    )
    db.add(user_message)
    await db.flush()

    # Capture IDs before the streaming generator (session scope may close)
    session_id = session.id
    session_agent_type = session.agent_type
    session_gdrive_folder_id = session.gdrive_folder_id
    session_project_id = session.project_id

    # Build chat history
    history_result = await db.execute(
        select(Message)
        .where(
            Message.chat_session_id == session_id,
            Message.id != user_message.id,
        )
        .order_by(Message.created_at.asc())
    )
    prior_messages = history_result.scalars().all()
    chat_history = [
        {"role": msg.role.value.lower(), "content": msg.content}
        for msg in prior_messages
    ]

    # Commit user message + session before streaming
    await db.commit()

    async def event_generator():
        """Generate SSE events from the agent's streaming loop."""
        # Send session_id immediately so frontend can track the conversation
        yield f"event: session\ndata: {json.dumps({'session_id': str(session_id)})}\n\n"

        full_answer = []
        final_citations = None

        try:
            from app.services import (
                DRIVE_AGENT_TOOLS,
                DRIVE_SYSTEM_PROMPT,
                AzureSearchService,
                EmbeddingsService,
                FolderAgent,
                GoogleDriveService,
                LLMClient,
            )
            from app.utils.security import decrypt_token

            llm_client = LLMClient(
                anthropic_api_key=settings.ANTHROPIC_API_KEY,
                openai_api_key=settings.OPENAI_API_KEY,
            )
            drive_service = GoogleDriveService()

            if is_drive or session_agent_type == AgentType.DRIVE:
                logger.info("[CHAT-STREAM] Setting up DRIVE agent, folder_id=%s", session_gdrive_folder_id)
                agent = FolderAgent(
                    llm_client=llm_client,
                    drive_service=drive_service,
                    tools=DRIVE_AGENT_TOOLS,
                    system_prompt=DRIVE_SYSTEM_PROMPT,
                )
                folder_id = session_gdrive_folder_id or body.gdrive_folder_id or ""
            else:
                logger.info("[CHAT-STREAM] Setting up RAG agent, project_id=%s", session_project_id)
                search_service = AzureSearchService(
                    endpoint=settings.AZURE_SEARCH_ENDPOINT,
                    api_key=settings.AZURE_SEARCH_API_KEY,
                    index_name=settings.AZURE_SEARCH_INDEX_NAME,
                )
                embeddings_service = EmbeddingsService(
                    api_key=settings.OPENAI_API_KEY,
                )
                agent = FolderAgent(
                    llm_client=llm_client,
                    drive_service=drive_service,
                    search_service=search_service,
                    embeddings_service=embeddings_service,
                )
                folder_id = str(session_project_id)

            user_access_token = decrypt_token(
                user.google_access_token, settings
            )
            logger.info("[CHAT-STREAM] Starting agent.answer_streaming, folder_id=%s", folder_id)

            async for event_type, data in agent.answer_streaming(
                question=body.message,
                project_id=folder_id,
                user_access_token=user_access_token,
                chat_history=chat_history if chat_history else None,
            ):
                if event_type == "status":
                    yield f"event: status\ndata: {json.dumps({'text': data})}\n\n"
                elif event_type == "delta":
                    full_answer.append(data)
                    yield f"event: delta\ndata: {json.dumps({'text': data})}\n\n"
                elif event_type == "citations":
                    final_citations = data
                    yield f"event: citations\ndata: {json.dumps(data)}\n\n"
                elif event_type == "done":
                    yield f"event: done\ndata: {json.dumps({})}\n\n"

        except Exception as exc:
            logger.error(
                "[CHAT-STREAM] Agent failed for session %s: %s: %s",
                session_id, type(exc).__name__, exc,
                exc_info=True,
            )
            error_text = (
                "The AI agent encountered an error. "
                f"Error: {type(exc).__name__}: {exc}"
            )
            full_answer.append(error_text)
            yield f"event: delta\ndata: {json.dumps({'text': error_text})}\n\n"
            yield f"event: citations\ndata: []\n\n"
            yield f"event: done\ndata: {json.dumps({})}\n\n"

        # Persist the assistant message after streaming completes
        from app.dependencies import _init_db

        factory = _init_db()
        async with factory() as save_db:
            assistant_msg = Message(
                chat_session_id=session_id,
                role=MessageRole.ASSISTANT,
                content="".join(full_answer),
                citations=final_citations,
            )
            save_db.add(assistant_msg)
            await save_db.commit()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# GET /sessions/drive – list Drive Chat sessions for current user
# ---------------------------------------------------------------------------
@router.get(
    "/sessions/drive",
    response_model=list[ChatSessionResponse],
)
async def list_drive_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all Drive Chat sessions for the current user, newest first."""
    result = await db.execute(
        select(ChatSession)
        .where(
            ChatSession.agent_type == AgentType.DRIVE,
            ChatSession.user_id == user.id,
        )
        .order_by(ChatSession.created_at.desc())
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# GET /sessions/{project_id} – list chat sessions for a project
# ---------------------------------------------------------------------------
@router.get(
    "/sessions/{project_id}",
    response_model=list[ChatSessionResponse],
)
async def list_sessions(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all chat sessions for a given project, newest first."""
    await _verify_project_access(project_id, user, db)

    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.project_id == project_id)
        .order_by(ChatSession.created_at.desc())
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# GET /sessions/{session_id}/messages – get messages for a session
# ---------------------------------------------------------------------------
@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[MessageResponse],
)
async def list_messages(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all messages in a chat session, ordered chronologically."""
    await _verify_session_access(session_id, user, db)

    result = await db.execute(
        select(Message)
        .where(Message.chat_session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    return result.scalars().all()
