"""Create dead_queue table for failed ingestion tracking.

Revision ID: 002
Create Date: 2026-01-28 00:00:00.000000

This migration creates the dead_queue table to track files
that failed during the ingestion pipeline.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create dead_queue table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Idempotent: skip if already exists
    if "dead_queue" in existing_tables:
        print("Table dead_queue already exists, skipping")
        return

    op.create_table(
        "dead_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("filename", sa.String(512), nullable=False, index=True),
        sa.Column("path", sa.String(1024), nullable=False),
        sa.Column("error_message", sa.Text, nullable=False, server_default=""),
        sa.Column("dag_run_id", sa.String(255), nullable=False, index=True),
        sa.Column("failed_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Drop dead_queue table."""
    op.drop_table("dead_queue")
