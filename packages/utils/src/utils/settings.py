"""Application settings with Pydantic Settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvMode:
    """Parser for flexible APP_ENV configuration.

    Supports colon-separated service overrides:
    - "local" - All local services (default)
    - "local:S3" - Local + S3 storage
    - "local:prod_chroma" - Local + remote ChromaDB
    - "local:prod_llm" - Local + production LLM (Gemma)
    - "local:S3:prod_chroma:prod_llm" - Combinations
    - "prod" - All production services

    Examples:
        >>> mode = AppEnvMode("local:S3:prod_chroma")
        >>> mode.use_s3  # True
        >>> mode.use_prod_chroma  # True
        >>> mode.use_prod_llm  # False
    """

    def __init__(self, app_env: str):
        self._raw = app_env.lower().strip()
        self._parts = set(self._raw.split(":"))

    @property
    def is_full_prod(self) -> bool:
        """True if APP_ENV is exactly 'prod' (all production services)."""
        return self._raw == "prod"

    @property
    def is_local_base(self) -> bool:
        """True if base environment is local."""
        return "local" in self._parts or not self.is_full_prod

    @property
    def use_s3(self) -> bool:
        """Use S3 storage instead of local filesystem."""
        return self.is_full_prod or "s3" in self._parts

    @property
    def use_prod_chroma(self) -> bool:
        """Use production ChromaDB instead of local Docker."""
        return self.is_full_prod or "prod_chroma" in self._parts

    @property
    def use_prod_llm(self) -> bool:
        """Use production LLM (Gemma) instead of Groq."""
        return self.is_full_prod or "prod_llm" in self._parts

    def __repr__(self) -> str:
        return (
            f"AppEnvMode({self._raw!r}, "
            f"s3={self.use_s3}, chroma={self.use_prod_chroma}, llm={self.use_prod_llm})"
        )


@lru_cache(maxsize=1)
def get_app_env_mode(app_env: str = "local") -> AppEnvMode:
    """Get cached AppEnvMode instance."""
    return AppEnvMode(app_env)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    app_mode: Literal["development", "production"] = Field(
        default="development",
        alias="APP_MODE",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "silent"] = Field(
        default="INFO",
        alias="LOG_LEVEL",
    )

    # Database - Optional for testing, required in production
    database_url: SecretStr | None = Field(default=None, alias="DATABASE_URL")

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_mode == "production"

    @property
    def is_silent(self) -> bool:
        """Check if logging should be suppressed."""
        return self.log_level == "silent"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()  # type: ignore[call-arg]
