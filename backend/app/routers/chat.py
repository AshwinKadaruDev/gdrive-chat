"""Chat router – converse with a Google Drive folder's contents."""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.dependencies import get_current_user, get_db, get_settings
from app.models.chat import ChatSession
from app.models.message import Message, MessageRole
from app.models.project import Project
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatSessionResponse,
    MessageResponse,
)
from app.services import (
    FolderAgent,
    GoogleDriveService,
    LLMClient,
)
from app.services.google_drive import DriveAuthError, DrivePermissionError
from app.utils.security import SESSION_COOKIE_NAME, get_valid_access_token

logger = logging.getLogger(__name__)

router = APIRouter()


def _rate_limit_key(request: Request) -> str:
    return request.cookies.get(SESSION_COOKIE_NAME, get_remote_address(request))


limiter = Limiter(key_func=_rate_limit_key)


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
    lock: bool = False,
) -> ChatSession:
    """Return the chat session if the user owns it, else 404.

    Ownership is verified via user_id, or through the parent project
    for legacy sessions.  When *lock* is True, a ``FOR UPDATE`` row
    lock is acquired.
    """
    stmt = select(ChatSession).where(ChatSession.id == session_id)
    if lock:
        stmt = stmt.with_for_update()
    result = await db.execute(stmt)
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

    # Legacy sessions with project_id: verify via project ownership
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
@limiter.limit("10/minute")
async def chat(
    body: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Send a message and receive an AI-generated response.

    * If ``session_id`` is provided, the message is appended to an existing
      chat session.
    * If ``session_id`` is ``None``, a new ``ChatSession`` is created
      automatically.  The caller must include a ``gdrive_folder_id``.
    """

    logger.info(
        "[CHAT] New message: session_id=%s, folder_id=%s, msg=%r",
        body.session_id, body.gdrive_folder_id, body.message[:80],
    )

    # Resolve or create the chat session ------------------------------------
    if body.session_id is not None:
        session = await _verify_session_access(body.session_id, user, db, lock=True)
        logger.info("[CHAT] Using existing session %s", session.id)
    else:
        if not body.gdrive_folder_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="gdrive_folder_id is required to start a new chat session.",
            )
        session = ChatSession(
            user_id=user.id,
            gdrive_folder_id=body.gdrive_folder_id,
            title=body.message[:120],
        )
        db.add(session)
        await db.flush()
        logger.info("[CHAT] Created new session %s", session.id)

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
        llm_client = LLMClient(
            openai_api_key=settings.OPENAI_API_KEY,
            anthropic_api_key=settings.ANTHROPIC_API_KEY,
        )
        drive_service = GoogleDriveService()
        agent = FolderAgent(
            llm_client=llm_client,
            drive_service=drive_service,
            model=body.model or settings.AGENT_MODEL,
        )
        folder_id = session.gdrive_folder_id or body.gdrive_folder_id or ""

        # Get a valid (possibly refreshed) Google access token
        user_access_token = await get_valid_access_token(
            user, settings, db
        )

        # Build chat history from prior messages in this session (bounded)
        history_result = await db.execute(
            select(Message)
            .where(
                Message.chat_session_id == session.id,
                Message.id != user_message.id,
            )
            .order_by(Message.created_at.desc())
            .limit(settings.MAX_CHAT_HISTORY_MESSAGES)
        )
        prior_messages = list(reversed(history_result.scalars().all()))
        chat_history = [
            {"role": msg.role.value.lower(), "content": msg.content}
            for msg in prior_messages
        ]

        agent_result = await agent.answer(
            question=body.message,
            project_id=folder_id,
            user_access_token=user_access_token,
            chat_history=chat_history if chat_history else None,
            session_id=str(session.id),
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

        # Persist the assistant message inside the try block
        assistant_message = Message(
            chat_session_id=session.id,
            role=MessageRole.ASSISTANT,
            content=answer_text,
            citations=citations,
        )
        db.add(assistant_message)
        await db.flush()

    except DriveAuthError as exc:
        logger.warning("[CHAT] Drive auth error for session %s: %s", session.id, exc)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your Google Drive authorization has expired. Please sign in again.",
        )
    except DrivePermissionError as exc:
        logger.warning("[CHAT] Drive permission error for session %s: %s", session.id, exc)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this Drive resource.",
        )
    except Exception as exc:
        logger.error(
            "[CHAT] Agent failed for session %s: %s: %s",
            session.id, type(exc).__name__, exc,
            exc_info=True,
        )
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request.",
        )

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
@limiter.limit("10/minute")
async def chat_stream(
    body: ChatRequest,
    request: Request,
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
    logger.info(
        "[CHAT-STREAM] New streaming message: session_id=%s, folder_id=%s, msg=%r",
        body.session_id, body.gdrive_folder_id, body.message[:80],
    )

    # Resolve or create the chat session
    if body.session_id is not None:
        session = await _verify_session_access(body.session_id, user, db, lock=True)
        logger.info("[CHAT-STREAM] Using existing session %s", session.id)
    else:
        if not body.gdrive_folder_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="gdrive_folder_id is required to start a new chat session.",
            )
        session = ChatSession(
            user_id=user.id,
            gdrive_folder_id=body.gdrive_folder_id,
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
    session_gdrive_folder_id = session.gdrive_folder_id

    # Build chat history (bounded)
    history_result = await db.execute(
        select(Message)
        .where(
            Message.chat_session_id == session_id,
            Message.id != user_message.id,
        )
        .order_by(Message.created_at.desc())
        .limit(settings.MAX_CHAT_HISTORY_MESSAGES)
    )
    prior_messages = list(reversed(history_result.scalars().all()))
    chat_history = [
        {"role": msg.role.value.lower(), "content": msg.content}
        for msg in prior_messages
    ]

    # Get a valid access token before committing (refresh needs DB write access)
    logger.info("[CHAT-STREAM] Getting valid access token for user %s", user.id)
    _user_access_token = await get_valid_access_token(user, settings, db)
    logger.info("[CHAT-STREAM] Access token obtained, length=%d", len(_user_access_token) if _user_access_token else 0)

    # Commit user message + session before streaming
    await db.commit()

    async def _save_streaming_message(
        sid: uuid.UUID, content: str, citations_data: list | None
    ) -> None:
        """Persist the assistant message using a fresh DB session."""
        try:
            from app.dependencies import _init_db

            factory = _init_db()
            async with factory() as save_db:
                assistant_msg = Message(
                    chat_session_id=sid,
                    role=MessageRole.ASSISTANT,
                    content=content,
                    citations=citations_data,
                )
                save_db.add(assistant_msg)
                await save_db.commit()
        except Exception as save_exc:
            logger.error(
                "[CHAT-STREAM] Failed to persist assistant message for session %s: %s",
                sid, save_exc, exc_info=True,
            )

    async def event_generator():
        """Generate SSE events from the agent's streaming loop."""
        # Send session_id immediately so frontend can track the conversation
        yield f"event: session\ndata: {json.dumps({'session_id': str(session_id)})}\n\n"

        full_answer = []
        final_citations = None

        try:
            llm_client = LLMClient(
                openai_api_key=settings.OPENAI_API_KEY,
                anthropic_api_key=settings.ANTHROPIC_API_KEY,
            )
            drive_service = GoogleDriveService()
            agent = FolderAgent(
                llm_client=llm_client,
                drive_service=drive_service,
                model=body.model or settings.AGENT_MODEL,
            )
            folder_id = session_gdrive_folder_id or body.gdrive_folder_id or ""

            user_access_token = _user_access_token
            logger.info("[CHAT-STREAM] Starting agent.answer_streaming, folder_id=%s", folder_id)

            async for event_type, data in agent.answer_streaming(
                question=body.message,
                project_id=folder_id,
                user_access_token=user_access_token,
                chat_history=chat_history if chat_history else None,
                session_id=str(session_id),
            ):
                if event_type == "status":
                    yield f"event: status\ndata: {json.dumps({'text': data})}\n\n"
                elif event_type == "delta":
                    full_answer.append(data)
                    yield f"event: delta\ndata: {json.dumps({'text': data})}\n\n"
                elif event_type == "reasoning":
                    yield f"event: reasoning\ndata: {json.dumps(data)}\n\n"
                elif event_type == "citations":
                    final_citations = data
                    yield f"event: citations\ndata: {json.dumps(data)}\n\n"
                elif event_type == "done":
                    logger.info(
                        "[CHAT-STREAM] Streaming complete for session %s: answer_length=%d, citations=%s",
                        session_id, len("".join(full_answer)),
                        len(final_citations) if final_citations else 0,
                    )
                    # Persist before yielding done so the DB write happens
                    # while we still control the async context.
                    await _save_streaming_message(
                        session_id, "".join(full_answer), final_citations
                    )
                    yield f"event: done\ndata: {json.dumps({})}\n\n"

        except DriveAuthError as exc:
            logger.warning("[CHAT-STREAM] Drive auth error for session %s: %s", session_id, exc)
            error_text = "Your Google Drive authorization has expired. Please sign in again."
            full_answer.append(error_text)
            yield f"event: delta\ndata: {json.dumps({'text': error_text})}\n\n"
            yield f"event: citations\ndata: []\n\n"
            await _save_streaming_message(session_id, "".join(full_answer), None)
            yield f"event: done\ndata: {json.dumps({})}\n\n"
        except DrivePermissionError as exc:
            logger.warning("[CHAT-STREAM] Drive permission error for session %s: %s", session_id, exc)
            error_text = "You don't have permission to access this Drive resource."
            full_answer.append(error_text)
            yield f"event: delta\ndata: {json.dumps({'text': error_text})}\n\n"
            yield f"event: citations\ndata: []\n\n"
            await _save_streaming_message(session_id, "".join(full_answer), None)
            yield f"event: done\ndata: {json.dumps({})}\n\n"
        except Exception as exc:
            logger.error(
                "[CHAT-STREAM] Agent failed for session %s: %s: %s",
                session_id, type(exc).__name__, exc,
                exc_info=True,
            )
            error_text = (
                "I'm sorry, something went wrong while processing your request. "
                "Please try again."
            )
            full_answer.append(error_text)
            yield f"event: delta\ndata: {json.dumps({'text': error_text})}\n\n"
            yield f"event: citations\ndata: []\n\n"
            await _save_streaming_message(session_id, "".join(full_answer), None)
            yield f"event: done\ndata: {json.dumps({})}\n\n"

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
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return all chat sessions for the current user, newest first."""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.created_at.desc())
        .limit(limit)
        .offset(offset)
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
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return all chat sessions for a given project, newest first."""
    await _verify_project_access(project_id, user, db)

    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.project_id == project_id)
        .order_by(ChatSession.created_at.desc())
        .limit(limit)
        .offset(offset)
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
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return all messages in a chat session, ordered chronologically."""
    await _verify_session_access(session_id, user, db)

    result = await db.execute(
        select(Message)
        .where(Message.chat_session_id == session_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# DELETE /sessions/{session_id} – delete a chat session
# ---------------------------------------------------------------------------
@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a chat session and all its messages (cascade)."""
    session = await _verify_session_access(session_id, user, db)
    await db.delete(session)
    await db.flush()
