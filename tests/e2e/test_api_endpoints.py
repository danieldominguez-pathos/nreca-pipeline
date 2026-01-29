"""E2E tests for API endpoints.

Tests all FastAPI endpoints against running Docker instances.
"""

from __future__ import annotations

import os

import httpx
import psycopg
import pytest


@pytest.mark.e2e
class TestHealthEndpoint:
    """Test the health check endpoint."""

    def test_health_check(self, api_client: httpx.Client) -> None:
        """Test GET /health returns healthy status."""
        response = api_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        assert "env" in data


@pytest.mark.e2e
class TestIngestEndpoints:
    """Test the ingestion endpoints."""

    def test_load_file_requires_filenames(self, api_client: httpx.Client) -> None:
        """Test that POST /ingest/load_file requires filenames."""
        response = api_client.post("/ingest/load_file", json={})
        # Should fail validation (422) or return error
        assert response.status_code in (400, 422)

    def test_load_file_accepts_list(
        self,
        api_client: httpx.Client,
        db_connection: psycopg.Connection,
        clean_db: None,
    ) -> None:
        """Test that POST /ingest/load_file accepts a list of filenames."""
        # Register test files first
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO file_records (filename, path, size_bytes, status)
                VALUES
                    (%s, %s, %s, %s),
                    (%s, %s, %s, %s)
                """,
                (
                    "test_file1.txt", "localpath/test_file1.txt", 100, "PENDING",
                    "test_file2.txt", "localpath/test_file2.txt", 200, "PENDING",
                ),
            )
        db_connection.commit()

        response = api_client.post(
            "/ingest/load_file",
            json={"filenames": ["test_file1.txt", "test_file2.txt"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["file_count"] == 2
        assert "test_file1.txt" in data["filenames"]
        assert "test_file2.txt" in data["filenames"]


@pytest.mark.e2e
class TestQueryEndpoint:
    """Test the RAG query endpoint."""

    def test_query_requires_question(self, api_client: httpx.Client) -> None:
        """Test that POST /query requires a question."""
        response = api_client.post("/query", json={})
        assert response.status_code in (400, 422)

    def test_query_returns_answer(self, api_client: httpx.Client) -> None:
        """Test that POST /query returns an answer."""
        response = api_client.post(
            "/query",
            json={"query": "What is NRECA?"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "sources" in data

    @pytest.mark.llm
    def test_query_with_context(
        self,
        api_client: httpx.Client,
        db_connection: psycopg.Connection,
        clean_db: None,
    ) -> None:
        """Test that POST /query uses document context when available.

        Requires LLM to be configured (GROQ_API_KEY or OPENAI_API_KEY).
        """
        # Skip if no LLM configured
        if not os.getenv("GROQ_API_KEY") and not os.getenv("OPENAI_API_KEY"):
            pytest.skip("LLM not configured (set GROQ_API_KEY or OPENAI_API_KEY)")

        response = api_client.post(
            "/query",
            json={
                "question": "What documents are available?",
                "top_k": 5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        # Answer should not be the fallback message
        assert "LLM not configured" not in data["answer"]


@pytest.mark.e2e
class TestAdminEndpoints:
    """Test the admin endpoints."""

    def test_dead_queue_returns_list(self, api_client: httpx.Client) -> None:
        """Test that GET /admin/dead_queue returns a list."""
        response = api_client.get("/admin/dead_queue")
        assert response.status_code == 200
        data = response.json()
        assert "failed_files" in data
        assert "count" in data
        assert isinstance(data["failed_files"], list)

    def test_dead_queue_pagination(self, api_client: httpx.Client) -> None:
        """Test that GET /admin/dead_queue supports pagination."""
        response = api_client.get(
            "/admin/dead_queue",
            params={"limit": 10, "offset": 0},
        )
        assert response.status_code == 200
        data = response.json()
        assert "failed_files" in data

    def test_chroma_list_returns_documents(self, api_client: httpx.Client) -> None:
        """Test that GET /admin/chroma_list returns documents."""
        response = api_client.get("/admin/chroma_list")
        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

    def test_chroma_list_pagination(self, api_client: httpx.Client) -> None:
        """Test that GET /admin/chroma_list supports pagination."""
        response = api_client.get(
            "/admin/chroma_list",
            params={"limit": 5, "offset": 0},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 5
        assert data["offset"] == 0

    def test_list_files_returns_files(self, api_client: httpx.Client) -> None:
        """Test that GET /admin/list_files returns files."""
        response = api_client.get("/admin/list_files")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

    def test_list_files_status_validation(self, api_client: httpx.Client) -> None:
        """Test that GET /admin/list_files validates status parameter."""
        # Valid statuses should work
        for status in ["PENDING", "PROCESSING", "LOADED", "FAILED"]:
            response = api_client.get(
                "/admin/list_files",
                params={"status": status},
            )
            assert response.status_code == 200

        # Invalid status should fail
        response = api_client.get(
            "/admin/list_files",
            params={"status": "INVALID"},
        )
        assert response.status_code == 422


@pytest.mark.e2e
class TestChromaDBIntegration:
    """Test ChromaDB integration."""

    def test_chroma_heartbeat(self, docker_services_ready: None) -> None:
        """Test that ChromaDB is accessible."""
        from tests.conftest import CHROMA_URL

        response = httpx.get(f"{CHROMA_URL}/api/v2/heartbeat")
        assert response.status_code == 200

    def test_chroma_list_via_api(self, api_client: httpx.Client) -> None:
        """Test listing ChromaDB contents via API."""
        response = api_client.get("/admin/chroma_list")
        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert isinstance(data["documents"], list)
        assert isinstance(data["total"], int)

        # If there are documents, verify structure
        if data["documents"]:
            doc = data["documents"][0]
            assert "id" in doc
            assert "path" in doc
            assert "filename" in doc
            assert "chunk_index" in doc
            assert "total_chunks" in doc


@pytest.mark.e2e
class TestDatabaseIntegration:
    """Test PostgreSQL integration."""

    def test_database_connection(self, db_connection: psycopg.Connection) -> None:
        """Test that database is accessible."""
        with db_connection.cursor() as cur:
            cur.execute("SELECT 1")
            result = cur.fetchone()
            assert result == (1,)

    def test_file_records_table_exists(self, db_connection: psycopg.Connection) -> None:
        """Test that file_records table exists."""
        with db_connection.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'file_records'
                )
                """
            )
            result = cur.fetchone()
            assert result is not None
            assert result[0] is True

    def test_dead_queue_table_exists(self, db_connection: psycopg.Connection) -> None:
        """Test that dead_queue table exists."""
        with db_connection.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'dead_queue'
                )
                """
            )
            result = cur.fetchone()
            assert result is not None
            assert result[0] is True
