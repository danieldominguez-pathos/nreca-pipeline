"""ChromaDB configuration settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChromaSettings(BaseSettings):
    """Configuration for ChromaDB client."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["local", "prod"] = Field(
        default="local",
        validation_alias="APP_ENV",
        description="Environment mode: 'local' for docker chroma, 'prod' for remote",
    )

    # Local ChromaDB settings (docker container)
    chroma_local_host: str = Field(
        default="localhost",
        validation_alias="CHROMA_LOCAL_HOST",
        description="Local ChromaDB host",
    )
    chroma_local_port: int = Field(
        default=8001,
        validation_alias="CHROMA_LOCAL_PORT",
        description="Local ChromaDB port",
    )

    # Production ChromaDB settings (remote server)
    chroma_prod_host: str = Field(
        default="18.205.154.91",
        validation_alias="CHROMA_PROD_HOST",
        description="Production ChromaDB host",
    )
    chroma_prod_port: int = Field(
        default=8000,
        validation_alias="CHROMA_PROD_PORT",
        description="Production ChromaDB port",
    )

    # Collection settings
    collection_name: str = Field(
        default="nreca_documents",
        validation_alias="CHROMA_COLLECTION",
        description="ChromaDB collection name for documents",
    )

    # Embedding model settings
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        validation_alias="EMBEDDING_MODEL",
        description="Sentence transformer model for embeddings",
    )

    @property
    def is_local(self) -> bool:
        """Check if running in local mode."""
        return self.app_env == "local"

    @property
    def host(self) -> str:
        """Get the appropriate host based on environment."""
        return self.chroma_local_host if self.is_local else self.chroma_prod_host

    @property
    def port(self) -> int:
        """Get the appropriate port based on environment."""
        return self.chroma_local_port if self.is_local else self.chroma_prod_port


@lru_cache(maxsize=1)
def get_chroma_settings() -> ChromaSettings:
    """Get cached ChromaDB settings singleton."""
    return ChromaSettings()
