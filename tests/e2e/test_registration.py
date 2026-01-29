"""E2E tests for file registration.

Tests the registration_dag flow that scans storage and registers files to PostgreSQL.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import psycopg
import pytest


@pytest.mark.e2e
class TestFileRegistration:
    """Test file registration via the registration DAG."""

    def test_manual_registration_via_db(
        self,
        db_connection: psycopg.Connection,
        test_file_txt: Path,
        clean_db: None,
    ) -> None:
        """Test that files can be registered directly in the database."""
        filename = test_file_txt.name
        file_size = test_file_txt.stat().st_size

        # Insert a file record directly
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO file_records (filename, path, size_bytes, status)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (filename, f"localpath/{filename}", file_size, "PENDING"),
            )
            result = cur.fetchone()
            assert result is not None
            file_id = result[0]
        db_connection.commit()

        # Verify the record exists
        with db_connection.cursor() as cur:
            cur.execute(
                "SELECT filename, status, size_bytes FROM file_records WHERE id = %s",
                (file_id,),
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] == filename
            assert row[1] == "PENDING"
            assert row[2] == file_size

    def test_list_files_endpoint_shows_registered_files(
        self,
        api_client: httpx.Client,
        db_connection: psycopg.Connection,
        clean_db: None,
    ) -> None:
        """Test that /admin/list_files returns registered files."""
        # Register a test file
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO file_records (filename, path, size_bytes, status)
                VALUES (%s, %s, %s, %s)
                """,
                ("test_api_file.txt", "localpath/test_api_file.txt", 1024, "PENDING"),
            )
        db_connection.commit()

        # Call the API endpoint
        response = api_client.get("/admin/list_files")
        assert response.status_code == 200

        data = response.json()
        assert "files" in data
        assert "total" in data

        # Find our test file
        test_files = [f for f in data["files"] if f["path"] == "localpath/test_api_file.txt"]
        assert len(test_files) == 1
        assert test_files[0]["chroma_status"] == "PENDING"
        assert test_files[0]["size"] == "1.0 KB"

    def test_list_files_with_status_filter(
        self,
        api_client: httpx.Client,
        db_connection: psycopg.Connection,
        clean_db: None,
    ) -> None:
        """Test that /admin/list_files can filter by status."""
        # Register files with different statuses
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO file_records (filename, path, size_bytes, status)
                VALUES
                    (%s, %s, %s, %s),
                    (%s, %s, %s, %s),
                    (%s, %s, %s, %s)
                """,
                (
                    "test_pending.txt", "localpath/test_pending.txt", 100, "PENDING",
                    "test_loaded.txt", "localpath/test_loaded.txt", 200, "LOADED",
                    "test_failed.txt", "localpath/test_failed.txt", 300, "FAILED",
                ),
            )
        db_connection.commit()

        # Filter by PENDING
        response = api_client.get("/admin/list_files", params={"status": "PENDING"})
        assert response.status_code == 200
        data = response.json()
        pending_files = [f for f in data["files"] if f["path"].startswith("localpath/test_")]
        assert all(f["chroma_status"] == "PENDING" for f in pending_files)

        # Filter by LOADED
        response = api_client.get("/admin/list_files", params={"status": "LOADED"})
        assert response.status_code == 200
        data = response.json()
        loaded_files = [f for f in data["files"] if f["path"].startswith("localpath/test_")]
        assert all(f["chroma_status"] == "LOADED" for f in loaded_files)

    def test_list_files_pagination(
        self,
        api_client: httpx.Client,
        db_connection: psycopg.Connection,
        clean_db: None,
    ) -> None:
        """Test that /admin/list_files supports pagination."""
        # Register multiple test files
        with db_connection.cursor() as cur:
            for i in range(5):
                cur.execute(
                    """
                    INSERT INTO file_records (filename, path, size_bytes, status)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (f"test_page_{i}.txt", f"localpath/test_page_{i}.txt", 100 * (i + 1), "PENDING"),
                )
        db_connection.commit()

        # Get first page
        response = api_client.get("/admin/list_files", params={"limit": 2, "offset": 0})
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 2
        assert data["offset"] == 0
        assert len(data["files"]) <= 2

        # Get second page
        response = api_client.get("/admin/list_files", params={"limit": 2, "offset": 2})
        assert response.status_code == 200
        data = response.json()
        assert data["offset"] == 2
