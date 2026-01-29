"""ChromaDB configuration settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from utils import AppEnvMode


class ChromaSettings(BaseSettings):
    """Configuration for ChromaDB client.

    Supports flexible APP_ENV:
    - "local" - Local Docker ChromaDB
    - "local:prod_chroma" - Use remote production ChromaDB (VPN required)
    - "prod" - Use remote production ChromaDB
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(
        default="local",
        validation_alias="APP_ENV",
        description="Environment mode: 'local', 'local:prod_chroma', 'prod', etc.",
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

    # Production ChromaDB settings (remote server - requires VPN)
    chroma_prod_host: str = Field(
        default="",
        validation_alias="CHROMA_PROD_HOST",
        description="Production ChromaDB host (set in .env, requires VPN)",
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
    def env_mode(self) -> AppEnvMode:
        """Get parsed environment mode."""
        return AppEnvMode(self.app_env)

    @property
    def use_prod_chroma(self) -> bool:
        """Check if production ChromaDB should be used."""
        return self.env_mode.use_prod_chroma

    @property
    def host(self) -> str:
        """Get the appropriate host based on environment."""
        if self.use_prod_chroma:
            if not self.chroma_prod_host:
                raise ValueError("CHROMA_PROD_HOST must be set when using prod_chroma mode")
            return self.chroma_prod_host
        return self.chroma_local_host

    @property
    def port(self) -> int:
        """Get the appropriate port based on environment."""
        return self.chroma_prod_port if self.use_prod_chroma else self.chroma_local_port


@lru_cache(maxsize=1)
def get_chroma_settings() -> ChromaSettings:
    """Get cached ChromaDB settings singleton."""
    return ChromaSettings()
