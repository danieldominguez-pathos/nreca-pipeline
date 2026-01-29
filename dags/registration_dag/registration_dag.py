"""File registration DAG - scans storage and registers file metadata to PostgreSQL.

This DAG handles file discovery and registration:
1. List files from S3 bucket or local path (based on APP_ENV)
2. Register each file's metadata (filename, path, size) to file_records table
3. Set initial status to PENDING

Can be triggered manually or scheduled to run periodically.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from airflow.sdk import dag, task


@dag(
    dag_id="registration_dag",
    description="Scan storage and register file metadata to PostgreSQL",
    schedule="@hourly",  # Run hourly to pick up new files
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "airflow",
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["registration", "metadata", "storage"],
)
def registration_dag() -> None:
    """File registration pipeline.

    Scans the configured storage (S3 or local) and registers
    any new files to the file_records table with PENDING status.
    """

    @task.virtualenv(
        requirements=[
            "boto3>=1.35.0",
            "pydantic>=2.9.0",
            "pydantic-settings>=2.6.0",
            "sqlalchemy>=2.0.0",
            "psycopg[binary]>=3.0",
            "sqlmodel>=0.0.22",
        ],
        system_site_packages=True,
        venv_cache_path="/opt/airflow/venv_cache",
    )
    def scan_and_register() -> dict[str, Any]:
        """Scan storage and register new files."""
        import sys

        sys.path.insert(0, "/opt/airflow")
        sys.path.insert(0, "/opt/airflow/dags")

        from utils import get_logger

        log = get_logger("registration_dag.scan_and_register")
        log.info("starting_registration_scan")

        from storage import get_storage

        storage = get_storage()

        # List all files in storage with metadata
        files = storage.list_files_with_info()
        log.info("files_found", count=len(files))

        if not files:
            return {
                "scanned": 0,
                "registered": 0,
                "skipped": 0,
                "errors": 0,
            }

        from ingestion_dag.task_file_records import get_registered_filenames, register_file

        # Get already registered filenames to skip
        registered = get_registered_filenames()
        log.info("already_registered", count=len(registered))

        stats = {"scanned": 0, "registered": 0, "skipped": 0, "errors": 0}

        for file_info in files:
            stats["scanned"] += 1
            filename = file_info["filename"]

            if filename in registered:
                stats["skipped"] += 1
                continue

            try:
                register_file(
                    filename=filename,
                    path=file_info["path"],
                    size_bytes=file_info["size"],
                )
                stats["registered"] += 1
                log.info("file_registered", filename=filename, size=file_info["size"])
            except Exception as e:
                stats["errors"] += 1
                log.error("registration_failed", filename=filename, error=str(e))

        log.info(
            "registration_complete",
            scanned=stats["scanned"],
            registered=stats["registered"],
            skipped=stats["skipped"],
            errors=stats["errors"],
        )

        return stats

    @task
    def print_summary(stats: dict[str, Any]) -> None:
        """Print registration summary."""
        print("=" * 60)
        print("REGISTRATION SUMMARY")
        print("=" * 60)
        print(f"Files scanned: {stats['scanned']}")
        print(f"Newly registered: {stats['registered']}")
        print(f"Already registered (skipped): {stats['skipped']}")
        print(f"Errors: {stats['errors']}")
        print("=" * 60)

    # DAG flow
    stats = scan_and_register()
    print_summary(stats)


# Instantiate the DAG
registration_dag()
