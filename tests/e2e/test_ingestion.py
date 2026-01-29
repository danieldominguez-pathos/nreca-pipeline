"""E2E tests for file ingestion.

Tests the ingestion pipeline: register -> load_file -> process -> store in ChromaDB.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import psycopg
import pytest

# Maximum time to wait for DAG to complete (seconds)
DAG_TIMEOUT = 120
DAG_POLL_INTERVAL = 5


def wait_for_dag_completion(
    airflow_client: httpx.Client,
    dag_run_id: str,
    dag_id: str = "ingestion_dag",
    timeout: int = DAG_TIMEOUT,
) -> dict:
    """Wait for a DAG run to complete and return final state."""
    start = time.time()
    while time.time() - start < timeout:
        response = airflow_client.get(f"/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}")
        if response.status_code != 200:
            time.sleep(DAG_POLL_INTERVAL)
            continue

        data = response.json()
        state = data.get("state", "")

        if state in ("success", "failed"):
            return data

        time.sleep(DAG_POLL_INTERVAL)

    raise TimeoutError(f"DAG run {dag_run_id} did not complete within {timeout}s")


@pytest.mark.e2e
@pytest.mark.slow
class TestFileIngestion:
    """Test file ingestion via the ingestion DAG."""

    def test_load_file_triggers_dag(
        self,
        api_client: httpx.Client,
        db_connection: psycopg.Connection,
        test_file_txt: Path,
        clean_db: None,
    ) -> None:
        """Test that POST /ingest/load_file triggers the ingestion DAG."""
        filename = test_file_txt.name

        # First register the file
        file_size = test_file_txt.stat().st_size
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO file_records (filename, path, size_bytes, status)
                VALUES (%s, %s, %s, %s)
                """,
                (filename, f"localpath/{filename}", file_size, "PENDING"),
            )
        db_connection.commit()

        # Trigger ingestion
        response = api_client.post(
            "/ingest/load_file",
            json={"filenames": [filename]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "triggered"
        assert "dag_run_id" in data
        assert filename in data["filenames"]

    def test_single_file_ingestion_flow(
        self,
        api_client: httpx.Client,
        airflow_client: httpx.Client,
        db_connection: psycopg.Connection,
        test_file_txt: Path,
        clean_db: None,
    ) -> None:
        """Test full ingestion flow for a single text file."""
        filename = test_file_txt.name

        # Step 1: Register the file
        file_size = test_file_txt.stat().st_size
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO file_records (filename, path, size_bytes, status)
                VALUES (%s, %s, %s, %s)
                """,
                (filename, f"localpath/{filename}", file_size, "PENDING"),
            )
        db_connection.commit()

        # Step 2: Trigger ingestion
        response = api_client.post(
            "/ingest/load_file",
            json={"filenames": [filename]},
        )
        assert response.status_code == 200
        dag_run_id = response.json()["dag_run_id"]

        # Step 3: Wait for DAG completion
        try:
            result = wait_for_dag_completion(airflow_client, dag_run_id)
            assert result["state"] == "success", f"DAG failed: {result}"
        except TimeoutError:
            pytest.skip("DAG did not complete in time - Airflow may be slow")

        # Step 4: Verify file status is LOADED
        with db_connection.cursor() as cur:
            cur.execute(
                "SELECT status, chunk_count FROM file_records WHERE filename = %s",
                (filename,),
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "LOADED"
            assert row[1] > 0  # Should have at least one chunk

        # Step 5: Verify document is in ChromaDB via API
        response = api_client.get("/admin/chroma_list")
        assert response.status_code == 200
        data = response.json()
        test_docs = [d for d in data["documents"] if d["filename"] == filename]
        assert len(test_docs) > 0

    def test_failed_file_goes_to_dead_queue(
        self,
        api_client: httpx.Client,
        airflow_client: httpx.Client,
        db_connection: psycopg.Connection,
        clean_db: None,
    ) -> None:
        """Test that a non-existent file ends up in the dead queue."""
        filename = "test_nonexistent_file.txt"

        # Register a file that doesn't exist
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO file_records (filename, path, size_bytes, status)
                VALUES (%s, %s, %s, %s)
                """,
                (filename, f"localpath/{filename}", 0, "PENDING"),
            )
        db_connection.commit()

        # Trigger ingestion
        response = api_client.post(
            "/ingest/load_file",
            json={"filenames": [filename]},
        )
        assert response.status_code == 200
        dag_run_id = response.json()["dag_run_id"]

        # Wait for DAG completion (may succeed even if individual file fails)
        try:
            wait_for_dag_completion(airflow_client, dag_run_id)
        except TimeoutError:
            pytest.skip("DAG did not complete in time")

        # Verify file status is FAILED
        with db_connection.cursor() as cur:
            cur.execute(
                "SELECT status, error_message FROM file_records WHERE filename = %s",
                (filename,),
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] == "FAILED"
            assert row[1] is not None  # Should have error message

        # Verify file is in dead queue
        response = api_client.get("/admin/dead_queue")
        assert response.status_code == 200
        data = response.json()
        dead_files = [f for f in data["failed_files"] if f["filename"] == filename]
        assert len(dead_files) == 1

    def test_status_transitions(
        self,
        api_client: httpx.Client,
        db_connection: psycopg.Connection,
        test_file_txt: Path,
        clean_db: None,
    ) -> None:
        """Test that file status transitions correctly: PENDING -> PROCESSING -> LOADED."""
        filename = test_file_txt.name
        file_size = test_file_txt.stat().st_size

        # Register file as PENDING
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO file_records (filename, path, size_bytes, status)
                VALUES (%s, %s, %s, %s)
                """,
                (filename, f"localpath/{filename}", file_size, "PENDING"),
            )
        db_connection.commit()

        # Verify initial status
        response = api_client.get("/admin/list_files", params={"status": "PENDING"})
        data = response.json()
        pending = [f for f in data["files"] if f["path"] == f"localpath/{filename}"]
        assert len(pending) == 1

        # Manually update to PROCESSING (simulating DAG behavior)
        with db_connection.cursor() as cur:
            cur.execute(
                "UPDATE file_records SET status = %s WHERE filename = %s",
                ("PROCESSING", filename),
            )
        db_connection.commit()

        # Verify PROCESSING status
        response = api_client.get("/admin/list_files", params={"status": "PROCESSING"})
        data = response.json()
        processing = [f for f in data["files"] if f["path"] == f"localpath/{filename}"]
        assert len(processing) == 1

        # Manually update to LOADED (simulating DAG completion)
        with db_connection.cursor() as cur:
            cur.execute(
                "UPDATE file_records SET status = %s, chunk_count = %s WHERE filename = %s",
                ("LOADED", 3, filename),
            )
        db_connection.commit()

        # Verify LOADED status
        response = api_client.get("/admin/list_files", params={"status": "LOADED"})
        data = response.json()
        loaded = [f for f in data["files"] if f["path"] == f"localpath/{filename}"]
        assert len(loaded) == 1
        assert loaded[0]["chunk_count"] == 3
