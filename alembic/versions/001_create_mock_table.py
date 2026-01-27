"""Create mock_items table.

Revision ID: 001
Create Date: 2025-01-01 00:00:00.000000

This migration creates an example table to demonstrate:
- UUID primary keys
- Timestamp columns
- Idempotent migration patterns
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create mock_items table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Idempotent: skip if already exists
    if "mock_items" in existing_tables:
        print("Table mock_items already exists, skipping")
        return

    op.create_table(
        "mock_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, index=True),
        sa.Column("value", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    """Drop mock_items table."""
    op.drop_table("mock_items")
