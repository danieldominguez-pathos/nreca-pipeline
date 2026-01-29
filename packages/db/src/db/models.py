"""SQLModel database models.

All models use SQLModel which provides both SQLAlchemy ORM and Pydantic validation.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class MockItem(SQLModel, table=True):
    """Example table demonstrating SQLModel usage.

    This table is used by the example DAG to demonstrate:
    - UUID primary keys
    - Timestamp tracking
    - Basic CRUD operations via SQLModel
    """

    __tablename__ = "mock_items"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(max_length=255, index=True)
    value: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(default=None)


class DeadQueueItem(SQLModel, table=True):
    """Records files that failed during ingestion.

    When a file fails to process in the ingestion DAG, an entry is
    created here with error details. The dead_queue endpoint reads
    from this table to show failed files.
    """

    __tablename__ = "dead_queue"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    filename: str = Field(max_length=512, index=True)
    path: str = Field(max_length=1024)
    error_message: str = Field(default="")
    dag_run_id: str = Field(max_length=255, index=True)
    failed_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    retry_count: int = Field(default=0)


class FileRecord(SQLModel, table=True):
    """Central registry of files and their ingestion status.

    Tracks all files that have been processed or attempted to be processed.
    Updated by the ingestion DAG and queried by the list_files endpoint.
    """

    __tablename__ = "file_records"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    filename: str = Field(max_length=512, index=True, unique=True)
    path: str = Field(max_length=1024)
    size_bytes: int = Field(default=0)
    status: str = Field(
        default="PENDING",
        max_length=20,
        index=True,
        description="PENDING, PROCESSING, LOADED, FAILED",
    )
    chunk_count: int = Field(default=0, description="Number of chunks in ChromaDB")
    error_message: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
