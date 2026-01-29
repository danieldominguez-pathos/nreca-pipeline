"""ChromaDB vector database client with environment-aware configuration."""

from vectordb.client import get_chroma_client
from vectordb.collections import (
    add_documents,
    get_collection_for_add,
    get_collection_for_query,
    list_documents,
    query_documents,
)
from vectordb.config import ChromaSettings, get_chroma_settings
from vectordb.models import DocumentChunk, DocumentMetadata, QueryResult

__all__ = [
    "ChromaSettings",
    "DocumentChunk",
    "DocumentMetadata",
    "QueryResult",
    "add_documents",
    "get_chroma_client",
    "get_chroma_settings",
    "get_collection_for_add",
    "get_collection_for_query",
    "list_documents",
    "query_documents",
]
