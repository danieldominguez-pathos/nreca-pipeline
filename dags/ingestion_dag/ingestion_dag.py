"""Document ingestion DAG for processing files into ChromaDB.

Pipeline flow:
1. Receive list of file_ids OR process all PENDING files
2. Fetch & parse documents in parallel
3. Chunk text with overlap
4. Generate embeddings (concurrent)
5. Aggregate chunks from all files
6. Write to ChromaDB in batch
7. Update metadata and summarize

Trigger modes:
- With file_ids: {"file_ids": ["uuid1", "uuid2", ...]}
- Process all pending: {"process_pending": true} or just {}

CRITICAL PATTERNS (Airflow 3.x):
- Tasks using @task.virtualenv MUST be defined INSIDE the @dag function
- All imports MUST be inside the task function body
- Use sys.path.insert(0, "/opt/airflow") to access custom packages
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from airflow.sdk import dag, task


@dag(
    dag_id="ingestion_dag",
    description="Ingest documents from S3/local into ChromaDB",
    schedule=None,  # Triggered via API only
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=3,
    default_args={
        "owner": "airflow",
        "retries": 2,
        "retry_delay": timedelta(minutes=1),
    },
    tags=["ingestion", "rag", "chromadb"],
    params={
        "file_ids": [],  # List of file UUIDs to process (explicit mode)
        "process_pending": False,  # If true, process all PENDING files
        "pending_limit": 50,  # Max files to process in pending mode
    },
)
def ingestion_dag() -> None:
    """Document ingestion pipeline.

    Receives a list of file_ids (UUIDs) via DAG params and processes each
    through the full pipeline: fetch → parse → chunk → embed → store.

    Failed files are recorded in the dead_queue table.
    """

    @task
    def get_file_ids(**context) -> list[str]:
        """Get file_ids from params or fetch all PENDING files.

        Modes:
        - Explicit: {"file_ids": ["uuid1", "uuid2"]}
        - All pending: {"process_pending": true} or {} (empty)
        """
        params = context.get("params", {})
        file_ids = params.get("file_ids", [])
        process_pending = params.get("process_pending", False)
        pending_limit = params.get("pending_limit", 50)

        # If explicit file_ids provided, use them
        if file_ids:
            print(f"[INGESTION] Processing {len(file_ids)} explicit file(s)")
            return file_ids

        # Otherwise, fetch all PENDING files (uses raw SQL to avoid SQLAlchemy 2.x issues)
        import os

        import psycopg

        db_url = os.environ.get(
            "DATABASE_URL", "postgresql+psycopg://app:app@postgres:5432/app"
        )
        # Convert SQLAlchemy URL to psycopg format
        dsn = db_url.replace("postgresql+psycopg://", "postgresql://")

        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM file_records WHERE status = 'PENDING' ORDER BY created_at ASC LIMIT %s",
                    (pending_limit,),
                )
                rows = cur.fetchall()
                pending_ids = [str(row[0]) for row in rows]

        if pending_ids:
            print(f"[INGESTION] Found {len(pending_ids)} PENDING file(s)")
            return pending_ids

        print("[INGESTION] No PENDING files found")
        return []

    @task
    def get_dag_run_id(**context) -> str:
        """Get DAG run ID for dead_queue tracking."""
        return context.get("run_id", "unknown")

    @task.virtualenv(
        requirements=[
            "boto3>=1.35.0",
            "pypdf>=4.0.0",
            "python-docx>=1.1.0",
            "pydantic>=2.9.0",
            "pydantic-settings>=2.6.0",
            "sqlalchemy>=2.0.0",
            "psycopg[binary]>=3.0",
            "sqlmodel>=0.0.22",
        ],
        system_site_packages=True,
        venv_cache_path="/opt/airflow/venv_cache",
    )
    def fetch_and_parse(file_id: str, dag_run_id: str) -> dict[str, Any]:
        """Fetch and parse a single file.

        Args:
            file_id: UUID of the file from file_records
            dag_run_id: DAG run ID for error tracking

        Returns:
            Dict with parsed content and metadata, or error info
        """
        import sys
        import traceback

        sys.path.insert(0, "/opt/airflow")
        sys.path.insert(0, "/opt/airflow/dags")

        from utils import get_logger

        log = get_logger("ingestion_dag.fetch_and_parse")

        # Get file info from database
        from ingestion_dag.task_file_records import (
            get_file_record_by_id,
            update_file_status,
        )

        record = get_file_record_by_id(file_id)
        if not record:
            log.error("file_not_found", file_id=file_id)
            return {
                "success": False,
                "file_id": file_id,
                "filename": "unknown",
                "error": f"File record not found: {file_id}",
                "chunks": [],
            }

        filename = record["filename"]
        log.info("processing_file", file_id=file_id, filename=filename)

        # Update status to PROCESSING
        update_file_status(filename=filename, status="PROCESSING")

        try:
            # Fetch file content
            from ingestion_dag.task_fetch import fetch_file_content

            fetch_result = fetch_file_content(filename)
            log.info("file_fetched", filename=filename, size=fetch_result["size"])

            # Parse document
            from ingestion_dag.task_parse import parse_document

            parse_result = parse_document(fetch_result["content_b64"], filename)
            parse_result["path"] = fetch_result["path"]
            log.info(
                "document_parsed",
                filename=filename,
                file_type=parse_result["file_type"],
                text_length=len(parse_result["text"]),
            )

            # Chunk text
            from ingestion_dag.task_chunk import chunk_text

            chunks = chunk_text(
                text=parse_result["text"],
                filename=filename,
                path=parse_result["path"],
                chunk_size=512,
                chunk_overlap=50,
            )
            log.info("content_chunked", filename=filename, chunk_count=len(chunks))

            return {
                "success": True,
                "file_id": file_id,
                "filename": filename,
                "path": fetch_result["path"],
                "chunks": chunks,
                "error": None,
            }

        except Exception as e:
            error_message = f"{type(e).__name__}: {e}"
            log.error(
                "fetch_parse_failed",
                filename=filename,
                error=error_message,
                traceback=traceback.format_exc(),
            )

            # Update status to FAILED
            update_file_status(
                filename=filename,
                status="FAILED",
                error_message=error_message,
            )

            # Write to dead queue
            try:
                from ingestion_dag.task_dead_queue import write_to_dead_queue

                write_to_dead_queue(
                    filename=filename,
                    path=record.get("path", filename),
                    error_message=error_message,
                    dag_run_id=dag_run_id,
                )
            except Exception as dq_error:
                log.error("dead_queue_write_failed", error=str(dq_error))

            return {
                "success": False,
                "file_id": file_id,
                "filename": filename,
                "path": record.get("path", ""),
                "chunks": [],
                "error": error_message,
            }

    @task
    def aggregate_chunks(parse_results: list[dict[str, Any]]) -> dict[str, Any]:
        """Aggregate chunks from all files for batch embedding.

        Args:
            parse_results: List of parse results from fetch_and_parse

        Returns:
            Dict with all chunks and file mapping
        """
        results_list = list(parse_results)  # Convert LazyXComSequence

        all_chunks = []
        file_mapping = {}  # chunk_index -> file_id for tracking

        successful = [r for r in results_list if r.get("success")]
        failed = [r for r in results_list if not r.get("success")]

        print(f"[AGGREGATE] Processing {len(successful)} successful, {len(failed)} failed files")

        for result in successful:
            file_id = result["file_id"]
            for chunk in result.get("chunks", []):
                chunk_idx = len(all_chunks)
                file_mapping[chunk_idx] = {
                    "file_id": file_id,
                    "filename": result["filename"],
                    "path": result["path"],
                }
                all_chunks.append(chunk)

        print(f"[AGGREGATE] Total chunks to embed: {len(all_chunks)}")

        return {
            "chunks": all_chunks,
            "file_mapping": file_mapping,
            "successful_files": [r["filename"] for r in successful],
            "failed_files": [{"filename": r["filename"], "error": r["error"]} for r in failed],
        }

    @task
    def embed_and_store(aggregated: dict[str, Any]) -> dict[str, Any]:
        """Generate embeddings and store in ChromaDB.

        Uses sentence-transformers from the base Airflow image.

        Args:
            aggregated: Aggregated chunks from all files

        Returns:
            Dict with storage results
        """
        import sys

        sys.path.insert(0, "/opt/airflow")
        sys.path.insert(0, "/opt/airflow/dags")

        from utils import get_logger

        log = get_logger("ingestion_dag.embed_and_store")

        chunks = aggregated.get("chunks", [])
        if not chunks:
            log.info("no_chunks_to_store")
            return {
                "stored_count": 0,
                "file_chunks": {},
            }

        log.info("embedding_chunks", count=len(chunks))

        # Store in ChromaDB (embeddings generated internally)
        from ingestion_dag.task_embed import embed_and_store_chunks

        store_result = embed_and_store_chunks(chunks)

        log.info("chunks_stored", stored_count=store_result["stored_count"])

        # Count chunks per file
        file_mapping = aggregated.get("file_mapping", {})
        file_chunks: dict[str, int] = {}
        for _idx, info in file_mapping.items():
            filename = info["filename"]
            file_chunks[filename] = file_chunks.get(filename, 0) + 1

        return {
            "stored_count": store_result["stored_count"],
            "file_chunks": file_chunks,
        }

    @task.virtualenv(
        requirements=[
            "pydantic>=2.9.0",
            "pydantic-settings>=2.6.0",
            "sqlalchemy>=2.0.0",
            "psycopg[binary]>=3.0",
            "sqlmodel>=0.0.22",
        ],
        system_site_packages=True,
        venv_cache_path="/opt/airflow/venv_cache",
    )
    def update_metadata(
        store_result: dict[str, Any],
        aggregated: dict[str, Any],
    ) -> None:
        """Update file_records with chunk counts for successful files."""
        import sys

        sys.path.insert(0, "/opt/airflow")
        sys.path.insert(0, "/opt/airflow/dags")

        from utils import get_logger

        log = get_logger("ingestion_dag.update_metadata")

        from ingestion_dag.task_file_records import update_file_status

        file_chunks = store_result.get("file_chunks", {})
        successful_files = aggregated.get("successful_files", [])

        for filename in successful_files:
            chunk_count = file_chunks.get(filename, 0)
            update_file_status(
                filename=filename,
                status="LOADED",
                chunk_count=chunk_count,
            )
            log.info(
                "file_status_updated",
                filename=filename,
                status="LOADED",
                chunks=chunk_count,
            )

    @task
    def summarize(
        aggregated: dict[str, Any],
        store_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Summarize ingestion results."""
        successful = aggregated.get("successful_files", [])
        failed = aggregated.get("failed_files", [])
        total_stored = store_result.get("stored_count", 0)
        file_chunks = store_result.get("file_chunks", {})

        print("=" * 60)
        print("INGESTION SUMMARY")
        print("=" * 60)
        print(f"Total files: {len(successful) + len(failed)}")
        print(f"Successful: {len(successful)}")
        print(f"Failed: {len(failed)}")
        print(f"Total chunks stored: {total_stored}")
        print("-" * 60)

        if successful:
            print("Successful files:")
            for filename in successful:
                chunks = file_chunks.get(filename, 0)
                print(f"  + {filename}: {chunks} chunks")

        if failed:
            print("Failed files (written to dead_queue):")
            for f in failed:
                print(f"  x {f['filename']}: {f['error']}")

        print("=" * 60)

        return {
            "total_files": len(successful) + len(failed),
            "successful": len(successful),
            "failed": len(failed),
            "total_chunks_stored": total_stored,
            "successful_files": successful,
            "failed_files": [f["filename"] for f in failed],
        }

    # =========================================================================
    # DAG FLOW
    # =========================================================================

    # Step 1: Get file_ids and DAG run ID
    file_ids = get_file_ids()
    dag_run_id = get_dag_run_id()

    # Step 2: Fetch and parse each file (parallel via expand)
    parse_results = fetch_and_parse.partial(dag_run_id=dag_run_id).expand(file_id=file_ids)

    # Step 3: Aggregate chunks from all files
    aggregated = aggregate_chunks(parse_results)

    # Step 4: Embed and store in ChromaDB (batch operation)
    store_result = embed_and_store(aggregated)

    # Step 5: Update file metadata (parallel with summarize)
    update_metadata(store_result, aggregated)

    # Step 6: Summarize results
    summarize(aggregated, store_result)


# Instantiate the DAG
ingestion_dag()
