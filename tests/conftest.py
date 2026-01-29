"""Shared test fixtures and configuration.

Tests run on local machine against Docker instances:
- API: localhost:8000
- Airflow: localhost:8080
- ChromaDB: localhost:8001
- PostgreSQL: localhost:5432

Environment variables for LLM:
- Local testing: Set GROQ_API_KEY for GROQ provider
- Production testing: Set GEMMA_API_KEY for Gemma provider
"""

from __future__ import annotations

import os
import time
from collections.abc import Generator
from pathlib import Path

import httpx
import psycopg
import pytest

# Test configuration - Docker service ports on localhost
API_URL = os.getenv("TEST_API_URL", "http://localhost:8000")
AIRFLOW_URL = os.getenv("TEST_AIRFLOW_URL", "http://localhost:8080")
CHROMA_URL = os.getenv("TEST_CHROMA_URL", "http://localhost:8001")
POSTGRES_DSN = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://app:app@localhost:5434/app",
)

# Test file directory (mounted into Docker at /data/files)
TEST_FILES_DIR = Path(os.getenv("TEST_FILES_PATH", "./test_files"))


# HTTP status code threshold for considering a service "up"
HTTP_SERVER_ERROR = 500


def wait_for_service(url: str, timeout: int = 30, interval: float = 1.0) -> bool:
    """Wait for a service to become healthy."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = httpx.get(url, timeout=5)
            if response.status_code < HTTP_SERVER_ERROR:
                return True
        except httpx.RequestError:
            pass
        time.sleep(interval)
    return False


@pytest.fixture(scope="session")
def docker_services_ready() -> None:
    """Ensure all Docker services are up before running tests."""
    services = [
        (f"{API_URL}/health", "API"),
        (f"{CHROMA_URL}/api/v2/heartbeat", "ChromaDB"),
    ]

    for url, name in services:
        if not wait_for_service(url, timeout=60):
            pytest.skip(f"{name} service not available at {url}")


@pytest.fixture(scope="session")
def api_client(docker_services_ready: None) -> Generator[httpx.Client, None, None]:
    """HTTP client for API requests."""
    with httpx.Client(base_url=API_URL, timeout=30) as client:
        yield client


@pytest.fixture(scope="session")
def async_api_client(
    docker_services_ready: None,
) -> Generator[httpx.AsyncClient, None, None]:
    """Async HTTP client for API requests."""
    with httpx.AsyncClient(base_url=API_URL, timeout=30) as client:
        yield client


@pytest.fixture(scope="session")
def airflow_client(docker_services_ready: None) -> Generator[httpx.Client, None, None]:
    """HTTP client for Airflow API requests."""
    with httpx.Client(
        base_url=AIRFLOW_URL,
        timeout=30,
        auth=("admin", "admin"),
    ) as client:
        yield client


@pytest.fixture
def db_connection(docker_services_ready: None) -> Generator[psycopg.Connection, None, None]:
    """PostgreSQL connection for direct DB access (fresh per test)."""
    with psycopg.connect(POSTGRES_DSN) as conn:
        yield conn


@pytest.fixture
def clean_db(docker_services_ready: None) -> Generator[None, None, None]:
    """Clean up test data before and after test."""
    # Use fresh connection for cleanup to avoid transaction issues
    with psycopg.connect(POSTGRES_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM file_records WHERE filename LIKE 'test_%'")
            cur.execute("DELETE FROM dead_queue WHERE filename LIKE 'test_%'")
        conn.commit()

    yield

    # Cleanup after test with fresh connection
    with psycopg.connect(POSTGRES_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM file_records WHERE filename LIKE 'test_%'")
            cur.execute("DELETE FROM dead_queue WHERE filename LIKE 'test_%'")
        conn.commit()


@pytest.fixture
def test_file_txt(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a test text file."""
    test_file = TEST_FILES_DIR / "test_sample.txt"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(
        "This is a test document for the NRECA pipeline.\n"
        "It contains sample content for testing ingestion.\n"
        "The document discusses rural electric cooperatives.\n"
    )
    yield test_file
    # Cleanup
    if test_file.exists():
        test_file.unlink()


@pytest.fixture
def test_file_pdf() -> Path | None:
    """Path to a test PDF file (must exist in test_files/)."""
    pdf_path = TEST_FILES_DIR / "test_document.pdf"
    if not pdf_path.exists():
        pytest.skip("test_document.pdf not found in test_files/")
    return pdf_path


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "e2e: end-to-end tests against Docker services")
    config.addinivalue_line("markers", "slow: tests that take longer to run")
    config.addinivalue_line("markers", "llm: tests that require LLM API access")
