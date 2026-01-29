"""ChromaDB collection management and operations.

This module provides:
- Query operations (no local embedding needed - server handles it)
- Add operations (requires sentence-transformers for embedding)
"""

from collections.abc import Sequence

from chromadb import Collection

from vectordb.client import get_chroma_client
from vectordb.config import ChromaSettings, get_chroma_settings
from vectordb.models import DocumentChunk, QueryResult


def get_collection_for_query(
    collection_name: str | None = None,
    settings: ChromaSettings | None = None,
) -> Collection:
    """Get a ChromaDB collection for querying.

    Uses the same embedding function as add operations for consistency.
    This ensures collection is created with correct embedding function.

    Args:
        collection_name: Optional collection name. Defaults to settings.collection_name.
        settings: Optional ChromaDB settings. If not provided, loads from environment.

    Returns:
        ChromaDB Collection with sentence-transformer embedding function
    """
    if settings is None:
        settings = get_chroma_settings()

    if collection_name is None:
        collection_name = settings.collection_name

    client = get_chroma_client(settings)

    # Use same embedding function as add operations for consistency
    from chromadb.utils import embedding_functions

    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=settings.embedding_model
    )

    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )


def get_collection_for_add(
    collection_name: str | None = None,
    settings: ChromaSettings | None = None,
) -> Collection:
    """Get a ChromaDB collection for adding documents (with embedding function).

    Requires sentence-transformers to be installed.

    Args:
        collection_name: Optional collection name. Defaults to settings.collection_name.
        settings: Optional ChromaDB settings. If not provided, loads from environment.

    Returns:
        ChromaDB Collection with configured embedding function
    """
    if settings is None:
        settings = get_chroma_settings()

    if collection_name is None:
        collection_name = settings.collection_name

    client = get_chroma_client(settings)

    # Import embedding function only when needed (requires sentence-transformers)
    from chromadb.utils import embedding_functions

    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=settings.embedding_model
    )

    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )


def add_documents(
    chunks: Sequence[DocumentChunk],
    collection_name: str | None = None,
    settings: ChromaSettings | None = None,
) -> int:
    """Add document chunks to ChromaDB.

    Requires sentence-transformers for embedding generation.

    Args:
        chunks: Sequence of DocumentChunk objects to add
        collection_name: Optional collection name
        settings: Optional ChromaDB settings

    Returns:
        Number of chunks added
    """
    if not chunks:
        return 0

    collection = get_collection_for_add(collection_name, settings)

    ids = [chunk.chunk_id for chunk in chunks]
    documents = [chunk.content for chunk in chunks]
    metadatas = [chunk.metadata.to_chroma_metadata() for chunk in chunks]

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )

    return len(chunks)


def query_documents(
    query: str,
    n_results: int = 5,
    collection_name: str | None = None,
    settings: ChromaSettings | None = None,
) -> list[QueryResult]:
    """Query documents from ChromaDB.

    Does NOT require sentence-transformers - uses server-side embeddings.

    Args:
        query: Search query text
        n_results: Number of results to return
        collection_name: Optional collection name
        settings: Optional ChromaDB settings

    Returns:
        List of QueryResult objects with similarity scores
    """
    collection = get_collection_for_query(collection_name, settings)

    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    query_results: list[QueryResult] = []

    # Results are nested lists (one per query)
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for doc, meta, dist in zip(documents, metadatas, distances, strict=False):
        if doc and meta:
            query_results.append(
                QueryResult.from_chroma_result(
                    document=doc,
                    metadata=meta,
                    distance=dist,
                )
            )

    return query_results


def list_documents(
    limit: int = 100,
    offset: int = 0,
    collection_name: str | None = None,
    settings: ChromaSettings | None = None,
) -> tuple[list[dict], int]:
    """List documents in ChromaDB collection with pagination.

    Does NOT require sentence-transformers.

    Args:
        limit: Maximum number of documents to return
        offset: Number of documents to skip
        collection_name: Optional collection name
        settings: Optional ChromaDB settings

    Returns:
        Tuple of (list of document metadata dicts, total count)
    """
    collection = get_collection_for_query(collection_name, settings)

    # Get total count
    total = collection.count()

    if total == 0:
        return [], 0

    # Get all IDs and metadata (ChromaDB doesn't support offset directly)
    # We need to fetch more than needed and slice
    results = collection.get(
        include=["metadatas"],
        limit=limit + offset if offset > 0 else limit,
    )

    metadatas = results.get("metadatas", [])

    # Apply offset
    if offset > 0:
        metadatas = metadatas[offset:]

    # Apply limit
    metadatas = metadatas[:limit]

    return metadatas, total
