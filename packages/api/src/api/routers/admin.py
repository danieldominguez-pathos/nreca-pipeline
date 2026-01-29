"""Admin router - GET /dead_queue, GET /chroma_list, GET /list_files endpoints."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query
from utils import get_logger
from vectordb import list_documents

from api.schemas.responses import (
    ChromaDocument,
    ChromaListResponse,
    DeadQueueItem,
    DeadQueueResponse,
    FileItem,
    ListFilesResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"])
log = get_logger("api.routers.admin")


@router.get("/dead_queue", response_model=DeadQueueResponse)
async def get_dead_queue(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> DeadQueueResponse:
    """List files that failed ingestion.

    Reads from the dead_queue table in PostgreSQL.

    Args:
        limit: Maximum number of entries to return
        offset: Number of entries to skip

    Returns:
        DeadQueueResponse with failed files and count
    """
    log.info("dead_queue_request", limit=limit, offset=offset)

    # Import here to avoid circular imports and allow virtualenv usage
    import sys

    sys.path.insert(0, "/opt/airflow/dags")

    try:
        from ingestion_dag.task_dead_queue import get_dead_queue_entries

        entries, total = get_dead_queue_entries(limit=limit, offset=offset)

        failed_files = [
            DeadQueueItem(
                filename=entry["filename"],
                path=entry["path"],
                error=entry["error"],
                failed_at=datetime.fromisoformat(entry["failed_at"]),
                dag_run_id=entry["dag_run_id"],
            )
            for entry in entries
        ]

        log.info("dead_queue_response", count=len(failed_files), total=total)

        return DeadQueueResponse(
            failed_files=failed_files,
            count=total,
        )

    except ImportError:
        # Fallback for when running outside Airflow context
        log.warning("dead_queue_import_failed")
        return DeadQueueResponse(failed_files=[], count=0)


@router.get("/chroma_list", response_model=ChromaListResponse)
async def get_chroma_list(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    include_content: bool = Query(default=False, description="Include chunk text content"),
) -> ChromaListResponse:
    """List contents in ChromaDB collection.

    Args:
        limit: Maximum number of documents to return
        offset: Number of documents to skip
        include_content: Whether to include chunk text content

    Returns:
        ChromaListResponse with documents and pagination info
    """
    log.info("chroma_list_request", limit=limit, offset=offset, include_content=include_content)

    metadatas, total = list_documents(limit=limit, offset=offset, include_content=include_content)

    documents = [
        ChromaDocument(
            id=meta.get("id", ""),
            path=meta.get("path", ""),
            filename=meta.get("filename", ""),
            chunk_index=meta.get("chunk_index", 0),
            total_chunks=meta.get("total_chunks", 0),
            ingested_at=meta.get("ingested_at", ""),
            chunk=meta.get("chunk"),
        )
        for meta in metadatas
    ]

    log.info("chroma_list_response", count=len(documents), total=total)

    return ChromaListResponse(
        documents=documents,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/chroma_stats")
async def get_chroma_stats() -> dict:
    """Get ChromaDB collection statistics.

    Returns:
        Statistics including total chunks, unique files, etc.
    """
    log.info("chroma_stats_request")

    # Get all metadatas to compute stats
    metadatas, total = list_documents(limit=10000, offset=0)

    unique_files = set()
    for meta in metadatas:
        filename = meta.get("filename", "")
        if filename:
            unique_files.add(filename)

    stats = {
        "total_chunks": total,
        "loaded_files": len(unique_files),
        "files": sorted(unique_files),
    }

    log.info("chroma_stats_response", **stats)
    return stats


@router.get("/list_files", response_model=ListFilesResponse)
async def list_files(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    status: Literal["PENDING", "PROCESSING", "LOADED", "FAILED"] | None = Query(
        default=None, description="Filter by status"
    ),
) -> ListFilesResponse:
    """List files from the file registry with their ingestion status.

    Returns files from the file_records table in PostgreSQL with:
    - id: UUID
    - path: S3 URI or localpath
    - chroma_status: PENDING, PROCESSING, LOADED, or FAILED
    - size: Human-readable size (e.g., 1.5 MB)

    Args:
        limit: Maximum number of files to return
        offset: Number of files to skip
        status: Optional filter by status

    Returns:
        ListFilesResponse with files and pagination info
    """
    log.info("list_files_request", limit=limit, offset=offset, status=status)

    # Import here to avoid circular imports
    import sys

    sys.path.insert(0, "/opt/airflow/dags")

    try:
        from ingestion_dag.task_file_records import get_file_records

        records, total = get_file_records(
            limit=limit,
            offset=offset,
            status_filter=status,
        )

        files = [
            FileItem(
                id=record["id"],
                path=record["path"],
                chroma_status=record["chroma_status"],
                size=record["size"],
                chunk_count=record.get("chunk_count", 0),
                error_message=record.get("error_message"),
            )
            for record in records
        ]

        log.info("list_files_response", count=len(files), total=total)

        return ListFilesResponse(
            files=files,
            total=total,
            limit=limit,
            offset=offset,
        )

    except ImportError as e:
        log.warning("list_files_import_failed", error=str(e))
        return ListFilesResponse(files=[], total=0, limit=limit, offset=offset)
