from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the project root (.env lives next to backend/, not inside it)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/talk_to_folder"

    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/google/callback"

    # OpenAI
    OPENAI_API_KEY: str

    # Anthropic (optional) — TODO: Re-enable Anthropic support — currently unused
    ANTHROPIC_API_KEY: Optional[str] = None

    # Security
    ENCRYPTION_KEY: str
    FRONTEND_URL: str = "http://localhost:5173"

    # Azure Storage (optional)
    AZURE_STORAGE_CONNECTION_STRING: Optional[str] = None

    # LLM Model names
    AGENT_MODEL: str = "gpt-5.2"

    # Resource limits
    MAX_MESSAGE_LENGTH: int = 32000
    MAX_CHAT_HISTORY_MESSAGES: int = 100
    MAX_SPREADSHEET_SEARCH_ROWS: int = 10000
    MAX_FILE_DOWNLOAD_BYTES: int = 104857600   # 100 MB
    MAX_SPREADSHEET_BYTES: int = 52428800      # 50 MB
    MAX_SYNC_FILES: int = 5000
    MAX_FOLDER_DEPTH: int = 10

    # Timeouts
    DRIVE_API_TIMEOUT: float = 30.0
    DRIVE_DOWNLOAD_TIMEOUT: float = 60.0

    # CORS
    CORS_ALLOWED_METHODS: str = "GET,POST,DELETE,OPTIONS"
    CORS_ALLOWED_HEADERS: str = "Content-Type,X-Requested-With"
