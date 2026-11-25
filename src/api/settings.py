"""Configuración específica del servicio Backend FastAPI (SIAMA-Clima)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    """Configuración tipada para base de datos, CORS y cliente IBM Granite."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    POSTGRES_USER: str = "siama_user"
    POSTGRES_PASSWORD: str = "siama_dev_password"
    POSTGRES_DB: str = "siama_impute"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None

    SIAMA_AUTO_INIT_DB: bool = True

    OLLAMA_BASE_URL: str = "http://granite-llm:11434/v1"
    GRANITE_MODEL: str = "granite4:3b"
    GRANITE_GUARDIAN_MODEL: str = "granite3-guardian:2b"
    OLLAMA_TIMEOUT_SECONDS: float = 8.0

    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000", "*"]
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return value
        return ["http://localhost:5173", "http://localhost:3000", "*"]

    @property
    def effective_database_url(self) -> str:
        """Retorna DATABASE_URL si existe, o construye la URL PostgreSQL+psycopg."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache(maxsize=1)
def get_api_settings() -> ApiSettings:
    """Devuelve la instancia cacheada de configuración de la API."""
    return ApiSettings()
