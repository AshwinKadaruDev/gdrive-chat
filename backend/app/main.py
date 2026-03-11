import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status

# Configure logging for the app — without this, logger.info() calls in
# routers/services are silently discarded (only Uvicorn access logs show).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Quiet down noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.security import SESSION_COOKIE_NAME, validate_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="Talk-to-a-Folder",
    description="Chat with your Google Drive folders using AI",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Auth guard middleware — safety net for /api/* routes
# ---------------------------------------------------------------------------
class AuthGuardMiddleware(BaseHTTPMiddleware):
    """Reject unauthenticated requests to /api/* before they reach handlers.

    This is a defense-in-depth layer.  Individual endpoints still declare
    ``Depends(get_current_user)`` for proper user injection.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/"):
            session_id = request.cookies.get(SESSION_COOKIE_NAME)
            if not session_id:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Not authenticated"},
                )
            from app.dependencies import get_settings

            settings = get_settings()
            if validate_session(session_id, settings) is None:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid or expired session"},
                )
        return await call_next(request)


app.add_middleware(AuthGuardMiddleware)

# CORS middleware — derive allowed origins from config
from app.dependencies import get_settings as _get_settings
from urllib.parse import urlunparse, urlparse

_settings = _get_settings()
_cors_origins = [_settings.FRONTEND_URL]
_backend_parsed = urlparse(_settings.GOOGLE_REDIRECT_URI)
_backend_origin = urlunparse((_backend_parsed.scheme, _backend_parsed.netloc, "", "", "", ""))
if _backend_origin not in _cors_origins:
    _cors_origins.append(_backend_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from app.routers import auth, chat, projects, sync  # noqa: E402

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])

# Mount static files for production SPA serving (if the directory exists)
_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")


@app.get("/")
async def root():
    """Root endpoint: redirect to static SPA or return status."""
    if os.path.isdir(_static_dir):
        return RedirectResponse(url="/index.html")
    return JSONResponse({"status": "ok"})
