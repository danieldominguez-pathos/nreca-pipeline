"""Embedding and ChromaDB storage task utilities."""

from __future__ import annotations


def embed_and_store_chunks(chunks: list[dict]) -> dict:
    """Generate embeddings and store chunks in ChromaDB.

    Uses the vectordb package to:
    1. Create DocumentChunk objects from chunk dicts
    2. Add them to ChromaDB with metadata

    Args:
        chunks: List of chunk dicts from task_chunk

    Returns:
        Dict with storage results:
        - stored_count: number of chunks stored
        - filename: original filename
        - path: canonical path
    """
    from datetime import datetime
    from uuid import UUID

    from vectordb import DocumentChunk, DocumentMetadata, add_documents

    if not chunks:
        return {
            "stored_count": 0,
            "filename": None,
            "path": None,
        }

    doc_chunks: list[DocumentChunk] = []

    for chunk in chunks:
        metadata = DocumentMetadata(
            id=UUID(chunk["id"]) if isinstance(chunk["id"], str) else chunk["id"],
            path=chunk["path"],
            filename=chunk["filename"],
            chunk_index=chunk["chunk_index"],
            total_chunks=chunk["total_chunks"],
            ingested_at=datetime.utcnow(),
        )

        doc_chunk = DocumentChunk(
            content=chunk["content"],
            metadata=metadata,
        )
        doc_chunks.append(doc_chunk)

    stored_count = add_documents(doc_chunks)

    return {
        "stored_count": stored_count,
        "filename": chunks[0]["filename"],
        "path": chunks[0]["path"],
    }
