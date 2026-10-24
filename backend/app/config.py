"""Application configuration and settings."""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load variables from available .env files
_root_env = Path(__file__).resolve().parents[2] / ".env"
_backend_env = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_root_env)
load_dotenv(_backend_env)
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=(
            _root_env,
            _backend_env,
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Parakh AI"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    SQL_ECHO: bool = False
    API_V1_STR: str = "/api"

    # Security
    SECRET_KEY: str = "temporary-dev-secret-key-change-in-production-12345"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./viva.db"

    # CORS
    CORS_ORIGINS: list[str] | str = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]

    # Groq-hosted language model
    GROQ_API_KEY: str | None = None
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_TIMEOUT_SECONDS: float = 45.0
    GROQ_STT_MODEL: str = "whisper-large-v3-turbo"
    WHISPER_MODEL: str = "base"

    # Storage and upload limits (in megabytes)
    MAX_UPLOAD_SIZE_MB: int = 25

    @field_validator("DATABASE_URL")
    @classmethod
    def _anchor_sqlite_path(cls, v: str) -> str:
        """Resolve relative SQLite paths against backend/ so every entry point shares one DB."""
        prefix = "sqlite+aiosqlite:///./"
        if v.startswith(prefix):
            db = Path(__file__).resolve().parents[1] / v[len(prefix) :]
            return f"sqlite+aiosqlite:///{db.as_posix()}"
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Convert comma-separated strings to list of origins."""
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, str)):
            return v  # type: ignore[return-value]
        raise ValueError(f"Invalid CORS_ORIGINS format: {v}")

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Validate that SECRET_KEY meets minimum entropy requirement."""
        if not v or len(v.strip()) < 16:
            raise ValueError("SECRET_KEY must be at least 16 characters long.")
        return v.strip()


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()
