from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    APP_NAME: str = "Resolvix-AI"
    APP_ENV: str = "development"
    DEBUG: bool = True

    HOST: str = "0.0.0.0"
    PORT: int = 8000
    API_V1_PREFIX: str = "/api/v1"

    BACKEND_CORS_ORIGINS: List[str] = []

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def split_origins(cls, v):
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    # Security
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Roles
    ROLE_ADMIN: str = "admin"
    ROLE_AGENT: str = "support_agent"
    ROLE_CUSTOMER: str = "customer"
    ROLE_AUDITOR: str = "auditor"

    # Database
    DATABASE_URL: str = "sqlite:///./resolvix.db"

    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_HOST: Optional[str] = None
    POSTGRES_PORT: Optional[int] = 5432
    POSTGRES_DB: Optional[str] = None

    # AI
    LLM_PROVIDER: str = "google"
    LLM_MODEL_NAME: str = "gemini-2.5-pro"
    LLM_API_KEY: Optional[str] = None

    # Vector DB
    VECTOR_DB_PROVIDER: str = "chroma"
    VECTOR_DB_COLLECTION: str = "resolvix_policies"

    # Storage
    STORAGE_BACKEND: str = "local"
    STORAGE_LOCAL_PATH: str = "storage/uploads"

    # Logging
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: Optional[AnyHttpUrl] = None


@lru_cache
def get_settings():
    return Settings()