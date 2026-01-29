"""Text chunking task utilities."""

from __future__ import annotations


def chunk_text(
    text: str,
    filename: str,
    path: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> list[dict]:
    """Split text into overlapping chunks for embedding.

    Uses character-based chunking with overlap to preserve context.
    Each chunk includes metadata for ChromaDB storage.

    Args:
        text: Full text content to chunk
        filename: Original filename
        path: Canonical path (localpath/<file> or s3://...)
        chunk_size: Target size of each chunk in characters
        chunk_overlap: Number of overlapping characters between chunks

    Returns:
        List of chunk dicts with:
        - content: chunk text
        - filename: original filename
        - path: canonical path
        - chunk_index: position in document
        - total_chunks: total number of chunks
    """
    from uuid import uuid4

    if not text.strip():
        return []

    # Clean text - normalize whitespace
    text = " ".join(text.split())

    chunks: list[dict] = []
    start = 0
    chunk_index = 0

    while start < len(text):
        end = start + chunk_size

        # Try to break at sentence/word boundary
        if end < len(text):
            # Look for sentence boundary
            for sep in [". ", "! ", "? ", "\n"]:
                boundary = text.rfind(sep, start, end)
                if boundary > start + chunk_size // 2:
                    end = boundary + len(sep)
                    break
            else:
                # Fall back to word boundary
                space = text.rfind(" ", start, end)
                if space > start + chunk_size // 2:
                    end = space + 1

        chunk_text = text[start:end].strip()

        if chunk_text:
            chunks.append({
                "id": str(uuid4()),
                "content": chunk_text,
                "filename": filename,
                "path": path,
                "chunk_index": chunk_index,
            })
            chunk_index += 1

        # Move start position with overlap
        start = end - chunk_overlap if end < len(text) else end

    # Add total_chunks to all chunks
    total = len(chunks)
    for chunk in chunks:
        chunk["total_chunks"] = total

    return chunks
