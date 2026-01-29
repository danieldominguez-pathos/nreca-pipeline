"""ChromaDB client factory."""

import chromadb
from chromadb import HttpClient

from vectordb.config import ChromaSettings, get_chroma_settings


def get_chroma_client(settings: ChromaSettings | None = None) -> HttpClient:
    """Get ChromaDB HTTP client configured for the current environment.

    Factory function that returns a ChromaDB client connected to either
    local docker instance or production remote server based on APP_ENV.

    Args:
        settings: Optional ChromaDB settings. If not provided, loads from environment.

    Returns:
        ChromaDB HttpClient instance

    Example:
        >>> client = get_chroma_client()
        >>> collection = client.get_or_create_collection("documents")
    """
    if settings is None:
        settings = get_chroma_settings()

    return chromadb.HttpClient(
        host=settings.host,
        port=settings.port,
    )
