"""Storage configuration settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageSettings(BaseSettings):
    """Configuration for file storage backends."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["local", "prod"] = Field(
        default="local",
        validation_alias="APP_ENV",
        description="Environment mode: 'local' for filesystem, 'prod' for S3",
    )

    # Local storage settings
    local_path: str = Field(
        default="/home/danyiel/Working/NovaDynamics/test_files",
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
    def is_local(self) -> bool:
        """Check if running in local mode."""
        return self.app_env == "local"


@lru_cache(maxsize=1)
def get_storage_settings() -> StorageSettings:
    """Get cached storage settings singleton."""
    return StorageSettings()
