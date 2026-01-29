"""Dead queue management utilities."""

from __future__ import annotations


def write_to_dead_queue(
    filename: str,
    path: str,
    error_message: str,
    dag_run_id: str,
) -> dict:
    """Write a failed file entry to the dead queue.

    Called when file ingestion fails at any stage.

    Args:
        filename: Name of the failed file
        path: Canonical path of the file
        error_message: Error message describing the failure
        dag_run_id: Airflow DAG run ID for tracking

    Returns:
        Dict with dead queue entry details
    """
    from db import DeadQueueItem, get_session

    with get_session() as session:
        item = DeadQueueItem(
            filename=filename,
            path=path,
            error_message=error_message,
            dag_run_id=dag_run_id,
        )
        session.add(item)
        session.flush()

        return {
            "id": str(item.id),
            "filename": item.filename,
            "path": item.path,
            "error_message": item.error_message,
            "dag_run_id": item.dag_run_id,
            "failed_at": item.failed_at.isoformat(),
        }


def get_dead_queue_entries(limit: int = 100, offset: int = 0) -> tuple[list[dict], int]:
    """Get dead queue entries with pagination.

    Args:
        limit: Maximum entries to return
        offset: Number of entries to skip

    Returns:
        Tuple of (list of entry dicts, total count)
    """
    from db import DeadQueueItem, get_session
    from sqlalchemy import func, select

    with get_session() as session:
        # Get total count
        count_stmt = select(func.count()).select_from(DeadQueueItem)
        total = session.execute(count_stmt).scalar() or 0

        # Get entries
        stmt = (
            select(DeadQueueItem)
            .order_by(DeadQueueItem.failed_at.desc())
            .offset(offset)
            .limit(limit)
        )
        results = session.execute(stmt).scalars().all()

        entries = [
            {
                "id": str(item.id),
                "filename": item.filename,
                "path": item.path,
                "error": item.error_message,
                "dag_run_id": item.dag_run_id,
                "failed_at": item.failed_at.isoformat(),
                "retry_count": item.retry_count,
            }
            for item in results
        ]

        return entries, total
