"""Storage configuration settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from utils import AppEnvMode


class StorageSettings(BaseSettings):
    """Configuration for file storage backends.

    Supports flexible APP_ENV:
    - "local" - Local filesystem storage
    - "local:S3" - Use S3 storage
    - "prod" - Use S3 storage (production default)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(
        default="local",
        validation_alias="APP_ENV",
        description="Environment mode: 'local', 'local:S3', 'prod', etc.",
    )

    # Local storage settings
    local_path: str = Field(
        default="/data/files",
        validation_alias="TEST_FILES_PATH",
        description="Base path for local file storage",
    )

    # S3 storage settings
    s3_bucket: str = Field(
        default="nreca-ingest-bucket",
        validation_alias="S3_BUCKET",
        description="S3 bucket name for file storage",
    )
    s3_prefix: str = Field(
        default="documents/",
        validation_alias="S3_PREFIX",
        description="S3 key prefix for documents",
    )
    s3_region: str = Field(
        default="us-east-1",
        validation_alias="AWS_REGION",
        description="AWS region for S3",
    )

    @property
    def env_mode(self) -> AppEnvMode:
        """Get parsed environment mode."""
        return AppEnvMode(self.app_env)

    @property
    def use_s3(self) -> bool:
        """Check if S3 storage should be used."""
        return self.env_mode.use_s3


@lru_cache(maxsize=1)
def get_storage_settings() -> StorageSettings:
    """Get cached storage settings singleton."""
    return StorageSettings()
