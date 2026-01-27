"""Example DAG demonstrating @task.virtualenv patterns for Airflow 3.x.

This DAG shows the correct patterns for working with SQLAlchemy 2.0+ in Airflow,
which uses SQLAlchemy 1.4.x internally.

CRITICAL PATTERNS:
1. Tasks using @task.virtualenv MUST be defined INSIDE the @dag function
2. All imports MUST be inside the task function body
3. Use sys.path.insert(0, "/opt/airflow") to access custom packages
4. Use venv_cache_path for performance

Flow:
1. extract -> Generate mock items (returns list for parallel processing)
2. process_item.expand() -> Process items CONCURRENTLY (one task per item)
3. aggregate_results -> Collect all results into a single list
4. write_to_db -> Store aggregated results in database
5. read_from_db -> Verify data was written correctly
6. summarize -> Log statistics
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from airflow.sdk import dag, task


@dag(
    dag_id="example_dag",
    description="Example DAG demonstrating @task.virtualenv patterns",
    schedule="@hourly",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "airflow",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["example", "template"],
)
def example_dag() -> None:
    """Example pipeline using virtualenv for SQLAlchemy 2.0+ isolation.

    IMPORTANT: All @task.virtualenv decorated functions MUST be defined
    inside this @dag function, NOT at module level.
    """

    @task
    def extract() -> list[dict[str, Any]]:
        """Extract data - generates mock items for parallel processing.

        Returns a list that will be expanded for concurrent task execution.
        Each item becomes input to a separate process_item task.
        """
        import sys

        sys.path.insert(0, "/opt/airflow/dags")

        from example_dag.task_extract import generate_items

        items = generate_items(count=5)
        print(f"[EXTRACT] Generated {len(items)} items for parallel processing")

        for item in items:
            print(f"  - {item['name']}: value={item['value']}")

        return items

    @task.virtualenv(
        requirements=["sqlalchemy>=2.0.0", "psycopg[binary]>=3.0"],
        system_site_packages=True,
        venv_cache_path="/opt/airflow/venv_cache",
    )
    def process_item(item: dict[str, Any]) -> dict[str, Any]:
        """Process a single item - runs CONCURRENTLY with other items.

        This task is expanded with .expand(), meaning Airflow creates
        one task instance per item and runs them in parallel.

        IMPORTANT:
        - This function runs in a subprocess with SQLAlchemy 2.0+
        - All imports MUST be inside the function body
        - sys.path.insert is needed to access custom packages

        Args:
            item: Single item to process.

        Returns:
            Processed item with additional fields.
        """
        import sys

        sys.path.insert(0, "/opt/airflow")
        sys.path.insert(0, "/opt/airflow/dags")

        from utils import get_logger

        from example_dag.task_transform import transform_item

        log = get_logger("example_dag.process_item")
        log.info("processing_item", name=item["name"], value=item["value"])

        result = transform_item(item)

        log.info(
            "item_processed",
            name=item["name"],
            original_value=item["value"],
            doubled_value=result["value_doubled"],
        )

        return result

    @task
    def aggregate_results(processed_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Aggregate results from all concurrent process_item tasks.

        When tasks are expanded with .expand(), the downstream task receives
        all results as a LazyXComSequence. We convert it to a plain list
        for serialization and further processing.

        Args:
            processed_items: Results from expanded tasks (may be LazyXComSequence).

        Returns:
            Plain list of all processed items.
        """
        # CRITICAL: Convert LazyXComSequence to plain list for serialization
        items = list(processed_items)

        print(f"[AGGREGATE] Received {len(items)} items from concurrent tasks")

        total_value = sum(item.get("value_doubled", 0) for item in items)
        print(f"[AGGREGATE] Total doubled value: {total_value}")

        return items

    @task.virtualenv(
        requirements=["sqlalchemy>=2.0.0", "psycopg[binary]>=3.0"],
        system_site_packages=True,
        venv_cache_path="/opt/airflow/venv_cache",
    )
    def write_to_db(items: list[dict[str, Any]]) -> dict[str, Any]:
        """Write aggregated items to database.

        Demonstrates SQLModel/SQLAlchemy 2.0+ usage inside virtualenv.
        Creates MockItem records in the database.

        Args:
            items: List of processed items to store.

        Returns:
            Write statistics including IDs of created records.
        """
        import sys

        sys.path.insert(0, "/opt/airflow")

        from datetime import datetime

        from db import MockItem, get_session
        from utils import get_logger

        log = get_logger("example_dag.write_to_db")
        log.info("writing_to_db", count=len(items))

        created_ids: list[str] = []

        with get_session() as session:
            for item in items:
                mock_item = MockItem(
                    name=item["name_upper"],
                    value=item["value_doubled"],
                    updated_at=datetime.utcnow(),
                )
                session.add(mock_item)
                session.flush()  # Ensure ID is generated
                created_ids.append(str(mock_item.id))

                log.info(
                    "record_created",
                    id=str(mock_item.id),
                    name=mock_item.name,
                    value=mock_item.value,
                )

        log.info("write_complete", records_created=len(created_ids))

        return {
            "records_created": len(created_ids),
            "created_ids": created_ids,
            "timestamp": datetime.utcnow().isoformat(),
        }

    @task.virtualenv(
        requirements=["sqlalchemy>=2.0.0", "psycopg[binary]>=3.0"],
        system_site_packages=True,
        venv_cache_path="/opt/airflow/venv_cache",
    )
    def read_from_db(write_result: dict[str, Any]) -> dict[str, Any]:
        """Read back the records we just wrote to verify DB operations.

        Demonstrates reading from database and SQLModel query patterns.

        Args:
            write_result: Results from write_to_db including created IDs.

        Returns:
            Verification results with read records.
        """
        import sys

        sys.path.insert(0, "/opt/airflow")

        from uuid import UUID

        from db import MockItem, get_session
        from sqlalchemy import select
        from utils import get_logger

        log = get_logger("example_dag.read_from_db")

        created_ids = write_result.get("created_ids", [])
        log.info("reading_from_db", expected_count=len(created_ids))

        with get_session() as session:
            # Query all records we just created
            stmt = select(MockItem).where(
                MockItem.id.in_([UUID(id_str) for id_str in created_ids])
            )
            results = session.execute(stmt).scalars().all()

            records_found = [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "value": r.value,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in results
            ]

        log.info(
            "read_complete",
            expected=len(created_ids),
            found=len(records_found),
            verified=len(created_ids) == len(records_found),
        )

        return {
            "expected_count": len(created_ids),
            "found_count": len(records_found),
            "verified": len(created_ids) == len(records_found),
            "records": records_found,
        }

    @task
    def summarize(
        extract_count: int,
        write_result: dict[str, Any],
        read_result: dict[str, Any],
    ) -> None:
        """Log summary statistics for the entire pipeline.

        Args:
            extract_count: Number of items extracted.
            write_result: Results from write_to_db.
            read_result: Results from read_from_db verification.
        """
        print("=" * 60)
        print("EXAMPLE DAG SUMMARY")
        print("=" * 60)
        print(f"Items extracted:     {extract_count}")
        print(f"Records written:     {write_result['records_created']}")
        print(f"Records verified:    {read_result['found_count']}")
        print(f"Verification passed: {read_result['verified']}")
        print("-" * 60)
        print("Records in database:")
        for record in read_result.get("records", []):
            print(f"  - {record['name']}: value={record['value']}")
        print("=" * 60)

        if not read_result["verified"]:
            raise ValueError(
                f"Verification failed! Expected {read_result['expected_count']}, "
                f"found {read_result['found_count']}"
            )

    # =========================================================================
    # DAG FLOW - Demonstrates concurrent execution and aggregation
    # =========================================================================

    # Step 1: Extract items (returns list)
    raw_items = extract()

    # Step 2: CONCURRENT PROCESSING - .expand() creates N parallel tasks
    # Each item is processed by a separate task instance running in parallel
    processed = process_item.expand(item=raw_items)

    # Step 3: Aggregate all results from parallel tasks into single list
    aggregated = aggregate_results(processed)

    # Step 4: Write aggregated results to database
    write_result = write_to_db(aggregated)

    # Step 5: Read back from database to verify write succeeded
    read_result = read_from_db(write_result)

    # Step 6: Summarize results
    # Note: We pass len(raw_items) via a helper to avoid serialization issues
    @task
    def get_count(items: list) -> int:
        return len(items)

    item_count = get_count(raw_items)
    summarize(item_count, write_result, read_result)


# Instantiate the DAG
example_dag()
