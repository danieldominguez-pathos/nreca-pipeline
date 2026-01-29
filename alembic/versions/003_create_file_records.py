"""Create file_records table for file registry.

Revision ID: 003
Create Date: 2026-01-28 00:00:00.000000

This migration creates the file_records table to track all files
and their ingestion status (PENDING, PROCESSING, LOADED, FAILED).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create file_records table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Idempotent: skip if already exists
    if "file_records" in existing_tables:
        print("Table file_records already exists, skipping")
        return

    op.create_table(
        "file_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("filename", sa.String(512), nullable=False, unique=True, index=True),
        sa.Column("path", sa.String(1024), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING", index=True),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Drop file_records table."""
    op.drop_table("file_records")
