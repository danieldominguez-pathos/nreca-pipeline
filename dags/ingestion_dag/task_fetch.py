"""File fetching task utilities."""

from __future__ import annotations


def fetch_file_content(filename: str) -> dict:
    """Fetch file content from storage backend.

    Uses the storage package to retrieve file content based on APP_ENV.
    - APP_ENV=local: reads from local filesystem
    - APP_ENV=prod: reads from S3

    Args:
        filename: Name of the file to fetch

    Returns:
        Dict with file content and metadata:
        - content: bytes (base64 encoded for serialization)
        - filename: original filename
        - path: canonical path (localpath/<file> or s3://...)
        - size: file size in bytes

    Raises:
        FileNotFoundError: If file does not exist
    """
    import base64

    from storage import get_storage

    storage = get_storage()

    if not storage.exists(filename):
        raise FileNotFoundError(f"File not found: {filename}")

    content = storage.read(filename)
    path = storage.get_path(filename)

    return {
        "content_b64": base64.b64encode(content).decode("utf-8"),
        "filename": filename,
        "path": path,
        "size": len(content),
    }
