"""Ingest router - file registration and ingestion endpoints."""

import os
import sys

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from utils import get_logger

from api.schemas import LoadFileRequest, LoadFileResponse
from api.services import get_airflow_client

router = APIRouter(prefix="/ingest", tags=["ingest"])
log = get_logger("api.routers.ingest")


class RegisterFilesRequest(BaseModel):
    """Request to register files by filename."""

    filenames: list[str]


class RegisterFilesResponse(BaseModel):
    """Response from file registration."""

    registered: list[str]
    skipped: list[str]
    errors: list[str]


class IngestPendingResponse(BaseModel):
    """Response from triggering pending file ingestion."""

    status: str
    dag_run_id: str
    pending_count: int


@router.post("/load_file", response_model=LoadFileResponse)
async def load_file(request: LoadFileRequest) -> LoadFileResponse:
    """Trigger file ingestion pipeline.

    Looks up file IDs from the database and triggers Airflow ingestion_dag.
    Files must be registered first (via registration_dag or direct DB insert).

    Args:
        request: LoadFileRequest with list of filenames

    Returns:
        LoadFileResponse with DAG run ID and file info
    """
    log.info("load_file_request", filenames=request.filenames)

    # Import DAG helpers (add path for Airflow environment compatibility)
    sys.path.insert(0, "/opt/airflow/dags")

    try:
        from ingestion_dag.task_file_records import get_file_record_by_filename
    except ImportError:
        log.warning("dag_imports_failed", hint="Running outside Airflow context")
        raise HTTPException(
            status_code=503,
            detail="File record service not available",
        )

    # Look up file IDs from database
    file_ids = []
    not_found = []

    for filename in request.filenames:
        record = get_file_record_by_filename(filename)
        if record:
            file_ids.append(record["id"])
        else:
            not_found.append(filename)

    if not_found:
        log.warning("files_not_registered", not_found=not_found)
        raise HTTPException(
            status_code=404,
            detail=f"Files not registered: {', '.join(not_found)}. Run registration_dag first.",
        )

    # Trigger Airflow DAG with file_ids
    try:
        airflow = get_airflow_client()
        result = await airflow.trigger_dag(
            dag_id="ingestion_dag",
            conf={"file_ids": file_ids},
        )

        log.info(
            "ingestion_triggered",
            dag_run_id=result["dag_run_id"],
            file_count=len(file_ids),
        )

        return LoadFileResponse(
            status="triggered",
            dag_run_id=result["dag_run_id"],
            filenames=request.filenames,
            file_count=len(request.filenames),
        )

    except Exception as e:
        log.error("airflow_trigger_failed", error=str(e))
        raise HTTPException(
            status_code=503,
            detail=f"Failed to trigger ingestion: {e}",
        )


@router.post("/register", response_model=RegisterFilesResponse)
async def register_files(request: RegisterFilesRequest) -> RegisterFilesResponse:
    """Register files for ingestion.

    Files must exist in TEST_FILES_PATH directory.
    Skips already-registered files.

    Args:
        request: RegisterFilesRequest with list of filenames

    Returns:
        RegisterFilesResponse with registered, skipped, and error lists
    """
    log.info("register_files_request", count=len(request.filenames))

    sys.path.insert(0, "/opt/airflow/dags")

    try:
        from ingestion_dag.task_file_records import (
            get_registered_filenames,
            register_file,
        )
    except ImportError:
        log.warning("dag_imports_failed")
        raise HTTPException(status_code=503, detail="File record service not available")

    files_dir = os.environ.get("TEST_FILES_PATH", "/data/files")
    existing = get_registered_filenames()

    registered = []
    skipped = []
    errors = []

    for filename in request.filenames:
        if filename in existing:
            skipped.append(filename)
            continue

        filepath = os.path.join(files_dir, filename)
        if not os.path.exists(filepath):
            errors.append(f"{filename}: not found in {files_dir}")
            continue

        try:
            size = os.path.getsize(filepath)
            register_file(
                filename=filename,
                path=f"localpath/{filename}",
                size_bytes=size,
            )
            registered.append(filename)
        except Exception as e:
            errors.append(f"{filename}: {e}")

    log.info(
        "register_files_complete",
        registered=len(registered),
        skipped=len(skipped),
        errors=len(errors),
    )

    return RegisterFilesResponse(
        registered=registered,
        skipped=skipped,
        errors=errors,
    )


@router.post("/pending", response_model=IngestPendingResponse)
async def ingest_pending(limit: int = 50) -> IngestPendingResponse:
    """Trigger ingestion for all PENDING files.

    Args:
        limit: Maximum number of files to process (default 50)

    Returns:
        IngestPendingResponse with DAG run info
    """
    log.info("ingest_pending_request", limit=limit)

    sys.path.insert(0, "/opt/airflow/dags")

    try:
        from ingestion_dag.task_file_records import get_pending_file_ids
    except ImportError:
        log.warning("dag_imports_failed")
        raise HTTPException(status_code=503, detail="File record service not available")

    pending_ids = get_pending_file_ids(limit=limit)

    if not pending_ids:
        return IngestPendingResponse(
            status="no_pending_files",
            dag_run_id="",
            pending_count=0,
        )

    try:
        airflow = get_airflow_client()
        result = await airflow.trigger_dag(
            dag_id="ingestion_dag",
            conf={"file_ids": pending_ids},
        )

        log.info(
            "pending_ingestion_triggered",
            dag_run_id=result["dag_run_id"],
            file_count=len(pending_ids),
        )

        return IngestPendingResponse(
            status="triggered",
            dag_run_id=result["dag_run_id"],
            pending_count=len(pending_ids),
        )

    except Exception as e:
        log.error("airflow_trigger_failed", error=str(e))
        raise HTTPException(
            status_code=503,
            detail=f"Failed to trigger ingestion: {e}",
        )
