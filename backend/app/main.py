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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.security import SESSION_COOKIE_NAME, validate_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    yield
    # Shutdown
    from app.dependencies import dispose_engine
    await dispose_engine()


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

            # CSRF protection: state-changing methods must include the
            # X-Requested-With header (set automatically by Axios/fetch).
            if request.method in ("POST", "PUT", "DELETE", "PATCH"):
                if not request.headers.get("x-requested-with"):
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "Missing CSRF header"},
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
    allow_methods=_settings.CORS_ALLOWED_METHODS.split(","),
    allow_headers=_settings.CORS_ALLOWED_HEADERS.split(","),
)

# Import and include routers
from app.routers import auth, chat, projects, sync  # noqa: E402

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])

# Rate limiting handler
from app.routers.chat import limiter as _chat_limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

app.state.limiter = _chat_limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# Static files / SPA serving (production only)
# ---------------------------------------------------------------------------
# In production the built frontend lives in ../static/ (copied by Dockerfile).
# We mount /assets for JS/CSS bundles, then use middleware to serve index.html
# as a fallback for client-side routes.  Middleware runs AFTER all API routes
# have been tried, so /api/* and /auth/* are never shadowed.
_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
_has_static = os.path.isdir(_static_dir)

if _has_static:
    _assets_dir = os.path.join(_static_dir, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="static-assets")


@app.middleware("http")
async def spa_middleware(request: Request, call_next):
    """Serve SPA index.html for non-API GET requests that would otherwise 404."""
    response = await call_next(request)

    if not _has_static:
        return response

    # Only intercept GET 404s for non-API, non-auth paths
    if (
        response.status_code == 404
        and request.method == "GET"
        and not request.url.path.startswith(("/api/", "/auth/"))
    ):
        # Try to serve the exact static file first (favicon.ico, etc.)
        rel_path = request.url.path.lstrip("/")
        if rel_path:
            file_path = os.path.join(_static_dir, rel_path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)

        # SPA fallback: serve index.html for client-side routes
        index = os.path.join(_static_dir, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)

    return response
