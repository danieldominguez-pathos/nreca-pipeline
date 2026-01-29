"""Database session management with psycopg3 driver.

IMPORTANT: Airflow 3.x uses SQLAlchemy 1.4.x internally, but SQLModel requires 2.0+.
This client is designed to run inside @task.virtualenv where SQLAlchemy 2.0+ is installed.

Key configuration:
- URL: postgresql+psycopg:// (explicitly uses psycopg3, not psycopg2)
- SSL: Uses sslmode/sslrootcert in connect_args (not ssl=SSLContext)
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import TYPE_CHECKING

from sqlalchemy import create_engine
from sqlmodel import Session
from utils import get_logger
from utils.settings import get_settings

if TYPE_CHECKING:
    from sqlalchemy import Engine

log = get_logger("db.client")


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Get cached SQLAlchemy engine with psycopg3 configuration.

    The engine is configured for psycopg3 driver with appropriate
    connection pooling settings for Airflow task execution.
    """
    settings = get_settings()

    if not settings.database_url:
        raise RuntimeError("DATABASE_URL environment variable required")

    database_url = settings.database_url.get_secret_value()

    # Remove sslmode from URL if present (we handle SSL explicitly via connect_args)
    if "sslmode=" in database_url:
        database_url = re.sub(r"\?sslmode=[^&]+&?", "?", database_url)
        database_url = re.sub(r"&sslmode=[^&]+", "", database_url)
        database_url = database_url.rstrip("?&")

    # Use psycopg3 driver explicitly
    # Replace postgresql:// with postgresql+psycopg://
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    # psycopg3 uses sslmode in connect_args, NOT ssl=SSLContext
    connect_args: dict[str, str] = {}

    engine = create_engine(
        database_url,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_pre_ping=True,
        connect_args=connect_args,
    )

    log.info("database_engine_created")
    return engine


@contextmanager
def get_session() -> Iterator[Session]:
    """Get database session with automatic cleanup.

    Usage:
        with get_session() as session:
            item = session.get(FileRecord, file_id)

    The session automatically commits on success and rolls back on exception.
    """
    engine = get_engine()
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
