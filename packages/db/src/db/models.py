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
