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

    # Azure AI Search
    AZURE_SEARCH_ENDPOINT: str
    AZURE_SEARCH_API_KEY: str
    AZURE_SEARCH_INDEX_NAME: str = "talk-to-folder-chunks"

    # OpenAI
    OPENAI_API_KEY: str

    # Anthropic (optional) — TODO: Re-enable Anthropic support — currently unused
    ANTHROPIC_API_KEY: Optional[str] = None

    # Temporal
    TEMPORAL_HOST: str = "localhost:7233"
    TEMPORAL_NAMESPACE: str = "default"
    TEMPORAL_API_KEY: Optional[str] = None

    # Security
    ENCRYPTION_KEY: str
    FRONTEND_URL: str = "http://localhost:5173"

    # Azure Storage (optional)
    AZURE_STORAGE_CONNECTION_STRING: Optional[str] = None
