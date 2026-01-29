"""API configuration settings."""

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _read_password_file(path: str) -> str | None:
    """Read password from file if it exists."""
    try:
        with open(path) as f:
            return f.read().strip()
    except (FileNotFoundError, PermissionError):
        return None


class APISettings(BaseSettings):
    """Configuration for FastAPI application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["local", "prod"] = Field(
        default="local",
        validation_alias="APP_ENV",
    )

    # Airflow API settings (v2 for Airflow 3.x)
    airflow_api_url: str = Field(
        default="http://localhost:8080/api/v2",
        validation_alias="AIRFLOW_API_URL",
    )
    airflow_username: str = Field(
        default="admin",
        validation_alias="AIRFLOW_USERNAME",
    )
    airflow_password: SecretStr = Field(
        default="airflow",
        validation_alias="AIRFLOW_PASSWORD",
    )
    airflow_password_file: str | None = Field(
        default=None,
        validation_alias="AIRFLOW_PASSWORD_FILE",
    )

    @field_validator("airflow_password", mode="before")
    @classmethod
    def load_password_from_file(cls, v, info):
        """Load password from file if AIRFLOW_PASSWORD_FILE is set."""
        password_file = os.environ.get("AIRFLOW_PASSWORD_FILE")
        if password_file:
            file_password = _read_password_file(password_file)
            if file_password:
                return file_password
        return v

    # LLM settings
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        validation_alias="LLM_MODEL",
    )
    llm_base_url: str | None = Field(
        default=None,
        validation_alias="LLM_BASE_URL",
        description="Base URL for OpenAI-compatible API (e.g., GROQ, Gemma)",
    )

    # GROQ settings (local testing)
    groq_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="GROQ_API_KEY",
    )
    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        validation_alias="GROQ_MODEL",
    )

    # Gemma settings (production - previously called immediatum)
    gemma_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="GEMMA_API_KEY",
    )
    gemma_base_url: str = Field(
        default="http://localhost:11434/v1",
        validation_alias="GEMMA_BASE_URL",
    )
    gemma_model: str = Field(
        default="gemma2",
        validation_alias="GEMMA_MODEL",
    )

    @property
    def is_local(self) -> bool:
        """Check if running in local mode."""
        return self.app_env == "local"


@lru_cache(maxsize=1)
def get_api_settings() -> APISettings:
    """Get cached API settings singleton."""
    return APISettings()
