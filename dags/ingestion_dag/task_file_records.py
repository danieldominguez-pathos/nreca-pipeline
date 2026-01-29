"""File record management utilities."""

from __future__ import annotations

from datetime import datetime

# Size constants for human-readable formatting
KB = 1024
MB = KB * 1024
GB = MB * 1024


def format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable string (e.g., "1.5 MB", "256 KB")
    """
    if size_bytes >= GB:
        return f"{size_bytes / GB:.1f} GB"
    elif size_bytes >= MB:
        return f"{size_bytes / MB:.1f} MB"
    elif size_bytes >= KB:
        return f"{size_bytes / KB:.1f} KB"
    else:
        return f"{size_bytes} B"


def register_file(filename: str, path: str, size_bytes: int) -> dict:
    """Register a new file with PENDING status.

    Called by registration_dag when discovering new files.

    Args:
        filename: Name of the file
        path: Full path (S3 URI or localpath)
        size_bytes: File size in bytes

    Returns:
        Dict with file record details
    """
    from db import FileRecord, get_session

    with get_session() as session:
        record = FileRecord(
            filename=filename,
            path=path,
            size_bytes=size_bytes,
            status="PENDING",
        )
        session.add(record)
        session.flush()

        return {
            "id": str(record.id),
            "filename": record.filename,
            "path": record.path,
            "size_bytes": record.size_bytes,
            "size": format_size(record.size_bytes),
            "status": record.status,
        }


def get_registered_filenames() -> set[str]:
    """Get set of all registered filenames.

    Used by registration_dag to skip already registered files.

    Returns:
        Set of filenames
    """
    from db import FileRecord, get_session
    from sqlalchemy import select

    with get_session() as session:
        stmt = select(FileRecord.filename)
        results = session.execute(stmt).scalars().all()
        return set(results)


def update_file_status(
    filename: str,
    status: str,
    chunk_count: int | None = None,
    error_message: str | None = None,
) -> dict | None:
    """Update file status and optionally chunk_count/error_message.

    Called by ingestion_dag during processing.

    Args:
        filename: Name of the file
        status: PROCESSING, LOADED, or FAILED
        chunk_count: Number of chunks stored (for LOADED status)
        error_message: Error message (for FAILED status)

    Returns:
        Dict with updated record or None if not found
    """
    from db import FileRecord, get_session
    from sqlalchemy import select

    with get_session() as session:
        stmt = select(FileRecord).where(FileRecord.filename == filename)
        record = session.execute(stmt).scalar_one_or_none()

        if not record:
            return None

        record.status = status
        record.updated_at = datetime.utcnow()

        if chunk_count is not None:
            record.chunk_count = chunk_count

        if error_message is not None:
            record.error_message = error_message

        session.flush()

        return {
            "id": str(record.id),
            "filename": record.filename,
            "status": record.status,
            "chunk_count": record.chunk_count,
            "error_message": record.error_message,
        }


def get_file_records(
    limit: int = 100,
    offset: int = 0,
    status_filter: str | None = None,
) -> tuple[list[dict], int]:
    """Get file records with pagination.

    Args:
        limit: Maximum records to return
        offset: Number of records to skip
        status_filter: Optional status filter (PENDING, PROCESSING, LOADED, FAILED)

    Returns:
        Tuple of (list of file record dicts, total count)
    """
    from db import FileRecord, get_session
    from sqlalchemy import func, select

    with get_session() as session:
        # Build base query
        base_query = select(FileRecord)
        count_query = select(func.count()).select_from(FileRecord)

        if status_filter:
            base_query = base_query.where(FileRecord.status == status_filter)
            count_query = count_query.where(FileRecord.status == status_filter)

        # Get total count
        total = session.execute(count_query).scalar() or 0

        # Get records
        stmt = (
            base_query
            .order_by(FileRecord.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        results = session.execute(stmt).scalars().all()

        records = [
            {
                "id": str(r.id),
                "filename": r.filename,
                "path": r.path,
                "size_bytes": r.size_bytes,
                "size": format_size(r.size_bytes),
                "chroma_status": r.status,
                "chunk_count": r.chunk_count,
                "error_message": r.error_message,
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat(),
            }
            for r in results
        ]

        return records, total


def get_file_record_by_id(file_id: str) -> dict | None:
    """Get a single file record by ID.

    Args:
        file_id: UUID of the file

    Returns:
        File record dict or None if not found
    """
    from uuid import UUID

    from db import FileRecord, get_session
    from sqlalchemy import select

    try:
        uuid_id = UUID(file_id)
    except ValueError:
        return None

    with get_session() as session:
        stmt = select(FileRecord).where(FileRecord.id == uuid_id)
        record = session.execute(stmt).scalar_one_or_none()

        if not record:
            return None

        return {
            "id": str(record.id),
            "filename": record.filename,
            "path": record.path,
            "size_bytes": record.size_bytes,
            "size": format_size(record.size_bytes),
            "status": record.status,
            "chunk_count": record.chunk_count,
            "error_message": record.error_message,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }


def get_file_record_by_filename(filename: str) -> dict | None:
    """Get a single file record by filename.

    Args:
        filename: Name of the file

    Returns:
        File record dict or None if not found
    """
    from db import FileRecord, get_session
    from sqlalchemy import select

    with get_session() as session:
        stmt = select(FileRecord).where(FileRecord.filename == filename)
        record = session.execute(stmt).scalar_one_or_none()

        if not record:
            return None

        return {
            "id": str(record.id),
            "filename": record.filename,
            "path": record.path,
            "size_bytes": record.size_bytes,
            "size": format_size(record.size_bytes),
            "chroma_status": record.status,
            "chunk_count": record.chunk_count,
            "error_message": record.error_message,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }


def get_pending_file_ids(limit: int = 100) -> list[str]:
    """Get IDs of all files with PENDING status.

    Used by ingestion_dag when triggered without explicit file_ids.

    Args:
        limit: Maximum number of file IDs to return

    Returns:
        List of file ID strings (UUIDs)
    """
    from db import FileRecord, get_session
    from sqlalchemy import select

    with get_session() as session:
        stmt = (
            select(FileRecord.id)
            .where(FileRecord.status == "PENDING")
            .order_by(FileRecord.created_at.asc())
            .limit(limit)
        )
        results = session.execute(stmt).scalars().all()
        return [str(r) for r in results]
